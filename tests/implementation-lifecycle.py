#!/usr/bin/env python3
"""Exercise real npm wrappers/builders from two immutable purifier sources."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True


def execute(arguments, cwd=None, env=None, success=True):
    result = subprocess.run(list(map(str, arguments)), cwd=cwd, env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    print("$ " + " ".join(map(str, arguments)), flush=True)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    if success and result.returncode:
        raise AssertionError(f"command failed with status {result.returncode}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--bootstrap", required=True)
    parser.add_argument("--source-model", required=True)
    parser.add_argument("--local-source", help="local Git locator for pre-publication validation only")
    parser.add_argument("--output")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("bootstrap", args.bootstrap)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    source_a = json.loads(Path(args.baseline).read_text())["source"]
    bootstrap.validate_source(source_a)
    current_cli = Path(execute(["nix", "build", args.current + "#npm-purifier", "--no-link", "--print-out-paths"]).stdout.strip())
    current_native = Path(execute(["nix", "build", args.current + "#npm", "--no-link", "--print-out-paths"]).stdout.strip())
    config = json.loads((current_cli / "share/purifier/implementation.json").read_text())
    source_b = config["source"]
    bootstrap.validate_source(source_b)
    assert not bootstrap.same_source(source_a, source_b)
    if args.local_source:
        for name, source in (("baseline", source_a), ("current", source_b)):
            metadata = json.loads(execute(["nix", "flake", "metadata", "--json",
                                          "git+" + Path(args.local_source).resolve().as_uri() + "?rev=" + source["rev"]]).stdout)
            locked = metadata["locked"]
            effective = {key: locked[key] for key in ("type", "url", "rev", "narHash")}
            assert bootstrap.same_source(effective, source)
            if name == "baseline":
                source_a = effective
            else:
                source_b = effective
    with tempfile.TemporaryDirectory(prefix="npm-implementation-") as temporary:
        work = Path(temporary).resolve()
        project = work / "project"
        shutil.copytree(args.fixture, project)
        for path in [project, *project.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | (0o700 if path.is_dir() else 0o200))
        package = json.loads((project / "package.json").read_text())
        package["scripts"]["pin-origin"] = "node -e 'console.log(require(\"fs\").readFileSync(process.env.NPM_PURIFIER_IMPLEMENTATION_CONFIG,\"utf8\"))'"
        (project / "package.json").write_text(json.dumps(package, indent=2) + "\n")
        lock = project / "npm-purifier.lock.json"
        pin_a = {"version": 1, "tool": "npm-purifier", "source": source_a}
        old_cli = bootstrap.resolve_package(pin_a, config, "npm-purifier", lock)
        bootstrap.verify_package(old_cli, pin_a)
        environment = dict(os.environ)
        environment.update({"HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache")})
        Path(environment["HOME"]).mkdir()
        execute([old_cli / "bin/npm-purifier", "lock"], project, environment)
        if args.local_source:
            execute([old_cli / "bin/npm-purifier", "self-update", "--to", bootstrap.source_ref(source_a)], project, environment)
        def read_lock():
            return bootstrap.read_lock(lock.read_text(), "npm")
        assert bootstrap.same_source(read_lock()["implementation"]["source"], source_a)
        execute([current_native / "bin/npm", "ci"], project, environment)
        execute([current_native / "bin/npm", "run", "build"], project, environment)
        execute([current_native / "bin/npm", "test"], project, environment)
        origin = json.loads(execute([current_native / "bin/npm", "run", "--silent", "pin-origin"], project, environment).stdout)
        assert bootstrap.same_source(origin["source"], source_a)
        selected = json.loads(execute([current_cli / "bin/npm-purifier", "implementation"], project, environment).stdout)
        assert bootstrap.same_source(selected["source"], source_a)
        # Ordinary dependency update must retain the implementation verbatim.
        before_pin = read_lock()["implementation"]
        execute([current_cli / "bin/npm-purifier", "update"], project, environment)
        assert read_lock()["implementation"] == before_pin
        original_lock = lock.read_bytes()
        original_value = read_lock()
        native = project / "package-lock.json"
        original_native = native.read_bytes()

        def project_expression(source):
            return ("let f = ((import " + args.source_model + ").resolve (builtins.fromJSON "
                    + bootstrap.nix_string(json.dumps(source)) + ")).flake; "
                    + "pkgs = import f.inputs.nixpkgs { system = " + bootstrap.nix_string(config["system"])
                    + "; overlays = [ f.overlays.default ]; }; "
                    + "in (pkgs.npm-purifier.buildNpmProject { src = /. + "
                    + bootstrap.nix_string(str(project)) + "; }).tests")
        matched = execute(["nix", "build", "--impure", "--no-link", "--print-out-paths", "--expr", project_expression(source_a)])
        matched_path = matched.stdout.strip()
        matched_derivation = execute(["nix-store", "--query", "--deriver", matched_path]).stdout.strip()
        mismatch = execute(["nix", "eval", "--impure", "--raw", "--expr", "(" + project_expression(source_b) + ").drvPath"], success=False)
        assert mismatch.returncode and "builder implementation differs" in mismatch.stderr

        target = bootstrap.source_ref(source_b) if args.local_source else "installed"
        execute([current_cli / "bin/npm-purifier", "self-update", "--to", target], project, environment)
        assert bootstrap.same_source(read_lock()["implementation"]["source"], source_b)
        assert {key: value for key, value in read_lock().items() if key not in ("implementation", "hash")} == {
            key: value for key, value in original_value.items() if key not in ("implementation", "hash")}
        assert native.read_bytes() == original_native
        origin = json.loads(execute([current_native / "bin/npm", "run", "--silent", "pin-origin"], project, environment).stdout)
        assert bootstrap.same_source(origin["source"], source_b)
        execute([current_native / "bin/npm", "ci"], project, environment)
        execute([current_native / "bin/npm", "run", "build"], project, environment)
        execute([current_native / "bin/npm", "test"], project, environment)
        matched_b = execute(["nix", "build", "--impure", "--no-link", "--print-out-paths", "--expr", project_expression(source_b)], project, environment).stdout.strip()
        matched_b_derivation = execute(["nix-store", "--query", "--deriver", matched_b], project, environment).stdout.strip()
        execute([current_cli / "bin/npm-purifier", "self-update", "--to", bootstrap.source_ref(source_a)], project, environment)
        assert lock.read_bytes() == original_lock and native.read_bytes() == original_native
        external = work / "external.lock.json"
        lock.rename(external)
        external_environment = dict(environment, NPM_PURIFIER_LOCKFILE=str(external))
        origin = json.loads(execute([current_native / "bin/npm", "run", "--silent", "pin-origin"], project, external_environment).stdout)
        assert bootstrap.same_source(origin["source"], source_a)
        external_native = work / "external-package-lock.json"
        native.rename(external_native)
        (project / ".npm-purifier/stamp").unlink(missing_ok=True)
        rootless_environment = dict(external_environment, NPM_PURIFIER_TOOL_LOCKFILE=str(external_native))
        origin = json.loads(execute([current_native / "bin/npm", "run", "--silent", "pin-origin"], project, rootless_environment).stdout)
        assert bootstrap.same_source(origin["source"], source_a)
        external_native.rename(native)
        external.rename(lock)
        # A relative override must have one meaning before and after root-cd
        # child invocations. A competing real B pin occupies the wrong path.
        nested = project / "nested"
        nested.mkdir()
        competing = work / "npm-purifier.lock.json"
        competing_value = read_lock()
        competing_value["implementation"] = {"version": 1, "tool": "npm-purifier", "source": source_b}
        competing.write_text(bootstrap.render_lock(competing_value, "npm"))
        (project / ".npm-purifier/stamp").unlink(missing_ok=True)
        relative_environment = dict(environment, NPM_PURIFIER_LOCKFILE="../npm-purifier.lock.json")
        origin = json.loads(execute([current_native / "bin/npm", "run", "--silent", "pin-origin"], nested, relative_environment).stdout)
        assert bootstrap.same_source(origin["source"], source_a)
        assert (project / ".npm-purifier/stamp").read_text().strip().split(" ", 1)[1] == str(lock.resolve())
        (nested / "package.json").write_text('{"name":"nested-probe","version":"1.0.0"}\n')
        inherited = json.loads(execute([current_cli / "bin/npm-purifier", "implementation"], nested, environment).stdout)
        assert bootstrap.same_source(inherited["source"], source_a)
        rejected = execute([current_cli / "bin/npm-purifier", "lock"], nested, environment, success=False)
        assert rejected.returncode and "parent project" in rejected.stderr
        assert not (nested / "package-lock.json").exists() and lock.read_bytes() == original_lock
        receipt = {"baseline": source_a, "installed": source_b, "system": config["system"],
                   "transport": "local-git" if args.local_source else "public-github",
                   "currentPackages": list(map(str, (current_cli, current_native))), "baselineCli": str(old_cli),
                   "bootstrapSha256": hashlib.sha256(Path(args.bootstrap).read_bytes()).hexdigest(),
                   "matchedBuild": matched_path, "matchedDerivation": matched_derivation,
                   "updatedBuild": matched_b, "updatedDerivation": matched_b_derivation,
                   "nativeCiBuildTest": True, "actualWrapperOrigin": True, "dependencyUpdatePreservesPin": True,
                   "explicitPurifierUpdate": True, "nativeLockUnchanged": True, "restoredLockBytes": True,
                   "mismatchedBuilderRejected": True, "externalLock": True, "coldExternalNativeLock": True,
                   "relativeOverrideWithCompetingPin": True, "ancestorImplementationSelected": True,
                   "ambiguousNestedLockRejectedBeforeNativeWork": True}
        text = json.dumps(receipt, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text)
        print(text, end="")


if __name__ == "__main__":
    main()
