import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..audit import record
from ..config import settings
from ..database import get_db, set_request_tenant
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return base[:40]


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    i = 2
    while db.scalar(select(models.Tenant).where(models.Tenant.slug == slug)) is not None:
        slug = f"{base}-{i}"
        i += 1
    return slug


def _auth_payload(user: models.User, tenant: models.Tenant) -> schemas.AuthOut:
    return schemas.AuthOut(
        access_token=security.create_access_token(user.id, tenant.id, user.role),
        refresh_token=security.create_refresh_token(user.id, tenant.id, user.role),
        expires_in=settings.access_token_expire_minutes * 60,
        user=schemas.UserOut.model_validate(user),
        tenant=schemas.TenantOut.model_validate(tenant),
    )


@router.post("/register", response_model=schemas.AuthOut, status_code=status.HTTP_201_CREATED)
def register(data: schemas.RegisterIn, db: Session = Depends(get_db)) -> schemas.AuthOut:
    email = data.email.lower()
    if db.scalar(select(models.User).where(func.lower(models.User.email) == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    tenant_id = uuid.uuid4().hex
    set_request_tenant(tenant_id)  # scope every subsequent write to the new tenant
    tenant = models.Tenant(id=tenant_id, name=data.workspace_name, slug=_unique_slug(db, data.workspace_name))
    db.add(tenant)
    db.flush()
    user = models.User(
        tenant_id=tenant_id, email=email, name=data.name, password_hash=security.hash_password(data.password), role="owner"
    )
    db.add(user)
    db.flush()
    record(db, tenant_id=tenant_id, action="tenant.created", actor=user, object_type="tenant", object_id=tenant_id, object_label=tenant.name)
    record(db, tenant_id=tenant_id, action="user.registered", actor=user, object_type="user", object_id=user.id, object_label=user.name)
    db.commit()
    return _auth_payload(user, tenant)


@router.post("/login", response_model=schemas.AuthOut)
def login(data: schemas.LoginIn, db: Session = Depends(get_db)) -> schemas.AuthOut:
    user = db.scalar(select(models.User).where(func.lower(models.User.email) == data.email.lower()))
    if user is None or not user.is_active or not security.verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    set_request_tenant(user.tenant_id)
    tenant = db.get(models.Tenant, user.tenant_id)
    record(db, tenant_id=user.tenant_id, action="auth.login", actor=user, object_type="user", object_id=user.id, object_label=user.name)
    db.commit()
    return _auth_payload(user, tenant)


@router.post("/refresh", response_model=schemas.TokenOut)
def refresh(data: schemas.RefreshIn, db: Session = Depends(get_db)) -> schemas.TokenOut:
    try:
        payload = security.decode_token(data.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.is_active or user.tenant_id != payload.get("tid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
    return schemas.TokenOut(
        access_token=security.create_access_token(user.id, user.tenant_id, user.role),
        refresh_token=security.create_refresh_token(user.id, user.tenant_id, user.role),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> schemas.MeOut:
    tenant = db.get(models.Tenant, user.tenant_id)
    return schemas.MeOut(user=schemas.UserOut.model_validate(user), tenant=schemas.TenantOut.model_validate(tenant))
