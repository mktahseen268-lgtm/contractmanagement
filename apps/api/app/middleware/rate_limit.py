"""Rate-limiting middleware. Pluggable backing store — in-memory token-bucket for single-replica
deployments, Redis-backed (atomic Lua-script token bucket) for multi-replica. The store is
selected via `RATE_LIMIT_STORE` env var (`memory` | `redis`). See
[`docs/20-security-compliance.md`](../../../docs/20-security-compliance.md) §8.

The Redis implementation uses an atomic Lua script so refill+consume is one round-trip and
race-free across replicas. Failure mode: if Redis is unreachable we fail OPEN (allow the
request) and log a warning — better to serve traffic than to lock everyone out on a Redis
hiccup. The `LoggingMiddleware` captures the warning into the SIEM trail."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import settings

log = logging.getLogger("uvicorn.error")


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


class _RedisStore:
    """Distributed token bucket backed by Redis. The refill+consume is a single Lua script so
    multiple API replicas see consistent state with no race window. Falls back to fail-open
    when Redis is unreachable — see module docstring."""

    # Atomic refill+consume. Storage shape per key:
    #   HSET cm:rl:<key>  t <tokens>  ts <last_refill_monotonic_ms>  capacity <capacity>
    # Args: KEYS[1]=bucket key, ARGV[1]=now_ms, ARGV[2]=capacity, ARGV[3]=rate_per_ms,
    #       ARGV[4]=ttl_ms
    # Returns: {allowed, retry_after_ms, reset_in_ms, remaining}
    _LUA = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local capacity = tonumber(ARGV[2])
        local rate = tonumber(ARGV[3])
        local ttl = tonumber(ARGV[4])
        local data = redis.call('HMGET', key, 't', 'ts')
        local tokens = tonumber(data[1])
        local last = tonumber(data[2])
        if tokens == nil then
            tokens = capacity
            last = now
        end
        local elapsed = math.max(0, now - last)
        tokens = math.min(capacity, tokens + elapsed * rate)
        local allowed = 0
        local retry_after = 0
        if tokens >= 1 then
            tokens = tokens - 1
            allowed = 1
        else
            retry_after = math.ceil((1 - tokens) / rate)
        end
        local reset = math.ceil((capacity - tokens) / rate)
        redis.call('HMSET', key, 't', tokens, 'ts', now)
        redis.call('PEXPIRE', key, ttl)
        return {allowed, retry_after, reset, math.floor(tokens)}
    """

    def __init__(self, url: str) -> None:
        import redis  # lazy import — only when redis store is selected

        self._redis = redis.Redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.5)
        self._script = self._redis.register_script(self._LUA)

    def consume(self, key: str, limit_per_min: int, burst: int) -> tuple[bool, float, float, int]:
        rate_per_ms = (limit_per_min / 60.0) / 1000.0
        capacity = max(1, limit_per_min + burst)
        now_ms = int(time.time() * 1000)
        ttl_ms = max(60_000, int((capacity / max(rate_per_ms, 1e-9)) * 2))
        try:
            res = self._script(keys=[f"cm:rl:{key}"], args=[now_ms, capacity, rate_per_ms, ttl_ms])
        except Exception as e:  # noqa: BLE001
            log.warning("rate-limit redis failure; failing open (key=%s err=%s)", key, e.__class__.__name__)
            return True, 0.0, 60.0, capacity  # fail open
        allowed, retry_after_ms, reset_in_ms, remaining = res
        return (
            bool(allowed),
            float(retry_after_ms) / 1000.0,
            float(reset_in_ms) / 1000.0,
            int(remaining),
        )


def _build_store() -> "_MemoryStore | _RedisStore":
    if settings.rate_limit_store == "redis":
        url = settings.rate_limit_redis_url or settings.redis_url
        try:
            store = _RedisStore(url)
            log.info("Rate limiter: Redis-backed (%s)", url.rsplit("@", 1)[-1])
            return store
        except Exception as e:  # noqa: BLE001
            log.warning("Rate limiter: requested redis store unavailable (%s); falling back to memory.", e.__class__.__name__)
    log.info("Rate limiter: in-memory (single-replica only)")
    return _MemoryStore()


_store: "_MemoryStore | _RedisStore" = _build_store()


_SKIP_PATHS = ("/health", "/healthz/ready", "/metrics", "/docs", "/openapi.json", "/redoc", "/")


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


def reload_store_from_settings() -> None:
    """Re-read RATE_LIMIT_STORE from settings and rebuild the store. Used after env changes
    in long-running test sessions; not called at request time."""
    global _store
    _store = _build_store()


def emit_limit_headers(response: Response, klass: str, limit_per_min: int, remaining: int, reset_in: float) -> None:
    """Used by other rate-limited contexts (e.g. login lockout) to align header shape."""
    response.headers["X-RateLimit-Limit"] = str(limit_per_min)
    response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
    response.headers["X-RateLimit-Reset"] = str(max(1, int(reset_in + 0.5)))
    response.headers["X-RateLimit-Class"] = klass
