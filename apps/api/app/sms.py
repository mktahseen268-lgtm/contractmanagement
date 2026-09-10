"""SMS delivery — OTP codes and reminders.

Required by the visitor eSigning surface: a merchant at a branch counter has a phone, not
necessarily an email address they can check on the spot.

Three backends, selected by `SMS_BACKEND`:

  console   dev/CI. Logs the message and records it in `email_outbox` (as `channel='sms'`) so
            the same delivery-audit surface covers both channels. Never sends anything.
  http      a generic HTTP gateway — which is what the Pakistani aggregators (Jazz, Telenor,
            Zong resellers) actually expose. Configure the URL, method, and a template for the
            payload; no per-vendor code, so switching aggregator is a config change.
  null      accepts and drops. For load testing, where 400 real SMS per business day would be
            both expensive and rude.

**Residency:** the gateway URL goes through the same `residency.py` allowlist as every other
egress. A foreign SMS aggregator will refuse to boot unless an operator has explicitly
reviewed and allowlisted it.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from .config import settings

log = logging.getLogger("uvicorn.error")

_HTTP_TIMEOUT = 10


class SmsError(RuntimeError):
    """Delivery failed. Callers decide whether that is fatal — for an OTP it is."""


def normalise_msisdn(raw: str, *, default_country: str = "92") -> str:
    """Best-effort E.164 without a phone-number library.

    Pakistani numbers arrive as `0300-1234567`, `+92 300 1234567`, `92 300 1234567` and
    `3001234567`. Normalising matters because the number is an identity claim: two spellings
    of the same number must not produce two different `party_ref` values and therefore two
    certificates for one person.
    """
    digits = re.sub(r"[^\d+]", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("+"):
        return digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0"):
        return f"+{default_country}{digits[1:]}"
    if digits.startswith(default_country):
        return f"+{digits}"
    return f"+{default_country}{digits}"


def mask_msisdn(number: str) -> str:
    """`+923001234567` → `+92 300 ***4567`. What goes on the Certificate of Completion:
    enough to reconcile against a branch record, not enough to be a data leak."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def mask_email(address: str) -> str:
    local, _, domain = (address or "").partition("@")
    if not domain:
        return "***"
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}***@{domain}"


class SmsBackend(ABC):
    name: str

    @abstractmethod
    def send(self, to: str, body: str) -> str:
        """Send and return a provider reference (or '' when there isn't one)."""


class ConsoleSmsBackend(SmsBackend):
    name = "console"

    def send(self, to: str, body: str) -> str:
        log.info("SMS (console) -> %s: %s", mask_msisdn(to), body)
        return "console"


class NullSmsBackend(SmsBackend):
    name = "null"

    def send(self, to: str, body: str) -> str:  # noqa: ARG002
        return "null"


class HttpSmsBackend(SmsBackend):
    """Generic HTTP gateway.

    `SMS_HTTP_BODY_TEMPLATE` is a template with `{to}` and `{text}` placeholders; it is sent as
    a JSON body when it parses as JSON, otherwise as form-encoded. That covers essentially
    every aggregator without a per-vendor adapter — the differences between them are the URL,
    the field names and the auth header, all of which are configuration.
    """

    name = "http"

    def send(self, to: str, body: str) -> str:
        if not settings.sms_http_url:
            raise SmsError("SMS_BACKEND=http but SMS_HTTP_URL is not set.")

        template = settings.sms_http_body_template or '{"to": "{to}", "text": "{text}"}'
        # Substitute through JSON encoding so a message containing quotes or newlines cannot
        # break out of the payload.
        payload = template.replace("{to}", _escape(to)).replace("{text}", _escape(body))

        headers = {"User-Agent": "contract-management/1.0"}
        if settings.sms_http_auth_header and settings.sms_http_auth_value:
            headers[settings.sms_http_auth_header] = settings.sms_http_auth_value

        data: bytes
        try:
            json.loads(payload)
            headers["Content-Type"] = "application/json"
            data = payload.encode("utf-8")
        except json.JSONDecodeError:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(
                {"to": to, "text": body}
            ).encode("utf-8")

        url = settings.sms_http_url
        if not url.lower().startswith(("http://", "https://")):
            raise SmsError("SMS_HTTP_URL must be http(s).")
        try:
            request = urllib.request.Request(url, data=data, headers=headers,  # noqa: S310
                                             method=settings.sms_http_method or "POST")
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:  # noqa: S310
                reference = response.read(200).decode("utf-8", "replace").strip()
                log.info("SMS sent to %s via gateway (ref=%s)", mask_msisdn(to), reference[:80])
                return reference[:120]
        except Exception as e:  # noqa: BLE001
            raise SmsError(f"SMS gateway rejected the message: {e}") from e


def _escape(value: str) -> str:
    """JSON-escape a value for interpolation into the body template, without the quotes."""
    return json.dumps(value)[1:-1]


_backend: SmsBackend | None = None


def get_backend() -> SmsBackend:
    global _backend
    if _backend is None:
        _backend = {
            "http": HttpSmsBackend,
            "null": NullSmsBackend,
        }.get(settings.sms_backend, ConsoleSmsBackend)()
    return _backend


def reset_backend() -> None:
    """Tests switch backends; nothing else should call this."""
    global _backend
    _backend = None


def send_sms(db, tenant_id: str, to: str, body: str) -> bool:
    """Send, recording the attempt in `email_outbox` so SMS and email share one delivery audit.

    Returns True on success. The caller decides what a failure means — for an OTP it must be
    surfaced to the visitor, not swallowed, or they will sit waiting for a code that is never
    coming.
    """
    from . import models

    number = normalise_msisdn(to)
    row = models.EmailOutbox(
        tenant_id=tenant_id, to_email=number, subject="SMS",
        body=body, status="pending", channel="sms",
    )
    db.add(row)
    try:
        reference = get_backend().send(number, body)
        row.status = "sent"
        row.provider_ref = reference[:200]
        db.flush()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("sms: delivery to %s failed: %s", mask_msisdn(number), e)
        row.status = "failed"
        row.last_error = str(e)[:500]
        db.flush()
        return False
