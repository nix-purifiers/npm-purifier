#!/usr/bin/env python3
"""Local lock/adoption must preserve a caller runtime outside the store."""

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    sdk = root / "user-runtime"
    (sdk / "bin").mkdir(parents=True)
    (sdk / "lib/node_modules").mkdir(parents=True)
    shutil.copy2(Path(sys.argv[1]) / "bin/node", sdk / "bin/node")
    shutil.copytree(
        Path(sys.argv[1]) / "lib/node_modules/npm",
        sdk / "lib/node_modules/npm",
        symlinks=True,
    )
    npm = sdk / "bin/npm"
    npm.write_text(
        "#!" + str(sdk / "bin/node") + "\n"
        "require('fs').appendFileSync(process.env.ACTOR_LOG, JSON.stringify({"
        "executable:process.execPath,version:process.version})+'\\n');"
        "require('../lib/node_modules/npm/bin/npm-cli.js');\n"
    )
    npm.chmod(0o755)
    selectors = root / "runtime-selection"
    selectors.mkdir()
    (selectors / "node").symlink_to(sdk / "bin/node")
    environment = dict(
        os.environ,
        PATH=str(selectors) + ":" + str(sdk / "bin") + ":" + os.environ["PATH"],
        HOME=str(root),
        ACTOR_LOG=str(root / "actors.jsonl"),
        npm_config_cache=str(root / "cache"),
        npm_config_offline="true",
        npm_config_audit="false",
        npm_config_registry="http://127.0.0.1:9/",
    )
    project = root / "project"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps(
            {
                "name": "local-runtime-test",
                "version": "1.0.0",
                "private": True,
                "scripts": {"runtime": "node -p process.execPath"},
            }
        )
    )
    def legacy_lock(directory, env):
        # Relock a valid pre-identity sidecar, so this check also runs for
        # dirty source trees whose fresh portable identity is unavailable.
        subprocess.run([str(npm), "install", "--package-lock-only", "--ignore-scripts"],
                       cwd=directory, env=env, check=True)
        text = json.dumps({"version": 3, "hash": "", "packageLockSha256":
            hashlib.sha256((directory / "package-lock.json").read_bytes()).hexdigest(),
            "git": {}}, indent=2) + "\n"
        digest = base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
        (directory / "npm-purifier.lock.json").write_text(
            text.replace('"hash": ""', '"hash": "sha256-' + digest + '"'))

    legacy_lock(project, environment)
    subprocess.run([sys.argv[2], "lock"], cwd=project, env=environment, check=True)
    state = project / ".npm-purifier"
    facts = list((state / "runtime").glob("*/facts.json"))
    assert len(facts) == 1
    identity = json.loads(facts[0].read_text())
    assert identity["runtime"]["executable"] == str(sdk / "bin/node")
    assert identity["node"] == str(selectors / "node"), (
        "retain caller runtime selection"
    )
    captured = dict(
        line.split("=", 1)
        for line in (facts[0].parent / "environment").read_text().splitlines()
    )
    assert shlex.split(captured["nativeNode"]) == [str(sdk / "bin/node")], (
        "headers follow actual runtime through shims"
    )
    assert identity["npmMain"] == str(npm), "preserve the actual caller npm launcher"
    # The bypass path must select the same runtime and preserve npm arguments.
    environment["NPM_PURIFIER"] = "0"
    output = subprocess.check_output(
        [sys.argv[3], "run", "--silent", "runtime"],
        cwd=project,
        env=environment,
        text=True,
    )
    assert output.strip() == str(sdk / "bin/node")
    actors = [
        json.loads(line) for line in (root / "actors.jsonl").read_text().splitlines()
    ]
    assert len(actors) >= 2
    assert all(actor["executable"] == str(sdk / "bin/node") for actor in actors)
    # Version managers commonly expose shell/native shims instead of JS files.
    manager = root / "manager-shims"
    manager.mkdir()
    shell_log = root / "shell-launcher.log"
    for name, command in [
        ("node", [str(sdk / "bin/node")]),
        ("npm", [str(sdk / "bin/node"), str(npm)]),
    ]:
        launcher = manager / name
        launcher.write_text(
            "#!"
            + sys.argv[5]
            + "\n"
            + (
                'printf "npm-shim-used\\n" >> ' + shlex.quote(str(shell_log)) + "\n"
                if name == "npm"
                else ""
            )
            + "exec "
            + shlex.join(command)
            + ' "$@"\n'
        )
        launcher.chmod(0o755)
    shell_project = root / "shell-project"
    shell_project.mkdir()
    (shell_project / "package.json").write_bytes(
        (project / "package.json").read_bytes()
    )
    shell_environment = dict(
        environment,
        PATH=str(manager) + ":" + str(sdk / "bin") + ":" + os.environ["PATH"],
    )
    legacy_lock(shell_project, shell_environment)
    subprocess.run(
        [sys.argv[2], "lock"], cwd=shell_project, env=shell_environment, check=True
    )
    shell_facts = next((shell_project / ".npm-purifier/runtime").glob("*/facts.json"))
    shell_identity = json.loads(shell_facts.read_text())
    assert shell_identity["npmCommand"] == [str(manager / "npm")], (
        "retain the native shell launcher"
    )
    assert shell_identity["runtime"]["executable"] == str(sdk / "bin/node")
    assert shell_identity["npmModules"] == str(
        sdk / "lib/node_modules/npm/node_modules"
    )
    output = subprocess.check_output(
        [sys.argv[3], "run", "--silent", "runtime"],
        cwd=shell_project,
        env=shell_environment,
        text=True,
    )
    assert output.strip() == str(sdk / "bin/node")
    assert "npm-shim-used" in shell_log.read_text()
    # Absence of a project runtime must fail instead of substituting the helper.
    empty = root / "empty-path"
    empty.mkdir()
    environment["PATH"] = str(empty)
    for command in (
        [sys.executable, sys.argv[4], "exec", "--", "--version"],
        [sys.argv[2], "lock"],
        [sys.argv[3], "--version"],
    ):
        failed = subprocess.run(
            command, cwd=project, env=environment, text=True, capture_output=True
        )
        assert (
            failed.returncode != 0
            and "No existing Node runtime on PATH" in failed.stderr
        )
    print("PASS local lock, npm proxy, bypass, and missing-runtime behavior")
