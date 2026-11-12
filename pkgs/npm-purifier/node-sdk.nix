# SPDX-License-Identifier: MIT
# Pinned upstream binaries for exact historical and current compatibility points.
{ pkgs, version }:
let
  archives = import ./node-sdk-sources.nix;
  archive = archives.${version}.${pkgs.stdenv.hostPlatform.system};
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "nodejs-legacy-fixture";
  inherit version;
  src = pkgs.fetchurl {
    url = "https://nodejs.org/${
      if pkgs.lib.hasInfix "-rc." version then "download/rc" else "dist"
    }/v${version}/node-v${version}-${
      if pkgs.stdenv.hostPlatform.isDarwin then "darwin" else "linux"
    }-${archive.arch}.tar.xz";
    inherit (archive) sha256;
  };
  nativeBuildInputs =
    pkgs.lib.optional pkgs.stdenv.hostPlatform.isLinux pkgs.patchelf
    ++ pkgs.lib.optional pkgs.stdenv.hostPlatform.isDarwin pkgs.makeBinaryWrapper;
  dontConfigure = true;
  dontBuild = true;
  dontStrip = true;
  # Sorting this historical ELF's program headers makes it segfault before
  # main. Keep its order when installing the Nix loader and runtime libraries.
  dontPatchELF = true;
  installPhase = ''
    mkdir -p "$out"
    cp -r bin include lib share "$out/"
    ${pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
      patchelf --no-sort \
        --set-interpreter ${pkgs.stdenv.cc.bintools.dynamicLinker} \
        --set-rpath ${pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ]} \
        "$out/bin/node"
    ''}
    ${pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isDarwin ''
      # Keep the upstream runtime while declaring its OpenSSL configuration.
      # A compiled wrapper remains usable as npm's shebang interpreter on Darwin.
      wrapProgram "$out/bin/node" --set-default OPENSSL_CONF ${pkgs.writeText "node-fixture-openssl.cnf" ""}
    ''}"$out/bin/node" --version
    export PATH="$out/bin:$PATH"
    patchShebangs "$out/lib/node_modules/npm"
  '';
}
