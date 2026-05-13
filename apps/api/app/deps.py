import datetime as dt
import hashlib
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, security
from .database import get_db, set_request_tenant

bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)

_API_KEY_PREFIX = "cm_"


def get_token_payload(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any] | None:
    """Return a JWT payload if the bearer is a JWT, or None if it's an API key (handled in
    get_current_user instead). Unauthenticated requests trigger 401 here."""
    if creds is None:
        raise _CREDENTIALS_ERROR
    token = creds.credentials
    if token.startswith(_API_KEY_PREFIX):
        return None  # let get_current_user resolve it via the api_keys table
    try:
        payload = security.decode_token(token)
    except Exception:
        raise _CREDENTIALS_ERROR
    if payload.get("type") != "access":
        raise _CREDENTIALS_ERROR
    return payload


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    payload: dict[str, Any] | None = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> models.User:
    # API-key path: lookup the key by SHA-256 hash, ensure it's not revoked, return the owning user
    if payload is None and creds is not None and creds.credentials.startswith(_API_KEY_PREFIX):
        h = hashlib.sha256(creds.credentials.encode("utf-8")).hexdigest()
        k = db.scalar(select(models.ApiKey).where(models.ApiKey.token_hash == h))
        if k is None or k.revoked_at is not None:
            raise _CREDENTIALS_ERROR
        set_request_tenant(k.tenant_id)  # RLS scope before the user lookup
        user = db.get(models.User, k.user_id)
        if user is None or not user.is_active or user.tenant_id != k.tenant_id:
            raise _CREDENTIALS_ERROR
        # touch last_used_at (best-effort)
        k.last_used_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        return user

    if payload is None:
        raise _CREDENTIALS_ERROR
    tenant_id = payload.get("tid")
    set_request_tenant(tenant_id)  # set the RLS tenant context before the first query
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.is_active or user.tenant_id != tenant_id:
        raise _CREDENTIALS_ERROR
    return user


def current_session_id(payload: dict[str, Any] | None = Depends(get_token_payload)) -> str | None:
    return payload.get("sid") if payload else None


def require_role(*roles: str):
    def _dep(user: models.User = Depends(get_current_user)) -> models.User:
        if roles and user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _dep


def client_ip(request) -> str:  # type: ignore[no-untyped-def]
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""
