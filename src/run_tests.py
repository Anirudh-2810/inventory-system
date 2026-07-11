"""Smoke-test runner for the inventory system."""

import os
import tempfile

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

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
