"""WSGI application for production deployments (gunicorn / uWSGI).

This lets the exact same secure request pipeline run under a production WSGI
server without changing any handler code. For local/offline zero-dependency
runs you don't need this file at all — `python web_app.py` uses the stdlib
server instead.

Production:
    pip install gunicorn
    gunicorn web.wsgi:application --bind 0.0.0.0:8000 --workers 4

The app reads INVENTORY_DB_PATH / JWT_SECRET_KEY / ALLOWED_ORIGINS / WEB_*
from the environment (same as the offline tier).
"""

import os
import sys
import logging
import http

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.config import Config
from web.store import UserStore
from web.server import ServerState, dispatch
from web.app import build_routes

_config = Config()
_users = UserStore(_config.db_path)
_state = ServerState(_config, _users, build_routes())

logging.basicConfig(level=_config.log_level,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def application(environ, start_response):
    """WSGI entry point."""
    method = environ["REQUEST_METHOD"]
    path = environ.get("PATH_INFO") or "/"
    if environ.get("QUERY_STRING"):
        path = f"{path}?{environ['QUERY_STRING']}"

    # Reconstruct headers (WSGI puts them in HTTP_* except a few special keys).
    headers: dict = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            name = key[5:].lower().replace("_", "-")
            headers[name] = value
    if environ.get("CONTENT_TYPE"):
        headers["content-type"] = environ["CONTENT_TYPE"]
    if environ.get("ORIGIN"):
        headers["origin"] = environ["ORIGIN"]

    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (ValueError, TypeError):
        length = 0
    body = environ["wsgi.input"].read(length) if length > 0 else b""
    client_ip = environ.get("REMOTE_ADDR", "127.0.0.1")

    status, resp_headers, resp_body = dispatch(
        _state, method, path, headers, body, client_ip)
    # WSGI requires "CODE REASON" (e.g. "200 OK"), not a bare integer.
    reason = http.HTTPStatus(status).phrase
    start_response(f"{status} {reason}", [(k, v) for k, v in resp_headers.items()])
    return [resp_body]
