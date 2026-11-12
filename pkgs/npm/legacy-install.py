# SPDX-License-Identifier: MIT
"""Lend old native npm a shrinkwrap backed by pinned local archives."""
import json
from pathlib import Path
import subprocess
import sys

lock = Path(sys.argv[1])
bindings = json.loads(Path(sys.argv[2]).read_text())
saved = lock.read_bytes()
saved_stat = lock.stat()
document = json.loads(saved)


def bind(dependencies):
    for entry in dependencies.values():
        resolved = entry.get('resolved')
        if resolved in bindings:
            entry['resolved'] = 'file:' + bindings[resolved]
        bind(entry.get('dependencies', {}))


bind(document.get('dependencies', {}))
try:
    lock.write_text(json.dumps(document))
    result = subprocess.run(sys.argv[3:])
    if result.returncode == 0 and '--production' in sys.argv[3:]:
        result = subprocess.run([sys.argv[3], 'prune', '--production', '--ignore-scripts'])
finally:
    lock.write_bytes(saved)
    import os
    os.utime(lock, ns=(saved_stat.st_atime_ns, saved_stat.st_mtime_ns))
raise SystemExit(result.returncode)
