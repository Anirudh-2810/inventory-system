"""Secure, dependency-free web/API tier for the offline inventory system.

This package adds an HTTP API on top of the same SQLite database the CLI/GUI
use. It has ZERO third-party dependencies (standard library only) so it runs
anywhere the offline app runs — no pip install, no internet required.

Security is enforced here, not assumed:
  * JWT auth on every protected route (auth.py)
  * Ownership checks on every inventory record (prevents IDOR)
  * Server-side role checks (prevents privilege escalation)
  * Security headers, restricted CORS, rate limiting, correlation IDs
"""

from .config import Config

__all__ = ["Config"]
