// SPDX-License-Identifier: MIT
//
// Unit tests of the lock run's parsing: which lockfile entries are git
// dependencies, where npm gets each one from, how submodule URLs resolve,
// and which dependencies npm prepares. They need no network; the flake's
// check `lock-run-units` runs them with `node --test`.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  gitDependencies,
  sourceOf,
  resolveSubmoduleUrl,
  submodulesOf,
  needsPreparation,
  preparationLock,
  incompleteEntries,
  completeLock,
  withHash,
  implementationPin,
  publishedLocks,
} = require("./lock.js");

test("published shrinkwrap discovery follows nested archives without rewriting the consumer lock", () => {
  const outer = {resolved: 'https://r/outer.tgz', integrity: 'sha512-outer', hasShrinkwrap: true};
  const nested = {resolved: 'https://r/nested.tgz', integrity: 'sha512-nested', hasShrinkwrap: true};
  const root = {packages: {'node_modules/outer': outer,
    'node_modules/outer/node_modules/leaf': {version: '9.0.0'},
    'node_modules/bundled': {...nested, inBundle: true}}};
  const before = JSON.stringify(root);
  const calls = [];
  const recorded = publishedLocks(root, entry => {
    calls.push(entry.resolved);
    return entry === outer ? {packages: {'node_modules/nested': nested,
      'node_modules/leaf': {version: '2.0.0'}}} : {packages: {'node_modules/outer': outer}};
  });
  assert.deepEqual(calls, ['https://r/outer.tgz', 'https://r/nested.tgz']);
  assert.equal(recorded['https://r/outer.tgz'].packageLock.packages['node_modules/leaf'].version, '2.0.0');
  assert.equal(JSON.stringify(root), before);
  assert.throws(() => publishedLocks(root, () => null), /contains no npm-shrinkwrap/);
  assert.throws(() => publishedLocks({packages: {a: outer, b: {...outer, integrity: 'sha512-other'}}},
    () => ({packages: {}})), /conflicting integrity/);
  assert.throws(() => publishedLocks({packages: {a: {...outer, integrity: undefined}}},
    () => ({packages: {}})), /no integrity/);
});

const sha = "98e8ff1da1a89f93d1397a24d7413ed15421c139";

test("dependency relocking preserves implementation and explicit legacy migration", () => {
  const old = { version: 1, tool: "npm-purifier", source: { rev: "old" } };
  const installed = { source: { rev: "new" } };
  assert.deepEqual(implementationPin({ implementation: old }, installed), old);
  assert.equal(implementationPin({ version: 3 }, installed), undefined);
  assert.deepEqual(implementationPin(null, installed), {
    version: 1, tool: "npm-purifier", source: installed.source,
  });
  assert.throws(() => implementationPin(null, { source: null }), /portable source identity/);
});

test("new pins retain SDK recipe and dependency relocking preserves it", () => {
  const configuration = { version: 1, node: { type: "upstream-node", version: "8.17.0" } };
  const installed = { source: { rev: "A" }, configuration };
  const pin = implementationPin(null, installed);
  assert.deepEqual(pin.configuration, configuration);
  assert.deepEqual(implementationPin({ implementation: pin }, { source: { rev: "B" } }), pin);
  assert.deepEqual(implementationPin(null, { source: { rev: "A" }, configuration: null }), {
    version: 1, tool: "npm-purifier", source: { rev: "A" },
  });
});

test("legacy nested locks retain their format and scoped paths when completed", () => {
  const lock = {lockfileVersion: 1, dependencies: {
    a: {version: "1.0.0", resolved: "https://r/a.tgz", integrity: "sha512-a", dependencies: {
      "@scope/b": {version: "2.0.0"},
      bundled: {version: "1.0.0", bundled: true},
      source: {version: `git+https://github.com/o/r.git#${sha}`},
    }},
  }};
  assert.deepEqual(incompleteEntries(lock), ["node_modules/a/node_modules/@scope/b"]);
  assert.deepEqual(gitDependencies(lock), [`git+https://github.com/o/r.git#${sha}`]);
  completeLock(lock, (name, version) => {
    assert.equal(name, "@scope/b"); assert.equal(version, "2.0.0");
    return {tarball: "https://r/b.tgz", integrity: "sha512-b"};
  });
  assert.equal(lock.lockfileVersion, 1);
  assert.equal(lock.packages, undefined);
  assert.equal(lock.dependencies.a.dependencies["@scope/b"].resolved, "https://r/b.tgz");
  assert.equal(lock.dependencies.a.dependencies["@scope/b"].inBundle, undefined);
});

