# SPDX-License-Identifier: MIT
{
  pkgs,
  scope,
  version ? "12.22.12",
}:
let
  nodejs = import ./node-fixture.nix {
    inherit pkgs;
    inherit version;
  };
  command = scope.npm-purifier.override {
    inherit nodejs;
    hostNode = pkgs.nodejs;
  };
  npm = scope.npm.override {
    inherit nodejs;
    npm-purifier = command;
  };
in
pkgs.buildEnv {
  name = "npm-node-${version}-tools";
  paths = [
    (pkgs.lib.lowPrio nodejs)
    npm
    command
  ];
  postBuild = ''ln -s ${nodejs} "$out/native-runtime"'';
}
