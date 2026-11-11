# SPDX-License-Identifier: MIT
{

  description = "npm-purifier: sandboxed Nix builds of npm projects from their package-lock.json";

  inputs = {
    caisson.url = "github:nix-caisson/caisson";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # The library comes from the nixpkgs.lib mirror. The package sets
    # take nixpkgs.
    nixpkgs-lib.url = "github:nix-community/nixpkgs.lib";
    flake-parts.url = "github:hercules-ci/flake-parts";
    # The shared library of the nix-purifiers, which fetches the locked
    # downloads and lays them out.
    purifier.url = "github:nix-purifiers/purifier";
  };

  outputs =
    inputs@{ caisson, purifier, ... }:
    let
      lib = caisson.lib.caisson.mkLib {
        inherit (caisson.lib.caisson.pins.flake inputs) sources root;
        name = "npm-purifier";
        systems = [
          "x86_64-linux"
          "aarch64-linux"
          "aarch64-darwin"
        ];
        projects = {
          inherit caisson purifier;
        };

        configs = lib: lib.caisson.mkModules ./configs;

        pkgSets = lib: lib.caisson.nixpkgs.mkConfigurations { };

        libOverlays = lib: lib.caisson.mkLibOverlays ./lib-overlays;
        pkgOverlays = lib: lib.caisson.mkPkgOverlays ./pkg-overlays;
      };
      base = lib.caisson.flake-parts.mkTopConfiguration { };
    in
    base
    // {
      lib = base.lib // {
        npm-purifier = base.lib.npm-purifier // {
          # Only this immutable source interprets these typed SDK recipes.
          implementationPackage =
            {
              system,
              entry,
              configuration,
            }:
            let
              pkgs = import inputs.nixpkgs {
                inherit system;
                overlays = [ base.overlays.default ];
              };
              node = import ./nix/lib/sdk-from-configuration.nix { inherit pkgs configuration; };
              command = pkgs.npm-purifier.npm-purifier.override {
                nodejs = node;
                hostNode = pkgs.nodejs;
              };
            in
            if entry == "npm-purifier" then
              command
            else if entry == "npm" then
              pkgs.npm-purifier.npm.override {
                nodejs = node;
                npm-purifier = command;
              }
            else
              throw "npm-purifier: unknown configured implementation entrypoint";
        };
      };
    };

}
