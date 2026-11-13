# SPDX-License-Identifier: MIT
"""Resolve the caller's Node/npm; never select a packaged project runtime."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

MARKER = b"# npm-purifier-local-wrapper-v1"


def managed(path):
    try:
        with open(path, "rb") as stream:
            data = stream.read(16384)
            return MARKER in data or (
                b"NPM_PURIFIER_LEGACY_BINDINGS" in data
                and b"dependencies/environment" in data
            )
    except OSError:
        return False


def npm_package(executable):
    path = Path(executable).resolve()
    parents = [path.parent, *path.parents, path.parent.parent / "lib/node_modules/npm"]
    for parent in parents:
        metadata = parent / "package.json"
        try:
            if json.loads(metadata.read_text()).get("name") == "npm":
                main = parent / "bin/npm-cli.js"
                if main.is_file():
                    first = path.read_bytes()[:256].split(b"\n", 1)[0]
                    entry = path if path.suffix == ".js" or b"node" in first else main
                    return parent, entry
        except (OSError, ValueError):
            pass
    return None


def launcher_package(candidate, facts):
    """Keep version-manager/native launchers while locating their npm modules."""
    command = [str(candidate.absolute())]
    version = subprocess.check_output([*command, "--version"], text=True).strip()
    versions = json.loads(
        subprocess.check_output(
            [*command, "version", "--json", "--workspaces=false"], text=True
        )
    )
    if not isinstance(versions, dict):
        raise RuntimeError(
            "The existing npm launcher did not report runtime capabilities as JSON"
        )
    if str(versions.get("node", "")).lstrip("v") != facts["version"]:
        raise RuntimeError(
            "The existing npm launcher runs a different Node version from the selected node on PATH"
        )
    if versions.get("modules") is not None and str(versions["modules"]) != str(
        facts["abi"]
    ):
        raise RuntimeError(
            "The existing npm launcher reports a different Node ABI from the selected node on PATH"
        )
    roots = []
    global_modules = subprocess.check_output(
        [*command, "root", "--global"], text=True
    ).strip()
    if global_modules:
        roots.append(Path(global_modules) / "npm")
    paired = npm_package(Path(facts["executable"]).parent / "npm")
    if paired:
        roots.append(paired[0])
    for root in roots:
        try:
            metadata = json.loads((root / "package.json").read_text())
            main = root / "bin/npm-cli.js"
            if (
                metadata.get("name") == "npm"
                and metadata.get("version") == version
                and main.is_file()
            ):
                return root, main, command, version
        except (OSError, ValueError):
            pass
    raise RuntimeError(
        "Cannot locate matching npm modules for the existing launcher: "
        + str(candidate)
    )


def discover():
    selected = shutil.which("node")
    if not selected:
        raise RuntimeError(
            "No existing Node runtime on PATH; select your project runtime before using npm-purifier"
        )
    node = str(Path(selected).absolute())
    facts = json.loads(
        subprocess.check_output(
            [
                node,
                "-p",
                "JSON.stringify({version:process.versions.node,abi:process.versions.modules||null,platform:process.platform,arch:process.arch,executable:process.execPath})",
            ],
            text=True,
        )
    )
    if not facts.get("version") or not facts.get("platform") or not facts.get("arch"):
        raise RuntimeError(
            "The selected Node executable did not report its runtime capabilities"
        )
    candidates = [Path(directory or ".") / "npm" for directory in os.get_exec_path()]
    # A buildEnv can co-locate our wrapper with the selected Node. Follow that
    # Node's installation only when PATH contains no underlying npm launcher.
    candidates.append(Path(facts["executable"]).parent / "npm")
    for candidate in candidates:
        if (
            not candidate.is_file()
            or not os.access(candidate, os.X_OK)
            or managed(candidate)
        ):
            continue
        package = npm_package(candidate)
        if package and candidate.resolve() == package[1]:
            root, main = package
            command = [node, str(main)]
            version = subprocess.check_output(
                [*command, "--version"], text=True
            ).strip()
        else:
            root, main, command, version = launcher_package(candidate, facts)
        return {
            "node": node,
            "npmMain": str(main),
            "npmModules": str(root / "node_modules"),
            "npmExecutable": str(candidate.absolute()),
            "npmCommand": command,
            "npmVersion": version,
            "runtime": facts,
        }
    raise RuntimeError(
        "No existing npm installation found for the selected Node runtime; no Nix SDK was substituted"
    )


def write_state_file(path, text, mode=0o644):
    # Concurrent npm invocations may discover the same runtime. Publish whole
    # files atomically so another process never executes a truncated shim.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture(state, shell):
    info = discover()
    identity = dict(info)
    for key, path in [
        ("nodeFile", info["node"]),
        ("npmFile", info["npmMain"]),
        ("launcherFile", info["npmExecutable"]),
    ]:
        stat = os.stat(path)
        identity[key] = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]
    fingerprint = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()
    directory = state / "runtime" / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "npm"
    write_state_file(
        shim,
        "#!" + shell + "\nexec " + shlex.join(info["npmCommand"]) + ' "$@"\n',
        0o755,
    )
    write_state_file(directory / "facts.json", json.dumps(info, indent=2) + "\n")
    values = {
        "npm": str(shim),
        "nativeNode": info["runtime"]["executable"],
        "nativeNpmModules": info["npmModules"],
        "runtimeFingerprint": fingerprint,
    }
    # This is private shell state, not a portable lockfile or SDK declaration.
    environment = directory / "environment"
    write_state_file(
        environment,
        "".join(key + "=" + shlex.quote(value) + "\n" for key, value in values.items()),
    )
    print(environment)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["capture", "exec"])
    parser.add_argument("--state", type=Path)
    parser.add_argument("--shell")
    args, remainder = parser.parse_known_args()
    try:
        if args.operation == "exec":
            info = discover()
            arguments = remainder[1:] if remainder[:1] == ["--"] else remainder
            os.execv(info["npmCommand"][0], [*info["npmCommand"], *arguments])
        if args.state is None or args.shell is None:
            parser.error("capture needs --state and --shell")
        capture(args.state, args.shell)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("npm-purifier: " + str(error), file=sys.stderr)
        sys.exit(1)
