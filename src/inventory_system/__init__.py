"""Offline inventory management system package."""

__version__ = "0.1.0"

from .services.inventory_service import InventoryService, csv_safe
from .models.product import Product
from .models.transaction import InventoryTransaction

__all__ = ["InventoryService", "csv_safe", "Product", "InventoryTransaction", "__version__"]
