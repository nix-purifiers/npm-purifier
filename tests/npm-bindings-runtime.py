#!/usr/bin/env python3
"""Supplied coordinates must bind the caller's actual npm, including JS launchers."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

bindings = Path(sys.argv[1]).resolve()
inspector = Path(sys.argv[2]).resolve()
caller = Path(sys.argv[3]).resolve()
modules = caller / 'lib/node_modules/npm/node_modules'
main = caller / 'lib/node_modules/npm/bin/npm-cli.js'
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    repository = root / 'repository'
    repository.mkdir()
    package = {'name': 'provided-native-fixture', 'version': '1.0.0-nix'}
    archive = repository / 'fixture.tgz'
    with tarfile.open(archive, 'w:gz') as stream:
        for name, contents in [('package.json', json.dumps(package).encode()), ('index.js', b'module.exports = 42;\n')]:
            entry = tarfile.TarInfo('package/' + name)
            entry.size = len(contents)
            stream.addfile(entry, io.BytesIO(contents))
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    catalog = root / 'catalog.json'
    catalog.write_text(json.dumps({'version': 1, 'modules': [{**package, 'primary': True,
        'archive': archive.name, 'integrity': integrity, 'package': package}]}))
    views = root / 'views.json'
    views.write_text(json.dumps([{'repository': str(repository), 'catalog': str(catalog)}]))
    proxy = root / 'caller-npm.js'
    proxy.write_text('require(' + json.dumps(str(main)) + ');\n')
    environment = dict(os.environ, HOME=str(root), NODE_OPTIONS='--require=' + str(bindings),
        NPM_PURIFIER_NPM_MODULES=str(inspector / 'lib/node_modules/npm/node_modules'),
        NPM_PURIFIER_TARGET_NPM_MODULES=str(modules), NPM_PURIFIER_INPUT_VIEWS=str(views),
        npm_config_offline='true', npm_config_registry='http://127.0.0.1:9/',
        npm_config_fetch_retries='0', npm_config_audit='false', npm_config_fund='false',
        npm_config_update_notifier='false')
    locks = []
    for name, launcher in [('direct', main), ('proxy', proxy)]:
        project = root / name
        project.mkdir()
        (project / 'package.json').write_text(json.dumps({'name': 'native-input-consumer',
            'version': '1.0.0', 'dependencies': {package['name']: '>=99'}}))
        env = dict(environment, npm_config_cache=str(root / (name + '-cache')))
        for args in [['install', '--package-lock-only', '--ignore-scripts'], ['ci', '--ignore-scripts']]:
            subprocess.run([str(caller / 'bin/node'), str(launcher), *args], cwd=project, env=env, check=True)
        subprocess.run([str(caller / 'bin/node'), '-e', "if(require('./node_modules/provided-native-fixture')!==42)process.exit(1)"],
                       cwd=project, env=env, check=True)
        lock = json.loads((project / 'package-lock.json').read_text())
        assert lock['packages']['node_modules/' + package['name']]['version'] == package['version']
        locks.append(lock)
        (project / 'package.json').write_text(json.dumps({'name': 'negative-input-consumer',
            'version': '1.0.0', 'dependencies': {'unprovided-input-negative-control': '1.0.0'}}))
        failed = subprocess.run([str(caller / 'bin/node'), str(launcher), 'install', '--package-lock-only', '--ignore-scripts'],
                                cwd=project, env=env, text=True, capture_output=True)
        assert failed.returncode and 'ENOTCACHED' in failed.stderr, failed.stderr
    assert locks[0] == locks[1]
    print('PASS actual caller npm direct/proxy supplied input, offline CI, runtime import and unprovided-name rejection')
