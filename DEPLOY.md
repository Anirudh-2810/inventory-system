# Deploying StockOffline

The product runs **two ways from one codebase**:
- **Offline** (core): `python main.py` / `python gui.py` — no server, no internet.
- **Web/API tier**: a secure HTTP API on the same SQLite DB. It can run with
  zero dependencies (stdlib) or behind a production WSGI server.

> The web tier refuses to start unless `INVENTORY_DB_PATH` and a real
> `JWT_SECRET_KEY` are set. `DEBUG` defaults to OFF.

---

## 1. Local web tier (zero installs)

```bash
cd src
python web_app.py          # stdlib http.server, reads .env
```

## 2. Production WSGI (gunicorn) — same code, real server

```bash
pip install gunicorn
cd src
gunicorn web.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

`web/wsgi.py` exposes the **identical** secure pipeline (`dispatch()`) as the
offline server, so behavior is unchanged — only the surrounding server differs.
Gunicorn/uvicorn are *not* needed for offline use; they are deploy-only.

## 3. Docker

```bash
docker build -t stockoffline .
docker run -d -p 8000:8000 \
  -e INVENTORY_DB_PATH=/app/src/inventory.db \
  -e JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  -e ALLOWED_ORIGINS="https://your-frontend.com" \
  -v "$(pwd)/data:/app/src" \
  stockoffline
```

The image installs **only gunicorn** — your app code stays dependency-free.
Secrets are passed at runtime, never baked into the image (see `.dockerignore`).

---

## 4. One-click cloud platforms (budget-friendly)

All three have free/very-cheap tiers that fit a ₹2–3k budget. They need a git
repo + the env vars below. (This machine has no git repo yet — run
`git init`, commit, and push to GitHub first, or use the platform's direct
repo import.)

### Render
- New **Web Service** → connect repo → Runtime: *Docker* → use the Dockerfile.
- Add env vars (see table). Start command is auto-read from the Dockerfile.

### Railway
- New project → deploy from GitHub repo → it detects the Dockerfile.
- Set env vars in the Variables tab.

### Fly.io
- `fly launch` (detects Dockerfile) → `fly deploy`.
- Set secrets: `fly secrets set JWT_SECRET_KEY=... ALLOWED_ORIGINS=...`.

---

## 5. Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `INVENTORY_DB_PATH` | yes | SQLite file path |
| `JWT_SECRET_KEY` | yes (web) | strong random value; rotate if leaked |
| `ALLOWED_ORIGINS` | yes (web) | comma-separated exact origins, e.g. `https://app.example.com` |
| `WEB_HOST` | no | default `127.0.0.1` (Docker sets `0.0.0.0`) |
| `WEB_PORT` | no | default `8000` |
| `RAZORPAY_WEBHOOK_SECRET` | payments only | verify Razorpay webhooks |
| `STRIPE_WEBHOOK_SECRET` | payments only | verify Stripe webhooks |
| `DEBUG` | no | must be `false` in production |

---

## 6. Production hardening checklist

- [ ] Terminate TLS at a reverse proxy / load balancer (Render/Railway/Fly do
      this for you). The app already sends HSTS, `nosniff`, `DENY`, CSP.
- [ ] Set `ALLOWED_ORIGINS` to your exact frontend domain(s) — never `*`.
- [ ] Use a strong, unique `JWT_SECRET_KEY` from a secret manager.
- [ ] Put the SQLite file on a persistent volume (see the `-v` mount above).
- [ ] Keep `DEBUG=false`.
- [ ] For high traffic, raise gunicorn `--workers` (CPU cores × 2 + 1).
- [ ] The stdlib server is for local/offline only; **use gunicorn in prod**.
