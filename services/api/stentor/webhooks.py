"""Signed webhook delivery to downstream systems (alerting gateways, chat bridges, signage).

Only sendable languages are ever delivered (exports.json_bundle). Each POST carries
  X-Stentor-Event:      compiled | reviewed | cancelled | test
  X-Stentor-Delivery:   unique id
  X-Stentor-Signature:  sha256=<hex HMAC of the raw body with the webhook secret>
Every attempt, success or failure, is written to the alert's audit log."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from urllib.parse import urlparse

import httpx

from stentor import db

TIMEOUT = 5.0
EVENTS = ("compiled", "reviewed", "cancelled", "test")


def new_secret() -> str:
    return secrets.token_hex(24)


def valid_url(url: str) -> bool:
    u = urlparse(url)
    return u.scheme in ("http", "https") and bool(u.netloc)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header: str) -> bool:
    return hmac.compare_digest(sign(secret, body), header or "")


def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    """Separate so tests can replace it."""
    return httpx.post(url, content=body, headers=headers, timeout=TIMEOUT).status_code


def deliver(event: str, alert_id: str, payload: dict) -> list[dict]:
    hooks = [h for h in db.list_rows(db.Webhook) if h.active]
    body = json.dumps({"event": event, "alert_id": alert_id, "data": payload}, ensure_ascii=False, sort_keys=True).encode()
    out = []
    for h in hooks:
        delivery = uuid.uuid4().hex
        headers = {"Content-Type": "application/json", "User-Agent": "stentor-webhook/1", "X-Stentor-Event": event,
                   "X-Stentor-Delivery": delivery, "X-Stentor-Signature": sign(h.secret, body)}
        try:
            code = _post(h.url, body, headers)
            ok = 200 <= code < 300
            detail = f"HTTP {code}"
        except Exception as e:  # noqa: BLE001 - any network failure is recorded, never raised
            ok, detail = False, f"{type(e).__name__}: {e}"
        host = urlparse(h.url).netloc
        db.audit(alert_id, "*", "webhook", "DELIVERED" if ok else "FAILED", f"{event} to {host} ({h.id}): {detail}")
        out.append({"webhook": h.id, "ok": ok, "detail": detail, "delivery": delivery})
    return out
