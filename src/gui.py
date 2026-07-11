"""Soft, minimal Tkinter GUI for the offline inventory system.

Run:
    python gui.py

Barcode scanners that act as a keyboard (the common USB kind) simply type
the code into the Scan box and press Enter, so no extra hardware library is
needed. The same box also searches by SKU or name.

All data stays local (inventory.db) - no network access.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from inventory_system import InventoryService

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

# -- soft palette ---------------------------------------------------------
BG = "#f4f6f8"        # window background
PANEL = "#ffffff"     # cards / frames
ACCENT = "#3b82f6"    # buttons / highlight
ACCENT_DK = "#2563eb"
TEXT = "#1f2933"      # primary text
MUTED = "#7b8794"     # secondary text
LOW = "#e12d39"       # low-stock flag
LINE = "#e4e7eb"      # separators


def _style(root):
    s = ttk.Style(root)
    try:
        s.theme_use("vista")  # native soft look on Windows
    except tk.TclError:
        s.theme_use("clam")
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=PANEL, relief="flat")
    s.configure("TLabel", background=BG, foreground=TEXT,
                font=("Segoe UI", 10))
    s.configure("Title.TLabel", background=BG, foreground=TEXT,
                font=("Segoe UI Semibold", 16))
    s.configure("Muted.TLabel", background=BG, foreground=MUTED,
                font=("Segoe UI", 9))
    s.configure("TButton", background=ACCENT, foreground="white",
                font=("Segoe UI", 10), borderwidth=0, padding=(10, 6))
    s.map("TButton", background=[("active", ACCENT_DK), ("pressed", ACCENT_DK)])
    s.configure("Ghost.TButton", background=PANEL, foreground=TEXT,
                font=("Segoe UI", 10), borderwidth=1, padding=(10, 6))
    s.map("Ghost.TButton", background=[("active", "#eef2f7")])
    s.configure("Treeview", background=PANEL, foreground=TEXT, rowheight=30,
                fieldbackground=PANEL, font=("Segoe UI", 10))
    s.configure("Treeview.Heading", background="#eef2f7", foreground=TEXT,
                font=("Segoe UI Semibold", 10))
    s.configure("TEntry", font=("Segoe UI", 11), padding=(8, 6))
    return s


class InventoryApp:
    COLUMNS = ("sku", "barcode", "name", "category", "quantity",
               "reorder_level", "unit_price", "flag")

    def __init__(self, root):
        self.root = root
        self.svc = InventoryService(DB_PATH)
        self.root.title("Inventory")
        self.root.geometry("920x600")
        self.root.minsize(760, 480)
        self.root.configure(background=BG)
        _style(root)

        self._build()
        self.refresh()
        # Scanners act as a keyboard and press Enter; keep focus on the box.
        self.scan_var = tk.StringVar()
        self.scan_entry.configure(textvariable=self.scan_var)
        self.scan_entry.focus_set()

    # -- layout -----------------------------------------------------------
    def _build(self):
        # Title + scan bar
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=18, pady=(16, 8))
        ttk.Label(top, text="Inventory", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="offline", style="Muted.TLabel").pack(
            side="left", padx=(8, 0), pady=(6, 0))

        scan_frame = ttk.Frame(self.root, style="Card.TFrame")
        scan_frame.pack(fill="x", padx=18, pady=(0, 10))
        ttk.Label(scan_frame, text="Scan / search",
                  style="Muted.TLabel").pack(anchor="w", padx=12, pady=(8, 0))
        self.scan_entry = ttk.Entry(scan_frame)
        self.scan_entry.pack(fill="x", padx=12, pady=(2, 10))
        self.scan_entry.bind("<Return>", lambda e: self._lookup())
        self.scan_entry.bind("<Escape>", lambda e: self._clear_scan())

        # Table
        table_card = ttk.Frame(self.root, style="Card.TFrame")
        table_card.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.tree = ttk.Treeview(
            table_card, columns=self.COLUMNS, show="headings",
            selectmode="browse")
        heads = {
            "sku": "SKU", "barcode": "Barcode", "name": "Name",
            "category": "Category", "quantity": "Qty",
            "reorder_level": "Reorder", "unit_price": "Price", "flag": "Flag",
        }
        for c in self.COLUMNS:
            self.tree.heading(c, text=heads[c])
            anchor = "w" if c in ("sku", "barcode", "name", "category") else "e"
            self.tree.column(c, anchor=anchor, width=90)
        self.tree.column("name", width=180)
        self.tree.column("barcode", width=120)
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Double-1>", lambda e: self._sell())

        # Action buttons
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=18, pady=(0, 6))
        for label, cmd in (
            ("Add", self._add),
            ("Edit", self._edit),
            ("Sell", self._sell),
            ("Restock", self._restock),
            ("Delete", self._delete),
            ("Report", self._report),
            ("Export", self._export),
        ):
            ttk.Button(bar, text=label, command=cmd).pack(side="left", padx=(0, 8))

        # Status bar
        self.status = ttk.Label(self.root, text="", style="Muted.TLabel")
        self.status.pack(fill="x", padx=18, pady=(0, 12))

    # -- data -------------------------------------------------------------
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.svc.list_products():
            flag = "LOW" if p.is_low_stock else ""
            self.tree.insert("", "end", iid=p.id, values=(
                p.sku, p.barcode, p.name, p.category, p.quantity,
                p.reorder_level, f"{p.unit_price:.2f}", flag))
        s = self.svc.get_stock_status()
        self.status.configure(
            text=f"{s['total_products']} products   |   "
                 f"low stock: {s['low_stock_products']}   |   "
                 f"out of stock: {s['out_of_stock_products']}")

    # -- scan / search ----------------------------------------------------
    def _lookup(self):
        q = self.scan_var.get().strip()
        if not q:
            return
        p = self.svc.find_product(q)
        if p is None:
            messagebox.showinfo("Not found", f"No product for: {q}")
            return
        self.tree.selection_set(p.id)
        self.tree.see(p.id)
        self._open_sale(p)  # scanning implies a sale

    def _clear_scan(self):
        self.scan_var.set("")
        self.scan_entry.focus_set()

    # -- selection helpers ------------------------------------------------
    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a product", "Pick a row first.")
            return None
        return self.svc.get_product(sel[0])

    def _on_select(self):
        pass

    # -- actions ----------------------------------------------------------
    def _add(self):
        data = ProductDialog(self.root, "Add product").result
        if data:
            self.svc.add_product(data)
            self.refresh()

    def _edit(self):
        p = self._selected()
        if p is None:
            return
        data = ProductDialog(self.root, "Edit product", p).result
        if data:
            self.svc.update_product(p.id, data)
            self.refresh()

    def _sell(self):
        p = self._selected()
        if p is None:
            return
        self._open_sale(p)

    def _open_sale(self, p):
        qty = simpledialog.askinteger(
            "Record sale", f"How many '{p.name}' sold?",
            minvalue=1, initialvalue=1)
        if qty:
            try:
                self.svc.record_sale(p.id, qty)
            except ValueError as e:
                messagebox.showerror("Sale failed", str(e))
            self.refresh()

    def _restock(self):
        p = self._selected()
        if p is None:
            return
        qty = simpledialog.askinteger(
            "Restock / adjust", f"Adjust stock for '{p.name}' (use +/-):",
            initialvalue=0)
        if qty:
            try:
                self.svc.adjust_stock(p.id, qty)
            except ValueError as e:
                messagebox.showerror("Adjust failed", str(e))
            self.refresh()

    def _delete(self):
        p = self._selected()
        if p is None:
            return
        if messagebox.askyesno("Delete", f"Delete '{p.name}'?"):
            self.svc.delete_product(p.id)
            self.refresh()

    def _report(self):
        ReportWindow(self.root, self.svc)

    def _export(self):
        import csv
        out = os.path.join(os.path.dirname(DB_PATH), "inventory.csv")
        products = self.svc.list_products()
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sku", "name", "category", "quantity",
                        "reorder_level", "unit_price", "cost_price", "supplier"])
            for p in products:
                w.writerow([p.sku, p.name, p.category, p.quantity,
                            p.reorder_level, p.unit_price, p.cost_price,
                            p.supplier])
        messagebox.showinfo("Exported", f"{len(products)} products -> {out}")


class ProductDialog(simpledialog.Dialog):
    """Add/Edit product form."""

    FIELDS = [
        ("name", "Name*", str),
        ("sku", "SKU", str),
        ("barcode", "Barcode", str),
        ("category", "Category", str),
        ("unit_price", "Unit price", float),
        ("cost_price", "Cost price", float),
        ("quantity", "Stock", int),
        ("reorder_level", "Reorder level", int),
        ("supplier", "Supplier", str),
    ]

    def __init__(self, parent, title, product=None):
        self.product = product
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        self.entries = {}
        for i, (key, label, _t) in enumerate(self.FIELDS):
            ttk.Label(master, text=label).grid(
                row=i, column=0, sticky="w", padx=8, pady=4)
            var = tk.StringVar()
            if self.product:
                cur = getattr(self.product, key, "")
                var.set("" if cur is None else cur)
            e = ttk.Entry(master, textvariable=var, width=28)
            e.grid(row=i, column=1, sticky="w", padx=8, pady=4)
            self.entries[key] = (var, self.FIELDS[i][2])
        return master

    def apply(self):
        data = {}
        for key, (var, typ) in self.entries.items():
            val = var.get().strip()
            if val == "":
                continue
            try:
                data[key] = typ(val)
            except ValueError:
                data[key] = val
        if "name" not in data or not data.get("name"):
            messagebox.showerror("Missing", "Name is required.")
            self.result = None
            return
        self.result = data


class ReportWindow(tk.Toplevel):
    def __init__(self, parent, svc):
        super().__init__(parent)
        self.title("Reports")
        self.geometry("420x360")
        self.configure(background=BG)
        _style(self)

        s = svc.get_stock_status()
        ttk.Label(self, text="Stock status", style="Title.TLabel").pack(
            anchor="w", padx=16, pady=(14, 4))
        for line in (
            f"Products: {s['total_products']}",
            f"Low stock: {s['low_stock_products']} ({s['low_stock_percentage']}%)",
            f"Out of stock: {s['out_of_stock_products']} ({s['out_of_stock_percentage']}%)",
        ):
            ttk.Label(self, text=line).pack(anchor="w", padx=16, pady=2)

        ttk.Label(self, text="By category", style="Title.TLabel").pack(
            anchor="w", padx=16, pady=(14, 4))
        for c in svc.report_by_category():
            ttk.Label(self, text=(
                f"{c['category']} - {c['products']} products, "
                f"{c['quantity']} units, {c['low_stock']} low")
            ).pack(anchor="w", padx=16, pady=2)

        ttk.Label(self, text="Sales by month", style="Title.TLabel").pack(
            anchor="w", padx=16, pady=(14, 4))
        sales = svc.get_sales_report()
        if not sales:
            ttk.Label(self, text="(none yet)", style="Muted.TLabel").pack(
                anchor="w", padx=16)
        for r in sales:
            ttk.Label(self, text=f"{r['month']}: {r['units_sold']} units").pack(
                anchor="w", padx=16, pady=2)


def main():
    root = tk.Tk()
    InventoryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
