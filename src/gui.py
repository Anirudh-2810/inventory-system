"""Modern dark Tkinter GUI for the offline inventory system.

Run:
    python gui.py

Barcode scanners that act as a keyboard (the common USB kind) simply type
the code into the Scan box and press Enter, so no extra hardware library is
needed. The same box also searches by SKU or name.

All data stays local (inventory.db) - no network access.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from inventory_system import InventoryService

# When frozen by PyInstaller (one-file build), __file__ points into the temp
# extraction directory, so resolve the database next to the real executable
# instead -- otherwise inventory would be created in a temp dir and lost.
if getattr(sys, "frozen", False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE, "inventory.db")

# -- dark palette --------------------------------------------------------
BG       = "#15151f"   # window background
PANEL    = "#1d1d2b"   # cards / surfaces
PANEL_2  = "#262638"   # raised surfaces / inputs
INPUT    = "#2b2b40"   # entry field background
BORDER   = "#34344e"   # hairline separators
TEXT     = "#ecedf5"   # primary text (high contrast on dark)
MUTED    = "#9a9ab5"   # secondary text
ACCENT   = "#6366f1"   # primary action
ACCENT_H = "#818cf8"   # hover
ACCENT_P = "#4f46e5"   # pressed
SUCCESS  = "#34d399"
DANGER   = "#f87171"
DANGER_BG= "#7f1d2a"
DANGER_H = "#a1283a"
DANGER_P = "#5e1420"
WARN     = "#fbbf24"
ROW_ODD  = "#1a1a27"
ROW_EVEN = "#1f1f2e"
ROW_LOW  = "#2a1d24"   # subtle low-stock tint

# -- typography ----------------------------------------------------------
FONT_TITLE = ("Segoe UI Semibold", 19)
FONT_SUB   = ("Segoe UI", 10)
FONT_BTN   = ("Segoe UI Semibold", 10)
FONT_BODY  = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 9)

# button colour recipes (bg / hover / press / fg)
BTN = {
    "primary": {"bg": ACCENT,   "hover": ACCENT_H, "press": ACCENT_P, "fg": "#ffffff"},
    "ghost":   {"bg": PANEL_2,  "hover": "#32324a", "press": "#1b1b28", "fg": TEXT},
    "danger":  {"bg": DANGER_BG,"hover": DANGER_H,  "press": DANGER_P, "fg": "#ffe4e6"},
}

# -- colour helpers ------------------------------------------------------
def _rgb(hexc):
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def lerp_color(c1, c2, t):
    """Interpolate between two hex colours; t in [0,1] (smoothstep applied by caller)."""
    a, b = _rgb(c1), _rgb(c2)
    return _hex(tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))


def _style(root):
    s = ttk.Style(root)
    try:
        s.theme_use("clam")  # clam is fully themeable -> reliable dark look
    except tk.TclError:
        pass
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=PANEL, relief="flat", borderwidth=0)
    s.configure("TLabel", background=BG, foreground=TEXT, font=FONT_SUB)
    s.configure("Title.TLabel", background=BG, foreground=TEXT, font=FONT_TITLE)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    s.configure("Card.TLabel", background=PANEL, foreground=TEXT, font=FONT_BODY)

    s.configure("Treeview", background=PANEL, foreground=TEXT, rowheight=34,
                fieldbackground=PANEL, font=FONT_BODY, relief="flat", borderwidth=0)
    s.map("Treeview", background=[("selected", ACCENT)],
          foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=PANEL_2, foreground=TEXT,
                font=("Segoe UI Semibold", 10), relief="flat", borderwidth=0)
    s.map("Treeview.Heading", background=[("active", BORDER)])

    s.configure("TEntry", font=FONT_BODY, padding=(10, 7), fieldbackground=INPUT,
                foreground=TEXT, borderwidth=1, relief="flat", insertcolor=TEXT,
                bordercolor=BORDER)
    s.map("TEntry", bordercolor=[("focus", ACCENT)])

    s.configure("TScrollbar", background=PANEL_2, troughcolor=BG,
                borderwidth=0, relief="flat", arrowcolor=MUTED)
    s.map("TScrollbar", background=[("active", BORDER)])

    s.configure("TButton", background=PANEL_2, foreground=TEXT, font=FONT_BTN,
                borderwidth=1, relief="flat", padding=(12, 7))
    s.map("TButton", background=[("active", BORDER), ("pressed", INPUT)],
          foreground=[("active", "#ffffff")])
    return s


class AnimatedButton(tk.Button):
    """tk.Button with smooth hover / press colour tweening and a hand cursor."""

    def __init__(self, master, text="", command=None, style="ghost", **kw):
        self._recipe = BTN.get(style, BTN["ghost"])
        self._base = self._recipe["bg"]
        self._hover = self._recipe["hover"]
        self._press = self._recipe["press"]
        self._fg = self._recipe["fg"]
        self._inside = False
        self._anim = None
        self._cur = self._base

        kw.setdefault("font", FONT_BTN)
        kw.setdefault("relief", "flat")
        kw.setdefault("borderwidth", 0)
        kw.setdefault("padx", 16)
        kw.setdefault("pady", 9)
        kw.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command,
                         bg=self._base, fg=self._fg,
                         activebackground=self._base, activeforeground=self._fg,
                         **kw)

        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._down)
        self.bind("<ButtonRelease-1>", self._up)

    # -- animation --------------------------------------------------------
    def _tween(self, target, duration=150):
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
        start = self._cur
        steps = max(1, int(duration / 16))

        def step(i=0):
            t = i / steps
            ease = t * t * (3 - 2 * t)  # smoothstep
            col = lerp_color(start, target, ease)
            self.config(bg=col)
            self._cur = col
            if i < steps:
                self._anim = self.after(16, lambda: step(i + 1))
            else:
                self._anim = None

        step()

    def _enter(self, _e=None):
        self._inside = True
        self._tween(self._hover)

    def _leave(self, _e=None):
        self._inside = False
        self._tween(self._base)

    def _down(self, _e=None):
        self._tween(self._press, 90)

    def _up(self, _e=None):
        self._tween(self._hover if self._inside else self._base, 90)


class Toast:
    """Slide-in / fade-out notification anchored to the bottom-right of root."""

    PAD = 18

    def __init__(self, root):
        self.root = root
        self.active = None

    def show(self, message, kind="info", timeout=2600):
        if self.active:
            try:
                self.active.destroy()
            except tk.TclError:
                pass
            self.active = None

        color = {"info": ACCENT, "success": SUCCESS,
                 "error": DANGER, "warn": WARN}.get(kind, ACCENT)

        t = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes("-alpha", 0.0)
        t.configure(bg=PANEL, highlightthickness=1, highlightbackground=BORDER)

        bar = tk.Frame(t, width=4, bg=color)
        bar.pack(side="left", fill="y")
        tk.Label(t, text=message, bg=PANEL, fg=TEXT, font=FONT_BODY,
                 padx=12, pady=10, wraplength=280, justify="left").pack(side="left")

        t.update_idletasks()
        w, h = t.winfo_width(), t.winfo_height()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        x = rx + rw - w - self.PAD
        y = ry + rh - h - self.PAD
        t.geometry(f"{w}x{h}+{x + 40}+{y}")
        self.active = t

        def fade_in(i=0):
            a = min(1.0, i / 14)
            t.attributes("-alpha", a)
            t.geometry(f"{w}x{h}+{int(x + 40 * (1 - a))}+{y}")
            if i < 14:
                t.after(16, lambda: fade_in(i + 1))
            else:
                t.after(timeout, fade_out)

        def fade_out(i=0):
            a = max(0.0, 1 - i / 18)
            t.attributes("-alpha", a)
            t.geometry(f"{w}x{h}+{int(x + 40 * (1 - a))}+{y}")
            if i < 18:
                t.after(16, lambda: fade_out(i + 1))
            else:
                try:
                    t.destroy()
                except tk.TclError:
                    pass
                if self.active is t:
                    self.active = None

        fade_in()


class InventoryApp:
    COLUMNS = ("sku", "barcode", "name", "category", "quantity",
               "reorder_level", "unit_price", "flag")

    def __init__(self, root):
        self.root = root
        self.svc = InventoryService(DB_PATH)
        self.root.title("StockOffline — Inventory")
        self.root.geometry("960x620")
        self.root.minsize(780, 500)
        self.root.configure(background=BG)
        _style(root)
        self.toast = Toast(self.root)

        self._build()
        self.refresh()

        self.scan_var = tk.StringVar()
        self.scan_entry.configure(textvariable=self.scan_var)
        self.scan_entry.focus_set()

    # -- launch animation -------------------------------------------------
    def fade_in(self, duration=380):
        self.root.attributes("-alpha", 0.0)
        steps = max(1, int(duration / 16))

        def step(i=0):
            self.root.attributes("-alpha", i / steps)
            if i < steps:
                self.root.after(16, lambda: step(i + 1))

        step()

    # -- layout -----------------------------------------------------------
    def _build(self):
        self._build_progress()

        # header
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=22, pady=(18, 6))
        ttk.Label(header, text="StockOffline", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="offline inventory", style="Muted.TLabel").pack(
            side="left", padx=(8, 0), pady=(6, 0))

        pill = tk.Frame(header, bg=PANEL_2, highlightbackground=BORDER,
                        highlightthickness=1)
        pill.pack(side="right", pady=(4, 0))
        tk.Label(pill, text="●", fg=SUCCESS, bg=PANEL_2, font=FONT_SMALL).pack(
            side="left", padx=(8, 2))
        tk.Label(pill, text="Local", fg=MUTED, bg=PANEL_2, font=FONT_SMALL).pack(
            side="left", padx=(0, 8))

        # scan / search card
        scan = ttk.Frame(self.root, style="Card.TFrame")
        scan.pack(fill="x", padx=22, pady=(4, 12))
        inner = ttk.Frame(scan, style="Card.TFrame")
        inner.pack(fill="x", padx=14, pady=(12, 14))
        ttk.Label(inner, text="Scan or search — by barcode, SKU, or name",
                  style="Muted.TLabel").pack(anchor="w")
        self.scan_entry = ttk.Entry(inner)
        self.scan_entry.pack(fill="x", pady=(6, 0))
        self.scan_entry.bind("<Return>", lambda e: self._lookup())
        self.scan_entry.bind("<Escape>", lambda e: self._clear_scan())

        # table card
        card = ttk.Frame(self.root, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=22, pady=(0, 12))
        self.tree = ttk.Treeview(
            card, columns=self.COLUMNS, show="headings", selectmode="browse")
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
        self.tree.tag_configure("odd", background=ROW_ODD)
        self.tree.tag_configure("even", background=ROW_EVEN)
        self.tree.tag_configure("low", background=ROW_LOW, foreground="#fca5a5")

        vsb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        vsb.pack(side="right", fill="y", pady=10, padx=(0, 6))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Double-1>", lambda e: self._sell())

        # action bar
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=22, pady=(0, 4))
        self._btn(bar, "Add", self._add, "primary").pack(side="left", padx=(0, 8))
        self._btn(bar, "Sell", self._sell, "primary").pack(side="left", padx=(0, 8))
        ttk.Frame(bar, width=12).pack(side="left")
        self._btn(bar, "Edit", self._edit, "ghost").pack(side="left", padx=(0, 8))
        self._btn(bar, "Restock", self._restock, "ghost").pack(side="left", padx=(0, 8))
        self._btn(bar, "Report", self._report, "ghost").pack(side="left", padx=(0, 8))
        self._btn(bar, "Import", self._import, "ghost").pack(side="left", padx=(0, 8))
        self._btn(bar, "Export", self._export, "ghost").pack(side="left", padx=(0, 8))
        ttk.Frame(bar, width=12).pack(side="left")
        self._btn(bar, "Delete", self._delete, "danger").pack(side="right")

        # status + hint
        self.status = ttk.Label(self.root, text="", style="Muted.TLabel")
        self.status.pack(fill="x", padx=22, pady=(4, 4))
        ttk.Label(self.root,
                  text="Tip: scan a barcode or type a name and press Enter to sell.",
                  style="Muted.TLabel").pack(fill="x", padx=22, pady=(0, 12))

    def _btn(self, parent, text, cmd, style="ghost"):
        return AnimatedButton(parent, text=text, command=cmd, style=style)

    def _build_progress(self):
        self.prog_track = tk.Frame(self.root, height=3, bg=BG)
        self.prog_track.pack(fill="x", side="top")
        self.prog_fill = tk.Frame(self.prog_track, height=3, bg=ACCENT)
        self.prog_fill.place(x=0, y=0, width=0, height=3)
        self._prog_anim = None

    def _flash_progress(self):
        track_w = self.prog_track.winfo_width() or 940
        if self._prog_anim:
            self.prog_fill.after_cancel(self._prog_anim)
            self._prog_anim = None

        def step(w=0):
            w += track_w / 22
            if w >= track_w:
                self.prog_fill.place(width=track_w)
                self._prog_anim = self.prog_fill.after(
                    140, lambda: self.prog_fill.place(width=0))
                return
            self.prog_fill.place(width=int(w))
            self._prog_anim = self.prog_fill.after(14, lambda: step(w))

        step()

    # -- data -------------------------------------------------------------
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.svc.list_products()):
            low = p.is_low_stock
            flag = "LOW" if low else ""
            tag = "low" if low else ("odd" if i % 2 else "even")
            self.tree.insert("", "end", iid=p.id, tags=(tag,),
                             values=(p.sku, p.barcode, p.name, p.category,
                                     p.quantity, p.reorder_level,
                                     f"{p.unit_price:.2f}", flag))
        s = self.svc.get_stock_status()
        self.status.configure(
            text=f"{s['total_products']} products   |   "
                 f"low stock: {s['low_stock_products']}   |   "
                 f"out of stock: {s['out_of_stock_products']}")
        self._flash_progress()

    # -- scan / search ----------------------------------------------------
    def _lookup(self):
        q = self.scan_var.get().strip()
        if not q:
            return
        p = self.svc.find_product(q)
        if p is None:
            self.toast.show(f"No product for: {q}", kind="warn")
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
            self.toast.show("Select a row first.", kind="info")
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
            self.toast.show(f"Added {data.get('name', 'product')}.", kind="success")

    def _edit(self):
        p = self._selected()
        if p is None:
            return
        data = ProductDialog(self.root, "Edit product", p).result
        if data:
            self.svc.update_product(p.id, data)
            self.refresh()
            self.toast.show("Updated.", kind="success")

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
                self.toast.show(str(e), kind="error")
                return
            self.refresh()
            self.toast.show(f"Sold {qty} × {p.name}.", kind="success")

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
                self.toast.show(str(e), kind="error")
                return
            self.refresh()
            self.toast.show(f"Adjusted {p.name} by {qty:+d}.", kind="success")

    def _delete(self):
        p = self._selected()
        if p is None:
            return
        if messagebox.askyesno("Delete", f"Delete '{p.name}'?"):
            self.svc.delete_product(p.id)
            self.refresh()
            self.toast.show(f"Deleted {p.name}.", kind="success")

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
        self.toast.show(f"Exported {len(products)} products to CSV.", kind="success")

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import sales CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            summary = self.svc.import_sales_csv(path)
        except ValueError as e:
            messagebox.showerror("Import failed", str(e), parent=self.root)
            return
        msg = (f"Imported {summary['imported']} sales rows, "
               f"skipped {summary['skipped']}.")
        if summary["problems"]:
            msg += "\n\nFirst issues:\n" + "\n".join(
                f"• {p}" for p in summary["problems"][:5])
        if summary["skipped"]:
            messagebox.showwarning("Import finished", msg, parent=self.root)
        else:
            self.toast.show(msg, kind="success")


class ProductDialog(simpledialog.Dialog):
    """Add/Edit product form (dark themed, fades in)."""

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
        self.configure(bg=BG)
        master.configure(background=BG)
        self.attributes("-alpha", 0.0)
        self.after(10, self._fade)

        self.entries = {}
        for i, (key, label, _t) in enumerate(self.FIELDS):
            ttk.Label(master, text=label, style="Card.TLabel").grid(
                row=i, column=0, sticky="w", padx=10, pady=5)
            var = tk.StringVar()
            if self.product:
                cur = getattr(self.product, key, "")
                var.set("" if cur is None else cur)
            e = ttk.Entry(master, textvariable=var, width=30)
            e.grid(row=i, column=1, sticky="w", padx=10, pady=5)
            self.entries[key] = (var, self.FIELDS[i][2])
        return master

    def _fade(self):
        for i in range(1, 15):
            self.attributes("-alpha", i / 14)
            self.update_idletasks()
        self.attributes("-alpha", 1.0)

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
        self.geometry("440x380")
        self.configure(background=BG)
        self.attributes("-alpha", 0.0)
        _style(self)

        s = svc.get_stock_status()
        ttk.Label(self, text="Stock status", style="Title.TLabel").pack(
            anchor="w", padx=18, pady=(16, 4))
        for line in (
            f"Products: {s['total_products']}",
            f"Low stock: {s['low_stock_products']} ({s['low_stock_percentage']}%)",
            f"Out of stock: {s['out_of_stock_products']} ({s['out_of_stock_percentage']}%)",
        ):
            ttk.Label(self, text=line, style="Card.TLabel").pack(
                anchor="w", padx=18, pady=2)

        ttk.Label(self, text="By category", style="Title.TLabel").pack(
            anchor="w", padx=18, pady=(16, 4))
        for c in svc.report_by_category():
            ttk.Label(self, text=(
                f"{c['category']} — {c['products']} products, "
                f"{c['quantity']} units, {c['low_stock']} low"),
                style="Card.TLabel").pack(anchor="w", padx=18, pady=2)

        ttk.Label(self, text="Sales by month", style="Title.TLabel").pack(
            anchor="w", padx=18, pady=(16, 4))
        sales = svc.get_sales_report()
        if not sales:
            ttk.Label(self, text="(none yet)", style="Muted.TLabel").pack(
                anchor="w", padx=18)
        for r in sales:
            ttk.Label(self, text=f"{r['month']}: {r['units_sold']} units",
                      style="Card.TLabel").pack(anchor="w", padx=18, pady=2)

        for i in range(1, 15):
            self.after(16, lambda v=i: self.attributes("-alpha", v / 14))
        self.after(16 * 15, lambda: self.attributes("-alpha", 1.0))


def main():
    root = tk.Tk()
    app = InventoryApp(root)
    app.fade_in()
    root.mainloop()


if __name__ == "__main__":
    main()
