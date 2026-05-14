"""Rate-limiting middleware. In-memory token-bucket today; the backing store is pluggable so a
Redis-backed implementation can drop in (one method to override). See
[`docs/20-security-compliance.md`](../../../docs/20-security-compliance.md) §8."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import settings


@dataclass
class _Bucket:
    capacity: int
    rate_per_sec: float
    tokens: float = 0.0
    last_refill: float = 0.0
    lock: threading.Lock = None  # type: ignore[assignment]


# (route_class, limit_per_minute, burst)
_RULES: list[tuple[str, int, int]] = [
    # most-specific first; first match wins
    ("POST /auth/login", 5, 5),
    ("POST /auth/register", 3, 1),
    ("POST /auth/refresh", 10, 10),
    ("POST /auth/mfa/", 8, 2),
    ("POST /auth/otp/send", 3, 0),
    ("POST /auth/password-change", 5, 0),
    ("POST /sign/", 30, 10),  # public signing portal
    ("POST /users", 10, 5),
    ("POST /api-keys", 10, 5),
    ("POST /webhooks", 10, 5),
    ("POST ", 120, 30),
    ("PATCH ", 120, 30),
    ("DELETE ", 120, 30),
    ("PUT ", 120, 30),
    ("", 240, 60),                          # GET-heavy default
]


def _classify(method: str, path: str) -> tuple[str, int, int]:
    key = f"{method} {path}"
    for prefix, limit, burst in _RULES:
        if prefix and (key.startswith(prefix) or path.startswith(prefix.split(" ", 1)[-1] if " " in prefix else prefix)):
            return prefix.strip() or "*", limit, burst
        if not prefix:
            return "*", limit, burst
    return "*", 120, 30


class _MemoryStore:
    """Process-local token bucket store. Fine for a single-instance API; for multi-replica
    deployments wire the Redis store (planned). The interface is `consume(key, limit, burst)
    -> (allowed, retry_after_seconds, reset_in_seconds, remaining)`."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def consume(self, key: str, limit_per_min: int, burst: int) -> tuple[bool, float, float, int]:
        now = time.monotonic()
        rate = limit_per_min / 60.0
        capacity = max(1, limit_per_min + burst)
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = _Bucket(capacity=capacity, rate_per_sec=rate, tokens=float(capacity), last_refill=now, lock=threading.Lock())
                self._buckets[key] = b
        with b.lock:
            elapsed = now - b.last_refill
            b.tokens = min(b.capacity, b.tokens + elapsed * b.rate_per_sec)
            b.last_refill = now
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                remaining = int(b.tokens)
                reset_in = (b.capacity - b.tokens) / b.rate_per_sec if b.rate_per_sec > 0 else 60.0
                return True, 0.0, reset_in, remaining
            retry_after = (1.0 - b.tokens) / b.rate_per_sec if b.rate_per_sec > 0 else 60.0
            return False, retry_after, retry_after, 0


_store = _MemoryStore()


_SKIP_PATHS = ("/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-`(client_ip, route_class)` token bucket. Skips health/docs endpoints. Sets the
    standard `X-RateLimit-*` + `Retry-After` headers; returns 429 with a JSON body when
    exhausted."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not settings.rate_limit_enabled:
            return await call_next(request)
        path = request.url.path
        if path in _SKIP_PATHS or path.startswith("/_next"):
            return await call_next(request)

        klass, limit_per_min, burst = _classify(request.method, path)
        client_ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        key = f"{klass}|{client_ip or '?'}"
        allowed, retry_after, reset_in, remaining = _store.consume(key, limit_per_min, burst)

        if not allowed:
            return JSONResponse(
                {"detail": "Too many requests — please slow down."},
                status_code=429,
                headers={
                    "Retry-After": str(max(1, int(retry_after + 0.5))),
                    "X-RateLimit-Limit": str(limit_per_min),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(max(1, int(reset_in + 0.5))),
                    "X-RateLimit-Class": klass,
                },
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit_per_min)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(max(1, int(reset_in + 0.5)))
        return response


def reset_for_tests() -> None:  # pragma: no cover
    global _store
    _store = _MemoryStore()


def emit_limit_headers(response: Response, klass: str, limit_per_min: int, remaining: int, reset_in: float) -> None:
    """Used by other rate-limited contexts (e.g. login lockout) to align header shape."""
    response.headers["X-RateLimit-Limit"] = str(limit_per_min)
    response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
    response.headers["X-RateLimit-Reset"] = str(max(1, int(reset_in + 0.5)))
    response.headers["X-RateLimit-Class"] = klass
