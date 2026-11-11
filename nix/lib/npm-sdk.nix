# SPDX-License-Identifier: MIT
{ pkgs }:
let
  latestNpm = pkgs.stdenvNoCC.mkDerivation {
    pname = "npm-cli-fixture";
    version = "12.2.2";
    src = pkgs.fetchurl {
      url = "https://registry.npmjs.org/npm/-/npm-12.2.2.tgz";
      hash = "sha512-KglgbZyacf7jH+FHuNRqVuCzQi8VhI2a7J87Ix43FsPTuZoGWmIXXGdZtBUOA79vwL+IJREqURVzupA7PsQTcA==";
    };
    nativeBuildInputs = [ pkgs.nodejs ];
    dontBuild = true;
    installPhase = ''
      mkdir -p "$out/lib/node_modules/npm" "$out/bin"
      cp -R . "$out/lib/node_modules/npm/"
      patchShebangs "$out/lib/node_modules/npm"
      ln -s ../lib/node_modules/npm/bin/npm-cli.js "$out/bin/npm"
      ln -s ../lib/node_modules/npm/bin/npx-cli.js "$out/bin/npx"
    '';
  };
  npmSdk =
    pkgs.runCommand "nodejs-${pkgs.nodejs.version}-npm-12.2.2"
      {
        passthru.version = pkgs.nodejs.version;
      }
      ''
        mkdir -p "$out/bin" "$out/lib/node_modules"
        ln -s ${pkgs.nodejs}/bin/node "$out/bin/node"
        ln -s ${pkgs.nodejs}/include "$out/include"
        ln -s ${latestNpm}/lib/node_modules/npm "$out/lib/node_modules/npm"
        ln -s ${latestNpm}/bin/npm "$out/bin/npm"
        ln -s ${latestNpm}/bin/npx "$out/bin/npx"
      '';
in
npmSdk
