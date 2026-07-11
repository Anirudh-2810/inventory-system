"""Application assembly: builds the route table and runs the web tier."""

import re
import logging

from .config import Config
from .server import run_server, Route
from .store import UserStore
from . import handlers as H


def build_routes() -> list:
    """Ordered route table. More specific paths must precede generic ones."""
    return [
        # --- Auth (public, rate-limited) ---
        ("POST", re.compile(r"^/api/auth/signup$"), H.signup, False, None, "signup"),
        ("POST", re.compile(r"^/api/auth/login$"), H.login, False, None, "login"),
        ("POST", re.compile(r"^/api/auth/reset-request$"), H.reset_request, False, None, "reset"),
        ("POST", re.compile(r"^/api/auth/reset-confirm$"), H.reset_confirm, False, None, "default"),
        ("POST", re.compile(r"^/api/auth/refresh$"), H.refresh, False, None, "default"),
        ("POST", re.compile(r"^/api/auth/logout$"), H.logout, True, None, "default"),

        # --- Inventory (protected + ownership-checked) ---
        ("GET", re.compile(r"^/api/products$"), H.list_products, True, None, "default"),
        ("POST", re.compile(r"^/api/products$"), H.create_product, True, None, "default"),
        ("POST", re.compile(r"^/api/products/[^/]+/sale$"), H.sale_product, True, None, "default"),
        ("POST", re.compile(r"^/api/products/[^/]+/adjust$"), H.adjust_product, True, None, "default"),
        ("GET", re.compile(r"^/api/products/[^/]+$"), H.get_product, True, None, "default"),
        ("PATCH", re.compile(r"^/api/products/[^/]+$"), H.update_product, True, None, "default"),
        ("DELETE", re.compile(r"^/api/products/[^/]+$"), H.delete_product, True, None, "default"),
        ("GET", re.compile(r"^/api/stock-status$"), H.stock_status, True, None, "default"),
        ("GET", re.compile(r"^/api/report$"), H.report, True, None, "default"),

        # --- Payments (server-side verification) ---
        ("POST", re.compile(r"^/api/payments/calculate$"), H.payment_calculate, True, None, "default"),
        # Webhook is called by the payment provider, not our users: no JWT,
        # protected by signature verification inside the handler.
        ("POST", re.compile(r"^/api/payments/webhook$"), H.payment_webhook, False, None, "default"),

        # --- Health (public, no system info) ---
        ("GET", re.compile(r"^/api/health$"), H.health, False, None, "default"),
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    config = Config()
    users = UserStore(config.db_path)
    routes = build_routes()
    run_server(config, users, routes)


if __name__ == "__main__":
    main()
