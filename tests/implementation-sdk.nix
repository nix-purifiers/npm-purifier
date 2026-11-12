# SPDX-License-Identifier: MIT
{ pkgs, scope }:
let
  node = import ../pkgs/npm-purifier/node-sdk.nix {
    inherit pkgs;
    version = if pkgs.stdenv.hostPlatform.isDarwin then "24.22.2" else "8.17.0";
  };
  command = scope.npm-purifier.override {
    nodejs = node;
    hostNode = pkgs.nodejs;
  };
  native = scope.npm.override {
    nodejs = node;
    npm-purifier = command;
  };
  expected = {
    version = 1;
    node = {
      type = "upstream-node";
      version = node.version;
    };
  };
  # Retaining a version label does not make a patched SDK the original recipe.
  patched = node.overrideAttrs (old: {
    pname = old.pname + "-custom";
  });
  customHost = scope.npm-purifier.override {
    nodejs = node;
    hostNode = pkgs.nodejs.overrideAttrs (old: {
      pname = old.pname + "-custom-host";
    });
  };
  invalid = [
    null
    { }
    {
      version = 1;
      node = [ ];
    }
    {
      version = true;
      node = expected.node;
    }
    {
      version = 1.0;
      node = expected.node;
    }
    (expected // { unexpected = true; })
    {
      version = 1;
      node = expected.node // {
        executable = "/tmp/node";
      };
    }
    {
      version = 1;
      node = {
        type = "upstream-node";
        version = "99.0.0";
      };
    }
    {
      version = 1;
      node = {
        type = "nixpkgs-node-npm";
        version = "99.0.0";
      };
    }
  ];
  custom = scope.npm-purifier.override {
    nodejs = patched;
    hostNode = pkgs.nodejs;
  };
in
assert command.implementation.configuration == expected;
assert native.implementation.configuration == expected;
assert custom.implementation.source == null;
assert customHost.implementation.source == null;
assert
  (scope.npm.override {
    nodejs = node;
    npm-purifier = customHost;
  }).implementation.source == null;
assert !(builtins.tryEval ((scope.npm.override { nodejs = patched; }).drvPath)).success;
assert
  (scope.npm.override {
    nodejs = patched;
    npm-purifier = custom;
  }).implementation.source == null;
assert builtins.all (
  configuration:
  !(builtins.tryEval (
    builtins.toString (
      import ../pkgs/npm-purifier/sdk-from-configuration.nix { inherit pkgs configuration; }
    )
  )).success
) invalid;
assert !(builtins.tryEval ((scope.npm.override { nodejs = node; }).drvPath)).success;
pkgs.runCommand "npm-implementation-sdk-recipe"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.nodejs
    ];
  }
  ''
    python - ${command}/share/purifier/implementation.json ${native}/share/purifier/implementation.json <<'PY'
    import json,sys
    manifests = [json.load(open(path)) for path in sys.argv[1:]]
    assert manifests[0] == manifests[1]
    assert manifests[0]['configuration'] == json.loads('${builtins.toJSON expected}')
    PY
    mkdir work
    cd work
    # Interactive execution uses the caller runtime; the recorded immutable SDK
    # recipe remains available separately for pure builders.
    ${native}/bin/npm --version > version
    test "$(cat version)" = "$(${pkgs.nodejs}/bin/npm --version)"
    cp version "$out"
  ''
