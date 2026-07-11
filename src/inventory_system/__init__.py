"""Offline inventory management system package."""

__version__ = "0.1.0"

from .services.inventory_service import InventoryService
from .models.product import Product
from .models.transaction import InventoryTransaction

__all__ = ["InventoryService", "Product", "InventoryTransaction", "__version__"]
