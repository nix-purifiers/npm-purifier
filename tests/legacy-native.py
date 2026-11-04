#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native npm 6 proof; takes the built checks.<system>.legacy-node-tools path."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from registry_fixture import registry

tools = Path(sys.argv[1]).resolve()
expected_archive = Path(sys.argv[2]).resolve()
version = sys.argv[3] if len(sys.argv) > 3 else '12.22.12'
prepared = Path(sys.argv[4]) if len(sys.argv) > 4 else None
catalog = Path(sys.argv[5]) if len(sys.argv) > 5 else None
env = dict(os.environ, PATH=str(tools / 'bin') + os.pathsep + os.environ['PATH'])


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()


with tempfile.TemporaryDirectory(prefix='npm-legacy-native-') as temporary:
    root = Path(temporary) / 'project'
    shutil.copytree(Path(__file__).parent / 'fixtures' / 'legacy-node', root)
    env['HOME'] = str(Path(temporary) / 'home')
    Path(env['HOME']).mkdir()
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert run('node', '--version', cwd=root) == 'v' + version
    npm_version = run('npm', '--version', cwd=root)
    run('npm-purifier', 'lock', cwd=root)
    assert (root / 'package.json').read_bytes() == before['package.json']
    before['package-lock.json'] = (root / 'package-lock.json').read_bytes()
    run('npm-purifier', 'prefetch', cwd=root)
    env['npm_config_registry'] = 'http://127.0.0.1:9'
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
    print('PASS npm' + npm_version + '/Node' + version + ' lock, prefetch, offline ci, build/test and actual publication; native lock preserved after resolution')
