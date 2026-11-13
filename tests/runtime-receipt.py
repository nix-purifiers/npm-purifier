#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build named runtime checks and bind their derivations, outputs and SDKs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory', type=Path)
directory = parser.parse_args().directory.resolve()
directory.mkdir(parents=True, exist_ok=True)
root = Path(__file__).resolve().parent.parent


def output(*args, **kwargs):
    return subprocess.check_output(args, cwd=root, text=True, **kwargs).strip()


system = output('nix', 'eval', '--impure', '--raw', '--expr', 'builtins.currentSystem')
receipt = {
    'sourceRevision': output('git', 'rev-parse', 'HEAD'),
    'sourceTree': output('git', 'rev-parse', 'HEAD^{tree}'),
    'trackedSourceClean': subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=root).returncode == 0,
    'system': system,
    'nixVersion': output('nix', '--version'),
    'sandbox': output('nix', 'config', 'show', 'sandbox'),
    'runnerOS': os.environ.get('RUNNER_OS'),
    'runnerArchitecture': os.environ.get('RUNNER_ARCH'),
    'flakeLock': json.loads((root / 'flake.lock').read_text()),
    'checks': [],
}
names = ['real-commander', 'real-commander-native-offline', 'real-http-server', 'webjar', 'npm-projection', 'current-node']
names += ['supported-node-22', 'supported-node-24', 'supported-node-26', 'latest-npm']
if system.endswith('-linux'):
    names += ['node-lts-22', 'node-lts-26']
try:
    assert receipt['trackedSourceClean'], 'runtime derivation evidence requires committed source'
    assert receipt['sandbox'] == 'true', 'runtime derivation evidence requires the Nix sandbox'
    for name in names:
        attribute = '.#checks.' + system + '.' + name
        result = json.loads(output('nix', 'build', '--no-link', '-L', '--json', attribute))[0]
        result['attribute'] = attribute
        result['command'] = ['nix', 'build', '--no-link', '-L', '--json', attribute]
        # Preserve actual deriver and NAR metadata independently of build JSON.
        result['pathInfo'] = json.loads(output('nix', 'path-info', '--json',
                                               *result['outputs'].values()))
        result['outputHashes'] = {key: output('nix', 'hash', 'path', path)
                                  for key, path in result['outputs'].items()}
        result['derivation'] = json.loads(output('nix', 'derivation', 'show', result['drvPath']))
        tools_attribute = ('.#toolchain' if name.startswith('real-') or name in ('webjar', 'npm-projection')
                           else '.#checks.' + system + '.' + name + '-tools')
        tools = Path(output('nix', 'build', '--no-link', '--print-out-paths', tools_attribute))
        native_sdk = tools / 'native-runtime'
        prefixes = [str(tools / 'bin')] + ([str(native_sdk / 'bin')] if native_sdk.exists() else [])
        native_env = dict(os.environ, NPM_PURIFIER='0', PATH=os.pathsep.join(prefixes + [os.environ['PATH']]))
        node = shutil.which('node', path=native_env['PATH'])
        assert node, 'native evidence requires an existing caller Node'
        if tools_attribute == '.#toolchain':
            assert not (tools / 'bin/node').exists(), 'default commands must preserve the caller runtime'
        result['sdk'] = {
            'role': 'caller runtime for the native probe; pure builder inputs are recorded separately in derivation',
            'selection': 'explicit test SDK' if native_sdk.exists() else 'existing caller PATH',
            'toolchainAttribute': tools_attribute,
            'toolchainPath': str(tools),
            'nodeExecutable': str(Path(node).resolve()),
            'nodeProcessExecPath': output(node, '-p', 'process.execPath', env=native_env),
            'npmWrapper': str((tools / 'bin/npm').resolve()),
            'nodeVersion': output(node, '--version', env=native_env),
            'npmVersion': output(str(tools / 'bin/npm'), '--version', env=native_env),
        }
        receipt['checks'].append(result)
finally:
    # A failed check must fail the job; retain any completed bindings for diagnosis.
    (directory / 'runtime.json').write_text(json.dumps(receipt, indent=2) + '\n')
