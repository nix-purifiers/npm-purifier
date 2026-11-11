#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# conformance-relock: relocking a fixture reproduces its lockfiles byte for
# byte. `npm-purifier lock` runs on copies of the fixtures, from the
# network, and has to write package-lock.json and npm-purifier.lock.json
# as committed.
#
# For tests/fixtures/git, relocking retains the existing immutable git
# entries, including the deliberately unreachable repository fixture.
#
# Usage: tests/conformance-relock.sh, from any directory, with Nix and the
# network.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export npm_config_cache="$work/.npm-cache"

nix build "$root#npm-purifier" --out-link "$work/command"
purifier="$work/command/bin/npm-purifier"

# relock <fixture directory>
relock() {
  local fixture="$root/tests/fixtures/$1" copy="$work/$1"
  mkdir -p "$copy"
  # The fixture's own files, without what an editor or agent left there,
  # one by one, as macOS's cp has no --parents.
  (cd "$fixture" && find . -type f -not -path './.claude/*') | while IFS= read -r file; do
    mkdir -p "$copy/${file%/*}"
    cp "$fixture/$file" "$copy/$file"
  done
  chmod -R u+w "$copy"
  (cd "$copy" && "$purifier" lock)
  diff -u "$fixture/package-lock.json" "$copy/package-lock.json"
  if [ -f "$fixture/npm-purifier.lock.json" ]; then
    diff -u "$fixture/npm-purifier.lock.json" "$copy/npm-purifier.lock.json"
  elif [ -f "$copy/npm-purifier.lock.json" ]; then
    # Native-only legacy fixtures gain a project-owned implementation pin on
    # first activation. The next lock must reproduce that complete file.
    python3 - "$copy/npm-purifier.lock.json" <<'PY'
import json, sys
pin = json.load(open(sys.argv[1]))['implementation']
assert pin['version'] == 1 and pin['tool'] == 'npm-purifier'
assert len(pin['source']['rev']) == 40 and pin['source']['narHash'].startswith('sha256-')
PY
    first="$work/first-${1//\//_}.lock"
    cp "$copy/npm-purifier.lock.json" "$first"
    (cd "$copy" && "$purifier" lock)
    diff -u "$first" "$copy/npm-purifier.lock.json"
    diff -u "$fixture/package-lock.json" "$copy/package-lock.json"
  fi
  echo "$1: relocked byte for byte"
}

relock app
relock workspaces
relock git
relock paths/app
# `lock` keeps the old semver that `update` would move.
relock update
