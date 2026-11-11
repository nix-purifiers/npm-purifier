#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native selected-SDK proof; takes tools, release and optional outgoing repository paths."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile

from registry_fixture import registry

tools = Path(sys.argv[1]).resolve()
expected_archive = Path(sys.argv[2]).resolve()
version = sys.argv[3] if len(sys.argv) > 3 else '12.22.12'
prepared = Path(sys.argv[4]) if len(sys.argv) > 4 else None
catalog = Path(sys.argv[5]) if len(sys.argv) > 5 else None
fixture = sys.argv[6] if len(sys.argv) > 6 else 'legacy-node'
point = sys.argv[7]
source = Path(__file__).resolve().parent.parent
source_ref = 'git+' + source.as_uri() + '?rev=' + subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
lock_name = 'npm-shrinkwrap.json' if fixture.startswith('shrinkwrap-') else 'package-lock.json'
env = dict(os.environ, PATH=str(tools / 'bin') + os.pathsep + os.environ['PATH'])


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()


with tempfile.TemporaryDirectory(prefix='npm-legacy-native-') as temporary:
    root = Path(temporary) / 'project'
    shutil.copytree(Path(__file__).parent / 'fixtures' / fixture, root)
    env['HOME'] = str(Path(temporary) / 'home')
    Path(env['HOME']).mkdir()
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert run('node', '--version', cwd=root) == 'v' + version
    npm_version = run('npm', '--version', cwd=root)
    run('npm-purifier', 'lock', cwd=root)
    assert (root / 'package.json').read_bytes() == before['package.json']
    before[lock_name] = (root / lock_name).read_bytes()
    run('npm-purifier', 'prefetch', cwd=root)
    # Compare publication against a pure build of the same post-lock source,
    # including the new implementation pin, with this exact test SDK.
    pure_environment = dict(os.environ, NPM_NATIVE_SOURCE=source_ref,
                            NPM_NATIVE_PROJECT=str(root), NPM_NATIVE_POINT=point)
    expression = '''let f = builtins.getFlake (builtins.getEnv "NPM_NATIVE_SOURCE");
      p = f.checks.${builtins.currentSystem}.${builtins.getEnv "NPM_NATIVE_POINT"}.withSource
        (/. + builtins.getEnv "NPM_NATIVE_PROJECT"); in p.release'''
    release = Path(subprocess.check_output(['nix','build','--impure','--no-link','--print-out-paths','--expr',expression],
                                          env=pure_environment,text=True).strip())
    baseline_archive = expected_archive
    expected_archive = release / 'legacy-npm-app.tgz'
    def payload(archive):
        with tarfile.open(archive, 'r:gz') as packed:
            return sorted((entry.name, entry.mode, entry.type, entry.linkname,
                           packed.extractfile(entry).read() if entry.isfile() else None)
                          for entry in packed.getmembers()
                          if entry.name != 'package/npm-purifier.lock.json')
    assert payload(expected_archive) == payload(baseline_archive), 'implementation pin changed unrelated release payload'

    env['npm_config_registry'] = 'http://127.0.0.1:9'
    if int(npm_version.split('.')[0]) < 6:
        run('npm', 'install', '--cache-min=999999999', cwd=root)
    else:
        run('npm', 'ci', cwd=root)
    run('npm', 'run', 'build', cwd=root)
    run('npm', 'test', cwd=root)
    assert run('node', 'cli.js', cwd=root) == '42 on v' + version
    assert (root / 'built.txt').read_text() == 'v' + version
    for name, contents in before.items():
        assert (root / name).read_bytes() == contents, f'native workflow changed {name}'
    with registry(root, version, prepared, catalog) as (url, uploads):
        env['npm_config_registry'] = url
        run('npm-purifier', 'publish', '--registry', url, cwd=root)
        assert uploads and 'npm/' + npm_version in uploads[0][1] and 'node/v' + version in uploads[0][1], uploads
        if prepared:
            import json
            modules = json.loads(catalog.read_text())['modules']
            app = next(entry for entry in modules if entry['name'] == 'legacy-npm-app')
            ordinary = Path(temporary) / 'ordinary'
            ordinary.mkdir()
            (ordinary / 'package.json').write_text(json.dumps({
                'name': 'ordinary-consumer', 'private': True,
                'dependencies': {'legacy-npm-app': app['version']}}))
            ordinary_env = dict(env, NPM_PURIFIER='0', npm_config_cache=str(Path(temporary) / 'ordinary-cache'),
                                npm_config_audit='false', npm_config_fund='false')
            subprocess.run(['npm', 'install', '--registry', url], cwd=ordinary,
                           env=ordinary_env, check=True, stdout=subprocess.PIPE, text=True)
            result = subprocess.check_output(['node', 'node_modules/legacy-npm-app/cli.js'],
                                             cwd=ordinary, env=ordinary_env, text=True).strip()
            assert result == '42 on v' + version, result
            assert not (ordinary / '.npm-purifier').exists()
            print('PASS ordinary registry resolution/install/execution of prepared graph', flush=True)
    assert uploads[0][0] == expected_archive.read_bytes(), 'native upload differs from the pure release'
    for name, contents in before.items():
        assert (root / name).read_bytes() == contents, f'publication changed {name}'
    if fixture.startswith('shrinkwrap-'):
        import json
        failed = Path(temporary) / 'failed-script'
        failed.mkdir()
        manifest = json.loads((root / 'package.json').read_text())
        manifest.setdefault('scripts', {})['preinstall'] = 'node -e "process.stderr.write(\"native-sdk-failure\");process.exit(23)"'
        (failed / 'package.json').write_text(json.dumps(manifest))
        (failed / lock_name).write_bytes(before[lock_name])
        (failed / 'cli.js').write_bytes(before['cli.js'])
        run('npm-purifier', 'prefetch', cwd=failed)
        saved_lock = (failed / lock_name).read_bytes()
        saved_mtime = (failed / lock_name).stat().st_mtime_ns
        result = subprocess.run(['npm', 'install'], cwd=failed, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert result.returncode != 0 and 'native-sdk-failure' in result.stdout, result.stdout
        assert (failed / lock_name).read_bytes() == saved_lock
        assert (failed / lock_name).stat().st_mtime_ns == saved_mtime
        print('PASS failed native lifecycle restores original shrinkwrap bytes and mtime', flush=True)
    print('PASS npm' + npm_version + '/Node' + version + ' lock, prefetch, offline install, build/test and actual publication; native lock preserved after resolution')
