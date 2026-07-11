"""Route handlers for the web tier.

Every inventory handler enforces ownership server-side (no IDOR) and never
trusts client-supplied prices/quantities for payments. All user-facing strings
are HTML-escaped on output (XSS defense) even though the API is JSON.
"""

import logging

import auth
import payments
import utils
from .security import get_bearer_token

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Output sanitization
# --------------------------------------------------------------------------- #
_TEXT_FIELDS = ("name", "sku", "barcode", "description", "category", "supplier")


def _sanitize_product(p) -> dict:
    d = p.to_dict()
    for f in _TEXT_FIELDS:
        if isinstance(d.get(f), str):
            d[f] = utils.sanitize_html(d[f])
    # Never return the user's plaintext password or internal hashes (none here),
    # but explicitly drop any future sensitive keys.
    d.pop("password_hash", None)
    d.pop("salt", None)
    d.pop("owner_id", None)  # internal tenant id; the client already has it via the JWT
    return d


# --------------------------------------------------------------------------- #
# Auth handlers
# --------------------------------------------------------------------------- #
def signup(req, ctx):
    data = req.json_data() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    try:
        user = ctx.users.create_user(email, password)
    except ValueError as e:
        return 400, {"error": str(e)}
    toks = auth.generate_tokens(user["id"])
    return 201, {
        "user": {"id": user["id"], "email": user["email"], "role": user["role"]},
        **toks,
    }


def login(req, ctx):
    data = req.json_data() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = ctx.users.verify_credentials(email, password)
    if user is None:
        # Generic message — do not reveal whether the email exists.
        return 401, {"error": "Invalid credentials"}
    toks = auth.generate_tokens(user["id"])
    return 200, {
        "user": {"id": user["id"], "email": user["email"], "role": user["role"]},
        **toks,
    }


def logout(req, ctx):
    token = get_bearer_token(req.headers)
    if token:
        payload = auth.verify_jwt(token)
        if payload and payload.get("jti"):
            auth.blacklist_token(payload["jti"])
    return 200, {"status": "logged_out"}


def refresh(req, ctx):
    data = req.json_data() or {}
    token = data.get("refresh_token") or get_bearer_token(req.headers)
    if not token:
        return 401, {"error": "Refresh token required"}
    payload = auth.verify_jwt(token)
    if not payload or payload.get("type") != "refresh":
        return 401, {"error": "Invalid refresh token"}
    new_access = auth.create_jwt({
        "sub": payload["sub"], "exp": int(__import__("time").time()) + 3600,
        "type": "access", "jti": __import__("uuid").uuid4().hex,
    })
    return 200, {"access_token": new_access, "expires_in": 3600}


def reset_request(req, ctx):
    data = req.json_data() or {}
    email = (data.get("email") or "").strip().lower()
    user = ctx.users.get_by_email(email)
    if user is not None:
        # Generate a single-use, 15-minute token. In production, email it.
        auth.generate_reset_token(user["email"])
        # Intentionally not returned to the client, and NEVER logged: a logged
        # reset token lets anyone with log access take over the account.
        logger.info("Password reset token issued (email verified; token not logged)")
    # Always return the same message to avoid account enumeration.
    return 202, {"status": "If the email exists, a reset link has been sent"}


def reset_confirm(req, ctx):
    data = req.json_data() or {}
    token = data.get("token") or ""
    new_password = data.get("password") or ""
    email = auth.verify_reset_token(token)
    if not email:
        return 400, {"error": "Invalid or expired reset token"}
    user = ctx.users.get_by_email(email)
    if user is None:
        return 400, {"error": "Invalid or expired reset token"}
    ctx.users.update_password(user["id"], new_password)
    return 200, {"status": "password_updated"}


def delete_account(req, ctx):
    """Delete the authenticated user and all of their personal data (GDPR-style).

    Requires the account password as confirmation so a stolen/valid token alone
    cannot destroy an account. Also blacklists the calling token.
    """
    data = req.json_data() or {}
    user = ctx.users.get_by_id(req.user["sub"])
    if user is None:
        return 404, {"error": "Not found"}
    # Password confirmation prevents accidental or coerced deletion.
    if not ctx.users.verify_credentials(user["email"], data.get("password") or ""):
        return 401, {"error": "Password confirmation required"}
    ctx.users.delete_user(req.user["sub"])
    token = get_bearer_token(req.headers)
    if token:
        payload = auth.verify_jwt(token)
        if payload and payload.get("jti"):
            auth.blacklist_token(payload["jti"])
    return 200, {"status": "account_deleted"}


