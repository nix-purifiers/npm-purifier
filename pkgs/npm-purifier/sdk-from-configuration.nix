# SPDX-License-Identifier: MIT
{ pkgs, configuration }:
let
  valid =
    builtins.isAttrs configuration
    &&
      builtins.attrNames configuration == [
        "node"
        "version"
      ]
    && builtins.isInt configuration.version
    && configuration.version == 1
    && builtins.isAttrs configuration.node;
  recipe = configuration.node;
in
assert pkgs.lib.assertMsg valid "npm-purifier: invalid implementation SDK configuration";
if
  builtins.attrNames recipe == [
    "type"
    "version"
  ]
  && recipe.type == "upstream-node"
  && builtins.isString recipe.version
then
  assert pkgs.lib.assertMsg (
    builtins.hasAttr recipe.version (import ./node-sdk-sources.nix)
    &&
      builtins.hasAttr pkgs.stdenv.hostPlatform.system
        (import ./node-sdk-sources.nix).${recipe.version}
  ) "npm-purifier: pinned SDK recipe is unavailable on this platform";
  import ./node-sdk.nix {
    inherit pkgs;
    inherit (recipe) version;
  }
else if
  recipe == {
    type = "nixpkgs-node-npm";
    version = "12.2.2";
  }
then
  import ./npm-sdk.nix { inherit pkgs; }
else
  throw "npm-purifier: this source cannot reproduce the pinned SDK configuration"
