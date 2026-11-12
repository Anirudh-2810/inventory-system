"""Weekly report runner — shared by the CLI (`main.py forecast`) and the
GUI (Forecast screen). Exports sales history + current stock from the local
DB, runs the tscore `report.py` pipeline, and returns the output directory
containing report.txt + forecast.csv.

Repo roles (ShopBrain): StockOffline = app, tscore = forecasting code. This
module is the ONLY bridge between them (subprocess, contract CSVs on disk).
TSCORE_DIR overrides the automatic sibling-checkout lookup.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional


def find_tscore_dir() -> Path:
    """TSCORE_DIR env, else the dev layout <Brain>/tscore next to this repo."""
    env = os.getenv("TSCORE_DIR")
    if env:
        return Path(env)
    # .../<Brain>/inventory-system/src/inventory_system/services/forecast_service.py
    return Path(__file__).resolve().parents[4] / "tscore"


def run_weekly_report(svc, db_path: str, out_dir: Optional[str] = None,
                      budget: Optional[float] = None,
                      safety: Optional[float] = None,
                      lead_time: Optional[int] = None,
                      max_order: Optional[int] = None,
                      max_multiple: Optional[float] = None) -> Path:
    """Run the full report pipeline. Returns the output dir.

    Raises:
      FileNotFoundError - tscore checkout missing (actionable message)
      ValueError        - no sales history yet
      RuntimeError      - report.py failed
    """
    script = find_tscore_dir() / "scripts" / "report.py"
    if not script.is_file():
        raise FileNotFoundError(
            f"tscore not found at {find_tscore_dir()} - set TSCORE_DIR "
            "to the tscore checkout")
    hist = svc.get_sales_history()
    if not hist:
        raise ValueError("no sales history yet - run import-sales first")

    tmp = Path(tempfile.mkdtemp(prefix="sb_forecast_"))
    sales_csv = tmp / "sales.csv"
    with open(sales_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "date", "quantity", "price"])
        for item, d, qty in hist:
            w.writerow([item, d.isoformat(), qty, 0])

    receipts = svc.get_last_receipts()
    stock_csv = tmp / "stock.csv"
    with open(stock_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "on_hand", "unit_price", "last_order_qty"])
        for p in svc.list_products():
            key = (p.sku or "").strip() or p.name
            w.writerow([key, p.quantity, p.unit_price, receipts.get(p.id, "")])

    out = (Path(out_dir) if out_dir
           else Path(db_path).parent / "reports" / date.today().isoformat())
    cmd = [sys.executable, str(script), "--sales", str(sales_csv),
           "--stock", str(stock_csv), "--out-dir", str(out)]
    for flag, val in (("--budget", budget), ("--safety", safety),
                      ("--lead-time", lead_time), ("--max-order", max_order),
                      ("--max-multiple", max_multiple)):
        if val is not None:
            cmd += [flag, str(val)]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(
            f"report generation failed (tscore exit {proc.returncode})")
    return out


def read_forecast_rows(out_dir: Path):
    """forecast.csv -> [(item, predicted_demand, suggested_reorder, confidence)]."""
    path = Path(out_dir) / "forecast.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return [(r["item"], float(r["predicted_demand"]),
                 int(r["suggested_reorder"]), float(r["confidence"]))
                for r in csv.DictReader(f)]
