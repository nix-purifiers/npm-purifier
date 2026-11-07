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
    # Gradle's file-lock contention listener uses loopback UDP, even offline.
    __darwinAllowLocalNetworking = true;
    nativeBuildInputs = [
      pkgs.python3
      pkgs.jdk
      pkgs.gradle
    ];
  }
  ''
    export HOME="$TMPDIR/home" GRADLE_USER_HOME="$TMPDIR/gradle"
    mkdir -p "$HOME"
    ${pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isDarwin ''
      python ${./darwin-loopback.py}
      # Darwin's sandbox denies the JDK's IPv4-mapped IPv6 loopback path.
      # Keep this adaptation within the ordinary WebJar consumer test.
      export JAVA_TOOL_OPTIONS="''${JAVA_TOOL_OPTIONS:+$JAVA_TOOL_OPTIONS }-Djava.net.preferIPv4Stack=true"
      ${pkgs.jdk}/bin/java -XshowSettings:properties -version > java-properties.log 2>&1
      cat java-properties.log
      grep -Eq '^[[:space:]]*java.net.preferIPv4Stack = true$' java-properties.log
    ''}
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
        ${pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isDarwin ''
          assert System.getProperty('java.net.preferIPv4Stack') == 'true'
        ''}def jar = new java.util.jar.JarFile(configurations.assets.singleFile)
        def resource = jar.getJarEntry('META-INF/resources/webjars/proof__browser/1.0.0/proof.js')
        assert jar.getInputStream(resource).text.contains('42')
        jar.close()
      }
    }
    GRADLE
    command -v gradle
    gradle --version
    gradleStatus=0
    gradle --offline --no-daemon --stacktrace verify > gradle-console.log 2>&1 || gradleStatus=$?
    cat gradle-console.log || true
    if [ "$gradleStatus" -ne 0 ]; then
      python ${./gradle-diagnostics.py} --gradle-home "$GRADLE_USER_HOME" \
        --project "$PWD" --tmpdir "$TMPDIR" || true
      exit "$gradleStatus"
    fi
    test -n "$(find ${built.projections.ivy} -name '*.jar')"
    touch $out
  ''
