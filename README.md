# StockOffline — Secure Offline Inventory System

A lightweight inventory manager for shops and small businesses. It runs
**fully offline** as a desktop app or CLI (all data stays in a local SQLite
file, no network required), with an **optional secure web/API tier** for teams
that want multi-user, multi-device access.

---

## Features

- **Offline-first** — desktop GUI and CLI work with zero third-party
  dependencies; data never leaves the machine.
- **Barcode-friendly** — USB keyboard-emulating scanners work out of the box;
  scan to sell, or search by SKU / name.
- **Core inventory ops** — add, edit, delete, sell, restock/adjust, low-stock
  flags, category & sales reports, CSV export.
- **Optional web/API tier** — JWT auth, per-tenant data isolation, rate
  limiting, and server-side payment verification.
- **Security-hardened** — see [Security](#security) below.

---

## Project layout

```
inventory-system/
├── src/
│   ├── gui.py                     # Desktop GUI (Tkinter, dark theme)
│   ├── main.py                    # Command-line interface
│   ├── auth.py                    # JWT + password hashing (PBKDF2)
│   ├── payments.py                # Server-side totals + webhook verification
│   ├── utils.py                   # Sanitization helpers
│   ├── web_app.py                 # Web tier entrypoint (stdlib server)
│   ├── web/                       # Web/API tier (router, handlers, store, config)
│   ├── inventory_system/          # Core domain: models + services + SQLite layer
│   ├── run_tests.py               # Offline service smoke tests
│   └── test_web.py                # Web tier integration + security tests
├── .env.example                   # Documented environment variables
├── StockOffline.spec              # PyInstaller build spec
├── Dockerfile / DEPLOY.md         # Web tier deployment
└── requirements.txt               # Web tier only (gunicorn); offline tier needs nothing
```

---

## Quick start

### Desktop GUI (offline)

```bash
cd src
python gui.py
```

Data is stored in `inventory.db` next to the app. When packaged as an `.exe`
(see [Building the Windows app](#building-the-windows-app)), the database lives
next to the executable so it persists between runs.

### Command line (offline)

```bash
cd src
export INVENTORY_DB_PATH=./inventory.db     # Windows: set INVENTORY_DB_PATH=./inventory.db

python main.py add --name "Widget" --price 9.99 --stock 100 --sku W-1 --reorder 20
python main.py list
python main.py sale --id W-1 --qty 5
python main.py status
python main.py report
python main.py export
```

Run `python main.py -h` for the full command list.

---

## Web / API tier (optional)

The web tier reuses the same secure request pipeline whether run via the
stdlib server (zero-install) or a production WSGI server.

### Run locally

```bash
cd src
cp ../.env.example ../.env        # then edit values (see below)
python web_app.py
```

### Run in production

```bash
pip install -r requirements.txt
cd src
gunicorn web.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

See **[DEPLOY.md](DEPLOY.md)** and the **Dockerfile** for container deployment.

> **Note on workers:** rate limiting is in-memory per process. Behind multiple
> gunicorn workers, limits are enforced per worker. For strict global limits,
> run a single worker or add a shared store (e.g. Redis).

### Environment variables

Copy `.env.example` to `.env` and fill in the values. The app **refuses to
start** if a critical variable is missing.

| Variable | Required | Description |
|---|---|---|
| `INVENTORY_DB_PATH` | ✅ | Path to the SQLite database file. |
| `JWT_SECRET_KEY` | ✅ | Strong random secret for signing JWTs. App won't start with the placeholder. |
| `RAZORPAY_WEBHOOK_SECRET` | If payments enabled | Verifies incoming payment webhooks (fails closed if unset). |
| `STRIPE_WEBHOOK_SECRET` | Optional | Reserved for future Stripe support. |
| `WEB_HOST` | Optional | Bind address (default `127.0.0.1`). |
| `WEB_PORT` | Optional | Bind port (default `8000`). |
| `ALLOWED_ORIGINS` | Optional | Comma-separated exact CORS origins. Empty = same-origin only. |
| `DEBUG` | Optional | Must be `false` in production (default `false`). |
| `LOG_LEVEL` | Optional | `DEBUG` / `INFO` / `WARNING` / `ERROR` (default `INFO`). |

### API endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/signup` | — | Create account |
| POST | `/api/auth/login` | — | Get access + refresh tokens |
| POST | `/api/auth/refresh` | — | Exchange refresh token |
| POST | `/api/auth/logout` | ✅ | Revoke current token |
| POST | `/api/auth/reset-request` | — | Request password reset |
| POST | `/api/auth/reset-confirm` | — | Confirm password reset |
| DELETE | `/api/account` | ✅ | Delete account + all personal data |
| GET/POST | `/api/products` | ✅ | List / create products |
| GET/PATCH/DELETE | `/api/products/{id}` | ✅ | Read / update / delete a product |
| POST | `/api/products/{id}/sale` | ✅ | Record a sale |
| POST | `/api/products/{id}/adjust` | ✅ | Adjust stock |
| GET | `/api/stock-status` | ✅ | Stock health (own data only) |
| GET | `/api/report` | ✅ | Category + sales report (own data only) |
| POST | `/api/payments/calculate` | ✅ | Server-side order total |
| POST | `/api/payments/webhook` | Signature | Payment provider webhook |
| GET | `/api/health` | — | Liveness check |

---

## Security

- **Passwords** hashed with PBKDF2-HMAC-SHA256 (100k iterations, per-user salt),
  constant-time comparison. Never stored, logged, or returned in plaintext.
- **JWT auth** with HMAC-SHA256 signatures, expiry checks, and a logout
  blacklist. `JWT_SECRET_KEY` is required at startup.
- **Per-tenant isolation** — every product and every aggregate report is scoped
  to the authenticated user; ownership is verified server-side (no IDOR).
- **SQL injection safe** — all queries are parameterized.
- **Security headers** on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Strict-Transport-Security` (1 year), and a
  restrictive `Content-Security-Policy`.
- **Rate limiting** — login 5/min, signup 3/hr, password reset 3/hr per IP.
- **CORS** restricted to explicit origins (never `*`).
- **Generic error responses** with a correlation ID; details go to server logs
  only (no stack traces, paths, or internals leaked).
- **Payments** verified server-side; webhook signatures required.
- **Data deletion** — `DELETE /api/account` removes the user and cascades to
  their products and transactions (password confirmation required).

---

## Testing

```bash
cd src
python run_tests.py     # offline service smoke tests
python test_web.py      # web tier integration + security tests
```

---

## Building the Windows app

The GUI can be packaged as a standalone `.exe` with PyInstaller:

```bash
pip install pyinstaller
python marketing/build_exe.py      # outputs marketing/dist/StockOffline.exe
```

The build is configured (via `StockOffline.spec`) to use relative paths (no
developer info baked in), keep the database next to the executable, and disable
UPX to avoid antivirus false-positives.

> **Not code-signed:** first-run SmartScreen will warn about an unknown
> publisher. Sign the binary with an Authenticode certificate for a clean
> install experience.

---

## License

Proprietary — © StockOffline. All rights reserved.
