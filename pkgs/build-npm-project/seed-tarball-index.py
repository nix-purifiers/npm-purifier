#!/usr/bin/env python3
"""Index Nix-fetched tarballs for npm requests that omit their integrity."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile


def seed(catalog, cache, registry):
    registry = registry.rstrip('/') + '/'
    for item in catalog:
        urls = {item['url']}
        default = 'https://registry.npmjs.org/'
        if item['url'].startswith(default):
            urls.add(registry + item['url'][len(default):])
        for url in sorted(urls):
            key = 'make-fetch-happen:request-cache:' + url
            digest = hashlib.sha256(key.encode()).hexdigest()
            target = cache / 'index-v5' / digest[:2] / digest[2:4] / digest[4:]
            records = []
            for accept in item.get('accepts', [None]):
                record = {'key': key, 'integrity': item['integrity'], 'time': 1,
                          'size': Path(item['path']).stat().st_size,
                          'metadata': {'time': 1, 'url': url,
                                       'reqHeaders': {'accept': accept} if accept else {},
                                       'resHeaders': {'content-type': item.get('contentType', 'application/octet-stream'),
                                                      'cache-control': 'public, max-age=31557600'},
                                       'options': {'compress': True}}}
                text = json.dumps(record, separators=(',', ':'), ensure_ascii=False)
                records.append(hashlib.sha1(text.encode()).hexdigest() + '\t' + text)
            line = '\n' + '\n'.join(records) + '\n'
            target.parent.mkdir(parents=True, exist_ok=True)
            # Replace links into the immutable store rather than appending to
            # them. cacache may later compact or update this writable index.
            if not target.is_symlink() and target.is_file() and target.read_text() == line:
                continue
            with tempfile.NamedTemporaryFile('w', dir=target.parent, prefix=target.name + '.seed-', delete=False) as stream:
                stream.write(line)
                temporary = Path(stream.name)
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    seed(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]), sys.argv[3])
