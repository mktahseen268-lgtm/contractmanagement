"""Structured-JSON access logging with request-ID propagation and sensitive-data redaction.

See [`docs/26-monitoring-observability.md`](../../../docs/26-monitoring-observability.md) §1 for
the field map (ECS / Splunk CIM compatible) and §1.2 for the redaction policy.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..config import settings

# Request-scoped correlation id. Read by audit + structured log callsites that want to attach
# a trace identifier without threading it through the function signature.
request_id_var: ContextVar[str] = ContextVar("cm_request_id", default="")

# stdout logger — uvicorn already configures the root; we just write a one-line JSON event.
_log = logging.getLogger("cm.access")
if not _log.handlers:
    _log.setLevel(getattr(logging, settings.log_level, logging.INFO))
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_h)
    _log.propagate = False


_REDACTED = "<redacted>"
_SENSITIVE_HEADER = {"authorization", "cookie", "set-cookie", "x-api-key", "x-captcha-token"}
_AUTH_PATH_PREFIXES = ("/auth/login", "/auth/mfa", "/auth/otp", "/auth/password", "/auth/register", "/auth/refresh", "/api-keys")


def _redact_headers(headers) -> dict[str, str]:
    out = {}
    for k, v in headers.items():
        out[k] = _REDACTED if k.lower() in _SENSITIVE_HEADER else v
    return out


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _serialize(record: dict[str, Any]) -> str:
    if settings.log_format == "text":
        # cheap human-readable fallback for dev terminals
        parts = [record.get("ts", ""), record.get("level", "INFO"), record.get("request_id", "")[:8], record.get("method", ""),
                 record.get("path", ""), str(record.get("status", "")), f"{record.get('duration_ms', 0)}ms"]
        return " ".join(p for p in parts if p)
    return json.dumps(record, separators=(",", ":"), default=str)


class LoggingMiddleware(BaseHTTPMiddleware):
    """One structured event per request. Severity is inferred from the status code; redacts
    auth / API-key bodies. Sets the `X-Request-Id` response header on every response."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Honour client-supplied X-Request-Id if it looks well-formed; otherwise mint a new one.
        incoming = (request.headers.get("x-request-id") or "").strip()[:64]
        rid = incoming if (incoming and incoming.replace("-", "").isalnum()) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        path = request.url.path
        method = request.method
        is_auth_path = path.startswith(_AUTH_PATH_PREFIXES)
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception as e:  # noqa: BLE001
            # the error response is returned by FastAPI's exception handlers; log + re-raise
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._emit({
                "ts": _utc_now_iso(), "level": "ERROR",
                "logger": "http", "request_id": rid,
                "method": method, "path": path, "status": 500, "duration_ms": elapsed_ms,
                "client_ip": _client_ip(request), "exc_type": e.__class__.__name__,
                "msg": "unhandled exception",
            })
            request_id_var.reset(token)
            raise

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        level = "INFO"
        if status_code >= 500:
            level = "ERROR"
        elif status_code >= 400:
            level = "WARN"
        record = {
            "ts": _utc_now_iso(),
            "level": level,
            "logger": "http",
            "request_id": rid,
            "method": method,
            "path": path,
            "status": status_code,
            "duration_ms": elapsed_ms,
            "client_ip": _client_ip(request),
            "user_agent": request.headers.get("user-agent", "")[:200],
            "msg": "request",
        }
        # never log query strings of auth paths; otherwise include length only
        qs_len = len(request.url.query or "")
        if qs_len:
            record["qs_len"] = qs_len
        if is_auth_path:
            record["redacted"] = True
        response.headers.setdefault("X-Request-Id", rid)
        self._emit(record)
        request_id_var.reset(token)
        return response

    def _emit(self, record: dict[str, Any]) -> None:
        try:
            level = record.get("level", "INFO")
            line = _serialize(record)
            getattr(_log, level.lower(), _log.info)(line)
        except Exception:  # noqa: BLE001
            pass
