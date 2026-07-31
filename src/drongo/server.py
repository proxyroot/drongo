"""Standalone HTTP server ("drongo server").

Like ``moto_server``, this exposes the exact same in-memory backends over a real
socket so that GCP SDKs in *any* language - or the google client libraries in
emulator mode - can talk to drongo. State lives for the lifetime of the process.

Point clients at it with the relevant emulator environment variable, e.g. for
Cloud Storage::

    $ drongo server --port 9090 &
    $ export STORAGE_EMULATOR_HOST=http://localhost:9090

Other services accept an explicit endpoint via ``client_options``::

    client = secretmanager.SecretManagerServiceClient(
        transport="rest",
        client_options={"api_endpoint": "http://localhost:9090"},
    )
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from drongo.core import registry
from drongo.core.responses import BaseResponse, HttpResponse

# Backends are shared mutable state; serialise request handling so the
# threading server stays correct without sprinkling locks through every model.
_LOCK = threading.Lock()


def _json(status: int, payload: dict) -> HttpResponse:
    return status, {"Content-Type": "application/json"}, json.dumps(payload)


def _management(method: str, path: str) -> HttpResponse:
    """drongo's management API, analogous to moto's ``/moto-api``.

    * ``POST /drongo/reset`` clears every service's in-memory state, so a
      long-lived server can be reset between tests (including from non-Python
      test suites).
    * ``GET /drongo/health`` reports liveness and the registered services.
    """
    if method == "POST" and path == "/drongo/reset":
        with _LOCK:
            registry.reset_all_backends()
        return _json(200, {"reset": True})
    if method == "GET" and path == "/drongo/health":
        services = [service.name for service in registry.iter_services()]
        return _json(200, {"status": "ok", "services": services})
    return _json(
        404,
        {"error": {"code": 404, "message": f"drongo: unknown management route {path}"}},
    )


class _RequestShim:
    """Minimal stand-in for a ``requests`` PreparedRequest for :meth:`decode`."""

    def __init__(self, method: str, url: str, headers: dict[str, str], body: bytes):
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body


class DrongoHTTPRequestHandler(BaseHTTPRequestHandler):
    """Dispatches every request across all registered service routers."""

    server_version = "drongo"
    protocol_version = "HTTP/1.1"

    def _dispatch(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        shim = _RequestShim(self.command, self.path, dict(self.headers), body)
        request = BaseResponse.decode(shim)

        # drongo's own management API (like moto's /moto-api), before services.
        if request.path.startswith("/drongo/"):
            self._write(_management(request.method, request.path))
            return

        with _LOCK:
            for service in registry.iter_services():
                # gRPC-only services (e.g. pubsub) have no HTTP router.
                if service.response is None:
                    continue
                response = service.response.handle(request)
                if response is not None:
                    self._write(response)
                    return

        self._write(
            (
                404,
                {"Content-Type": "application/json"},
                '{"error": {"code": 404, "message": "drongo: no matching route"}}',
            )
        )

    def _write(self, response: HttpResponse) -> None:
        status, headers, body = response
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if not any(k.lower() == "content-length" for k in headers):
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    # All verbs share one dispatcher.
    do_GET = _dispatch
    do_POST = _dispatch
    do_PUT = _dispatch
    do_PATCH = _dispatch
    do_DELETE = _dispatch
    do_HEAD = _dispatch

    def log_message(self, *args: object) -> None:  # noqa: D401 - silence by default
        """Suppress the default noisy stderr logging."""


def create_server(host: str = "localhost", port: int = 0) -> ThreadingHTTPServer:
    """Build (but do not start) a server with all services registered."""
    import drongo.services  # noqa: F401  (import for registration side effects)

    registry.reset_all_backends()
    return ThreadingHTTPServer((host, port), DrongoHTTPRequestHandler)


def run(host: str = "localhost", port: int = 5000) -> None:
    """Run the server until interrupted (used by the CLI)."""
    httpd = create_server(host, port)
    bound_port = httpd.server_address[1]
    endpoint = f"http://{host}:{bound_port}"
    print(f"drongo server listening on {endpoint}")
    print(f"  export STORAGE_EMULATOR_HOST={endpoint}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        pass
    finally:
        httpd.server_close()


def start_background(
    host: str = "localhost", port: int = 0
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start the server in a daemon thread; returns ``(server, thread)``.

    Handy in tests: read the bound port from ``server.server_address[1]``.
    """
    httpd = create_server(host, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread
