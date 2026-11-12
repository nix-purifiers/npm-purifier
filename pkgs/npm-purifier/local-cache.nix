# SPDX-License-Identifier: MIT
# Fetch-only local adoption. No project runtime is a derivation input here.
{
  lib,
  pkgs,
  packageLock,
  lockFile,
  toolLockFile ? null,
}:
let
  lock = lib.npm-purifier.readLock {
    src = dirOf packageLock;
    packageLock = if toolLockFile == null then packageLock else toolLockFile;
    inherit lockFile;
  };
  # Cache all locked platform artifacts. The caller's actual native npm makes
  # platform/ABI decisions; a Nix helper's architecture must not filter them.
  checked = lib.purifier.checkLock lock;
  localLock = checked // {
    entries = map (
      entry:
      builtins.removeAttrs entry [
        "systems"
        "os"
        "cpu"
        "libc"
      ]
    ) checked.entries;
  };
  cache = pkgs.callPackage ../build-npm-project/cache.nix {
    lock = localLock;
    inherit (lib) purifier;
  };
in
pkgs.runCommand "npm-purifier-local-dependencies"
  {
    passAsFile = [ "environment" ];
    environment = cache.environment + ''
      export NPM_PURIFIER_LEGACY_BINDINGS=${pkgs.writeText "npm-local-archive-bindings.json" cache.legacyBindings}
    '';
  }
  ''
    mkdir -p "$out"
    ln -s ${cache.tree} "$out/cache"
    cp "$environmentPath" "$out/environment"
  ''
