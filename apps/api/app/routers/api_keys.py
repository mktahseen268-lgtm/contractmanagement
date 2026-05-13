"""API keys for headless integrations. The plaintext token is returned ONCE at creation; only
its SHA-256 hash is stored. Each request authenticates via `Authorization: Bearer cm_…` (handled
in deps.get_current_user)."""

import datetime as dt
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/api-keys", tags=["api_keys"])

_PREFIX = "cm_"
_ADMIN_ROLES = {"owner", "admin"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.get("", response_model=list[schemas.ApiKeyOut])
def list_keys(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.ApiKeyOut]:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can manage API keys.")
    rows = db.scalars(select(models.ApiKey).where(models.ApiKey.tenant_id == user.tenant_id).order_by(desc(models.ApiKey.created_at))).all()
    return [schemas.ApiKeyOut.model_validate(r) for r in rows]


@router.post("", response_model=schemas.ApiKeyCreateOut, status_code=status.HTTP_201_CREATED)
def create_key(data: schemas.ApiKeyIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ApiKeyCreateOut:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can create API keys.")
    raw = _PREFIX + secrets.token_urlsafe(32)
    prefix = raw[: 8 + len(_PREFIX)]  # cm_xxxxxxxx
    k = models.ApiKey(
        tenant_id=user.tenant_id, user_id=user.id, name=data.name.strip()[:200],
        prefix=prefix, token_hash=_hash(raw),
    )
    db.add(k)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="api_key.created", actor=user, object_type="api_key", object_id=k.id, object_label=k.name, ip=client_ip(request), meta={"prefix": prefix})
    db.commit()
    db.refresh(k)
    out = schemas.ApiKeyCreateOut.model_validate(k)
    out.token = raw
    return out


@router.delete("/{kid}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(kid: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can revoke API keys.")
    k = db.get(models.ApiKey, kid)
    if k is None or k.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    if k.revoked_at is None:
        k.revoked_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        record(db, tenant_id=user.tenant_id, action="api_key.revoked", actor=user, object_type="api_key", object_id=k.id, object_label=k.name, ip=client_ip(request))
        db.commit()
