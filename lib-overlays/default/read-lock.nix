# SPDX-License-Identifier: MIT
#
# readLock: the lock in memory of an npm project (CONTRACT.md of the
# purifier library). It reads, at evaluation time, the package-lock.json
# (lockfileVersion 1, 2 or 3) of the project in `src` and, when that needs
# it, the npm-purifier.lock.json that `npm-purifier lock` writes. That file
# records the git dependencies. When it lies outside `src`, it also holds
# `completions`: the URL and integrity of the entries of package-lock.json
# that lack them, by their key. The flake publishes the reader as
# `lib.npm-purifier.readLock`:
#
#   lib.npm-purifier.readLock { src = ./.; }
#   # =>
#   {
#     purifier = "npm-purifier";
#     entries  = [ ... ];  # download entries of the purifier library
#     outputs  = { ... };  # the project's own packages
#     problems = [ ... ];  # why the lockfiles cannot be used
#   }
#
# `entries` holds one entry per tarball the install needs, and one per
# git dependency:
#
#   - A tarball entry is { path, url, mirrors, hash }. `path` is where the
#     tarball's content lies in npm's cache (_cacache/<path>), `url` is the
#     lock's `resolved` and `hash` the lock's SRI `integrity`. npm looks a
#     registry tarball up in its cache by integrity, so a cache holding
#     only the content files, at the paths cacache derives from each
#     integrity, serves `npm ci --offline` without index entries. An entry
#     with npm's `os`, `cpu` or `libc` filters keeps them, and lists in
#     `systems` the Nix systems they admit, as npm leaves packages for
#     other platforms out of the install.
#   - A git entry is { path, git, hash }, which the purifier library
#     fetches, with what git.nix needs to serve the dependency to npm:
#     `resolved`, `subdir` (the directory in the repository), `repository`
#     (the URL npm clones), `submodules` (the submodule repositories),
#     `archiveUrl` (for a dependency npm downloads as an archive), and
#     `packageLock` and `injectPackageLock` (for one npm prepares).
#
# The tarballs and git dependencies that prepared git dependencies install
# are among the entries.
#
# `outputs` holds the project's own packages (the root, its workspaces
# and the local directories it depends on), by package name, as
# { name, version, dir, bin }. `dir` is the package's directory relative
# to the project root ("" for the root) and `bin` its commands, as command
# name to file. A root that declares workspaces is one only when it has
# commands.
#
# `problems` is empty for usable lockfiles. Otherwise it holds a message
# for each problem found, naming the command that fixes it, and the
# builder passes the lock to `checkLock` of the purifier library, which
# fails evaluation with them.
{ lib }:
{
  # The source tree. It holds the project.
  src,
  providedNames ? [ ],
  providedVersions ? [ ],
  # The directory of the project inside `src`.
  projectDir ? "",
  # npm's lockfile. An external build can keep its own copy outside the
  # repository, which then takes the place of the one in `src`.
  packageLock ?
    let
      root = src + lib.optionalString (projectDir != "") "/${projectDir}";
    in
    root
    + (
      if builtins.pathExists (root + "/npm-shrinkwrap.json") then
        "/npm-shrinkwrap.json"
      else
        "/package-lock.json"
    ),
  # npm-purifier.lock.json records the implementation and any git or
  # incomplete download entries. A flake that
  # packages a project without changing it keeps the file outside `src`.
  lockFile ? src + lib.optionalString (projectDir != "") "/${projectDir}" + "/npm-purifier.lock.json",
}:
let
  inherit (lib) purifier;

  # The systems an entry with npm's platform filters is checked against:
  # those npm-purifier builds for, which are those `admits` of the
  # purifier library knows.
  systems = [
    "x86_64-linux"
    "aarch64-linux"
    "aarch64-darwin"
  ];

  # The steps below return { value } or { problem }.
  problemOf = message: { problem = "npm-purifier: ${message}"; };

  # Reads a lockfile. Nix cannot catch a JSON parse error, and its message
  # does not name the file, so the reader refuses a file that cannot be
  # JSON first: one with merge conflict markers, which `npm install`
  # resolves in package-lock.json, or one that does not start an object.
  # The checks use no regular expression that spans the whole text: Nix
  # matches `.*` recursively, character by character, and a match over a
  # lockfile of a few hundred kilobytes overflows the evaluator's stack.
  readLockFile =
    file: fix:
    let
      text = builtins.readFile file;
    in
    if builtins.length (builtins.split "\n<<<<<<< " ("\n" + text)) > 1 then
      problemOf "${toString file} has merge conflict markers; ${fix}."
    else if !(lib.hasPrefix "{" (lib.trim (builtins.substring 0 4096 text))) then
      problemOf "${toString file} is not a JSON lockfile; ${fix}."
    else
      # Nix cannot catch a parse error of the rest of the file, so it
      # fails evaluation with this context.
      {
        value = builtins.addErrorContext "while reading ${toString file}, which is not valid JSON; ${fix}" (
          builtins.fromJSON text
        );
      };

  # npm 5/6 records its installed tree recursively rather than as paths.
  # Normalize it in memory only; the selected npm still reads its original
  # lockfile and performs its own native resolution/install.
  legacyPackages =
    prefix: dependencies:
    lib.concatMap (
      name:
      let
        entry = dependencies.${name};
        key = prefix + "node_modules/" + name;
        normalized =
          entry
          // {
            inherit name;
            inBundle = entry.bundled or false;
          }
          // lib.optionalAttrs (
            !(entry ? resolved)
            && (lib.hasPrefix "file:" (entry.version or "") || lib.hasPrefix "git+" (entry.version or ""))
          ) { resolved = entry.version; };
      in
      [ (lib.nameValuePair key normalized) ] ++ legacyPackages (key + "/") (entry.dependencies or { })
    ) (builtins.attrNames dependencies);

  # The `packages` of a package-lock.json.
  packagesOf =
    name: read:
    let
      version = read.value.lockfileVersion or 1;
    in
    if read ? problem then
      read
    else if
      builtins.elem version [
        2
        3
      ]
    then
      { value = read.value.packages; }
    else if version == 1 then
      { value = lib.listToAttrs (legacyPackages "" (read.value.dependencies or { })); }
    else
      problemOf "${name} is unsupported lockfileVersion ${toString version}; this reader supports versions 1, 2 and 3.";

  root = packagesOf (toString packageLock) (
    readLockFile packageLock "run `npm install` to write it again"
  );
  manifest = src + lib.optionalString (projectDir != "") "/${projectDir}" + "/package.json";
  packages =
    (root.value or { })
    // lib.optionalAttrs (
      !(root ? problem)
      && ((lib.importJSON packageLock).lockfileVersion or 1) == 1
      && builtins.pathExists manifest
    ) { "" = lib.importJSON manifest; };

  # A key under node_modules/ is an installed package; any other key is a
  # package of the project itself ("" for the root, a directory for a
  # workspace or a local dependency).
  isInstalled = key: lib.hasPrefix "node_modules/" key || lib.hasInfix "/node_modules/" key;

  isGit = resolved: lib.hasPrefix "git+" resolved;

  platformFilters = [
    "os"
    "cpu"
    "libc"
  ];

  # A tarball entry, from an installed package that npm downloads.
  remote =
    name: key: entry:
    let
      resolved = entry.resolved;
      isHttp = lib.hasPrefix "https://" resolved || lib.hasPrefix "http://" resolved;
    in
    if !(entry ? resolved) then
      problemOf "${key} has no resolved URL in ${name}; run `npm-purifier lock` to record it."
    else if !isHttp then
      problemOf "${key} in ${name} comes from ${resolved}, which is neither a tarball URL, a git repository nor a path."
    else if !(entry ? integrity) then
      problemOf "${key} (${resolved}) has no integrity in ${name}; run `npm-purifier lock` to record one."
    else
      let
        # An integrity may list several hashes; the strongest comes first
        # in what npm writes.
        sri = builtins.head (lib.splitString " " entry.integrity);
        algorithm = builtins.head (lib.splitString "-" sri);
        hex = builtins.convertHash {
          hash = sri;
          toHashFormat = "base16";
        };
        filters = lib.getAttrs (builtins.filter (f: entry ? ${f}) platformFilters) entry;
      in
      {
        value = {
          path = "content-v2/${algorithm}/${builtins.substring 0 2 hex}/${builtins.substring 2 2 hex}/${builtins.substring 4 (-1) hex}";
          url = resolved;
          # npm knows one URL per tarball.
          mirrors = [ ];
          hash = sri;
        }
        // filters
        // lib.optionalAttrs (filters != { }) {
          systems = builtins.filter (purifier.admits {
            os = entry.os or null;
            cpu = entry.cpu or null;
            libc = entry.libc or null;
          }) systems;
        };
      };

  # Installed packages that come from elsewhere: not links to the
  # project's own directories, not bundled inside another tarball, and not
  # tarballs inside the project (`file:` specs, which npm reads from the
  # source).
  installed =
    ps:
    lib.filterAttrs (
      key: entry:
      isInstalled key
      && !(
        let
          name = entry.name or (lib.last (lib.splitString "node_modules/" key));
        in
        builtins.elem name providedNames
        || builtins.any (
          item: item.name == name && item.version == (entry.version or null)
        ) providedVersions
      )
      && !(entry.link or false)
      && !(entry.inBundle or false)
      && !((entry.optional or false) && !(entry ? version) && !(entry ? resolved) && !(entry ? integrity))
      && !lib.hasPrefix "file:" (entry.resolved or "")
    ) ps;

  # `completed` gives the `resolved` and `integrity` of incomplete entries,
  # by their key.
  tarballsOf =
    name: completed: ps:
    lib.mapAttrsToList (key: entry: remote name key (entry // completed.${key} or { })) (
      lib.filterAttrs (_: entry: !isGit (entry.resolved or "")) (installed ps)
    );

  # The installed registry packages without a URL or an integrity. npm
  # fills them in from the registry at install time, which a build cannot.
  incomplete = lib.filterAttrs (
    _: entry: !isGit (entry.resolved or "") && !(entry ? resolved && entry ? integrity)
  ) (installed packages);
  gitOf =
    ps:
    lib.mapAttrsToList (_: entry: entry.resolved) (
      lib.filterAttrs (_: entry: isGit (entry.resolved or "")) (installed ps)
    );

  # The lockfile format this reader reads.
  formatVersion = 3;

  lockName = toString lockFile;

  # npm-purifier.lock.json holds the SRI hash of its own text, with the
  # value of its top-level `hash` field left empty. A file whose hash does
  # not match was changed after `npm-purifier lock` wrote it.
  hashOf =
    stored:
    let
      text = builtins.readFile lockFile;
      blank = builtins.replaceStrings [ "\"hash\": \"${stored}\"" ] [ "\"hash\": \"\"" ] text;
    in
    builtins.convertHash {
      hash = builtins.hashString "sha256" blank;
      hashAlgo = "sha256";
      toHashFormat = "sri";
    };

  # npm-purifier.lock.json, read when package-lock.json needs it. Without
  # the file, an incomplete entry names its own problem.
  hasGit = gitOf packages != [ ];
  hasPublished = builtins.any (entry: entry.hasShrinkwrap or false) (
    builtins.attrValues (installed packages)
  );
  purifierLock =
    let
      read = readLockFile lockFile "run `npm-purifier lock` to write it again";
      stored = read.value.hash or "";
    in
    if !hasGit && !hasPublished && incomplete == { } && !builtins.pathExists lockFile then
      { value = { }; }
    else if !builtins.pathExists lockFile then
      if hasGit || hasPublished then
        problemOf "${toString packageLock} has git dependencies or published shrinkwraps, and ${lockName} does not exist; run `npm-purifier lock`."
      else
        { value = { }; }
    else if read ? problem then
      read
    else if (read.value.version or null) != formatVersion then
      problemOf "${lockName} is not of format version ${toString formatVersion}; run `npm-purifier lock` to write it again."
    else if hashOf stored != stored then
      problemOf "${lockName} was changed after `npm-purifier lock` wrote it: its hash does not match its content; run `npm-purifier lock` to write it again."
    else if (read.value.packageLockSha256 or null) != builtins.hashFile "sha256" packageLock then
      problemOf "${lockName} was made for another package-lock.json; run `npm-purifier lock`."
    else
      { inherit (read) value; };
  git = purifierLock.value.git or { };
  completions = purifierLock.value.completions or { };
  published = purifierLock.value.published or { };
  registrySnapshots = purifierLock.value.registry or { };
  registryProbes = lib.listToAttrs (
    lib.concatMap (
      document:
      map (
        manifest:
        lib.nameValuePair "node_modules/${manifest.name}@${manifest.version}" (
          manifest
          // {
            resolved = manifest.dist.tarball;
            integrity = manifest.dist.integrity;
            hasShrinkwrap = manifest._hasShrinkwrap or false;
          }
        )
      ) (builtins.attrValues document.versions)
    ) (builtins.attrValues registrySnapshots)
  );

  # A git dependency as git.nix takes it: the entry of the purifier
  # lockfile, with what its `resolved` tells. npm writes `resolved` as
  # git+<URL>#<commit> and, for a directory in the repository,
  # ::path:<directory> after the commit. A repository npm clones comes
  # from the URL itself, and its library entry asks for a .git directory,
  # made from the checkout and the recorded commit object.
  gitEntry =
    resolved:
    let
      entry = git.${resolved};
      fragment = lib.last (lib.splitString "#" resolved);
      parts = lib.splitString "::path:" fragment;
      rev = builtins.head parts;
      subdir = if builtins.length parts > 1 then lib.last parts else "";
      cloneUrl = lib.removePrefix "git+" (builtins.head (lib.splitString "#" resolved));
      archived = entry ? archive;
    in
    if !(git ? ${resolved}) then
      problemOf "${lockName} has no entry for ${resolved}; run `npm-purifier lock`."
    else
      {
        value = {
          path = "git/${rev}" + lib.optionalString (subdir != "") "/${subdir}";
          git = {
            url = if archived then entry.url else cloneUrl;
            inherit rev;
            submodules = entry.submodules or false;
            leaveDotGit = !archived;
            commitObject = if archived then null else entry.commitObject;
          };
          inherit (entry) hash;
          inherit resolved subdir;
          repository = cloneUrl;
          submodules = entry.submoduleRepositories or [ ];
        }
        // lib.optionalAttrs archived { archiveUrl = entry.archive; }
        // lib.getAttrs (builtins.filter (f: entry ? ${f}) [
          "packageLock"
          "injectPackageLock"
        ]) entry;
      };

  # The lockfiles npm installs to prepare git dependencies.
  prepared = lib.mapAttrsToList (resolved: entry: {
    name = "the lockfile of ${resolved}";
    read = packagesOf "the lockfile of ${resolved}" { value = entry.packageLock; };
    completed = { };
  }) (lib.filterAttrs (_: entry: entry ? packageLock) git);

  packageSets = [
    {
      name = toString packageLock;
      read = root;
      completed = completions;
    }
  ]
  ++ lib.optional (registryProbes != { }) {
    name = "recorded native registry probes";
    read = {
      value = registryProbes;
    };
    completed = { };
    allPlatforms = true;
  }
  ++ prepared
  ++ lib.mapAttrsToList (url: entry: {
    name = "published npm-shrinkwrap.json from ${url}";
    read = packagesOf url { value = entry.packageLock; };
    completed = { };
    allPlatforms = true;
  }) published;

  missingPublished = lib.concatMap (
    set:
    lib.mapAttrsToList
      (
        _: entry:
        problemOf "${entry.resolved} declares a published shrinkwrap missing from ${lockName}; run `npm-purifier lock`."
      )
      (
        lib.filterAttrs (
          _: entry: (entry.hasShrinkwrap or false) && entry ? resolved && !(published ? ${entry.resolved})
        ) (installed (set.read.value or { }))
      )
  ) packageSets;

  tarballs = lib.concatMap (
    set:
    # npm may unpack optional foreign-platform packages from a published
    # shrinkwrap even though it omits them from a regular consumer lock.
    # Keep their archives available and let the selected npm make that choice.
    tarballsOf set.name set.completed (
      if set.allPlatforms or false then
        lib.mapAttrs (_: entry: builtins.removeAttrs entry platformFilters) (set.read.value or { })
      else
        set.read.value or { }
    )
  ) packageSets;
  # With no usable npm-purifier.lock.json, every git dependency would
  # repeat its problem.
  gitDependencies =
    if purifierLock ? problem then
      [ ]
    else
      map gitEntry (lib.unique (lib.concatMap (set: gitOf (set.read.value or { })) packageSets));

  problemsOf = results: map (r: r.problem) (builtins.filter (r: r ? problem) results);
  valuesOf = results: map (r: r.value) (builtins.filter (r: r ? value) results);

  # Content-addressed archives may occur in several locks, with different
  # platform filters or URLs. Cache availability is the union of those uses.
  uniqueTarballs = lib.foldl' (
    collected: entry:
    let
      previous = collected.${entry.path} or null;
      merged =
        if previous == null then
          entry
        else
          (builtins.removeAttrs previous (platformFilters ++ [ "systems" ]))
          // lib.optionalAttrs (previous ? systems && entry ? systems) {
            systems = lib.unique (previous.systems ++ entry.systems);
          }
          // {
            mirrors = lib.unique (
              (previous.mirrors or [ ])
              ++ (entry.mirrors or [ ])
              ++ lib.optional (entry.url != previous.url) entry.url
            );
          };
    in
    collected // { ${entry.path} = merged; }
  ) { } (valuesOf tarballs);

  binOf =
    entry:
    let
      bin = entry.bin or { };
    in
    if builtins.isString bin then { ${lib.last (lib.splitString "/" entry.name)} = bin; } else bin;

  # The project's own packages: the root, the workspaces and the local
  # directories the project depends on. A root that declares workspaces
  # and has no commands only coordinates the workspaces, and stays out.
  own = lib.filterAttrs (
    key: entry:
    !isInstalled key
    && !lib.hasPrefix "/" key
    && entry ? name
    && !(key == "" && entry ? workspaces && binOf entry == { })
  ) packages;
