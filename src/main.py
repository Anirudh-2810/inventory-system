"""Minimal offline inventory CLI.

Commands:
  add      add a product
  list     show all products
  edit     update a product's fields        (by id or sku)
  delete   remove a product                 (by id or sku)
  sale     record a sale  (reduces stock)
  restock  receive stock  (+qty)
  adjust   correct stock   (+/-)
  status   stock health at a glance
  report   category + sales breakdown
  export   write inventory.csv
  import-sales  import a sales CSV (item,date,quantity,price)
  forecast weekly reorder report (via the tscore repo)

Examples:
  python main.py add --name "Widget" --price 9.99 --stock 100 --sku W-1 --reorder 20
  python main.py sale --id W-1 --qty 5
  python main.py restock --id W-1 --qty 50
  python main.py forecast --budget 5000
  python main.py report
"""

import argparse
import csv
import logging
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

# --- Environment validation -------------------------------------------------
# Load environment variables (optionally from .env file if python-dotenv is available)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # No dotenv installed; rely on OS environment

# Helpers for secure failure reporting (no internal details leak to client)
def fail(message: str) -> None:
    """Log a generic error with a correlation ID; never expose internals."""
    correlation_id = str(uuid.uuid4())
    logger.error("Correlation ID %s: %s", correlation_id, message)
    print(f"Error: {message} (ref: {correlation_id[:8]})", file=sys.stderr)
    sys.exit(1)

# Validate critical environment variables before proceeding
DB_PATH = os.getenv("INVENTORY_DB_PATH")
if not DB_PATH:
    if getattr(sys, "frozen", False):
        DB_PATH = os.path.join(os.path.dirname(sys.executable), "inventory.db")
    else:
        fail("Configuration error: database path not set")

# Debug mode must default to OFF
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
if DEBUG:
    logger.warning("DEBUG mode is ON — disable in production")

# Configure logging (no sensitive data is logged)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inventory_system import InventoryService, csv_safe


# -- helpers --------------------------------------------------------------
def svc() -> InventoryService:
    return InventoryService(DB_PATH)


def resolve(identifier: str):
    product = svc().find_product(identifier)
    if product is None:
        fail(f"Product not found: {identifier}")
    return product


def print_table(products):
    if not products:
        print("No products yet. Add one:  python main.py add --name \"...\"")
        return
    rows = [
        (p.sku or "-", p.name, p.quantity, p.reorder_level, "LOW" if p.is_low_stock else "")
        for p in products
    ]
    headers = ("SKU", "NAME", "QTY", "REORDER", "FLAG")
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))


# -- commands -------------------------------------------------------------
def cmd_add(a):
    p = svc().add_product({
        "name": a.name, "sku": a.sku or "", "barcode": a.barcode or "",
        "category": a.category or "",
        "unit_price": a.price, "cost_price": a.cost, "quantity": a.stock,
        "reorder_level": a.reorder, "supplier": a.supplier or "",
    })
    print(f"Added {p.sku or p.id[:8]} | {p.name}")


def cmd_list(a):
    print_table(svc().list_products())


def cmd_edit(a):
    p = resolve(a.id)
    updates = {}
    for field, val in (("name", a.name), ("sku", a.sku), ("barcode", a.barcode),
                       ("category", a.category), ("supplier", a.supplier),
                       ("unit_price", a.price), ("cost_price", a.cost),
                       ("quantity", a.stock), ("reorder_level", a.reorder)):
        if val is not None:
            updates[field] = val
    p = svc().update_product(p.id, updates)
    print(f"Updated {p.sku or p.id[:8]} | {p.name}")


def cmd_delete(a):
    p = resolve(a.id)
    svc().delete_product(p.id)
    print(f"Deleted {p.sku or p.id[:8]} | {p.name}")


def cmd_sale(a):
    p = resolve(a.id)
    try:
        p = svc().record_sale(p.id, a.qty)
    except ValueError as e:
        fail(str(e))
    print(f"Sold {a.qty} | {p.name} -> {p.quantity} left")


