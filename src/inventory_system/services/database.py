"""SQLite persistence layer for the inventory system.

Fully offline: all data lives in a single local file, no network access.
"""

from pathlib import Path
from typing import Dict, List, Optional

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from ..models.product import Product
from ..models.transaction import InventoryTransaction


class InventoryDatabase:
    """Thin, dependency-free SQLite wrapper around products + transactions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_file = Path(db_path or "inventory.db")
        self._initialize_db()

    # -- connection -------------------------------------------------------
    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_file)
        try:
            yield conn
        finally:
            conn.close()

    def _fetch_one(self, sql: str, params=()) -> Optional[Product]:
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description]
            return Product.from_dict(dict(zip(cols, row)))

    def _fetch_all(self, sql: str, params=()) -> List[Product]:
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [Product.from_dict(dict(zip(cols, row))) for row in cur.fetchall()]

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    sku           TEXT,
                    barcode       TEXT,
                    description   TEXT,
                    category      TEXT,
                    unit_price    REAL NOT NULL,
                    cost_price    REAL NOT NULL,
                    quantity      INTEGER NOT NULL DEFAULT 0,
                    reorder_level INTEGER NOT NULL DEFAULT 0,
                    supplier      TEXT,
                    owner_id      TEXT,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id   TEXT PRIMARY KEY,
                    product_id       TEXT NOT NULL,
                    quantity_change  INTEGER NOT NULL,
                    transaction_type TEXT NOT NULL,
                    notes            TEXT,
                    timestamp        TEXT NOT NULL,
                    FOREIGN KEY (product_id) REFERENCES products (id)
                );
                """
            )
            conn.commit()
            # Migrations FIRST: older DBs predate these columns, and the
            # indexes below reference them (index-before-migration crashed
            # every legacy DB at startup).
            cols = [r[1] for r in conn.execute("PRAGMA table_info(products)")]
            if "barcode" not in cols:
                conn.execute("ALTER TABLE products ADD COLUMN barcode TEXT")
                conn.commit()
            if "owner_id" not in cols:
                conn.execute("ALTER TABLE products ADD COLUMN owner_id TEXT")
                conn.commit()
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_tx_time      ON transactions (timestamp);
                CREATE INDEX IF NOT EXISTS idx_prod_supplier ON products (supplier);
                CREATE INDEX IF NOT EXISTS idx_prod_owner    ON products (owner_id);
                """
            )
            conn.commit()

    # -- products ---------------------------------------------------------
    def add_product(self, product: Product) -> Product:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO products
                   (id, name, sku, barcode, description, category, unit_price,
                    cost_price, quantity, reorder_level, supplier, owner_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (product.id, product.name, product.sku, product.barcode,
                 product.description, product.category, product.unit_price,
                 product.cost_price, product.quantity, product.reorder_level,
                 product.supplier, product.owner_id, product.created_at.isoformat(),
                 product.updated_at.isoformat()),
            )
            conn.commit()
        return self.get_product(product.id)

    def get_product(self, product_id: str) -> Optional[Product]:
        return self._fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))

    def get_product_by_sku(self, sku: str) -> Optional[Product]:
        return self._fetch_one("SELECT * FROM products WHERE sku = ?", (sku,))

    def get_product_by_barcode(self, barcode: str) -> Optional[Product]:
        return self._fetch_one("SELECT * FROM products WHERE barcode = ?", (barcode,))

    def get_all_products(self, owner_id: Optional[str] = None) -> List[Product]:
        if owner_id is not None:
            return self._fetch_all(
                "SELECT * FROM products WHERE owner_id = ? ORDER BY name", (owner_id,))
        return self._fetch_all("SELECT * FROM products ORDER BY name")

    def update_product(self, product: Product) -> Product:
        with self._connect() as conn:
            conn.execute(
                """UPDATE products SET
                     name=?, sku=?, barcode=?, description=?, category=?,
                     unit_price=?, cost_price=?, quantity=?, reorder_level=?,
                     supplier=?, updated_at=?
                   WHERE id=?""",
                (product.name, product.sku, product.barcode, product.description,
                 product.category, product.unit_price, product.cost_price,
                 product.quantity, product.reorder_level, product.supplier,
                 product.updated_at.isoformat(), product.id),
            )
            conn.commit()
        return self.get_product(product.id)

    def delete_product(self, product_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()
            return cur.rowcount > 0

    # -- transactions (atomic: row + stock update together) ---------------
    def add_transaction(self, tx: InventoryTransaction,
                        apply_stock: bool = True) -> InventoryTransaction:
        """Insert a transaction.

        apply_stock=True (default): live operation — the product's quantity
        moves with the transaction and oversell is rejected.
        apply_stock=False: historical import — the row is recorded with its
        own timestamp but current stock is left alone (the shop's counted
        stock already reflects past sales; re-applying them would double-count).
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO transactions
                   (transaction_id, product_id, quantity_change,
                    transaction_type, notes, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tx.transaction_id, tx.product_id, tx.quantity_change,
                 tx.transaction_type, tx.notes, tx.timestamp.isoformat()),
            )
            cur = conn.execute(
                "SELECT quantity FROM products WHERE id = ?", (tx.product_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Unknown product: {tx.product_id}")
            if apply_stock:
                new_qty = row[0] + tx.quantity_change
                if new_qty < 0:
                    raise ValueError(
                        f"Not enough stock for {tx.product_id}: {row[0]} + {tx.quantity_change}")
                conn.execute(
                    "UPDATE products SET quantity=?, updated_at=? WHERE id=?",
                    (new_qty, datetime.now().isoformat(), tx.product_id),
                )
            conn.commit()
        return tx

    # -- reporting --------------------------------------------------------
    def get_stock_status(self, owner_id: Optional[str] = None) -> Dict[str, object]:
        with self._connect() as conn:
            if owner_id is not None:
                total, low, out = conn.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN quantity <= reorder_level THEN 1 ELSE 0 END),
                              SUM(CASE WHEN quantity = 0 THEN 1 ELSE 0 END)
                       FROM products WHERE owner_id = ?""", (owner_id,)
                ).fetchone()
            else:
                total, low, out = conn.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN quantity <= reorder_level THEN 1 ELSE 0 END),
                              SUM(CASE WHEN quantity = 0 THEN 1 ELSE 0 END)
                       FROM products"""
                ).fetchone()
        total = total or 0
        low = low or 0
        out = out or 0
        return {
            "total_products": total,
            "low_stock_products": low,
            "out_of_stock_products": out,
            "low_stock_percentage": round(low / total * 100, 2) if total else 0.0,
            "out_of_stock_percentage": round(out / total * 100, 2) if total else 0.0,
        }

    def get_sales_by_month(self, owner_id: Optional[str] = None) -> Dict[str, int]:
        with self._connect() as conn:
            if owner_id is not None:
                rows = conn.execute(
                    """SELECT strftime('%Y-%m', t.timestamp) AS month,
                              SUM(ABS(t.quantity_change)) AS units
                       FROM transactions t
                       JOIN products p ON t.product_id = p.id
                       WHERE t.transaction_type = 'sale' AND p.owner_id = ?
                       GROUP BY month ORDER BY month""", (owner_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT strftime('%Y-%m', timestamp) AS month,
                              SUM(ABS(quantity_change)) AS units
                       FROM transactions
                       WHERE transaction_type = 'sale'
                       GROUP BY month ORDER BY month"""
                ).fetchall()
        return {month: units for month, units in rows}

    def report_by_category(self, owner_id: Optional[str] = None) -> List[Dict[str, object]]:
        with self._connect() as conn:
            if owner_id is not None:
                rows = conn.execute(
                    """SELECT COALESCE(category, 'Unspecified') AS category,
                              COUNT(*) AS products,
                              SUM(quantity) AS qty,
                              SUM(CASE WHEN quantity <= reorder_level THEN 1 ELSE 0 END) AS low
                       FROM products WHERE owner_id = ?
                       GROUP BY category ORDER BY products DESC""", (owner_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT COALESCE(category, 'Unspecified') AS category,
                              COUNT(*) AS products,
                              SUM(quantity) AS qty,
                              SUM(CASE WHEN quantity <= reorder_level THEN 1 ELSE 0 END) AS low
                       FROM products GROUP BY category ORDER BY products DESC"""
                ).fetchall()
        return [
            {"category": c, "products": p, "quantity": q, "low_stock": l}
            for c, p, q, l in rows
        ]
