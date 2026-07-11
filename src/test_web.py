"""Live integration test for the secure web tier. Run from src/:

    python test_web.py
"""

import os
import sys
import json
import time
import socket
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- config via env (isolated temp DB) — must be set BEFORE importing web --- #
DB = os.path.join(os.path.dirname(__file__), "test_web.db")
os.environ["INVENTORY_DB_PATH"] = DB
os.environ["JWT_SECRET_KEY"] = "test-secret-" + os.urandom(16).hex()
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"
os.environ["WEB_HOST"] = "127.0.0.1"
os.environ["WEB_PORT"] = "0"  # ephemeral

import web.config as cfgmod
from web.store import UserStore
from web.server import SecureHTTPServer, ServerState, _Handler
from web.app import build_routes

config = cfgmod.Config()
users = UserStore(config.db_path)
routes = build_routes()

# pick a free port
s = socket.socket(); s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]; s.close()
config.port = PORT

state = ServerState(config, users, routes)
httpd = SecureHTTPServer(state, ("127.0.0.1", PORT), _Handler)
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()

BASE = f"http://127.0.0.1:{PORT}"


def call(method, path, body=None, token=None, origin=None, sig=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if origin:
        req.add_header("Origin", origin)
    if sig:
        req.add_header("x-razorpay-signature", sig)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


results = []
def check(name, cond):
    results.append((name, cond))
    print(("PASS" if cond else "FAIL"), name)


# 1. Health (public, no leak)
st, body, hdrs = call("GET", "/api/health")
check("health 200 + no server header leak", st == 200 and "status" in body)
check("security headers present", hdrs.get("X-Content-Type-Options") == "nosniff"
      and hdrs.get("X-Frame-Options") == "DENY")

# 2. CORS: allowed origin echoed, unknown origin not
_, _, h1 = call("GET", "/api/health", origin="http://localhost:3000")
_, _, h2 = call("GET", "/api/health", origin="http://evil.com")
check("CORS allows known origin", h1.get("Access-Control-Allow-Origin") == "http://localhost:3000")
check("CORS blocks unknown origin", "Access-Control-Allow-Origin" not in h2)

# 3. Protected route without token -> 401
st, _, _ = call("GET", "/api/products")
check("protected route requires auth", st == 401)

# 4. Signup + login
st, body, _ = call("POST", "/api/auth/signup", {"email": "a@shop.com", "password": "password123"})
check("signup 201", st == 201 and "access_token" in body)
st, bA, _ = call("POST", "/api/auth/login", {"email": "a@shop.com", "password": "password123"})
check("login 200 + token", st == 200 and "access_token" in bA)
tokenA = bA["access_token"]

# 5. Create product as A, then read it back (ownership)
st, body, _ = call("POST", "/api/products", {"name": "Widget", "price": 9.99, "stock": 10}, token=tokenA)
check("create product 201", st == 201 and body["product"]["name"] == "Widget")
pid = body["product"]["id"]

st, body, _ = call("GET", f"/api/products/{pid}", token=tokenA)
check("owner can read own product", st == 200 and body["product"]["id"] == pid)

# sale + adjust (regression: id must come from /<id>/sale, not the suffix)
st, body, _ = call("POST", f"/api/products/{pid}/sale", {"qty": 2}, token=tokenA)
check("sale reduces stock", st == 200 and body["product"]["quantity"] == 8)
st, body, _ = call("POST", f"/api/products/{pid}/adjust", {"qty": 3, "notes": "restock"}, token=tokenA)
check("adjust changes stock", st == 200 and body["product"]["quantity"] == 11)

# 6. Second user B cannot read A's product (IDOR defense)
st, bB, _ = call("POST", "/api/auth/signup", {"email": "b@shop.com", "password": "password123"})
tokenB = bB["access_token"]
st, _, _ = call("GET", f"/api/products/{pid}", token=tokenB)
check("IDOR blocked: other user gets 404", st == 404)

# 7. B cannot delete A's product
st, _, _ = call("DELETE", f"/api/products/{pid}", token=tokenB)
check("IDOR blocked on delete", st == 404)

# 8. Expired token rejected
import auth
exp_token = auth.create_jwt({"sub": bB["user"]["id"], "exp": int(time.time()) - 10, "type": "access", "jti": "x"})
st, _, _ = call("GET", "/api/products", token=exp_token)
check("expired token rejected", st == 401)

# 9. Logout blacklists token
st, _, _ = call("POST", "/api/auth/logout", token=tokenA)
check("logout 200", st == 200)
st, _, _ = call("GET", "/api/products", token=tokenA)
check("blacklisted token rejected after logout", st == 401)

# 10. Payment calc server-side (rejects negative / zero)
st, _, _ = call("POST", "/api/payments/calculate", {"items": []}, token=tokenB)
check("empty cart rejected", st == 400)
st, body, _ = call("POST", "/api/payments/calculate",
                    {"items": [{"product_id": "x", "quantity": 2, "unit_price": 10}]}, token=tokenB)
check("payment total calculated server-side", st == 200 and abs(body["grand_total"] - 23.6) < 0.01)

# 11. Webhook signature enforcement
st, _, _ = call("POST", "/api/payments/webhook",
                {"body": {"payment_status": "completed", "order_id": "o1", "payment_id": "p1", "user_id": "u1"}})
check("webhook without signature rejected", st == 400)

# 12. Rate limit on login (5/min) — 6th attempt blocked
for i in range(6):
    st, _, _ = call("POST", "/api/auth/login", {"email": "a@shop.com", "password": "wrong"})
last = st
check("login rate limit triggers 429", last == 429)

# --- summary --------------------------------------------------------------- #
failed = [n for n, c in results if not c]
print("\n" + ("ALL TESTS PASSED" if not failed else f"{len(failed)} FAILED: {failed}"))
httpd.shutdown()
try:
    os.remove(DB)
except OSError:
    pass
sys.exit(1 if failed else 0)
