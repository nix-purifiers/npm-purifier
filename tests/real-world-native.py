#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the pinned commander sample with ordinary npm and the purifier."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


root = Path(__file__).resolve().parent.parent


def output(*args):
    return subprocess.check_output(args, cwd=root, text=True).strip()


system = output('nix', 'eval', '--impure', '--raw', '--expr', 'builtins.currentSystem')
tools = output('nix', 'build', '--no-link', '--print-out-paths', '.#toolchain')
source = output('nix', 'eval', '--impure', '--raw', '--expr',
                '(import ./tests/real-world.nix { buildNpmProject = x: x; }).commander.src')
env = dict(os.environ, PATH=tools + '/bin' + os.pathsep + os.environ['PATH'],
           npm_config_audit='false', npm_config_fund='false')
# The upstream suite sets these itself to test color detection independently.
for variable in ('NO_COLOR', 'FORCE_COLOR', 'CLICOLOR_FORCE'):
    env.pop(variable, None)


def run(*args, cwd, ordinary=False, check=True):
    selected = dict(env)
    if ordinary:
        selected['NPM_PURIFIER'] = '0'
    print('+', 'ordinary' if ordinary else 'purified', *args, flush=True)
    result = subprocess.run(args, cwd=cwd, env=selected, check=False, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and result.returncode:
        print(result.stdout, end='', flush=True)
        result.check_returncode()
    return result


def passed(*args, cwd, ordinary=False):
    result = run(*args, cwd=cwd, ordinary=ordinary)
    print(result.stdout, end='', flush=True)
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix='npm-real-world-') as temporary:
    work = Path(temporary)
    project = work / 'commander'
    shutil.copytree(source, project, symlinks=True)
    project.chmod(project.stat().st_mode | 0o200)
    for path in project.rglob('*'):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o200)
    env.update(HOME=str(work / 'home'), npm_config_cache=str(work / 'ordinary-cache'))
    Path(env['HOME']).mkdir()
    print(json.dumps({'system': system, 'source': source, 'toolchain': tools,
                      'producer': output('git', 'rev-parse', 'HEAD'),
                      'sampleRevision': 'ba6d13ddb4243e5913367734f8c159089ffe7834',
                      'sourceHash': output('nix', 'hash', 'path', source),
                      'nodeExecutable': str((Path(tools) / 'bin/node').resolve()),
                      'npmWrapper': str((Path(tools) / 'bin/npm').resolve()),
                      'node': passed('node', '--version', cwd=project),
                      'npm': passed('npm', '--version', cwd=project, ordinary=True)}), flush=True)
    manifest = (project / 'package.json').read_bytes()
    # Start with npm's own resolution and the project's unmodified full test suite.
    passed('npm', 'ci', cwd=project, ordinary=True)
    passed('npm', 'test', cwd=project, ordinary=True)
    shutil.rmtree(project / 'node_modules')
    passed('npm-purifier', 'lock', cwd=project)
    lock = (project / 'package-lock.json').read_bytes()
    # Relocation plus a fresh resolver cache must reproduce the resolved graph.
    relocated = work / 'relocated'
    shutil.copytree(project, relocated, symlinks=True)
    env['npm_config_cache'] = str(work / 'relocated-cache')
    passed('npm-purifier', 'lock', cwd=relocated)
    assert (relocated / 'package-lock.json').read_bytes() == lock
    assert (relocated / 'package.json').read_bytes() == manifest
    assert (project / 'package.json').read_bytes() == manifest
    passed('npm-purifier', 'prefetch', cwd=project)
    # No ambient npm cache can satisfy the install, and the registry is unavailable.
    env.update(npm_config_registry='http://127.0.0.1:9/',
               npm_config_cache=str(work / 'cold-cache'), npm_config_offline='true')
    failed = run('npm', 'ci', cwd=relocated, ordinary=True, check=False)
    assert failed.returncode != 0 and 'ENOTCACHED' in failed.stdout, failed.stdout
    print('PASS negative control: ordinary cold offline npm ci fails', flush=True)
    passed('npm', 'ci', cwd=project)
    passed('npm', 'test', cwd=project)
    assert (project / 'package-lock.json').read_bytes() == lock
    assert (project / 'package.json').read_bytes() == manifest
    # Return to ordinary npm with its preexisting cache and no purifier state.
    shutil.rmtree(project / 'node_modules')
    shutil.rmtree(project / '.npm-purifier')
    env['npm_config_cache'] = str(work / 'ordinary-cache')
    passed('npm', 'ci', cwd=project, ordinary=True)
    passed('npm', 'test', cwd=project, ordinary=True)
    assert (project / 'package-lock.json').read_bytes() == lock
    assert (project / 'package.json').read_bytes() == manifest
    # The independently pinned sample also runs its suite in the Nix sandbox.
    passed('nix', 'build', '--no-link', '-L', '.#checks.' + system + '.real-commander', cwd=root)
    print('PASS pinned commander ordinary/purified/ordinary switching, relocated relock, '
          'prefetch, cold offline install/tests, and pure build/tests', flush=True)
