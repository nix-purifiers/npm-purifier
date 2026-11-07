#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build named runtime checks and bind their derivations, outputs and SDKs."""
import argparse
import json
import os
from pathlib import Path
import subprocess


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
    'system': system,
    'runnerOS': os.environ.get('RUNNER_OS'),
    'runnerArchitecture': os.environ.get('RUNNER_ARCH'),
    'flakeLock': json.loads((root / 'flake.lock').read_text()),
    'checks': [],
}
names = ['real-commander', 'real-commander-native-offline', 'current-node']
if system.endswith('-linux'):
    names += ['node-lts-22', 'node-lts-26']
try:
    for name in names:
        attribute = '.#checks.' + system + '.' + name
        result = json.loads(output('nix', 'build', '--no-link', '--json', attribute))[0]
        result['attribute'] = attribute
        # Preserve actual deriver and NAR metadata independently of build JSON.
        result['pathInfo'] = json.loads(output('nix', 'path-info', '--json',
                                               *result['outputs'].values()))
        result['outputHashes'] = {key: output('nix', 'hash', 'path', path)
                                  for key, path in result['outputs'].items()}
        result['derivation'] = json.loads(output('nix', 'derivation', 'show', result['drvPath']))
        tools_attribute = ('.#toolchain' if name.startswith('real-')
                           else '.#checks.' + system + '.' + name + '-tools')
        tools = Path(output('nix', 'build', '--no-link', '--print-out-paths', tools_attribute))
        native_env = dict(os.environ, NPM_PURIFIER='0')
        result['sdk'] = {
            'toolchainAttribute': tools_attribute,
            'toolchainPath': str(tools),
            'nodeExecutable': str((tools / 'bin/node').resolve()),
            'npmWrapper': str((tools / 'bin/npm').resolve()),
            'nodeVersion': output(str(tools / 'bin/node'), '--version', env=native_env),
            'npmVersion': output(str(tools / 'bin/npm'), '--version', env=native_env),
        }
        receipt['checks'].append(result)
finally:
    # A failed check must fail the job; retain any completed bindings for diagnosis.
    (directory / 'runtime.json').write_text(json.dumps(receipt, indent=2) + '\n')
