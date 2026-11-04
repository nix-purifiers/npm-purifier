# SPDX-License-Identifier: MIT
"""Minimal local npm publish endpoint for observing native upload bytes."""
import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import hashlib
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import tarfile
import threading


@contextmanager
def registry(root, expected_node='12.22.12', prepared=None, catalog=None):
    uploads = []
    modules = json.loads(Path(catalog).read_text())['modules'] if catalog else []
    archives = {entry['archive']: (Path(prepared) / entry['archive']).read_bytes() for entry in modules}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            route = unquote(urlsplit(self.path).path).lstrip('/')
            if route in archives:
                data = archives[route]
                content_type = 'application/octet-stream'
            else:
                entries = [entry for entry in modules if entry['name'] == route]
                if not entries:
                    self.send_error(404)
                    return
                versions = {}
                for entry in entries:
                    payload = archives[entry['archive']]
                    versions[entry['version']] = dict(entry['package'], dist={
                        'tarball': 'http://' + self.headers['Host'] + '/' + entry['archive'],
                        'integrity': entry['integrity'], 'shasum': hashlib.sha1(payload).hexdigest()})
                data = json.dumps({'name': route, 'versions': versions,
                                   'dist-tags': {'latest': entries[0]['version']}}).encode()
                content_type = 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_PUT(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            attachments = body.get('_attachments', {})
            assert attachments, 'native publication must send actual tarball bytes'
            for entry in attachments.values():
                contents = base64.b64decode(entry['data'])
                with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
                    assert archive.extractfile('package/built.txt').read() == ('v' + expected_node).encode()
                uploads.append((contents, self.headers.get('User-Agent', '')))
            response = b'{"ok":true,"id":"fixture","rev":"1"}'
            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    (root / '.npmrc').write_text(f'registry={url}\n//127.0.0.1:{server.server_port}/:_authToken=local-fixture-token\nalways-auth=true\n')
    try:
        yield url, uploads
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
