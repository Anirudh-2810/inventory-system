"""Dependency-free secure HTTP server and router for the web tier.

The core dispatch logic lives in `dispatch()` / `ServerState` so it can be
driven two ways with no behavior difference:
  * the stdlib `SecureHTTPServer` (offline / zero-install runs), and
  * a WSGI `application` (see web/wsgi.py) for gunicorn/uWSGI in production.

Request flow for every call:
  CORS preflight -> security headers -> rate limit -> auth (if protected)
  -> role check (if required) -> handler -> JSON encode
Any exception becomes a generic 500 with a correlation ID; details go to logs.
"""

import json
import re
import urllib.parse
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Dict, List, Optional, Tuple

from .config import Config
from .security import RateLimiter, authenticate, build_headers, error_response
from .store import UserStore
from inventory_system.services.inventory_service import InventoryService
import auth  # JWT + role helpers


class Request:
    def __init__(self, method: str, path: str, headers: Dict[str, str],
                 body: bytes, client_ip: str) -> None:
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
        self.client_ip = client_ip
        self.user: Optional[Dict] = None
        parsed = urllib.parse.urlparse(path)
        self.path_only = parsed.path
        self.query = dict(urllib.parse.parse_qsl(parsed.query))
        self._json = None

    def json_data(self) -> Optional[dict]:
        if self._json is not None:
            return self._json
        if not self.body:
            self._json = {}
            return self._json
        try:
            self._json = json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json = None
        return self._json


class Context:
    """Shared dependencies passed to every handler."""

    def __init__(self, config: Config, users: UserStore) -> None:
        self.config = config
        self.users = users

    def service(self) -> InventoryService:
        return InventoryService(self.config.db_path)


# Route: (method, compiled regex, handler, protected, role, rate_group)
Route = Tuple[str, re.Pattern, Callable, bool, Optional[str], str]


class ServerState:
    """Shared server state used by both the stdlib server and the WSGI app."""

    def __init__(self, config: Config, users: UserStore, routes: List[Route]) -> None:
        self.config = config
        self.users = users
        self.routes = routes
        self.ctx = Context(config, users)
        self.limiter = RateLimiter(config.rate)


def _match(routes: List[Route], method: str, path: str) -> Optional[Route]:
    for r in routes:
        if r[0] != method:
            continue
        if r[1].match(path):
            return r
    return None


def dispatch(state: ServerState, method: str, path: str,
             headers: Dict[str, str], body: bytes,
             client_ip: str) -> Tuple[int, Dict[str, str], bytes]:
    """Core request pipeline. Returns (status, headers, body_bytes)."""
    cfg = state.config
    origin = headers.get("origin")

    # CORS preflight
    if method == "OPTIONS":
        return 204, build_headers(cfg.allowed_origins, origin), b""

    req = Request(method, path, headers, body, client_ip)

    # Match route
    route = _match(state.routes, method, req.path_only)
    if route is None:
        return error_response(404, "Not found")

    _, _regex, handler, protected, role, rate_group = route

    # Rate limit
    if not state.limiter.is_allowed(f"{req.client_ip}:{rate_group}", rate_group):
        return error_response(429, "Too many requests")

    # Auth
    if protected:
        user = authenticate(req.headers)
        if user is None:
            return error_response(401, "Authentication required")
        if role and not auth.require_role(user, {role}):
            return error_response(403, "Insufficient permissions")
        req.user = user

    # Dispatch
    try:
        result = handler(req, state.ctx)
        if isinstance(result, tuple) and len(result) == 2:
            status, data = result
            extra: Dict[str, str] = {}
        else:
            status, data, extra = result  # type: ignore[misc]
        resp_body = json.dumps(data, default=str).encode("utf-8")
        return status, build_headers(cfg.allowed_origins, origin, extra), resp_body
    except ValueError as e:
        return error_response(400, str(e) or "Bad request")
    except Exception as e:  # noqa: BLE001 - never leak internals
        logging.getLogger(__name__).exception("Unhandled error: %s", e)
        return error_response(500, "Internal server error")


class SecureHTTPServer(HTTPServer):
    def __init__(self, state: ServerState, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.state = state


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs) -> None:  # type: ignore[override]
        pass

    def _dispatch(self, method: str) -> None:
        state: ServerState = self.server.state  # type: ignore[assignment]
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        headers_lc = {k.lower(): v for k, v in self.headers.items()}
        status, headers, body = dispatch(
            state, method, self.path, headers_lc, raw, self.client_address[0])
        self._send(status, headers, body)

    def _send(self, status: int, headers: Dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    # HTTP verbs
    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_PATCH(self): self._dispatch("PATCH")
    def do_DELETE(self): self._dispatch("DELETE")
    def do_OPTIONS(self): self._dispatch("OPTIONS")


def run_server(config: Config, users: UserStore, routes: List[Route]) -> None:
    """Start the web tier via the stdlib server (blocking)."""
    state = ServerState(config, users, routes)
    httpd = SecureHTTPServer(state, (config.host, config.port), _Handler)
    print(f"StockOffline web tier listening on http://{config.host}:{config.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