test("gitDependencies takes the git entries and nothing else", () => {
  const lock = {
    packages: {
      "": { name: "root", dependencies: { a: "1" } },
      "node_modules/a": { resolved: "https://registry.npmjs.org/a/-/a-1.0.0.tgz", integrity: "sha512-x" },
      "node_modules/b": { resolved: `git+ssh://git@github.com/o/b.git#${sha}` },
      "node_modules/c": { resolved: "packages/c", link: true },
      "node_modules/d": { resolved: "file:vendor/d.tgz" },
      "node_modules/e/node_modules/f": { resolved: `git+https://codeberg.org/o/f.git#${sha}` },
      "packages/c": { name: "c" },
    },
  };
  assert.deepEqual(gitDependencies(lock), [
    `git+ssh://git@github.com/o/b.git#${sha}`,
    `git+https://codeberg.org/o/f.git#${sha}`,
  ]);
});

test("a GitHub dependency comes from the archive of its commit", () => {
  assert.deepEqual(sourceOf(`git+ssh://git@github.com/jonschlinkert/is-number.git#${sha}`), {
    rev: sha,
    subdir: "",
    url: "https://github.com/jonschlinkert/is-number.git",
    archive: `https://codeload.github.com/jonschlinkert/is-number/tar.gz/${sha}`,
  });
});

test("a dependency in a directory of a repository keeps the directory", () => {
  const source = sourceOf(`git+ssh://git@github.com/o/r.git#${sha}::path:packages/x`);
  assert.equal(source.subdir, "packages/x");
  // npm requests the archive with the directory in its URL, so the cache
  // answers that URL.
  assert.equal(source.archive, `https://codeload.github.com/o/r/tar.gz/${sha}%3A%3Apath%3Apackages%2Fx`);
});

test("a GitLab dependency comes from GitLab's archive", () => {
  const source = sourceOf(`git+https://gitlab.com/o/r.git#${sha}`);
  assert.equal(source.archive, `https://gitlab.com/api/v4/projects/o%2Fr/repository/archive.tar.gz?sha=${sha}`);
});

test("a dependency on another host is cloned from its URL", () => {
  assert.deepEqual(sourceOf(`git+https://codeberg.org/o/r.git#${sha}`), {
    rev: sha,
    subdir: "",
    url: "https://codeberg.org/o/r.git",
    repository: "https://codeberg.org/o/r.git",
  });
});

test("a git dependency without a commit asks for npm install", () => {
  assert.throws(() => sourceOf("git+https://codeberg.org/o/r.git#main"), /run `npm install`/);
});

test("submodule URLs resolve against the superproject's URL", () => {
  assert.equal(resolveSubmoduleUrl("https://h/o/r.git", "../s.git"), "https://h/o/s.git");
  assert.equal(resolveSubmoduleUrl("https://h/o/r", "./s.git"), "https://h/o/r/s.git");
  assert.equal(resolveSubmoduleUrl("https://h/o/r.git", "../../p/s.git"), "https://h/p/s.git");
  assert.equal(resolveSubmoduleUrl("https://h/o/r.git", "https://x/s.git"), "https://x/s.git");
});