def cmd_adjust(a):
    p = resolve(a.id)
    try:
        p = svc().adjust_stock(p.id, a.qty, notes=a.reason or "")
    except ValueError as e:
        fail(str(e))
    print(f"Adjusted {a.qty:+d} | {p.name} -> {p.quantity}")


def cmd_restock(a):
    if a.qty < 1:
        fail("restock qty must be >= 1 (use adjust for removals)")
    p = resolve(a.id)
    try:
        p = svc().adjust_stock(p.id, a.qty, notes=a.reason or "restock")
    except ValueError as e:
        fail(str(e))
    print(f"Restocked {a.qty} | {p.name} -> {p.quantity}")


def cmd_status(a):
    s = svc().get_stock_status()
    print(f"Products      : {s['total_products']}")
    print(f"Low stock     : {s['low_stock_products']} ({s['low_stock_percentage']}%)")
    print(f"Out of stock  : {s['out_of_stock_products']} ({s['out_of_stock_percentage']}%)")


def cmd_report(a):
    print("By category")
    for c in svc().report_by_category():
        print(f"  {c['category']:<14} {c['products']} products  {c['quantity']} units  {c['low_stock']} low")
    print("\nSales by month")
    sales = svc().get_sales_report()
    print("  (none yet)" if not sales else "\n".join(
        f"  {r['month']}  {r['units_sold']} units" for r in sales))


def cmd_export(a):
    products = svc().list_products()
    out = a.file or os.path.join(os.path.dirname(DB_PATH), "inventory.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "category", "quantity",
                    "reorder_level", "unit_price", "cost_price", "supplier"])
        for p in products:
            w.writerow([csv_safe(p.sku), csv_safe(p.name), csv_safe(p.category),
                        p.quantity, p.reorder_level, p.unit_price,
                        p.cost_price, csv_safe(p.supplier)])
    print(f"Exported {len(products)} products -> {out}")


def cmd_import_sales(a):
    if not os.path.isfile(a.file):
        fail(f"No such file: {a.file}")
    try:
        summary = svc().import_sales_csv(a.file, create_missing=a.create_missing)
    except (ValueError, OSError) as e:
        fail(str(e))
    print(f"Imported {summary['imported']} sales rows"
          + (f" (created {summary['created']} new items)" if summary["created"] else "")
          + f", skipped {summary['skipped']}")
    for p in summary["problems"]:
        print(f"  ! {p}", file=sys.stderr)
    if summary["skipped"] > len(summary["problems"]):
        print(f"  ! ...and {summary['skipped'] - len(summary['problems'])} more skipped rows",
              file=sys.stderr)


def _tscore_dir() -> Path:
    """Where the tscore forecasting repo lives (override: TSCORE_DIR)."""
    env = os.getenv("TSCORE_DIR")
    if env:
        return Path(env)
    # dev layout: <Brain>/inventory-system/src/main.py -> <Brain>/tscore
    return Path(__file__).resolve().parents[2] / "tscore"


def cmd_forecast(a):
    """Weekly reorder report: export history+stock -> tscore report.py -> print."""
    script = _tscore_dir() / "scripts" / "report.py"
    if not script.is_file():
        fail(f"tscore not found at {_tscore_dir()} - set TSCORE_DIR "
             "to the tscore checkout")
    s = svc()
    hist = s.get_sales_history()
    if not hist:
        fail("no sales history yet - run import-sales first")
    tmp = Path(tempfile.mkdtemp(prefix="sb_forecast_"))
    sales_csv = tmp / "sales.csv"
    with open(sales_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "date", "quantity", "price"])
        for item, d, qty in hist:
            w.writerow([item, d.isoformat(), qty, 0])
    receipts = s.get_last_receipts()
    stock_csv = tmp / "stock.csv"
    with open(stock_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "on_hand", "unit_price", "last_order_qty"])
        for p in s.list_products():
            key = (p.sku or "").strip() or p.name
            w.writerow([key, p.quantity, p.unit_price, receipts.get(p.id, "")])
    out_dir = (Path(a.out) if a.out
               else Path(DB_PATH).parent / "reports" / date.today().isoformat())
    cmd = [sys.executable, str(script), "--sales", str(sales_csv),
           "--stock", str(stock_csv), "--out-dir", str(out_dir)]
    for flag, val in (("--budget", a.budget), ("--safety", a.safety),
                      ("--lead-time", a.lead_time),
                      ("--max-order", a.max_order),
                      ("--max-multiple", a.max_multiple)):
        if val is not None:
            cmd += [flag, str(val)]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        fail(f"report generation failed (tscore exit {proc.returncode})")