in
{
  purifier = "npm-purifier";
  inherit registrySnapshots;
  implementation = purifierLock.value.implementation or null;
  # The same tarball can be installed at several places in the tree; the
  # cache holds it once.
  entries = builtins.attrValues uniqueTarballs ++ valuesOf gitDependencies;
  # npm ci can consult packuments while rebuilding workspace peer contexts.
  # Supply precisely the manifests already described by these native locks;
  # Additional versions come only from recorded native resolver probes.
  registryMetadata = lib.concatMap (
    set:
    let
      completedPackages = lib.mapAttrs (key: entry: entry // (set.completed.${key} or { })) (
        set.read.value or { }
      );
    in
    lib.mapAttrsToList
      (
        key: raw:
        let
          entry = raw // (set.completed.${key} or { });
          name = entry.name or (lib.last (lib.splitString "node_modules/" key));
        in
        builtins.removeAttrs entry [
          "resolved"
          "integrity"
          "dev"
          "optional"
          "devOptional"
          "peer"
          "inBundle"
          "link"
          "hasShrinkwrap"
          "requires"
        ]
        // {
          inherit name;
          _hasShrinkwrap = entry.hasShrinkwrap or false;
          dist = {
            tarball = entry.resolved;
          }
          // lib.optionalAttrs (entry ? integrity) { integrity = entry.integrity; };
        }
        // lib.optionalAttrs (entry ? requires || entry ? dependencies) {
          dependencies = lib.mapAttrs (
            _: value: if builtins.isAttrs value then value.version or "*" else value
          ) (entry.requires or entry.dependencies);
        }
      )
      (
        lib.filterAttrs (
          _: entry:
          entry ? version
          && builtins.isString (entry.resolved or null)
          && (lib.hasPrefix "https://" entry.resolved || lib.hasPrefix "http://" entry.resolved)
        ) (installed completedPackages)
      )
  ) packageSets;
  outputs = lib.listToAttrs (
    lib.mapAttrsToList (
      key: entry:
      lib.nameValuePair entry.name {
        inherit (entry) name;
        version = entry.version or "0.0.0";
        dir = key;
        bin = binOf entry;
      }
    ) own
  );
  problems = problemsOf (
    map (set: set.read) packageSets
    ++ [ purifierLock ]
    ++ tarballs
    ++ gitDependencies
    ++ missingPublished
  );
}
