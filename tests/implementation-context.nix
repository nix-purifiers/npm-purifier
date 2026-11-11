# SPDX-License-Identifier: MIT
{
  pkgs,
  purifier,
  npm-purifier,
}:
let
  lib = pkgs.lib // {
    inherit purifier npm-purifier;
  };
  source = {
    rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    narHash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };
  make =
    host:
    import ../pkgs {
      inherit lib;
      callPackage = host.callPackage;
      implementationSource = source;
      implementationNixpkgs = pkgs.path;
    };
  baseline = make pkgs;
  patchedNodePkgs = pkgs.extend (
    final: prev: {
      nodejs = prev.nodejs.overrideAttrs (old: {
        pname = old.pname + "-host-context-probe";
      });
    }
  );
  patchedPythonPkgs = pkgs.extend (
    final: prev: {
      python3 = prev.python3.overrideAttrs (old: {
        pname = old.pname + "-host-context-probe";
      });
    }
  );
  foreignPathPkgs = pkgs.extend (_: _: { path = ./fixtures; });
  patched = make patchedNodePkgs;
  python = make patchedPythonPkgs;
  foreign = make foreignPathPkgs;
  node = import ../nix/lib/node-sdk.nix {
    inherit pkgs;
    version = if pkgs.stdenv.hostPlatform.isDarwin then "24.22.2" else "8.17.0";
  };
  known = make (pkgs.extend (_: _: { nodejs = node; }));
  coreutils = pkgs.coreutils.overrideAttrs (old: {
    pname = old.pname + "-host-context-probe";
  });
  customCli = baseline.npm-purifier.override { inherit coreutils; };
  customNative = baseline.npm.override {
    inherit coreutils;
    npm-purifier = customCli;
  };
in
assert baseline.npm-purifier.implementation.source.rev == source.rev;
assert baseline.npm.implementation == baseline.npm-purifier.implementation;
assert patched.npm-purifier.implementation.source == null;
assert patched.npm.implementation.source == null;
assert python.npm-purifier.implementation.source == null;
assert python.npm.implementation.source == null;
assert foreign.npm-purifier.implementation.source == null;
assert foreign.npm.implementation.source == null;
assert known.npm-purifier.implementation.source.rev == source.rev;
assert known.npm.implementation == known.npm-purifier.implementation;
assert known.npm.implementation.configuration.node.version == node.version;
assert customCli.implementation.source == null;
assert customNative.implementation.source == null;
pkgs.runCommand "npm-implementation-host-context" { } ''
  touch "$out"
''
