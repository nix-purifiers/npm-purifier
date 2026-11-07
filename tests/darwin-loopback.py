#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Require local HTTP/UDP while Darwin denies external outbound sockets."""
import errno
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import socket
import sys
import threading
from urllib.request import ProxyHandler, build_opener


assert sys.platform == 'darwin'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'locked-local-fixture'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


server = HTTPServer(('127.0.0.1', 0), Handler)
worker = threading.Thread(target=server.serve_forever, daemon=True)
worker.start()
try:
    opener = build_opener(ProxyHandler({}))
    with opener.open('http://127.0.0.1:' + str(server.server_port), timeout=3) as response:
        assert response.read() == b'locked-local-fixture'
finally:
    server.shutdown()
    server.server_close()
    worker.join()

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
    listener.bind(('127.0.0.1', 0))
    listener.settimeout(3)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.sendto(b'gradle-lock-ipc', listener.getsockname())
    assert listener.recvfrom(1024)[0] == b'gradle-lock-ipc'

denied = {}
for label, kind in (('tcp', socket.SOCK_STREAM), ('udp', socket.SOCK_DGRAM)):
    with socket.socket(socket.AF_INET, kind) as connection:
        connection.settimeout(1)
        try:
            # TEST-NET-2 avoids contacting a real service if the sandbox regresses.
            if kind == socket.SOCK_STREAM:
                connection.connect(('198.51.100.1', 443))
            else:
                connection.sendto(b'forbidden', ('198.51.100.1', 443))
        except OSError as error:
            assert error.errno in (errno.EPERM, errno.EACCES), error
            denied[label] = error.errno
        else:
            raise AssertionError('Darwin sandbox permitted an external outbound socket')
print(json.dumps({'localHTTP': True, 'localUDP': True, 'externalDenied': denied}), flush=True)