test("submodulesOf finds nested submodules with their directories", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nix-lock-test-"));
  try {
    fs.writeFileSync(
      path.join(dir, ".gitmodules"),
      '[submodule "vendor/a"]\n\tpath = vendor/a\n\turl = ../a.git\n',
    );
    fs.mkdirSync(path.join(dir, "vendor/a"), { recursive: true });
    fs.writeFileSync(
      path.join(dir, "vendor/a/.gitmodules"),
      '[submodule "deep"]\n\tpath = deep\n\turl = https://x/deep.git\n',
    );
    assert.deepEqual(submodulesOf(dir, "https://h/o/r.git"), [
      { url: "https://h/o/a.git", path: "vendor/a" },
      { url: "https://x/deep.git", path: "vendor/a/deep" },
    ]);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("the lock run completes registry entries without a URL or an integrity", () => {
  const lock = {
    packages: {
      "": { name: "root" },
      "node_modules/url-join": { version: "4.0.1", license: "MIT" },
      "node_modules/a/node_modules/@s/b": { version: "2.0.0", resolved: "https://r/@s/b/-/b-2.0.0.tgz" },
      "node_modules/c": { version: "1.0.0", resolved: "https://r/c/-/c-1.0.0.tgz", integrity: "sha512-c" },
      "node_modules/d": { resolved: "packages/d", link: true },
      "node_modules/e": { version: "1.0.0", resolved: `git+ssh://git@github.com/o/e.git#${sha}` },
    },
  };
  assert.deepEqual(incompleteEntries(lock), ["node_modules/url-join", "node_modules/a/node_modules/@s/b"]);
  const asked = [];
  completeLock(lock, (name, version) => {
    asked.push(`${name}@${version}`);
    return { tarball: `https://r/${name}-${version}.tgz`, integrity: `sha512-${name}` };
  });
  assert.deepEqual(asked, ["url-join@4.0.1", "@s/b@2.0.0"]);
  assert.deepEqual(lock.packages["node_modules/url-join"], {
    version: "4.0.1",
    resolved: "https://r/url-join-4.0.1.tgz",
    integrity: "sha512-url-join",
    license: "MIT",
  });
  assert.equal(lock.packages["node_modules/a/node_modules/@s/b"].resolved, "https://r/@s/b/-/b-2.0.0.tgz");
  assert.equal(lock.packages["node_modules/a/node_modules/@s/b"].integrity, "sha512-@s/b");
  assert.deepEqual(Object.keys(lock.packages["node_modules/url-join"]), ["version", "resolved", "integrity", "license"]);
});

test("the lockfile hash covers the text with the hash itself left empty", () => {
  const text = '{\n  "version": 3,\n  "hash": "",\n  "git": {}\n}\n';
  const written = withHash(text);
  const hash = written.match(/"hash": "(sha256-[^"]+)"/)[1];
  const expected = "sha256-" + require("crypto").createHash("sha256").update(text).digest("base64");
  assert.equal(hash, expected);
  assert.equal(written.replace(hash, ""), text);
});

test("npm prepares a dependency with a preparing script or workspaces", () => {
  assert.equal(needsPreparation({ name: "a" }), false);
  assert.equal(needsPreparation({ scripts: { test: "x" } }), false);
  assert.equal(needsPreparation({ scripts: { prepare: "x" } }), true);
  assert.equal(needsPreparation({ scripts: { install: "x" } }), true);
  assert.equal(needsPreparation({ workspaces: ["p/*"] }), true);
});

test("git preparation can lock and remove a nested read-only checkout", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "readonly-git-test-"));
  const source = path.join(root, "source");
  fs.mkdirSync(source);
  const nested = path.join(source, "nested");
  fs.mkdirSync(nested);
  fs.writeFileSync(path.join(nested, "data"), "unchanged");
  fs.symlinkSync(source, path.join(source, "link"));
  const manifest = JSON.stringify({name: "readonly-git-fixture", version: "1.0.0",
    scripts: {prepare: "node -e 'process.exit(99)'"}});
  fs.writeFileSync(path.join(source, "package.json"), manifest);
  fs.chmodSync(path.join(nested, "data"), 0o444);
  fs.chmodSync(nested, 0o555);
  fs.chmodSync(source, 0o555);
  try {
    const result = preparationLock(source);
    assert.equal(result.inject, true);
    assert.equal(result.lock.name, "readonly-git-fixture");
    assert.equal(fs.readFileSync(path.join(source, "package.json"), "utf8"), manifest);
    assert.equal(fs.statSync(source).mode & 0o777, 0o555);
    assert.equal(fs.statSync(nested).mode & 0o777, 0o555);
    assert.equal(fs.existsSync(path.join(source, "package-lock.json")), false);
  } finally {
    fs.chmodSync(source, 0o755);
    fs.chmodSync(nested, 0o755);
    fs.rmSync(root, {recursive: true, force: true});
  }
});
