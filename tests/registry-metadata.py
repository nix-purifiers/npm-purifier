#!/usr/bin/env python3
"""Replay native metadata probes and locked manifests with native pacote."""
import json
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import tarfile

seed = runpy.run_path(sys.argv[1])['seed']
generator = sys.argv[2]
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    manifests = []
    for name, version in [('example', '1.0.0'), ('example', '1.5.0'), ('@scope/example', '3.0.0')]:
        manifests.append({'name': name, 'version': version, 'peerDependencies': {'peer': '>=3'},
                          'dependencies': {'child': '^2'},
                          'dist': {'tarball': f'https://registry.npmjs.org/{name}/-/example-{version}.tgz',
                                   'integrity': 'sha512-YQ=='}})
    (root / 'manifests.json').write_text(json.dumps(manifests))
    package = json.dumps({'name': 'example', 'version': '1.5.0', 'main': 'index.js',
                          'scripts': {'postinstall': 'node postinstall.js'}}).encode()
    archive = root / 'example.tgz'
    with tarfile.open(archive, 'w:gz') as stream:
        info = tarfile.TarInfo('package/package.json')
        info.size = len(package)
        stream.addfile(info, io.BytesIO(package))
    (root / 'archives.json').write_text(json.dumps([{'url': manifests[1]['dist']['tarball'], 'path': str(archive)}]))
    probe = dict(manifests[0], version='0.8.0', dependencies={'probe': '^1'})
    snapshots = {'https://registry.npmjs.org/example': {'name': 'example',
                 'versions': {'0.8.0': probe}, 'dist-tags': {'stable': '0.8.0'}}}
    (root / 'snapshots.json').write_text(json.dumps(snapshots))
    subprocess.run(['node', generator, str(root / 'manifests.json'), str(root / 'metadata'),
                    str(root / 'archives.json'), str(root / 'snapshots.json')], check=True)
    catalog = json.loads((root / 'metadata/catalog.json').read_text())
    cache = root / 'metadata/cache'
    seed(catalog, cache, 'http://127.0.0.1:9/')
    javascript = r'''
const assert = require('node:assert/strict');
const pacote = require(process.argv[1]);
(async () => {
  for (const fullMetadata of [false, true, false, true]) {
    const options = {cache: process.argv[2], registry: 'http://127.0.0.1:9/', offline: true, fullMetadata};
    const result = await pacote.manifest('example@^1', options);
    assert.equal(result.version, '1.5.0');
    assert.deepEqual(result.peerDependencies, {peer: '>=3'});
    assert.deepEqual(result.dependencies, {child: '^2'});
    assert.equal(result.main, 'index.js');
    assert.deepEqual(result.scripts, {postinstall: 'node postinstall.js'});
    assert.equal((await pacote.manifest('@scope/example@3', options)).version, '3.0.0');
    assert.equal((await pacote.manifest('example@stable', options)).version, '0.8.0');
    await assert.rejects(pacote.manifest('example@^2', options), {code: 'ETARGET'});
    await assert.rejects(pacote.manifest('unlocked-package@1', options), {code: 'ENOTCACHED'});
  }
})().catch(error => {console.error(error); process.exitCode = 1});
'''
    environment = os.environ
    subprocess.run(['node', '-e', javascript,
                    str(Path(os.environ['NPM_PURIFIER_NPM_MODULES']) / 'pacote'), str(cache)],
                   env=environment, check=True)
    print('PASS scoped/full/abbreviated locked metadata and refusal of unrecorded names/versions')
