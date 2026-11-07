# SPDX-License-Identifier: MIT
# Pinned upstream binaries for exact historical and current compatibility points.
{ pkgs, version }:
let
  archives = {
    "22.23.4" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b";
      };
      aarch64-darwin = {
        arch = "arm64";
        sha256 = "037650d0839f457747396f052073fb48333d31bf5abd3c98b74da20d89ebb1ad";
      };
    };
    "24.22.2" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "48cc0e21e048790e54c0cf5749c2725005313d652651c40b7a21feb9697aaf75";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "eb187837a2230d4047161ac0be008584e16b46f726e9c9490ee35dc6b17d9ba8";
      };
      aarch64-darwin = {
        arch = "arm64";
        sha256 = "1f5ac075be50bed4780ea3be19a007fda95ea4d527d28d76d0b91de47d915115";
      };
    };
    "26.13.0" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "d28a96af6c38596f6d9d97c0ee531c13d238d757742387d1928de822d959e997";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "406fe3fbde1c054adff8b297c16fdb5af6659db327c1ac8acd46b56ef1af9a92";
      };
      aarch64-darwin = {
        arch = "arm64";
        sha256 = "6f5b3187d9df9fc007e881167905bc7d69ad26450ddc377c83d63256a2495b6e";
      };
    };
    "6.17.1" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "0f88dacefc4be4709e0a9f9fe685efdfe1582a724d8f42614179c2f604c36165";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "9c7fdb4208fe0d63ac4280d0894a076d11873d49b79648c448f059443c666fbe";
      };
    };
    "8.17.0" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "b7f6dd77fb173c8c7c30d61d0702eefc236bba74398538aa77bfa2bb47bddce6";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "8318d1ee0265d84025ecbea76aaecd732974a6f4ac8492ddd84231cee77ba948";
      };
    };
    "10.24.1" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "a3b9b97c23bcdc64334be6b02422e9014f040d59dcf604563ffda48003419356";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "b11ce837867e50d1b2bf09da6a85336bedfa257bf92f34712aeb94360c0bcd6e";
      };
    };
    "14.21.3" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "05c08a107c50572ab39ce9e8663a2a2d696b5d262d5bd6f98d84b997ce932d9a";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "f06642bfcf0b8cc50231624629bec58b183954641b638e38ed6f94cd39e8a6ef";
      };
    };
    "16.20.2" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "874463523f26ed528634580247f403d200ba17a31adf2de98a7b124c6eb33d87";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "e88d86154d1ce53dc52fd74d79d4bfdf0b05f58c0bb2639adfa36e9378b770c4";
      };
    };
    "18.20.8" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "5467ee62d6af1411d46b6a10e3fb5cacc92734dbcef465fea14e7b90993001c9";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "224e569dbe7b0ea4628ce383d9d482494b57ee040566583f1c54072c86d1116b";
      };
    };
    "20.19.0" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "b4e336584d62abefad31baecff7af167268be9bb7dd11f1297112e6eed3ca0d5";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "dbe339e55eb393955a213e6b872066880bb9feceaa494f4d44c7aac205ec2ab9";
      };
    };
    "22.14.0" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "69b09dba5c8dcb05c4e4273a4340db1005abeafe3927efda2bc5b249e80437ec";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "08bfbf538bad0e8cbb0269f0173cca28d705874a67a22f60b57d99dc99e30050";
      };
    };
    "26.0.0" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "345d558514c62622b5c7d1f7b5f2a19c31ab1405d217df49f010c5ea8decc0f4";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "f0f94e55142149a4d34634dc3d7e103921d898512dd0cef995ecb62c5ebd3f29";
      };
    };
    "26.1.0-rc.0" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "5978e4e39892e1b51d9135efb72f7021d89fa0c57994d45f5e4af2a1e1fa931d";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "05f1f6d6eeadba773082ee47f6e75c95f109723ea31bea6cdeee3220b6b1533b";
      };
    };
    "12.22.12" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "e6d052364bfa2c17da92cf31794100cfd709ba147415ddaeed2222eec9ca1469";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "eebdeb528df727271635196188ed7d04a5dba2c61ccaded22f693ae501cf17f5";
      };
    };
    "4.9.1" = {
      x86_64-linux = {
        arch = "x64";
        sha256 = "db65d409f0fd7e4ff817509c7ec29df72f4b3f6885297b98f64781ecea92feea";
      };
      aarch64-linux = {
        arch = "arm64";
        sha256 = "7203f9693e06ad220cfde2e5d70778cb021a176ecab1bdfee0bf546363333f26";
      };
    };
    "0.12.18".x86_64-linux = {
      arch = "x64";
      sha256 = "5d18077263e6d43b95015adf968a17b312ead1a275f894d40494be61210fa91b";
    };
  };
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
