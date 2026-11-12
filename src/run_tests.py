"""Smoke-test runner for the inventory system."""

import os
import tempfile
from pathlib import Path

from inventory_system import InventoryService


def main():
    tmp = os.path.join(tempfile.gettempdir(), "inventory_test.db")
    if os.path.exists(tmp):
        os.remove(tmp)

    svc = InventoryService(tmp)

    p1 = svc.add_product({
        "name": "Wireless Mouse", "sku": "WM-001", "barcode": "1234567890",
        "category": "Electronics",
        "unit_price": 25.0, "cost_price": 12.0, "quantity": 100, "reorder_level": 20,
    })
    p2 = svc.add_product({
        "name": "USB Cable", "sku": "UC-002", "barcode": "0987654321",
        "category": "Electronics",
        "unit_price": 8.0, "cost_price": 3.0, "quantity": 5, "reorder_level": 10,
    })
    print("[OK] Added:", p1.name, "/", p2.name)

    svc.record_sale(p1.id, 10)
    assert svc.get_product(p1.id).quantity == 90
    print("[OK] Sale recorded ->", svc.get_product(p1.id).quantity)

    status = svc.get_stock_status()
    assert status["total_products"] == 2 and status["low_stock_products"] == 1
    print("[OK] Stock status:", status)

    assert svc.report_by_category()[0]["category"] == "Electronics"
    print("[OK] Category report:", svc.report_by_category())

    assert svc.get_sales_report()[0]["units_sold"] == 10
    print("[OK] Sales report:", svc.get_sales_report())

    svc.adjust_stock(p2.id, 50)
    assert svc.get_product(p2.id).quantity == 55
    print("[OK] Adjusted ->", svc.get_product(p2.id).quantity)

    # Resolve by SKU and by barcode (not just id)
    assert svc.find_product("UC-002").id == p2.id
    assert svc.find_product("1234567890").id == p1.id
    print("[OK] find_product by SKU and barcode")

    # Edit via partial update
    svc.update_product(p1.id, {"unit_price": 27.5})
    assert svc.get_product(p1.id).unit_price == 27.5
    print("[OK] Updated price ->", svc.get_product(p1.id).unit_price)

    # Oversell guard
    try:
        svc.record_sale(p2.id, 9999)
        raise AssertionError("expected oversell to be rejected")
    except ValueError:
        print("[OK] Oversell rejected")

    svc.delete_product(p2.id)
    assert svc.get_product(p2.id) is None
    print("[OK] Deleted product")

    # -- Sales CSV import (tscore data-contract v1) ----------------------
    sales_csv = os.path.join(tempfile.gettempdir(), "inventory_sales_test.csv")
    with open(sales_csv, "w", newline="") as f:
        f.write("item,date,quantity,price\n")
        f.write("WM-001,2026-10-01,5,25.00\n")       # resolves by SKU
        f.write("WM-001,not-a-date,1,25.00\n")       # bad date -> problem
        f.write("GHOST-ITEM,2026-10-03,2,10.00\n")   # unknown -> skipped
    summary = svc.import_sales_csv(sales_csv)
    assert summary["imported"] == 1, summary
    assert summary["skipped"] == 2, summary
    assert len(summary["problems"]) == 2, summary
    assert svc.get_product(p1.id).quantity == 90, "import must not touch stock"
    monthly = {r["month"]: r["units_sold"] for r in svc.get_sales_report()}
    assert monthly.get("2026-10") == 5, monthly
    print("[OK] Sales CSV import:", summary)

    # create_missing path
    with open(sales_csv, "w", newline="") as f:
        f.write("item,date,quantity,price\n")
        f.write("NEW-ITEM-9,2026-10-04,3,99.00\n")
    summary = svc.import_sales_csv(sales_csv, create_missing=True)
    assert summary["imported"] == 1 and summary["created"] == 1, summary
    assert any(p.name == "NEW-ITEM-9" for p in svc.list_products())
    print("[OK] Import with --create-missing:", summary)

    # header-less file is a hard error, imports nothing
    with open(sales_csv, "w", newline="") as f:
        f.write("foo,bar\n1,2\n")
    try:
        svc.import_sales_csv(sales_csv)
        raise AssertionError("expected ValueError for non-contract CSV")
    except ValueError:
        print("[OK] Non-contract CSV rejected")

    # edge cases: Excel-style spaced headers, "2.0" qty, nan/inf price
    with open(sales_csv, "w", newline="", encoding="utf-8") as f:
        f.write(" item , date , quantity , price \n")
        f.write("WM-001,2026-10-05,2.0,25.00\n")   # integral float qty -> ok
        f.write("WM-001,2026-10-06,2.5,25.00\n")   # fractional qty -> problem
        f.write("WM-001,2026-10-07,1,nan\n")       # NaN price -> problem
        f.write("WM-001,2026-10-08,1,inf\n")       # Inf price -> problem
    summary = svc.import_sales_csv(sales_csv)
    assert summary["imported"] == 1, summary
    assert summary["skipped"] == 3, summary
    print("[OK] Import edges (spaced header, 2.0 qty, nan/inf price):", summary)

    # non-UTF8 file -> clean ValueError, not a UnicodeDecodeError traceback
    with open(sales_csv, "wb") as f:
        f.write(b"item,date,quantity,price\nCaf\xe9,2026-10-05,1,2.00\n")
    try:
        svc.import_sales_csv(sales_csv)
        raise AssertionError("expected ValueError for non-UTF8 CSV")
    except ValueError:
        print("[OK] Non-UTF8 CSV rejected cleanly")

    # CSV formula injection neutralized on export
    from inventory_system import csv_safe
    assert csv_safe("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
    assert csv_safe("+1234") == "'+1234"
    assert csv_safe(42) == 42 and csv_safe(3.5) == 3.5
    assert csv_safe("Plain Name") == "Plain Name"
    print("[OK] csv_safe formula-injection guard")

    # -- Weekly report via tscore (skip when the sibling repo is absent) --
    ts_dir = Path(__file__).resolve().parents[2] / "tscore"
    if (ts_dir / "scripts" / "report.py").is_file():
        import subprocess
        import sys as _sys
        out_dir = os.path.join(tempfile.gettempdir(), "sb_report_test")
        proc = subprocess.run(
            [_sys.executable, os.path.join(os.path.dirname(__file__), "main.py"),
             "forecast", "--out", out_dir, "--budget", "100000"],
            capture_output=True, text=True,
            env={**os.environ, "INVENTORY_DB_PATH": tmp})
        assert proc.returncode == 0, proc.stderr or proc.stdout
        report = os.path.join(out_dir, "report.txt")
        forecast = os.path.join(out_dir, "forecast.csv")
        assert os.path.isfile(report) and os.path.isfile(forecast)
        with open(forecast, newline="", encoding="utf-8") as f:
            header = f.readline().strip()
        assert header == "item,predicted_demand,suggested_reorder,confidence", header
        assert "ORDER THIS WEEK" in open(report, encoding="utf-8").read()
        print("[OK] Weekly report generated via tscore")
    else:
        print("[SKIP] tscore repo not found - forecast test skipped")

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