# -- parser ---------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="inventory", description="Offline inventory manager")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="add a product")
    a.add_argument("--name", required=True)
    a.add_argument("--price", type=float, required=True)
    a.add_argument("--stock", type=int, default=0)
    a.add_argument("--sku")
    a.add_argument("--barcode")
    a.add_argument("--category")
    a.add_argument("--cost", type=float, default=0.0)
    a.add_argument("--reorder", type=int, default=0)
    a.add_argument("--supplier")
    a.set_defaults(func=cmd_add)

    sub.add_parser("list", help="list products").set_defaults(func=cmd_list)

    e = sub.add_parser("edit", help="edit a product (by id or sku)")
    e.add_argument("--id", required=True)
    e.add_argument("--name")
    e.add_argument("--price", type=float)
    e.add_argument("--cost", type=float)
    e.add_argument("--stock", type=int)
    e.add_argument("--reorder", type=int)
    e.add_argument("--category")
    e.add_argument("--supplier")
    e.add_argument("--sku")
    e.add_argument("--barcode")
    e.set_defaults(func=cmd_edit)

    d = sub.add_parser("delete", help="delete a product (by id or sku)")
    d.add_argument("--id", required=True)
    d.set_defaults(func=cmd_delete)

    s = sub.add_parser("sale", help="record a sale")
    s.add_argument("--id", required=True)
    s.add_argument("--qty", type=int, required=True)
    s.set_defaults(func=cmd_sale)

    ad = sub.add_parser("adjust", help="adjust stock (+/-)")
    ad.add_argument("--id", required=True)
    ad.add_argument("--qty", type=int, required=True)
    ad.add_argument("--reason", default="", help="note recorded on the transaction")
    ad.set_defaults(func=cmd_adjust)

    rs = sub.add_parser("restock", help="receive stock (+qty)")
    rs.add_argument("--id", required=True)
    rs.add_argument("--qty", type=int, required=True)
    rs.add_argument("--reason", default="", help="note recorded on the transaction")
    rs.set_defaults(func=cmd_restock)

    sub.add_parser("status", help="stock health").set_defaults(func=cmd_status)
    sub.add_parser("report", help="reports").set_defaults(func=cmd_report)

    ex = sub.add_parser("export", help="export inventory.csv")
    ex.add_argument("--file")
    ex.set_defaults(func=cmd_export)

    im = sub.add_parser(
        "import-sales",
        help="import a sales CSV (contract: item,date,quantity,price)")
    im.add_argument("--file", required=True, help="path to the sales CSV")
    im.add_argument("--create-missing", action="store_true",
                    help="create a product for items not in the catalog")
    im.set_defaults(func=cmd_import_sales)

    fc = sub.add_parser(
        "forecast",
        help="weekly reorder report (needs the tscore repo; TSCORE_DIR)")
    fc.add_argument("--out", help="output dir (default <db dir>/reports/<today>)")
    fc.add_argument("--budget", type=float, help="weekly spend cap")
    fc.add_argument("--safety", type=float, help="safety buffer fraction")
    fc.add_argument("--lead-time", type=int, help="delivery weeks to cover")
    fc.add_argument("--max-order", type=int, help="per-line qty cap")
    fc.add_argument("--max-multiple", type=float, help="cap = this x last order")
    fc.set_defaults(func=cmd_forecast)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
