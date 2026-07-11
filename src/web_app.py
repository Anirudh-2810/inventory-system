"""Entrypoint for the StockOffline secure web/API tier.

Usage (from the src/ directory):
    python web_app.py

Requires INVENTORY_DB_PATH and JWT_SECRET_KEY in the environment (see .env.example).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import main

if __name__ == "__main__":
    main()
