# SPDX-License-Identifier: MIT
{
  callPackage,
  lib,
  implementationSource,
  implementationNixpkgs,
  ...
}:
let
  pkgs = callPackage ({ pkgs }: pkgs) { };
  canonicalPkgs = import implementationNixpkgs { system = pkgs.stdenv.hostPlatform.system; };
  canonicalContext =
    builtins.toString pkgs.path == builtins.toString implementationNixpkgs
    && builtins.all (name: builtins.toString pkgs.${name} == builtins.toString canonicalPkgs.${name}) [
      "coreutils"
      "python3"
      "git"
      "nix-prefetch-git"
      "stdenv"
      "stdenvNoCC"
      "runtimeShell"
    ];
  implementation = callPackage lib.purifier.implementation {
    source = implementationSource // {
      dirty = (implementationSource.dirty or false) || !canonicalContext;
    };
    repository = "nix-purifiers/npm-purifier";
    tool = "npm-purifier";
    nativeCommand = "npm";
    checksum = "npm";
    lockVersions = [ 3 ];
  };
  implementationRuntimeMatches =
    actual:
    builtins.all (name: builtins.toString actual.${name} == builtins.toString canonicalPkgs.${name}) (
      builtins.attrNames actual
    );
  implementationForSdk =
    node:
    let
      selected = builtins.tryEval (
        import ../nix/lib/sdk-configuration.nix {
          pkgs = canonicalPkgs;
          inherit node;
        }
      );
    in
    if selected.success then
      implementation.withConfiguration selected.value
    else
      implementation.withoutIdentity;
  npm-purifier = callPackage ./npm-purifier {
    inherit (lib) purifier;
    inherit implementationForSdk implementationRuntimeMatches;
    implementationHostNode = canonicalPkgs.nodejs;
  };

in
{
  # The builder of npm projects (nix/lib/build-npm-project.nix), a package
  # for callPackage in this scope. It reads lockfiles with the library of
  # this flake.
  buildNpmProject = callPackage (import ../nix/lib/build-npm-project.nix { inherit lib; }) {
    inherit implementation implementationForSdk;
    implementationPkgs = canonicalPkgs;
    hostNodejs = canonicalPkgs.nodejs;
  };
  # The command `npm-purifier`: lock, update, prefetch and publish.
  inherit npm-purifier;
  # npm that runs offline on what `npm-purifier prefetch` keeps, in a
  # project with a package-lock.json.
  npm = callPackage ./npm { inherit npm-purifier implementationForSdk implementationRuntimeMatches; };
}
