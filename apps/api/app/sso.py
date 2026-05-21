"""OIDC single-sign-on (RFI T-3 / docs/19). Real authorization-code flow against any OIDC IdP
(Okta / Microsoft Entra / Google / Keycloak), implemented with the stdlib + PyJWT — no extra
dependencies. Off by default; activates when `OIDC_ENABLED` + issuer/client are configured.

Flow:
  /auth/sso/login    → 302 to the IdP authorize endpoint (state + nonce in a short signed cookie)
  /auth/sso/callback → verify state, exchange code at the token endpoint, validate the id_token
                       (signature via the IdP JWKS, audience, issuer, nonce), then JIT-provision /
                       match the user and issue our normal rotating-refresh session.

We deliberately reuse the existing session model — SSO just establishes *who* you are, then the
same `cm_refresh` cookie + in-memory access token flow takes over (the web boot calls /auth/refresh).
"""

from __future__ import annotations

import json
import secrets
import time
import urllib.parse
import urllib.request

import jwt

from .config import settings

_DISCOVERY_CACHE: dict[str, tuple[float, dict]] = {}
_DISCOVERY_TTL = 3600.0


def is_enabled() -> bool:
    return bool(settings.oidc_enabled and settings.oidc_issuer and settings.oidc_client_id and settings.oidc_redirect_url)


def _http_json(url: str, *, data: bytes | None = None, headers: dict | None = None, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — issuer is operator-configured
        return json.loads(resp.read().decode("utf-8"))


def discovery() -> dict:
    """Fetch + cache the IdP's /.well-known/openid-configuration."""
    iss = settings.oidc_issuer.rstrip("/")
    cached = _DISCOVERY_CACHE.get(iss)
    now = time.time()
    if cached and (now - cached[0]) < _DISCOVERY_TTL:
        return cached[1]
    doc = _http_json(f"{iss}/.well-known/openid-configuration")
    _DISCOVERY_CACHE[iss] = (now, doc)
    return doc


def build_authorize_url(state: str, nonce: str) -> str:
    doc = discovery()
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_url,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": nonce,
    }
    return f"{doc['authorization_endpoint']}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Exchange the auth code for tokens at the IdP token endpoint."""
    doc = discovery()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_url,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }).encode("utf-8")
    return _http_json(
        doc["token_endpoint"],
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )


def validate_id_token(id_token: str, nonce: str) -> dict:
    """Validate the id_token: signature (IdP JWKS), audience, issuer, expiry, and nonce."""
    doc = discovery()
    jwks_client = jwt.PyJWKClient(doc["jwks_uri"])
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer.rstrip("/"),
        options={"require": ["exp", "iat", "aud"]},
    )
    if nonce and claims.get("nonce") not in (None, nonce):
        raise ValueError("OIDC nonce mismatch — possible replay.")
    if not claims.get("email"):
        raise ValueError("OIDC id_token has no email claim.")
    return claims


def new_state() -> str:
    return secrets.token_urlsafe(24)
