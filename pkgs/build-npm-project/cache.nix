# SPDX-License-Identifier: MIT
#
# Everything npm reads offline for one project, shared by the sandboxed
# build and the `npm` wrapper. It returns
#
#   tree          the content of npm's cache (`_cacache`): the locked
#                 tarballs, laid out by the shared purifier library, and
#                 the archives of git dependencies with their index entries
#   environment   shell commands that set up the environment npm runs in:
#                 the preparation of git dependencies and the git settings
#                 for cloned ones
#   needsGit      whether the install clones repositories with git
{
  lib,
  callPackage,
  symlinkJoin,
  stdenv,
  # What `tree` of the purifier library fetches the tarballs with and lays
  # them out with.
  runCommand,
  fetchurl,
  python3,
  nodejs,
  writeText,
  # The shared purifier library.
  purifier,
  # The lock in memory of the project (read-lock.nix).
  lock,
  # Fetchers that replace those of the purifier library.
  fetchers ? { },
  # Checkouts that replace the fetches of git dependencies (see git.nix).
  gitCheckouts ? { },
}:
let
  # The entries this system's install needs.
  entries = purifier.entriesFor stdenv.hostPlatform.system lock;

  tarballs = purifier.tree (
    {
      inherit runCommand fetchurl;
      name = "npm-purifier-tarballs";
      entries = builtins.filter (entry: !(entry ? git)) entries;
    }
    // fetchers
  );

  git = callPackage ./git.nix {
    git = lib.listToAttrs (
      map (entry: lib.nameValuePair entry.resolved entry) (builtins.filter (entry: entry ? git) entries)
    );
    inherit purifier fetchers;
    checkouts = gitCheckouts;
  };
  archiveUses = lib.concatMap (
    entry:
    map (url: {
      inherit url;
      inherit (entry) hash path;
    }) (lib.unique ([ entry.url ] ++ (entry.mirrors or [ ])))
  ) (builtins.filter (entry: !(entry ? git)) entries);
  tarballCatalog = writeText "npm-purifier-tarball-index.json" (
    builtins.toJSON (
      map (entry: {
        url = entry.url;
        integrity = entry.hash;
        path = toString (tarballs + "/${entry.path}");
      }) archiveUses
    )
  );
  registryMetadata =
    runCommand "npm-purifier-registry-metadata"
      {
        NPM_PURIFIER_NPM_MODULES = "${nodejs}/lib/node_modules/npm/node_modules";
      }
      ''
        ${nodejs}/bin/node ${./registry-metadata.cjs} \
          ${
            writeText "npm-purifier-registry-manifests.json" (builtins.toJSON (lock.registryMetadata or [ ]))
          } "$out" ${tarballCatalog} ${
            writeText "npm-purifier-registry-snapshots.json" (builtins.toJSON (lock.registrySnapshots or { }))
          }
      '';
in
{
  inherit (git) needsGit repositories;
  environment = git.environment + ''
    ${python3}/bin/python ${./seed-tarball-index.py} ${tarballCatalog} \
      "$npm_config_cache/_cacache" "$(${nodejs}/bin/npm config get registry)"
    ${python3}/bin/python ${./seed-tarball-index.py} ${registryMetadata}/catalog.json \
      "$npm_config_cache/_cacache" "$(${nodejs}/bin/npm config get registry)"
    if [ -d "$npm_config_cache/_cacache/index-v5" ] && [ ! -e "$npm_config_cache/index-v5" ] && [ ! -L "$npm_config_cache/index-v5" ]; then
      ln -s _cacache/index-v5 "$npm_config_cache/index-v5"
    fi
  '';
  legacyBindings = builtins.toJSON (
    lib.listToAttrs (
      map (entry: {
        name = entry.url;
        value = toString (tarballs + "/${entry.path}");
      }) archiveUses
    )
  );
  tree = symlinkJoin {
    name = "npm-purifier-cache";
    paths = [
      tarballs
      git.cache
      (registryMetadata + "/cache")
    ];
  };
}
