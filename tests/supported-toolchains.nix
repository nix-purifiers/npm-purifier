# SPDX-License-Identifier: MIT
# Exact upstream stable points checked against nodejs.org/dist on 2026-11-06.
# The separate npm point exercises npm's CLI independently of Node's release train.
{
  pkgs,
  buildNpmProject,
  scope,
}:
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
  points = {
    supported-node-22 = {
      node = import ./node-fixture.nix {
        inherit pkgs;
        version = "22.23.4";
      };
      npmVersion = "10.9.9";
    };
    supported-node-24 = {
      node = import ./node-fixture.nix {
        inherit pkgs;
        version = "24.22.2";
      };
      npmVersion = "11.19.1";
    };
    supported-node-26 = {
      node = import ./node-fixture.nix {
        inherit pkgs;
        version = "26.13.0";
      };
      npmVersion = "11.20.0";
    };
    latest-npm = {
      node = npmSdk;
      npmVersion = "12.2.2";
    };
  };
  make =
    name:
    { node, npmVersion }:
    let
      project = buildNpmProject {
        src = ./fixtures/legacy-node;
        inherit node;
        doCheck = true;
      };
      command = scope.npm-purifier.override {
        nodejs = node;
        hostNode = pkgs.nodejs;
      };
      npm = scope.npm.override {
        nodejs = node;
        npm-purifier = command;
      };
    in
    {
      ${name} =
        pkgs.runCommand "npm-${name}-runtime"
          {
            nativeBuildInputs = [
              node
              project.packages.legacy-npm-app
            ];
            passthru = {
              withSource =
                src:
                buildNpmProject {
                  inherit src node;
                  doCheck = true;
                };
              nodeVersion = node.version;
              inherit npmVersion;
              inherit (project) release;
              repository = project.packages.legacy-npm-app.projections.npm;
            };
          }
          ''
            test "$(node --version)" = v${node.version}
            test "$(npm --version)" = ${npmVersion}
            test "$(legacy-npm-app)" = "42 on v${node.version}"
            test ! -e ${project.packages.legacy-npm-app}/lib/node_modules/is-odd
            test "$(tar -xOf ${project.release}/legacy-npm-app.tgz package/built.txt)" = v${node.version}
            mkdir -p "$out"
            node --version > "$out/node-version"
            npm --version > "$out/npm-version"
          '';
      "${name}-tools" = pkgs.buildEnv {
        name = "npm-${name}-tools";
        paths = [
          (pkgs.lib.lowPrio node)
          npm
          command
        ];
      };
    };
in
pkgs.lib.concatMapAttrs make points
