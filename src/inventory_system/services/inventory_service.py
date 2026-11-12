"""Inventory service — high-level operations on products and stock levels."""

import csv
import math
import os
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from ..models.product import Product
from ..models.transaction import InventoryTransaction
from .database import InventoryDatabase

# Sales CSV contract (tscore data-contract.md v1): item, date, quantity, price.
# Column order may vary and extra columns are ignored; these four must exist.
SALES_CSV_COLUMNS = ("item", "date", "quantity", "price")

# Refuse absurd inputs before they are read into memory (a 50 MB sales CSV
# is already ~500k rows — far beyond any till export this app targets).
MAX_IMPORT_BYTES = 50 * 1024 * 1024


def csv_safe(value):
    """Neutralize spreadsheet formula injection on CSV export.

    Text cells starting with =, +, -, @, TAB or CR are prefixed with an
    apostrophe so Excel/Sheets treat them as text, not formulas (OWASP
    CSV-injection guidance). Non-str values (numbers) pass through untouched.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


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

    # ---- Sales CSV import (tscore data-contract v1) ---------------------
    def import_sales_csv(self, path: str, create_missing: bool = False) -> Dict:
        """Import historical sales rows (item, date, quantity, price).

        Records dated sale transactions WITHOUT touching current stock —
        see InventoryDatabase.add_transaction(apply_stock=False). Row-level
        problems are reported, never silently dropped; a file without the
        contract columns raises ValueError and imports nothing.

        Returns: {"imported": int, "created": int, "skipped": int,
                  "problems": [str, ...]}
        """
        if os.path.getsize(path) > MAX_IMPORT_BYTES:
            raise ValueError(
                f"sales CSV too large ({os.path.getsize(path)} bytes, "
                f"limit {MAX_IMPORT_BYTES})")
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                raw_header = reader.fieldnames or []
                # Headers may carry stray spaces from Excel exports (" item").
                header = [(h or "").strip() for h in raw_header]
                missing = [c for c in SALES_CSV_COLUMNS if c not in header]
                if missing:
                    raise ValueError(
                        f"not a contract sales CSV: missing column(s) {', '.join(missing)}")
                key_map = {(raw or "").strip(): raw for raw in raw_header}
                rows = [
                    {name: row.get(raw) for name, raw in key_map.items()}
                    for row in reader
                ]
        except UnicodeDecodeError:
            raise ValueError("file is not UTF-8 text — re-save it as UTF-8")
        except csv.Error as e:
            raise ValueError(f"malformed CSV: {e}")

        name_map = {
            (p.name or "").strip().casefold(): p.id
            for p in self.db.get_all_products()
        }
        imported = created = skipped = 0
        problems: List[str] = []

        def problem(msg: str) -> None:
            nonlocal skipped
            skipped += 1
            if len(problems) < 10:
                problems.append(msg)

        for i, row in enumerate(rows, start=2):  # start=2: row 1 is the header
            item = (row.get("item") or "").strip()
            raw_date = (row.get("date") or "").strip()
            raw_qty = (row.get("quantity") or "").strip()
            raw_price = (row.get("price") or "").strip()
            if not item:
                problem(f"row {i}: empty item")
                continue
            try:
                when = datetime.strptime(raw_date, "%Y-%m-%d")
            except ValueError:
                problem(f"row {i}: bad date {raw_date!r} (want YYYY-MM-DD)")
                continue
            if when.date() > date.today():
                problem(f"row {i}: future date {raw_date!r}")
                continue
            try:
                qty_f = float(raw_qty)  # Excel exports "2.0"; accept integral only
                if not math.isfinite(qty_f) or qty_f != int(qty_f):
                    raise ValueError
                qty = int(qty_f)
                if qty < 1:
                    raise ValueError
            except (ValueError, OverflowError):
                problem(f"row {i}: bad quantity {raw_qty!r} (want integer >= 1)")
                continue
            try:
                price = float(raw_price)
                if not math.isfinite(price) or price < 0:
                    raise ValueError
            except (ValueError, OverflowError):
                problem(f"row {i}: bad price {raw_price!r} (want finite number >= 0)")
                continue

            product = (
                self.db.get_product_by_sku(item)
                or self.db.get_product_by_barcode(item)
                or (self.db.get_product(name_map[item.casefold()])
                    if item.casefold() in name_map else None)
            )
            if product is None:
                if not create_missing:
                    problem(f"row {i}: unknown item {item!r}")
                    continue
                product = self.add_product({
                    "name": item, "unit_price": price, "quantity": 0,
                })
                name_map[item.casefold()] = product.id
                created += 1

            tx = InventoryTransaction(
                product_id=product.id,
                quantity_change=-qty,
                transaction_type="sale",
                notes=f"imported sale price={price:g}",
                timestamp=when,
            )
            self.db.add_transaction(tx, apply_stock=False)
            imported += 1

        return {"imported": imported, "created": created,
                "skipped": skipped, "problems": problems}

    # ---- Reporting --------------------------------------------------------
    def get_sales_history(self) -> List[tuple]:
        """All sale rows as (item_key, date, quantity) for tscore contracts.

        item_key prefers SKU (falls back to name) so values round-trip
        through find_product()/import resolution.
        """
        with self.db._connect() as conn:
            rows = conn.execute(
                """SELECT COALESCE(NULLIF(TRIM(p.sku), ''), p.name) AS item,
                          t.timestamp, t.quantity_change
                   FROM transactions t
                   JOIN products p ON p.id = t.product_id
                   WHERE t.transaction_type = 'sale'"""
            ).fetchall()
        out: List[tuple] = []
        for item, ts, qty in rows:
            when = datetime.fromisoformat(ts)
            out.append((item, when.date(), abs(int(qty))))
        return out

    def get_last_receipts(self) -> Dict[str, int]:
        """product_id -> qty of its most recent positive receipt.

        Approximates "last order" from deliveries (positive adjustments) —
        good enough for the multiple-of-last-order guard; corrections made
        with negative/positive adjusts can skew it (documented tradeoff).
        """
        with self.db._connect() as conn:
            rows = conn.execute(
                """SELECT product_id, quantity_change, timestamp
                   FROM transactions
                   WHERE quantity_change > 0 AND transaction_type != 'sale'
                   ORDER BY timestamp DESC"""
            ).fetchall()
        out: Dict[str, int] = {}
        for product_id, qty, _ in rows:
            if product_id not in out:
                out[product_id] = int(qty)
        return out

    # ---- Forecast decisions (approve/reject per weekly report) -----------
    def record_decision(self, item: str, report_date: str, suggested_qty: int,
                        decision: str) -> None:
        """Approve/reject a suggested reorder. Upserts per (item, report_date)
        so re-deciding in the same report replaces the first answer."""
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        with self.db._connect() as conn:
            conn.execute(
                """INSERT INTO forecast_decisions
                       (decision_id, item, report_date, suggested_qty,
                        decision, decided_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (item, report_date) DO UPDATE SET
                       decision = excluded.decision,
                       suggested_qty = excluded.suggested_qty,
                       decided_at = excluded.decided_at""",
                (str(uuid.uuid4()), item, report_date, int(suggested_qty),
                 decision, datetime.now().isoformat()),
            )
            conn.commit()

    def list_decisions(self, report_date: Optional[str] = None) -> List[Dict]:
        """Decisions as dicts, newest first; optionally one report's day."""
        query = ("SELECT item, report_date, suggested_qty, decision, decided_at "
                 "FROM forecast_decisions")
        params: tuple = ()
        if report_date is not None:
            query += " WHERE report_date = ?"
            params = (report_date,)
        query += " ORDER BY decided_at DESC"
        with self.db._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"item": r[0], "report_date": r[1], "suggested_qty": r[2],
                 "decision": r[3], "decided_at": r[4]} for r in rows]

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
