"""HTTP metrics middleware — records request count, latency, and in-flight gauge per request,
labelled by method + matched route template (low cardinality) + status. See `app/metrics.py`."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..metrics import HTTP_IN_FLIGHT, HTTP_LATENCY, HTTP_REQUESTS

# Don't meter the meta endpoints themselves (avoids self-referential scrape noise).
_SKIP = {"/metrics", "/health", "/healthz/ready"}


def _route_template(request: Request) -> str:
    """Use the matched route's path template (e.g. /contracts/{contract_id}) so we don't blow up
    cardinality with one series per contract id. Falls back to a coarse bucket if unmatched."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    # unmatched (404s, etc.) — bucket by first segment to stay bounded
    seg = request.url.path.strip("/").split("/", 1)[0]
    return f"/{seg}" if seg else "/"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in _SKIP:
            return await call_next(request)

        method = request.method
        HTTP_IN_FLIGHT.inc()
        start = time.perf_counter()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            return response
        finally:
            HTTP_IN_FLIGHT.dec()
            elapsed = time.perf_counter() - start
            path = _route_template(request)
            try:
                HTTP_REQUESTS.labels(method=method, path=path, status=str(status)).inc()
                HTTP_LATENCY.labels(method=method, path=path).observe(elapsed)
            except Exception:  # noqa: BLE001 — never let metrics break the response
                pass
