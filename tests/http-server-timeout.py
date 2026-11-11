#!/usr/bin/env python3
"""The packaged CLI's seconds option must not become a millisecond deadline."""
import json
import os
import signal
import socket
import subprocess
import sys
import time

with socket.socket() as reservation:
    reservation.bind(('127.0.0.1', 0))
    port = reservation.getsockname()[1]
process = subprocess.Popen([sys.argv[1], '-a', '127.0.0.1', '-p', str(port), '-t1', '.'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           start_new_session=True)
try:
    deadline = time.monotonic() + 15
    while True:
        try:
            client = socket.create_connection(('127.0.0.1', port), timeout=0.2)
            break
        except OSError:
            if process.poll() is not None or time.monotonic() >= deadline:
                raise AssertionError('packaged http-server did not become ready')
            time.sleep(0.05)
    assert process.poll() is None, 'packaged server exited before the probe'
    with client:
        client.settimeout(10)
        started = time.monotonic()
        assert client.recv(1) == b'', 'idle connection should close without HTTP data'
        elapsed = time.monotonic() - started
        assert 0.7 <= elapsed < 10, f'-t1 closed after {elapsed}s; expected one second'
    assert process.poll() is None, 'packaged server exited during the probe'
    print(json.dumps({'cli': sys.argv[1], 'secondsOption': 1, 'idleClosedAfterSeconds': elapsed}))
finally:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
