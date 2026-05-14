"""Security-headers middleware. Applies the modern hardening header set on every response —
mirroring (defence-in-depth) what the ingress should also be setting. See
[`docs/20-security-compliance.md`](../../../docs/20-security-compliance.md) §5 for the rationale
behind each header."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..config import settings


def _csp_value() -> str:
    """Build the Content-Security-Policy string from settings. Locks frame-ancestors to none
    (defence against clickjacking) + restricts `default-src` to self; allows the Google Fonts
    domains we actually use; `connect-src` extends if the operator configures additional API
    origins via `CSP_EXTRA_CONNECT`."""
    extra_connect = " " + " ".join(settings.csp_extra_connect_list) if settings.csp_extra_connect_list else ""
    return (
        "default-src 'self'; "
        "img-src 'self' data: blob: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "script-src 'self'; "
        f"connect-src 'self'{extra_connect}; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "worker-src 'self' blob:; "
        "upgrade-insecure-requests"
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        if not settings.security_headers_enabled:
            return response
        # Idempotent — only set if upstream hasn't already.
        h = response.headers
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault(
            "Permissions-Policy",
            "accelerometer=(), autoplay=(), camera=(), display-capture=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), usb=(), "
            "xr-spatial-tracking=()",
        )
        csp_header = "Content-Security-Policy-Report-Only" if settings.csp_report_only else "Content-Security-Policy"
        h.setdefault(csp_header, _csp_value())
        # cross-origin policies (modern defence in depth)
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # don't cache authenticated API responses; static gets its own Cache-Control elsewhere
        if request.url.path.startswith("/auth/") or request.url.path == "/auth/me":
            h.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, private")
            h.setdefault("Pragma", "no-cache")
        # signal we're not an embeddable surface
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        # custom branding (useful for blue-team triage)
        h.setdefault("Server", "ContractManagement")
        return response
