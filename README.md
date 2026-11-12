# npm-purifier

npm-purifier keeps npm's development workflow on locked,
Nix-resolved dependencies. Use the normal build and test commands in your
working tree; building the project itself in the Nix sandbox is an
optional next step.

## Quickstart

Keep the project's existing Node.js and native npm on `PATH`. The interactive
commands use that runtime, including installations outside the Nix store;
the toolchain shell supplies the purifier and wrapper. Pure Nix builders
select their immutable SDK separately.

From the project root:

```zsh
nix shell 'github:nix-purifiers/npm-purifier#toolchain'
npm-purifier lock
npm ci
npm run build
npm test
```

Commit the lockfiles that the lock command writes, including the build
tool's own lockfile when it has one. Keep using the project's usual build,
test and editor commands with this setup. Nix provides the locked
dependencies; the development commands above run outside the Nix sandbox.
No project Nix files are needed for this workflow.

Sandboxed builds are an optional
[next step](#building-the-project-with-nix).

The shell provides the `npm` wrapper. Use it for the locked
development workflow. The native lockfile can supply the complete
download record; the purifier lock records the implementation and any extra
download information npm cannot represent. With no usable lockfile, the wrapper warns on standard error and
runs the ordinary tool with impure resolution.

Install these packages through your usual Nix configuration.


## Development loop

The purifier contract runs the development loop through the build tool's
own command. npm has no plugin mechanism through which npm-purifier could
give that command the locked downloads, so the loop runs through the
`npm` wrapper that `nix shell 'github:nix-purifiers/npm-purifier#toolchain'` puts on
`PATH`. The wrapper takes npm's own commands and arguments.

The `npm` wrapper passes every command to npm. The commands that change
the lockfile (`install`, `update`, `uninstall` and their aliases) resolve
against the registry as npm does, and then run `npm-purifier lock`, so
`npm-purifier.lock.json` stays in step with `package-lock.json`. Every
other command (`ci`, `run`, `test`, `exec`) runs offline against the
dependencies Nix prefetched.

`npm-purifier lock` does three things:

- It runs `npm install --package-lock-only`, which brings
  `package-lock.json` in step with `package.json`.
- It records the URL and integrity of lockfile entries that lack them, as
  a later `npm install` would. Some lockfiles leave both out, and npm then
  asks the registry at install time.
- It writes `npm-purifier.lock.json` for the git dependencies, or removes
  it when the project has none.

`npm-purifier lock` keeps the versions `package-lock.json` resolves.
`npm-purifier update` moves them: it runs `npm update` on every
dependency, or on the packages named after it, and then locks as
`npm-purifier lock` does, so both lockfiles change in one run.

`npm-purifier publish` builds the package in the current directory with
Nix and runs `npm publish` on that tarball. Further arguments go to
`npm publish`, so `npm-purifier publish --dry-run` shows what would be
uploaded. Nothing is packed outside the sandbox.

### Updating npm-purifier

New project locks pin npm-purifier's source revision and hash. Updating the
installed wrapper or running `npm-purifier update` preserves that pin.
To select your installed version explicitly:

```sh
npm-purifier self-update --to installed
```

Or select a published revision with `--to github:nix-purifiers/npm-purifier/REV`.
The selected implementation relocks a staged copy before replacing the lock;
this operation preserves npm's dependency lock. `npm-purifier implementation`
prints the selected identity. Existing locks without a pin warn until explicitly
migrated with `self-update`.

Exact SDK variants shipped by this source are recorded with the pin and replayed
by the pinned source. An arbitrary patched SDK can still run unlocked or with a
legacy lock, but cannot create a portable pin without a reproducible SDK recipe.
The same applies when an overlay uses a different Nixpkgs or modified host tools;
use the purifier source's exported packages to create a portable pin.
Use a wrapper that supports implementation pins;
older wrappers cannot enforce them. Projects need no flake.

## Dependencies from another purified project

Supply a Nix-built package that exports an npm repository:

```sh
npm-purifier lock \
  --input 'github:example/library#library'
npm ci
```

The purifier pins the producer's Nix source identity. Supplied packages
come from its repository and stay out of `package-lock.json`; npm reconstructs
their native records from the pinned inputs when needed. Their Nix
identities take precedence over ordinary version constraints; your
`package.json` stays unchanged. `npm-purifier update` refreshes the inputs.

A Nix build can pass producer packages through `dependencies`. Its outputs
expose `projections.npm`, with exact dependency metadata for ordinary npm
consumers. Prepared native dependencies are included for the target platform.
With composed inputs, `npm-purifier publish` publishes those repository
archives using npm's authentication and options, under the `nix` tag unless
you specify another tag.

## Building the project with Nix

Once the native development workflow is working, you can also build and
test the project in the Nix sandbox. For this step, keep a flake or
another Nix build definition in the project's repository, or maintain an
external packaging repository that points at its sources and lockfiles.
The builder consumes the same lockfiles as the development workflow.

The root package, each workspace and each local directory the project
depends on become `packages.<name>`, installed with their production
dependencies and with their commands in `bin/`. `release` holds the
tarballs `npm publish` uploads, and `tests` runs the `test` script in a
derivation of its own. `fetches` lists every download as an entry of the
purifier library, for SBOM, license and vulnerability tools.
`pkgs/build-npm-project/default.nix` documents every argument of the builder.

A project whose authors want a flake can package it with one that calls the
builder directly. The flake can live in the repository of the project or in
another one:

```nix
{
  inputs.npm-purifier.url =
    "github:nix-purifiers/npm-purifier";
  inputs.nixpkgs.follows = "npm-purifier/nixpkgs";

  outputs =
    { nixpkgs, npm-purifier, ... }:
    let
      system = "x86_64-linux";
      pin = (builtins.fromJSON
        (builtins.readFile ./npm-purifier.lock.json)).implementation;
      selected =
        (npm-purifier.lib.purifier.implementationSource.resolve
          pin.source).flake;
      pkgs = import nixpkgs {
        inherit system;
        overlays = [ selected.overlays.default ];
      };
      project = pkgs.npm-purifier.buildNpmProject {
        src = ./.;
      };
    in
    {
      packages.${system} = {
        default = project.packages.my-app;
        release = project.release;
      };
      checks.${system}.tests = project.tests;
    };
}
```

A package in a package set that has the overlay applied takes the scope by
name:

```nix
{ npm-purifier }:
(npm-purifier.buildNpmProject { src = ./.; })
.packages.my-app
```

`npm-purifier.buildNpmProject.override` replaces the packages the builder
takes, such as the `nodejs` its packages run on, and
`npm-purifier.overrideScope` replaces what everything in the scope
shares.

`npm-purifier.lib.npm-purifier.readLock { src = ./.; }` reads the
lockfiles without building anything. It returns the downloads as
`entries`, the packages as `outputs`, and, in `problems`, each reason the
lockfiles cannot be used, which is the same shape every purifier returns.

### Toolchain versions

Native command packages retain the SDK recipe needed for later Nix evaluation.
Tests check ordinary cache copying, selected outputs and evaluation without IFD;
the SDK's arbitrary package passthru attributes are not reconstructed.

`buildNpmProject { src = ./.; node = projectNode; captureNode = helperNode; }`
selects the project's Node.js and its bundled native npm independently of the
modern graph inspector. `projectNode` and `helperNode` are caller-provided Nix
packages; historical packages can come from a pinned package set or a separate
package derivation. The helper reads the installed graph and does not replace
npm's resolver. Capture records the target Node version, ABI and platform.

Exact regression points include Node 8.17.0, 10.24.1, 12.22.12, 14.21.3,
16.20.2, 18.20.8, 20.19.0, 22.14.0 and stable 26.0.0, each using its
bundled native npm. The pure fixtures build from a v1 lock with nested dependency
versions and check project scripts, production dependencies, native tarballs
and outgoing projections. Native tests exercise lock/prefetch, offline `npm ci`,
build/test, byte-equal publication and ordinary registry installation/execution
of the prepared graph. Newer native npm may migrate an older lock during
resolution; subsequent installation and publication must preserve that result.

Older npm reads cache content at the cache root; later npm uses `_cacache`.
Both consume the same locked content by integrity.
The prepared cache accommodates both layouts. CI includes both Linux
architectures; exact execution evidence belongs to each system. These points
do not establish version intervals, addon compilation, or compatibility for
unobserved older releases. The separate shrinkwrap fixtures below cover
the npm 2/3 era. Incoming Nix dependency bindings use Arborist APIs and require
separate historical adapters before claiming those workflows.

`npm-shrinkwrap.json` takes precedence when present. Exact pre-package-lock
regressions use Node 4.9.1/npm 2.15.11 and Node 6.17.1/npm 3.10.10, with locks
generated by those native managers. Capture adds missing download integrity
without changing the nested format. Installation lends native npm a temporary
shrinkwrap whose resolved URLs point to Nix-fetched archives, then restores the
original bytes and mtime, including on failure. This avoids old npm downloading explicit
HTTP resolutions despite having a package cache. Production installation also
runs native `npm prune --production`, since npm 2 shrinkwraps do not identify
dev-only entries. Copied build-tree timestamps are normalized before native packing because old
npm predates SOURCE_DATE_EPOCH. Native npm still installs, executes scripts,
packs and publishes.
Historical incoming Nix bindings, Git preparation and addon compilation need
separate proofs; these registry fixture points do not establish them.

### One-off builds without a project Nix file

For an ad hoc build, the builder can also be evaluated directly from the
project root. Replace the example package name with one from your project:

```zsh
nix build --impure --expr 'let
  bootstrap = builtins.getFlake "github:nix-purifiers/npm-purifier";
  pin = (builtins.fromJSON
    (builtins.readFile ./npm-purifier.lock.json)).implementation;
  purifier =
    (bootstrap.lib.purifier.implementationSource.resolve
      pin.source).flake;
  pkgs = import purifier.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ purifier.overlays.default ];
  };
in
(pkgs.npm-purifier.buildNpmProject { src = ./.; })
.packages.my-app'
```

This uses the purifier's pinned nixpkgs, matching the lock command above.
To build with ambient `<nixpkgs>` from your Nix search path instead,
replace `import purifier.inputs.nixpkgs` with `import <nixpkgs>`.
Both forms need no Nix files in your project. The build tool and language
versions must match the lockfile; with ambient nixpkgs, lock with the
purifier from that package set or pass a compatible toolchain to the builder.

## Working offline

`npm-purifier prefetch` builds the npm cache of every locked tarball and
git dependency in the Nix store, with a garbage-collector root at
`.npm-purifier/dependencies` in the project. The contract puts that root
beside the purifier lockfile. npm-purifier keeps it in the project even
when `npm-purifier.lock.json` lies outside, because npm reads its cache
from there. The wrapper runs `prefetch` on its own when either
lockfile changed since the last prefetch. After the prefetch, the
wrapper runs npm with `offline` set and a registry that nothing needs to
answer: `npm ci`, the build scripts and the tests read only what the
lockfiles name.

A command that needs a download the lockfiles do not name stops with
npm's `ENOTCACHED` error, and the wrapper adds a line that names
`npm-purifier lock`. `NPM_PURIFIER=0` turns the wrapper off for one
command. `NPM_PURIFIER_LOCKFILE` names an `npm-purifier.lock.json` other
than the one at the project root, for the wrapper and for every
`npm-purifier` command. `NPM_PURIFIER_TOOL_LOCKFILE` names a
`package-lock.json` kept outside the project, for every `npm-purifier`
command. A flake that keeps the files outside the project can set both
variables in its development shell to the paths it passes the builder.

npm in the project reads the `package-lock.json` of the project. It reads
neither an outside copy nor the `completions` of an outside
`npm-purifier.lock.json`, which serve the Nix build. Where those differ
from the file in the project, the wrapper stops with `ENOTCACHED` on the
entries the prefetch did not keep, and says so. The development loop works
offline with both lockfiles committed in the project, which is the
recommended setup.

## Editor

Editors and language servers read `node_modules`, which `npm ci` through
the wrapper fills as plain npm does, so they need no setup of their own.
An editor that runs npm itself (task runners, script panels) gets the
wrapper when it starts from `nix shell` with the toolchain package,
or from your usual environment configuration with the wrapper on `PATH`.

## Troubleshooting

The builder checks the lockfiles at evaluation time and stops with a
message that names the fix. `readLock` lists the same messages in
`problems`.

| Message | Cause | Fix |
| --- | --- | --- |
| `has git dependencies, and npm-purifier.lock.json does not exist` | a git dependency and no `npm-purifier.lock.json` | run `npm-purifier lock` and commit the file |
| `was made for another package-lock.json` | `package-lock.json` changed without the wrapper | run `npm-purifier lock` |
| `has no entry for <resolved>` | a git dependency the lock run has not seen | run `npm-purifier lock` |
| `was changed after npm-purifier lock wrote it` | `npm-purifier.lock.json` was edited by hand | run `npm-purifier lock` |
| `is not of format version 3` | a file from an older npm-purifier | run `npm-purifier lock` |
| `has no resolved URL` or `has no integrity` | an incomplete lockfile entry | run `npm-purifier lock` |
| `unsupported lockfileVersion` | a native format without a reader | select a purifier adapter for that format; keep the project lockfile |
| `has merge conflict markers` | an unresolved merge in a lockfile | resolve it, then run `npm-purifier lock` |
| `seems to be corrupted` (from npm) | a tarball whose content does not match its integrity | check the URL and the integrity in `package-lock.json` |

## Supported language repositories

npm-purifier serves these sources:

- Registry tarballs from any registry, by the URL and integrity in
  `package-lock.json`. Optional packages for other platforms stay out of
  the fetch, as npm leaves them out of the install, so one lockfile serves
  every system.
- Git dependencies on GitHub, GitLab, Bitbucket and sourcehut, which npm
  downloads as the host's archive of the commit. Nix fetches the commit,
  packs the archive and adds the cache entry that answers its URL.
- Git dependencies from any other repository, with their submodules. npm
  clones these, so the build makes each repository again from a plain
  checkout and the raw commit object the lock run recorded, and checks the
  commit's ID.
- Git dependencies that npm prepares (one with a prepare, build or install
  script). The lock run records the lockfile npm installs before the
  script runs.
- Workspaces, and local directories and tarballs (`file:`), including
  directories outside the project when `src` holds them.

npm-purifier refuses these:

- An install script that downloads files itself, such as the browser
  download of Puppeteer, fails in the sandbox, because no lockfile names
  the download.
- A git dependency from a private repository cannot be fetched in the
  sandbox. The builder's `gitCheckouts` argument supplies its checkout
  instead.
- A git dependency that npm clones from a URL other than the one in its
  `resolved` stops the lock run, which asks for the dependency in the
  `git+<url>#<commit>` form.
- Native lockfile versions 1, 2 and 3 are read without upgrading the project. Version 1 records nested dependencies; the reader normalizes them in memory.

npm-purifier builds for x86_64-linux, aarch64-linux and aarch64-darwin.

`npm-purifier.lock.json` holds only what `package-lock.json` cannot
supply. Per git dependency, keyed by its `resolved`, it holds the Nix hash
of the checkout, which npm does not record. For a hosted repository it
adds the archive URL and the URL to fetch the checkout from, which npm's
rules for the host decide. For a cloned repository it adds whether there
are submodules, the raw commit objects, and the URL and commit of each
submodule, which live in the repository itself. For a prepared dependency
it adds the dependency's own lockfile. The commit and the directory in the
repository come from `resolved`.

A flake can also build a project as an external build, without changing
the project's repository. The flake keeps `npm-purifier.lock.json` outside
the project and passes its path to the builder as `lockFile`. It can keep
its own copy of `package-lock.json` outside the project too, and pass it
as `packageLock`; the build installs from that copy in place of the one
in `src`. A project whose committed `package-lock.json` is missing, stale
or incomplete builds this way from its source as published.

`npm-purifier lock --lockfile <path> --tool-lockfile <path>` writes both
outside files and leaves the files in the project as they are. When the
outside `package-lock.json` does not exist yet, the lock run starts from
the one in the project. `NPM_PURIFIER_TOOL_LOCKFILE` does the same as
`--tool-lockfile`, and `npm-purifier update` takes both options too.

A flake that keeps only `npm-purifier.lock.json` outside, and the
`package-lock.json` of the project as it is, can still build a project
whose `package-lock.json` leaves out the URL or integrity of entries. The
lock run records them in the `completions` of the outside
`npm-purifier.lock.json`, keyed by their place in `package-lock.json`, and
the build installs from a copy of `package-lock.json` completed with
them.

## Examples

For day-to-day work on these projects, use the native-tool setup and
commands in [Quickstart](#quickstart) and [Development loop](#development-loop).
The Nix expressions below show optional sandboxed packaging of those
projects.

### Working on commander.js

[commander.js](https://github.com/tj/commander.js) is a command-line
library with a test suite. In a checkout of it, enter the shell, lock and
work offline as usual:

```zsh
git clone https://github.com/tj/commander.js
cd commander.js
nix shell 'github:nix-purifiers/npm-purifier#toolchain'
npm-purifier lock
npm ci
npm test
```

The native lock records commander.js dependencies; `npm-purifier.lock.json`
also pins the purifier implementation. From the same directory, this builds the package
and runs its tests in the sandbox, with no Nix file added to the checkout:

```zsh
nix build --impure --expr 'let
  bootstrap = builtins.getFlake "github:nix-purifiers/npm-purifier";
  pin = (builtins.fromJSON
    (builtins.readFile ./npm-purifier.lock.json)).implementation;
  purifier =
    (bootstrap.lib.purifier.implementationSource.resolve
      pin.source).flake;
  pkgs = import purifier.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ purifier.overlays.default ];
  };
  project = pkgs.npm-purifier.buildNpmProject {
    src = ./.;
    doCheck = true;
  };
in
project.packages.commander'
```

### Building http-server without changing it

[http-server](https://github.com/http-party/http-server) is a static file
server. Its `package-lock.json` leaves out the URL and integrity of many
entries, so this example keeps the lockfile of npm-purifier outside the
checkout, and the checkout stays as the authors published it:

```zsh
git clone https://github.com/http-party/http-server
cd http-server
nix shell 'github:nix-purifiers/npm-purifier#toolchain'
npm-purifier lock --lockfile ../http-server.lock.json
```

The lock run leaves the checkout as it is and records the missing URLs and
integrities in `../http-server.lock.json`. From the checkout, this builds
the server with that lockfile:

```zsh
nix build --impure --expr 'let
  bootstrap = builtins.getFlake "github:nix-purifiers/npm-purifier";
  pin = (builtins.fromJSON
    (builtins.readFile ../http-server.lock.json)).implementation;
  purifier =
    (bootstrap.lib.purifier.implementationSource.resolve
      pin.source).flake;
  pkgs = import purifier.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ purifier.overlays.default ];
  };
in
(pkgs.npm-purifier.buildNpmProject {
  src = ./.;
  lockFile = ../http-server.lock.json;
}).packages.http-server'
```

A flake of your own can do the same with http-server as an input that has
`flake = false`, passing the path of its own `npm-purifier.lock.json` as
`lockFile`.

The pinned CI http-server sample carries an explicit
[timeout-unit fix](tests/real-world/http-server/timeouts.patch). The same patch
applies to its tests and packaged application; all upstream assertions remain,
with additional checks for the API's milliseconds and the CLI's seconds.

## Browser assets for JVM applications

`buildNpmProject { webAssets."@scope/package" = "dist"; ...; }` publishes
the selected built directory as a WebJar. Each selected package exposes
`projections.maven` and `projections.ivy`; the project's `projections` combines
the selected WebJars. Existing npm projections remain available.

The directory is relative to that package as packed by npm, so its `files`
policy must include it. Select self-contained browser assets; this does not
bundle dependencies or turn Node-only code into browser code. Package roots,
parent traversal and `node_modules` cannot be selected. Only the selected
subtree is published; sibling private files and installed dependencies are
excluded. Scoped names map to Maven artifact IDs by dropping `@` and replacing
`/` with `__`; the group is `org.webjars.npm`. Maven/Ivy versions include an
immutable Nix identity; asset URLs retain the source package version. The
integration check builds a scoped package and resolves its WebJar with
ordinary offline Gradle.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

The Node.js of nixpkgs carries the patch to pacote, npm's fetcher, that
prepares git dependencies inside the sandbox. nixpkgs' `importNpmLock`
also fetches each package of a `package-lock.json` separately.