# --------------------------------------------------------------------------- #
# Inventory handlers (all protected + ownership-checked)
# --------------------------------------------------------------------------- #
def _owned_product(ctx, user_id, product_id):
    """Return the product only if it belongs to the user, else None."""
    svc = ctx.service()
    p = svc.get_product(product_id)
    if p is None or not auth.check_ownership(user_id, p.owner_id):
        return None
    return p


def list_products(req, ctx):
    svc = ctx.service()
    items = [_sanitize_product(p) for p in svc.list_products(req.user["sub"])]
    return 200, {"products": items, "count": len(items)}


def create_product(req, ctx):
    data = req.json_data() or {}
    svc = ctx.service()
    product = svc.add_product(data, owner_id=req.user["sub"])
    return 201, {"product": _sanitize_product(product)}


def get_product(req, ctx):
    pid = req.path_only.rsplit("/", 1)[-1]
    p = _owned_product(ctx, req.user["sub"], pid)
    if p is None:
        return 404, {"error": "Not found"}
    return 200, {"product": _sanitize_product(p)}


def update_product(req, ctx):
    pid = req.path_only.rsplit("/", 1)[-1]
    p = _owned_product(ctx, req.user["sub"], pid)
    if p is None:
        return 404, {"error": "Not found"}
    data = req.json_data() or {}
    # Strip any attempt to change ownership or identity via the API.
    data.pop("owner_id", None)
    data.pop("id", None)
    svc = ctx.service()
    updated = svc.update_product(pid, data)
    return 200, {"product": _sanitize_product(updated)}


def delete_product(req, ctx):
    pid = req.path_only.rsplit("/", 1)[-1]
    p = _owned_product(ctx, req.user["sub"], pid)
    if p is None:
        return 404, {"error": "Not found"}
    ctx.service().delete_product(pid)
    return 200, {"status": "deleted"}


def sale_product(req, ctx):
    pid = req.path_only.split("/")[3]
    p = _owned_product(ctx, req.user["sub"], pid)
    if p is None:
        return 404, {"error": "Not found"}
    data = req.json_data() or {}
    try:
        qty = int(data.get("qty", 0))
    except (ValueError, TypeError):
        return 400, {"error": "qty must be an integer"}
    svc = ctx.service()
    try:
        updated = svc.record_sale(pid, qty)
    except ValueError as e:
        return 400, {"error": str(e)}
    return 200, {"product": _sanitize_product(updated)}


def adjust_product(req, ctx):
    pid = req.path_only.split("/")[3]
    p = _owned_product(ctx, req.user["sub"], pid)
    if p is None:
        return 404, {"error": "Not found"}
    data = req.json_data() or {}
    try:
        qty = int(data.get("qty", 0))
    except (ValueError, TypeError):
        return 400, {"error": "qty must be an integer"}
    svc = ctx.service()
    try:
        updated = svc.adjust_stock(pid, qty, notes=str(data.get("notes", "")))
    except ValueError as e:
        return 400, {"error": str(e)}
    return 200, {"product": _sanitize_product(updated)}


def stock_status(req, ctx):
    # Scoped to the caller so one tenant can never see another's aggregates.
    return 200, {"status": ctx.service().get_stock_status(req.user["sub"])}


def report(req, ctx):
    # Scoped to the caller (cross-tenant isolation — see security audit).
    return 200, {
        "by_category": ctx.service().report_by_category(req.user["sub"]),
        "sales": ctx.service().get_sales_report(req.user["sub"]),
    }


# --------------------------------------------------------------------------- #
# Payments handlers (server-side trust only)
# --------------------------------------------------------------------------- #
def payment_calculate(req, ctx):
    data = req.json_data() or {}
    try:
        total = payments.calculate_order_total(data.get("items", []))
    except ValueError as e:
        return 400, {"error": str(e)}
    return 200, total


def payment_webhook(req, ctx):
    # Build the webhook envelope from the raw body + signature header.
    envelope = {
        "headers": {"x-razorpay-signature": req.headers.get("x-razorpay-signature", "")},
        "body": req.json_data() or {},
    }
    try:
        result = payments.process_payment_webhook(envelope)
    except ValueError as e:
        return 400, {"error": str(e)}
    return 200, result


# --------------------------------------------------------------------------- #
# Health (public, minimal — no system info leaked)
# --------------------------------------------------------------------------- #
def health(req, ctx):
    return 200, {"status": "ok"}
