#!/usr/bin/env python3
"""Read seeded HTTP tarball entries through npm's own cache implementation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

seed = runpy.run_path(sys.argv[1])['seed']
with tempfile.TemporaryDirectory() as temporary:
    cache = Path(temporary)
    data = b'locked archive content'
    digest = hashlib.sha512(data)
    hexdigest = digest.hexdigest()
    content = cache / 'content-v2/sha512' / hexdigest[:2] / hexdigest[2:4] / hexdigest[4:]
    content.parent.mkdir(parents=True)
    content.write_bytes(data)
    original = 'https://registry.npmjs.org/example/-/example-1.tgz'
    remapped = 'http://127.0.0.1:9/example/-/example-1.tgz'
    catalog = [{'url': original, 'integrity': 'sha512-' + base64.b64encode(digest.digest()).decode(),
                'path': str(content)}]
    javascript = r'''
const assert = require('node:assert/strict');
const fetch = require(process.argv[1]);
(async () => {
  for (const url of process.argv.slice(4)) {
    try {
      const response = await fetch(url, {cachePath: process.argv[2], cache: 'only-if-cached'});
      assert.equal(process.argv[3], 'seeded');
      assert.equal(await response.text(), 'locked archive content');
    } catch (error) {
      if (process.argv[3] !== 'empty') throw error;
      assert.equal(error.code, 'ENOTCACHED');
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    module = str(Path(os.environ['NPM_PURIFIER_NPM_MODULES']) / 'make-fetch-happen')
    def fetch(mode):
        subprocess.run(['node', '-e', javascript, module, str(cache), mode, original, remapped], check=True)
    fetch('empty')
    seed(catalog, cache, 'http://127.0.0.1:9/')
    fetch('seeded')
    # Simulate immutable index files supplied by a Nix dependency.
    for index in cache.glob('index-v5/*/*/*'):
        immutable = cache / ('immutable-' + index.name)
        immutable.write_bytes(index.read_bytes())
        immutable.chmod(0o444)
        index.unlink()
        index.symlink_to(immutable)
    seed(catalog, cache, 'http://127.0.0.1:9/')
    assert all(not index.is_symlink() for index in cache.glob('index-v5/*/*/*'))
    fetch('seeded')
    print('PASS cold negative control, integrity-free URL lookup, registry remapping and writable index copy-up')
