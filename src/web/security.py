"""Shared security helpers for the web tier: auth, rate limiting, headers, errors.

These are deliberately small and explicit so the security posture is auditable.
"""

import time
import uuid
import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

import auth

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def get_bearer_token(headers: Dict[str, str]) -> Optional[str]:
    """Extract a Bearer token from the Authorization header."""
    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[len("Bearer "):].strip() or None


def authenticate(headers: Dict[str, str]) -> Optional[Dict]:
    """Validate the request's JWT. Returns the payload or None."""
    token = get_bearer_token(headers)
    if not token:
        return None
    return auth.verify_jwt(token)


# --------------------------------------------------------------------------- #
# Rate limiting (in-memory, per client IP + route group)
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self, limits: Dict[str, Tuple[int, int]]) -> None:
        self.limits = limits
        self.hits: Dict[str, deque] = defaultdict(deque)

    def is_allowed(self, key: str, group: str = "default") -> bool:
        limit, window = self.limits.get(group, self.limits["default"])
        now = time.time()
        dq = self.hits[key]
        # Drop timestamps outside the window.
        while dq and dq[0] <= now - window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


# --------------------------------------------------------------------------- #
# Security headers + CORS
# --------------------------------------------------------------------------- #
def build_headers(allowed_origins: List[str], origin: Optional[str],
                  extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Construct response headers with secure defaults + CORS."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "Content-Type": "application/json; charset=utf-8",
    }
    # CORS: only echo a precisely allowed origin (never "*").
    if origin and origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
        headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    if extra:
        headers.update(extra)
    return headers


# --------------------------------------------------------------------------- #
# Error responses (generic to client, detailed to server log)
# --------------------------------------------------------------------------- #
def error_response(status: int, message: str) -> Tuple[int, Dict[str, str], bytes]:
    correlation_id = str(uuid.uuid4())[:8]
    logger.error("Correlation %s: %s (status %d)", correlation_id, message, status)
    body = __import__("json").dumps({
        "error": message,
        "ref": correlation_id,
    }).encode("utf-8")
    return status, {"Content-Type": "application/json; charset=utf-8"}, body
