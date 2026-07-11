"""Inventory service — high-level operations on products and stock levels."""

from datetime import datetime
from typing import Dict, List, Optional

from ..models.product import Product
from ..models.transaction import InventoryTransaction
from .database import InventoryDatabase


class InventoryService:
    """Coordinates product tracking and stock-level changes."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = InventoryDatabase(db_path)

    # ---- Product tracking -------------------------------------------------
    def add_product(self, data: Dict, owner_id: str = "") -> Product:
        """Create a product from a dict of fields.

        `owner_id` scopes the product to a tenant (web) or is empty for the
        local offline user.
        """
        normalized = self._normalize_product(data)
        normalized["owner_id"] = owner_id
        product = Product.from_dict(normalized)
        return self.db.add_product(product)

    def get_product(self, product_id: str) -> Optional[Product]:
        return self.db.get_product(product_id)

    def find_product(self, identifier: str) -> Optional[Product]:
        """Resolve a product by its ID, SKU, or barcode."""
        return (
            self.db.get_product(identifier)
            or self.db.get_product_by_sku(identifier)
            or self.db.get_product_by_barcode(identifier)
        )

    def list_products(self, owner_id: Optional[str] = None) -> List[Product]:
        return self.db.get_all_products(owner_id)

    def update_product(self, product_id: str, data: Dict) -> Optional[Product]:
        existing = self.db.get_product(product_id)
        if not existing:
            return None
        # Merge only the fields the caller supplied (data already has the
        # correct Product field names) so untouched fields are preserved.
        merged = {**existing.to_dict(), **data, "id": product_id}
        merged["updated_at"] = datetime.now().isoformat()
        return self.db.update_product(Product.from_dict(merged))

    def delete_product(self, product_id: str) -> bool:
        return self.db.delete_product(product_id)

    # ---- Stock levels -----------------------------------------------------
    def adjust_stock(self, product_id: str, quantity_change: int, notes: str = "") -> Optional[Product]:
        """Apply a stock adjustment (positive = received, negative = removal)."""
        tx = InventoryTransaction(
            product_id=product_id,
            quantity_change=quantity_change,
            transaction_type="adjustment",
            notes=notes,
        )
        self.db.add_transaction(tx)
        return self.db.get_product(product_id)

    def record_sale(self, product_id: str, quantity: int, notes: str = "") -> Optional[Product]:
        """Record a sale (reduces stock)."""
        tx = InventoryTransaction(
            product_id=product_id,
            quantity_change=-abs(quantity),
            transaction_type="sale",
            notes=notes,
        )
        self.db.add_transaction(tx)
        return self.db.get_product(product_id)

    # ---- Reporting --------------------------------------------------------
    def get_stock_status(self, owner_id: Optional[str] = None) -> Dict:
        return self.db.get_stock_status(owner_id)

    def get_sales_report(self, owner_id: Optional[str] = None) -> List[Dict]:
        by_month = self.db.get_sales_by_month(owner_id)
        return [{"month": m, "units_sold": q} for m, q in by_month.items()]

    def report_by_category(self, owner_id: Optional[str] = None) -> List[Dict]:
        return self.db.report_by_category(owner_id)

    # ---- Helpers ----------------------------------------------------------
    @staticmethod
    def _normalize_product(data: Dict) -> Dict:
        """Map loose/alternate field names onto the Product schema."""
        return {
            "name": data.get("name", ""),
            "sku": data.get("sku", ""),
            "barcode": data.get("barcode", ""),
            "description": data.get("description", ""),
            "category": data.get("category", ""),
            "unit_price": float(data.get("unit_price") or data.get("price") or 0.0),
            "cost_price": float(data.get("cost_price") or 0.0),
            "quantity": int(data.get("quantity") or data.get("stock") or 0),
            "reorder_level": int(data.get("reorder_level") or 0),
            "supplier": data.get("supplier", ""),
        }
