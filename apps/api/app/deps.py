from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models, security
from .database import get_db, set_request_tenant

bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise _CREDENTIALS_ERROR
    try:
        payload = security.decode_token(creds.credentials)
    except Exception:
        raise _CREDENTIALS_ERROR
    if payload.get("type") != "access":
        raise _CREDENTIALS_ERROR
    tenant_id = payload.get("tid")
    # set the RLS tenant context BEFORE the first query so every statement in this request is scoped
    set_request_tenant(tenant_id)
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.is_active or user.tenant_id != tenant_id:
        raise _CREDENTIALS_ERROR
    return user


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
