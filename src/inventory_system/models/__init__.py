"""Data models for the inventory management system."""

from .product import Product
from .transaction import InventoryTransaction

__all__ = ['Product', 'InventoryTransaction']