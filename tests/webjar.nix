# SPDX-License-Identifier: MIT
{ pkgs, buildNpmProject }:
let
  built = buildNpmProject {
    src = ./fixtures/webjar;
    webAssets."@proof/browser" = "dist";
  };
  view = built.packages."@proof/browser".projections.maven;
in
pkgs.runCommand "npm-webjar-ordinary-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.jdk
      pkgs.gradle
    ];
  }
  ''
    export HOME="$TMPDIR/home" GRADLE_USER_HOME="$TMPDIR/gradle"
    mkdir -p "$HOME"
    python - <<'PY'
    import json, pathlib, zipfile
    catalog = json.load(open('${view.catalog}'))
    module, = catalog['modules']
    open('coordinate', 'w').write(f"{module['group']}:{module['name']}:{module['version']}")
    jar, = pathlib.Path('${view}').rglob('*.jar')
    with zipfile.ZipFile(jar) as archive:
        names = archive.namelist()
        assert not any('node_modules' in name or '.env' in name or 'build.js' in name for name in names)
        assert b'42' in archive.read('META-INF/resources/webjars/proof__browser/1.0.0/proof.js')
    PY
    cat > settings.gradle <<'GRADLE'
    rootProject.name = 'ordinary-webjar-consumer'
    GRADLE
    cat > build.gradle <<'GRADLE'
    repositories { maven { url = uri('${view}') } }
    configurations { assets }
    dependencies { assets file('coordinate').text }
    tasks.register('verify') {
      doLast {
        def jar = new java.util.jar.JarFile(configurations.assets.singleFile)
        def resource = jar.getJarEntry('META-INF/resources/webjars/proof__browser/1.0.0/proof.js')
        assert jar.getInputStream(resource).text.contains('42')
        jar.close()
      }
    }
    GRADLE
    gradle --offline --no-daemon verify
    test -n "$(find ${built.projections.ivy} -name '*.jar')"
    touch $out
  ''
