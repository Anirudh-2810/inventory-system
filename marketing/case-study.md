# Case study — ShopBrain: forecast-driven reordering for a small shop

> **STATUS: SKELETON — do not send to anyone yet.** Every `(TBC)` must be
> filled with a real pilot's numbers or a real customer's answer before this
> leaves draft. The plan's rule: *no number lives in a ShopBrain document
> until a shop owner agrees to it.* Pricing below is decided by what shops
> say they'd pay (plan Week 8), never invented here.

## The problem

Small shops (starting with pharmacies) reorder from memory and gut feel.
The result is the same everywhere: **(TBC)** stockouts on fast movers and
**(TBC)** dead stock tying up cash on slow ones. The owner spends
**(TBC)** hours a week on ordering that a spreadsheet should do.

## What we built

**StockOffline + tscore** — an offline-first inventory app paired with a
forecasting core:

1. **Sales history in** — import any till/export CSV in the contract format
   (or scan barcodes as you sell). Data stays on the shop's machine.
2. **Weekly forecast** — walk-forward-tested baselines (the model that
   passes the naive gate; a neural model was tested and **dropped** because
   it lost to simple averages — we only ship what actually wins).
3. **Reorder report** — item-by-item: forecast, suggested quantity,
   confidence, with guard rails (budget cap, max order, multiple-of-last).
   The owner **approves or rejects each line** in the app; decisions are
   remembered per report date.

No cloud, no subscription to view your own data, works with no internet.

## The pilot `(TBC — plan Week 5)`

| Metric | Result |
|---|---|
| Shop | `(TBC)` pharmacy, `(TBC)` items, `(TBC)` weeks of history |
| Forecast accuracy (WAPE) | `(TBC)` — vs naive baseline `(TBC)` |
| Stockouts vs previous practice | `(TBC)` |
| Dead stock vs previous practice | `(TBC)` |
| Owner's time saved per week | `(TBC)` |
| Owner's honest verdict | `(TBC)` |

*Method note (this part is already true): forecasts are scored with an
expanding-window walk-forward backtest — every prediction is made from past
data only, and the gate requires beating "reorder what sold last week."
Verified numbers on synthetic data: gate PASS, WAPE 28.10% vs 34.77% naive
(14 weeks, 12 items). Real-shop numbers replace this paragraph once the
pilot runs.*

## What it costs the shop `(TBC)`

- Setup: `(TBC)` — decided by what shops say they'd pay, not by us.
- Monthly: `(TBC)`
- *(The sales kit currently carries placeholder prices Rs.499/Rs.299 —
  see price_sheet.txt. Owner decision: keep as a starting anchor for
  conversations or strike them until Week 8 answers land.)*

## Results that are already real (no pilot needed)

- **Forecast core:** gate-tested walk-forward backtest; naive gate beaten
  on synthetic data (WAPE 28.10% vs 34.77%); 68 automated tests.
- **Neural model honestly dropped:** an RNN lost to moving averages under
  every configuration tried (34.92–49.67% vs 28.10%) — written up as a
  DROP verdict, not hidden. Ship what wins.
- **Fully offline:** desktop app + CLI, SQLite local file, no network
  required; optional authenticated web tier for teams.
- **Deterministic agent simulation** for showing how reorder policies live
  and die against real demand — demo dashboard included.

## Next step for the reader

Reply with your current reordering process and we'll run your numbers
through the forecast on your own data — no data leaves your machine.

---
*ShopBrain build: [StockOffline](https://github.com/Anirudh-2810/inventory-system)
(app) + [tscore](https://github.com/Anirudh-2810/tscore) (forecast core).
Demo: `python scripts/demo.py` in tscore runs the whole pipeline end to end.*
