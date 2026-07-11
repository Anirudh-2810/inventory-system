"""Environment-driven configuration for the web tier.

All values come from the environment (see .env.example). The app refuses to
start if a critical value is missing, and DEBUG defaults to False.
"""

import os
import logging
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

PLACEHOLDER_SECRET = "replace-with-strong-random-secret"


class Config:
    """Validated runtime configuration."""

    def __init__(self) -> None:
        db_path = os.getenv("INVENTORY_DB_PATH")
        if not db_path:
            raise RuntimeError(
                "INVENTORY_DB_PATH must be set (copy .env.example to .env)"
            )
        self.db_path: str = db_path

        secret = os.getenv("JWT_SECRET_KEY")
        if not secret or secret == PLACEHOLDER_SECRET:
            # Never run a web tier with a publicly-known secret.
            raise RuntimeError(
                "JWT_SECRET_KEY must be set to a strong random value in .env"
            )
        self.jwt_secret: str = secret

        self.debug: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

        lvl = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_level: int = getattr(logging, lvl, logging.INFO)

        self.host: str = os.getenv("WEB_HOST", "127.0.0.1")
        try:
            self.port: int = int(os.getenv("WEB_PORT", "8000"))
        except ValueError:
            raise RuntimeError("WEB_PORT must be an integer")

        # CORS: only these exact origins may call the API.
        raw_origins = os.getenv("ALLOWED_ORIGINS", "")
        self.allowed_origins: List[str] = [
            o.strip() for o in raw_origins.split(",") if o.strip()
        ]

        # Rate limits (requests per window). Keyed by route group + client IP.
        self.rate = {
            "login": (5, 60),       # 5 / minute
            "signup": (3, 3600),    # 3 / hour
            "reset": (3, 3600),     # 3 / hour
            "default": (60, 60),    # 60 / minute
        }

        if self.debug:
            logger.warning("WEB DEBUG mode is ON — disable in production")
