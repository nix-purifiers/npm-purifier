# SPDX-License-Identifier: MIT
{
  callPackage,
  lib,
  implementationSource,
  ...
}:
let
  pkgs = callPackage ({ pkgs }: pkgs) { };
  implementation = callPackage lib.purifier.implementation {
    source = implementationSource;
    repository = "nix-purifiers/npm-purifier";
    tool = "npm-purifier";
    nativeCommand = "npm";
    checksum = "npm";
    lockVersions = [ 3 ];
  };
  implementationForSdk =
    node:
    let
      selected = builtins.tryEval (import ../nix/lib/sdk-configuration.nix { inherit pkgs node; });
    in
    if selected.success then
      implementation.withConfiguration selected.value
    else
      implementation.withoutIdentity;
  npm-purifier = callPackage ./npm-purifier {
    inherit (lib) purifier;
    inherit implementationForSdk;
  };

in
{
  # The builder of npm projects (nix/lib/build-npm-project.nix), a package
  # for callPackage in this scope. It reads lockfiles with the library of
  # this flake.
  buildNpmProject = callPackage (import ../nix/lib/build-npm-project.nix { inherit lib; }) {
    inherit implementation implementationForSdk;
  };
  # The command `npm-purifier`: lock, update, prefetch and publish.
  inherit npm-purifier;
  # npm that runs offline on what `npm-purifier prefetch` keeps, in a
  # project with a package-lock.json.
  npm = callPackage ./npm { inherit npm-purifier implementationForSdk; };
}
