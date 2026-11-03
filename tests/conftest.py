"""Shared fixtures for the PingPanda test suite.

The tests never talk to the public internet: HTTP responses are produced with
``httpx.MockTransport`` and the few tests that need real sockets talk to a
throw away HTTP server that is started on localhost.
"""

import importlib
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]

# A fixed IP address so that the tests never depend on a working DNS server
FAKE_IP = "93.184.216.34"


@pytest.fixture(scope="session")
def checker():
    """The PingPanda package."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module("pingpanda")


@pytest.fixture
def fake_dns(monkeypatch):
    """Resolve every host name to a fixed IP address."""

    def fake_gethostbyname(hostname):
        return FAKE_IP

    monkeypatch.setattr(socket, "gethostbyname", fake_gethostbyname)
    return fake_gethostbyname


@pytest.fixture
def mock_transport(monkeypatch, checker):
    """Return a helper that installs a mock transport in the tool."""

    def install(handler):
        real_client_class = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client_class(*args, **kwargs)

        monkeypatch.setattr(checker.network.httpx, "AsyncClient", factory)

    return install


@pytest.fixture
def make_result(checker):
    """Build a :class:`UrlResult` without going through the network."""

    def build(status=200, url="https://example.com", **kwargs):
        defaults = {
            "url_id": 0,
            "url": url,
            "status": status,
            "elapsed": 0.125,
            "redirect_to": None,
            "ip_port": f"{FAKE_IP}:443",
            "redirect_ip_port": None,
        }
        defaults.update(kwargs)
        return checker.UrlResult(**defaults)

    return build


class _Handler(BaseHTTPRequestHandler):
    """A tiny HTTP server with predictable endpoints."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the test output clean
        pass

    def _send(self, code, body=b"ok", headers=None):
        self.send_response(code)

        for key, value in (headers or {}).items():
            self.send_header(key, value)

        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/ok"):
            self._send(200)
        elif path.startswith("/missing"):
            self._send(404)
        elif path.startswith("/boom"):
            self._send(500)
        elif path.startswith("/redirect-chain/"):
            time.sleep(0.2)
            hop = int(path.rsplit("/", 1)[-1])
            if hop < 5:
                self._send(302,headers={"Location": f"/redirect-chain/{hop + 1}"},)
            else:
                self._send(200)
        elif path.startswith("/redirect"):
            self._send(302, headers={"Location": "/ok"})
        elif path.startswith("/loop"):
            self._send(302, headers={"Location": "/loop"})
        elif path.startswith("/slow"):
            time.sleep(1.5)
            self._send(200)
        elif path.startswith("/trickle"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for i in range(10):
                    chunk = f"chunk-{i}\n".encode()
                    self.wfile.write(f"{len(chunk):X}\r\n".encode())
                    self.wfile.write(chunk + b"\r\n")
                    self.wfile.flush()
                    time.sleep(0.1)

                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

            except (BrokenPipeError, ConnectionResetError):
                pass
        elif path.startswith("/silent"):
            self.close_connection = True
            threading.Event().wait(2)
        else:
            self._send(404)


@pytest.fixture(scope="session")
def local_server():
    """Start a throw away HTTP server on localhost and yield its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
