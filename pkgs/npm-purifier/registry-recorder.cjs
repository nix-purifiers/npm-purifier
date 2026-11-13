// SPDX-License-Identifier: MIT
// Observe native pacote results without changing resolution or returned values.
'use strict';
const fs = require('fs');
const path = require('path');

function install(RegistryFetcher, append) {
  const originalPackument = RegistryFetcher.prototype.packument;
  const originalManifest = RegistryFetcher.prototype.manifest;
  if (typeof originalPackument !== 'function' || typeof originalManifest !== 'function') {
    throw new Error('npm-purifier: native pacote lacks registry observation methods');
  }
  const documents = new WeakMap();
  RegistryFetcher.prototype.packument = async function () {
    const document = await originalPackument.apply(this, arguments);
    documents.set(this, document);
    return document;
  };
  RegistryFetcher.prototype.manifest = async function () {
    const result = await originalManifest.apply(this, arguments);
    const document = documents.get(this);
    const dist = result.dist || {};
    if (document && /^https?:/.test(result._resolved || dist.tarball || '') &&
        /^https?:/.test(dist.tarball || '')) {
      const raw = (document.versions || {})[result.version] || result;
      const manifest = JSON.parse(JSON.stringify(raw));
      for (const field of ['_resolved', '_integrity', '_from', '_contentLength']) delete manifest[field];
      if (!manifest.dist.integrity && manifest.dist.shasum) {
        manifest.dist.integrity = 'sha1-' + Buffer.from(manifest.dist.shasum, 'hex').toString('base64');
      }
      append({url: this.packumentUrl, manifest: manifest, tags: document['dist-tags'] || {},
        time: (document.time || {})[result.version]});
    }
    return result;
  };
  return function () {
    RegistryFetcher.prototype.packument = originalPackument;
    RegistryFetcher.prototype.manifest = originalManifest;
  };
}

if (process.env.NPM_PURIFIER_REGISTRY_TRACE) {
  // Load the public entry first to preserve pacote's registry/fetcher cycle.
  const modules = process.env.NPM_PURIFIER_TARGET_NPM_MODULES;
  require(path.join(modules, 'pacote'));
  const RegistryFetcher = require(path.join(modules, 'pacote/lib/registry.js'));
  install(RegistryFetcher, function (record) {
    fs.appendFileSync(process.env.NPM_PURIFIER_REGISTRY_TRACE, JSON.stringify(record) + '\n');
  });
}
module.exports = {install: install};
