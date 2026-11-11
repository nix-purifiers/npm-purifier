# SPDX-License-Identifier: MIT
# Only source-owned recipes are portable. Matching the realized derivation
# identity rejects a patched/custom package that merely keeps a version label.
{ pkgs, node }:
let
  sources = import ./node-sdk-sources.nix;
  version = node.version or "";
  available =
    builtins.hasAttr version sources
    && builtins.hasAttr pkgs.stdenv.hostPlatform.system sources.${version};
  upstream = if available then import ./node-sdk.nix { inherit pkgs version; } else null;
  npm = import ./npm-sdk.nix { inherit pkgs; };
  selected =
    if builtins.toString node == builtins.toString pkgs.nodejs then
      null
    else if upstream != null && builtins.toString upstream == builtins.toString node then
      {
        type = "upstream-node";
        version = node.version;
      }
    else if builtins.toString node == builtins.toString npm then
      {
        type = "nixpkgs-node-npm";
        version = "12.2.2";
      }
    else
      throw "npm-purifier: custom SDK has no portable implementation recipe; use this source's exact SDK packages";
in
if selected == null then
  null
else
  {
    version = 1;
    node = selected;
  }
