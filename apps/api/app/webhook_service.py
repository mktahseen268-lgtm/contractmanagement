"""Outbound webhook dispatcher. v1: fire-and-forget per matching endpoint, signed with HMAC-
SHA256. In production this would queue a Celery task + retry with backoff; the scaffold ships
inline delivery for visibility (a WebhookDelivery row is logged either way). docs/14, docs/18."""

import datetime as dt
import hashlib
import hmac
import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def new_secret() -> str:
    return secrets.token_urlsafe(32)[:48]


def sign(secret: str, payload_bytes: bytes, *, timestamp: int) -> str:
    """X-CM-Signature header value: `t=<unix>,v1=<hex>` (Stripe-style)."""
    mac = hmac.new(secret.encode("utf-8"), msg=f"{timestamp}.".encode("utf-8") + payload_bytes, digestmod=hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def _matches(events: list[str], event: str) -> bool:
    if not events or "*" in events:
        return True
    if event in events:
        return True
    # support `contract.*`-style wildcards
    prefix = event.split(".", 1)[0]
    return f"{prefix}.*" in events


def dispatch(db: Session, *, tenant_id: str, event: str, data: dict) -> int:
    """Find every active endpoint that subscribes to `event`, attempt delivery, log the result.
    Returns the number of delivery rows created (= the number of endpoints matched). Caller
    commits."""
    rows = list(db.scalars(
        select(models.WebhookEndpoint).where(
            models.WebhookEndpoint.tenant_id == tenant_id,
            models.WebhookEndpoint.is_active.is_(True),
        )
    ).all())
    if not rows:
        return 0
    sent = 0
    now = _now()
    ts = int(now.replace(tzinfo=dt.timezone.utc).timestamp())
    body = {"event": event, "occurred_at": now.isoformat() + "Z", "tenant_id": tenant_id, "data": data}
    payload_bytes = json.dumps(body, default=str, separators=(",", ":")).encode("utf-8")
    for ep in rows:
        if not _matches(ep.events or [], event):
            continue
        delivery = models.WebhookDelivery(
            tenant_id=tenant_id, endpoint_id=ep.id, event=event, payload=body, status="pending",
        )
        db.add(delivery)
        db.flush()
        try:
            import urllib.request

            req = urllib.request.Request(
                ep.url, data=payload_bytes, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ContractManagement-Webhook/1.0",
                    "X-CM-Event": event,
                    "X-CM-Signature": sign(ep.secret or "", payload_bytes, timestamp=ts),
                    "X-CM-Delivery-Id": delivery.id,
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                code = resp.status
                snippet = (resp.read(400) or b"").decode("utf-8", errors="replace")
            delivery.status = "ok" if 200 <= code < 300 else "failed"
            delivery.response_code = code
            delivery.response_snippet = snippet[:500]
            ep.last_status = delivery.status
        except Exception as e:  # noqa: BLE001
            delivery.status = "failed"
            delivery.response_snippet = (str(e) or e.__class__.__name__)[:500]
            ep.last_status = "failed"
        delivery.attempts += 1
        delivery.delivered_at = _now()
        ep.last_delivery_at = delivery.delivered_at
        sent += 1
    return sent
