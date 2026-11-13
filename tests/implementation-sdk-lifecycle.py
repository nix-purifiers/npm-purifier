#!/usr/bin/env python3
"""Actual configured SDK handoff through immutable source-owned packages."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', help='Immutable flake reference with configuration support')
    parser.add_argument('--baseline-source', help='JSON source descriptor with expected revision and NAR hash')
    parser.add_argument('--current', required=True)
    parser.add_argument('--bootstrap', required=True)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('bootstrap', args.bootstrap)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    commands = []
    environment = dict(os.environ)

    def run(argv, cwd=None, success=True):
        result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True, capture_output=True, timeout=1800, env=environment)
        commands.append({'argv': list(map(str, argv)), 'cwd': str(cwd) if cwd else None,
                         'status': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        print('$ ' + ' '.join(map(str, argv)), flush=True)
        print(result.stdout, end='', flush=True)
        print(result.stderr, end='', file=sys.stderr, flush=True)
        if success and result.returncode:
            Path(args.output + '.failed-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
            raise AssertionError('native SDK command failed: ' + str(result.returncode))
        return result

    baseline_source = None
    if args.baseline_source:
        baseline_source = json.loads(Path(args.baseline_source).read_text())['source']
        bootstrap.validate_source(baseline_source)
        args.baseline = bootstrap.source_ref(baseline_source)
    if not args.baseline:
        parser.error('a baseline reference or source descriptor is required')
    current_default = Path(run(['nix', 'build', args.current + '#npm', '--no-link', '--print-out-paths']).stdout.strip())
    config = json.loads((current_default / 'share/purifier/implementation.json').read_text())
    if baseline_source is None:
        old_default = Path(run(['nix', 'build', args.baseline + '#npm', '--no-link', '--print-out-paths']).stdout.strip())
    else:
        # Verify the fixed baseline's source bytes before evaluating its code.
        old_pin = {'version': 1, 'tool': 'npm-purifier', 'source': baseline_source}
        old_default = bootstrap.resolve_package(old_pin, config, 'npm', Path(args.output).parent / 'sdk-bootstrap.lock.json')
        bootstrap.verify_package(old_default, old_pin)
    defaults = [old_default, current_default]
    sdk_version = '24.22.2' if config['system'].endswith('-darwin') else '8.17.0'
    configuration = {'version': 1, 'node': {'type': 'upstream-node', 'version': sdk_version}}
    sources = []
    for ref, default in zip((args.baseline, args.current), defaults):
        locked = json.loads(run(['nix', 'flake', 'metadata', '--json', ref]).stdout)['locked']
        keys = ('type', 'owner', 'repo', 'rev', 'narHash') if locked['type'] == 'github' else ('type', 'url', 'rev', 'narHash')
        source = {key: locked[key] for key in keys}
        manifest = json.loads((default / 'share/purifier/implementation.json').read_text())
        assert bootstrap.same_source(source, manifest['source'])
        if not sources and baseline_source is not None:
            assert bootstrap.same_source(source, baseline_source)
        sources.append(source)
    with tempfile.TemporaryDirectory(prefix='npm-configured-implementation-') as tmp:
        root = Path(tmp)
        environment.update({'HOME': str(root / 'home'), 'XDG_CACHE_HOME': str(root / 'cache'),
                            'npm_config_cache': str(root / 'cache/npm')})
        (root / 'home').mkdir()
        project = root / 'project'
        shutil.copytree(args.fixture, project)
        for path in [project, *project.rglob('*')]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | (0o700 if path.is_dir() else 0o200))
        package = json.loads((project / 'package.json').read_text())
        package['scripts']['pin-origin'] = 'node -e \'var fs=require("fs"); var v=JSON.parse(fs.readFileSync(process.env.NPM_PURIFIER_IMPLEMENTATION_CONFIG,"utf8")); v.runtime={node:process.version,executable:fs.realpathSync(process.execPath)}; console.log(JSON.stringify(v))\''
        (project / 'package.json').write_text(json.dumps(package, indent=2) + '\n')
        lock = project / 'npm-purifier.lock.json'
        pins = [dict(version=1, tool='npm-purifier', source=source, configuration=configuration) for source in sources]
        selected_cli = bootstrap.resolve_package(pins[0], config, 'npm-purifier', lock)
        selected_native = bootstrap.resolve_package(pins[1], config, 'npm', lock)
        bootstrap.verify_package(selected_cli, pins[0])
        bootstrap.verify_package(selected_native, pins[1])
        run([selected_cli / 'bin/npm-purifier', 'lock'], project)
        captured = bootstrap.read_lock(lock.read_text(), 'npm')['implementation']
        assert captured['configuration'] == configuration
        assert bootstrap.same_source(captured['source'], sources[0])
        # A local Git transport is an explicit mirror of the same verified
        # source, never a replacement of its revision/content identity.
        if sources[0]['type'] == 'git':
            run([selected_cli / 'bin/npm-purifier', 'self-update', '--to', args.baseline], project)
        original_lock = lock.read_bytes()
        original_native = (project / 'package-lock.json').read_bytes()
        observed = []
        sdk_outputs = {}
        for name, native in [('A-default', defaults[0]), ('B-default', defaults[1]), ('B-configured', selected_native)]:
            run([native / 'bin/npm', 'ci'], project)
            run([native / 'bin/npm', 'run', 'build'], project)
            run([native / 'bin/npm', 'test'], project)
            origin = json.loads(run([native / 'bin/npm', 'run', '--silent', 'pin-origin'], project).stdout)
            assert bootstrap.same_source(origin['source'], sources[0]), origin
            assert origin['configuration'] == configuration and origin['runtime']['node'] == 'v' + sdk_version, origin
            executable = Path(origin['runtime']['executable'])
            sdk_root = Path('/nix/store') / executable.relative_to('/nix/store').parts[0]
            if str(sdk_root) not in sdk_outputs:
                actual_hash = run(['nix', 'hash', 'path', sdk_root]).stdout.strip()
                registered = json.loads(run(['nix', 'path-info', '--json', sdk_root]).stdout)
                assert registered[str(sdk_root)]['narHash'] == actual_hash
                sdk_outputs[str(sdk_root)] = {'physicalNarHash': actual_hash,
                    'registered': registered[str(sdk_root)],
                    'executableSha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
            if name == 'A-default':
                # The old immutable implementation establishes this fixture's
                # SDK. Supply it explicitly as the caller for subsequent local
                # commands; implementation selection must not replace PATH.
                assert (sdk_root / 'bin/npm').is_file()
                environment['PATH'] = str(sdk_root / 'bin') + os.pathsep + os.environ['PATH']
            observed.append({'caller': name, 'origin': origin,
                             'npm': run([native / 'bin/npm', '--version'], project).stdout.strip()})
        # Dependency updates cannot turn the configured implementation into a
        # default package, even when invoked through an installed default.
        current_cli = Path(run(['nix', 'build', args.current + '#npm-purifier', '--no-link', '--print-out-paths']).stdout.strip())
        run([current_cli / 'bin/npm-purifier', 'update'], project)
        assert bootstrap.read_lock(lock.read_text(), 'npm')['implementation'] == pins[0]
        original_lock = lock.read_bytes()
        original_native = (project / 'package-lock.json').read_bytes()

        def build_expression(source, wrong_sdk=False):
            expression = ('let f = builtins.getFlake ' + bootstrap.nix_string(bootstrap.source_ref(source))
                          + '; pkgs = import f.inputs.nixpkgs { system = ' + bootstrap.nix_string(config['system'])
                          + '; overlays = [ f.overlays.default ]; }; in (pkgs.npm-purifier.buildNpmProject { src = /. + '
                          + bootstrap.nix_string(str(project)) + '; doCheck = true; ' + ('node = pkgs.nodejs; ' if wrong_sdk else '') + '}).packages."legacy-npm-app"')
            return expression

        # The Nix package must create this itself; do not reuse a native build.
        (project / 'built.txt').unlink()
        matched = run(['nix', 'build', '--impure', '--no-link', '--print-out-paths', '--expr', build_expression(sources[0])]).stdout.strip()
        pure_built_node = (Path(matched) / 'lib/node_modules/legacy-npm-app/built.txt').read_text()
        assert pure_built_node == 'v' + sdk_version
        mismatch = run(['nix', 'eval', '--impure', '--raw', '--expr', '(' + build_expression(sources[0], True) + ').drvPath'], success=False)
        assert mismatch.returncode and 'builder implementation differs' in mismatch.stderr
        run([current_cli / 'bin/npm-purifier', 'self-update', '--to', args.current], project)
        assert bootstrap.read_lock(lock.read_text(), 'npm')['implementation'] == pins[1]
        updated = json.loads(run([defaults[1] / 'bin/npm', 'run', '--silent', 'pin-origin'], project).stdout)
        assert bootstrap.same_source(updated['source'], sources[1]) and updated['runtime']['node'] == 'v' + sdk_version
        run([current_cli / 'bin/npm-purifier', 'self-update', '--to', args.baseline], project)
        assert lock.read_bytes() == original_lock and (project / 'package-lock.json').read_bytes() == original_native
        # Arbitrary package overrides remain usable for an unpinned project,
        # but must not manufacture a portable default-SDK pin.
        custom_expression = ('let f = builtins.getFlake ' + bootstrap.nix_string(args.current)
            + '; base = import f.inputs.nixpkgs { system = ' + bootstrap.nix_string(config['system'])
            + '; }; sdk = import (f.outPath + "/pkgs/npm-purifier/node-sdk.nix") '
            + '{ pkgs = base; version = ' + bootstrap.nix_string(sdk_version) + '; }; '
            + 'node = sdk.overrideAttrs (old: { pname = old.pname + "-nonportable"; }); '
            + 'pkgs = import f.inputs.nixpkgs { system = ' + bootstrap.nix_string(config['system'])
            + '; overlays = [ (_: _: { nodejs = node; }) f.overlays.default ]; }; '
            + 'in pkgs.buildEnv { name = "npm-custom-sdk-legacy"; '
            + 'paths = [ pkgs.npm-purifier.npm-purifier pkgs.npm-purifier.npm ]; }')
        custom = Path(run(['nix', 'build', '--impure', '--no-link', '--print-out-paths', '--expr', custom_expression]).stdout.strip())
        assert json.loads((custom / 'share/purifier/implementation.json').read_text())['source'] is None
        legacy = root / 'legacy'
        shutil.copytree(args.fixture, legacy)
        for path in [legacy, *legacy.rglob('*')]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | (0o700 if path.is_dir() else 0o200))
        run([custom / 'bin/npm', 'ci'], legacy)
        run([custom / 'bin/npm', 'run', 'build'], legacy)
        run([custom / 'bin/npm', 'test'], legacy)
        assert (legacy / 'built.txt').read_text() == 'v' + sdk_version
        no_pin = run([custom / 'bin/npm-purifier', 'lock'], legacy, success=False)
        assert no_pin.returncode and 'portable source identity' in no_pin.stderr
        assert not (legacy / 'npm-purifier.lock.json').exists()
        matched_info = json.loads(run(['nix', 'path-info', '--json', matched]).stdout)
        matched_hash = run(['nix', 'hash', 'path', matched]).stdout.strip()
        assert matched_info[matched]['narHash'] == matched_hash
        receipt = {'sources': sources, 'configuration': configuration, 'observed': observed,
                   'matchedOutput': matched, 'pureBuiltNode': pure_built_node, 'matchedDerivation': run(['nix-store', '--query', '--deriver', matched]).stdout.strip(),
                   'matchedOutputInfo': matched_info, 'matchedPhysicalNarHash': matched_hash, 'sdkOutputs': sdk_outputs,
                   'dependencyUpdateRetainsConfiguration': True, 'explicitSourceUpdateRetainsConfiguration': True,
                   'wrongSdkBuilderRejected': True, 'restoredLockBytes': True,
                   'customSdkLegacyNativeBuildTest': True, 'customSdkCannotCreatePortablePin': True,
                   'customSdkOverlayIdentityUnpinned': True,
                   'customSdkPreservesCallerRuntime': True,
                   'bootstrapSha256': hashlib.sha256(Path(args.bootstrap).read_bytes()).hexdigest(), 'commands': commands}
        Path(args.output).write_text(json.dumps(receipt, indent=2) + '\n')
        print('Configured SDK lifecycle passed:', sdk_version)


if __name__ == '__main__':
    main()
