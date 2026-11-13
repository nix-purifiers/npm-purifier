// SPDX-License-Identifier: MIT
// Materialize HTTP cache bodies from native lock manifests, without resolving.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const semver = require(path.join(process.env.NPM_PURIFIER_NPM_MODULES, 'semver'));
const tar = require(path.join(process.env.NPM_PURIFIER_NPM_MODULES, 'tar'));

const manifests = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const output = process.argv[3];
async function main() {
const archives = new Map(process.argv[4]
  ? JSON.parse(fs.readFileSync(process.argv[4], 'utf8')).map(item => [item.url, item.path]) : []);
const archiveManifests = new Map();
async function archiveManifest(file) {
  if (!archiveManifests.has(file)) {
    let text;
    await tar.t({file, onReadEntry(entry) {
      const parts = entry.path.split('/').filter(Boolean);
      if (parts.length === 2 && parts[1] === 'package.json' && entry.type === 'File') {
        const chunks = [];
        entry.on('data', chunk => chunks.push(chunk));
        entry.on('end', () => { text = Buffer.concat(chunks).toString('utf8'); });
      }
    }});
    archiveManifests.set(file, text === undefined ? {} : JSON.parse(text));
  }
  return archiveManifests.get(file);
}
const documents = new Map();
const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
for (const record of manifests) {
  const file = archives.get(record.dist.tarball);
  // Archive-only fields such as lifecycle scripts must survive metadata
  // lookup. Root-lock resolution fields retain their native precedence.
  const manifest = {...(file ? await archiveManifest(file) : {}), ...record};
  if (!semver.valid(manifest.version)) continue;
  const marker = '/' + manifest.name + '/-/';
  const index = manifest.dist.tarball.indexOf(marker);
  const registry = index >= 0 ? manifest.dist.tarball.slice(0, index + 1) : 'https://registry.npmjs.org/';
  const url = registry + manifest.name.replace('/', '%2f');
  let document = documents.get(url);
  if (!document) {
    document = {name: manifest.name, versions: {}};
    documents.set(url, document);
  }
  // Consumer-native records precede auxiliary shrinkwrap/preparation locks.
  if (!document.versions[manifest.version]) document.versions[manifest.version] = manifest;
}
// Native observations retain the exact registry fields used during locking.
const snapshots = process.argv[5] ? JSON.parse(fs.readFileSync(process.argv[5], 'utf8')) : {};
for (const [url, snapshot] of Object.entries(snapshots)) {
  const derived = documents.get(url);
  documents.set(url, {...snapshot, versions: {...derived?.versions, ...snapshot.versions}});
}
const catalog = [];
fs.mkdirSync(path.join(output, 'cache'), {recursive: true});
for (const url of [...documents.keys()].sort(compare)) {
  const document = documents.get(url);
  const versions = Object.keys(document.versions).sort(semver.rcompare);
  const latest = versions.find(version => !semver.prerelease(version)) || versions[0];
  const body = JSON.stringify({
    _id: document.name, name: document.name, 'dist-tags': document['dist-tags'] || {latest},
    ...(document.time ? {time: document.time} : {}),
    versions: Object.fromEntries(versions.map(version => [version, document.versions[version]])),
  });
  const digest = crypto.createHash('sha512').update(body).digest();
  const hex = digest.toString('hex');
  const file = path.join(output, 'cache/content-v2/sha512', hex.slice(0, 2), hex.slice(2, 4), hex.slice(4));
  fs.mkdirSync(path.dirname(file), {recursive: true});
  fs.writeFileSync(file, body);
  catalog.push({
    url, integrity: 'sha512-' + digest.toString('base64'), path: file,
    contentType: 'application/json',
    accepts: [null, 'application/json', 'application/vnd.npm.install-v1+json',
      'application/vnd.npm.install-v1+json; q=1.0, application/json; q=0.8, */*'],
  });
}
fs.writeFileSync(path.join(output, 'catalog.json'), JSON.stringify(catalog));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
