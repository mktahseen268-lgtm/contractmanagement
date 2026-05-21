"""SCIM 2.0 user provisioning (RFI T-3 / docs/19). An external IdP (Okta / Entra) calls these
endpoints to create, update, and deactivate users automatically. Off by default; enabled with
`SCIM_ENABLED=true`, a bearer `SCIM_TOKEN`, and a target `SCIM_TENANT_ID` (the workspace the IdP
provisions into).

Implements the core User resource (the 95% case): list+filter, get, create, replace, patch
(active toggle), and delete (soft-deactivate). Maps SCIM ↔ our `User`:
  userName ↔ email · name.{given,family}/formatted ↔ name · active ↔ is_active.

This is a real HTTP API — testable end-to-end without an IdP by calling it with the token.
"""

from __future__ import annotations

import datetime as dt
import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, security
from ..config import settings
from ..database import get_db, set_request_tenant

router = APIRouter(prefix="/scim/v2", tags=["scim"])

_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
_SCIM_MEDIA = "application/scim+json"


def _scim_error(detail: str, code: int) -> JSONResponse:
    return JSONResponse({"schemas": [_ERROR_SCHEMA], "detail": detail, "status": str(code)}, status_code=code, media_type=_SCIM_MEDIA)


def require_scim(request: Request) -> None:
    """Auth gate: SCIM must be enabled and the bearer token must match (constant-time). Also
    scopes all subsequent DB access to the configured provisioning tenant (RLS)."""
    if not (settings.scim_enabled and settings.scim_token and settings.scim_tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SCIM is not configured.")
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not token or not hmac.compare_digest(token, settings.scim_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid SCIM token.")
    set_request_tenant(settings.scim_tenant_id)


def _to_scim(u: models.User) -> dict:
    parts = (u.name or "").split(" ", 1)
    given = parts[0]
    family = parts[1] if len(parts) > 1 else ""
    created = (u.created_at.isoformat() + "Z") if u.created_at else None
    return {
        "schemas": [_USER_SCHEMA],
        "id": u.id,
        "userName": u.email,
        "name": {"formatted": u.name, "givenName": given, "familyName": family},
        "emails": [{"value": u.email, "primary": True}],
        "displayName": u.name,
        "active": bool(u.is_active),
        "meta": {"resourceType": "User", "created": created, "lastModified": created, "location": f"/scim/v2/Users/{u.id}"},
    }


def _name_from_payload(body: dict, fallback_email: str) -> str:
    n = body.get("name") or {}
    formatted = (n.get("formatted") or "").strip()
    if formatted:
        return formatted[:200]
    given = (n.get("givenName") or "").strip()
    family = (n.get("familyName") or "").strip()
    joined = (given + " " + family).strip()
    return (joined or body.get("displayName") or fallback_email.split("@")[0])[:200]


@router.get("/Users")
def list_users(request: Request, db: Session = Depends(get_db), _: None = Depends(require_scim)):
    tid = settings.scim_tenant_id
    flt = request.query_params.get("filter", "")
    start = max(1, int(request.query_params.get("startIndex", "1") or 1))
    count = max(0, min(200, int(request.query_params.get("count", "100") or 100)))

    stmt = select(models.User).where(models.User.tenant_id == tid)
    # SCIM filter we support: userName eq "x"
    if flt and "userName" in flt and " eq " in flt:
        val = flt.split(" eq ", 1)[1].strip().strip('"').lower()
        stmt = stmt.where(func.lower(models.User.email) == val)
    rows = list(db.scalars(stmt.order_by(models.User.created_at)).all())
    page = rows[start - 1 : start - 1 + count] if count else rows[start - 1 :]
    return JSONResponse({
        "schemas": [_LIST_SCHEMA],
        "totalResults": len(rows),
        "startIndex": start,
        "itemsPerPage": len(page),
        "Resources": [_to_scim(u) for u in page],
    }, media_type=_SCIM_MEDIA)


@router.get("/Users/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db), _: None = Depends(require_scim)):
    u = db.get(models.User, user_id)
    if u is None or u.tenant_id != settings.scim_tenant_id:
        return _scim_error("User not found", 404)
    return JSONResponse(_to_scim(u), media_type=_SCIM_MEDIA)


@router.post("/Users", status_code=status.HTTP_201_CREATED)
def create_user(body: dict, db: Session = Depends(get_db), _: None = Depends(require_scim)):
    tid = settings.scim_tenant_id
    email = str(body.get("userName") or "").lower().strip()
    if not email:
        return _scim_error("userName (email) is required", 400)
    existing = db.scalar(select(models.User).where(models.User.tenant_id == tid, func.lower(models.User.email) == email))
    if existing is not None:
        return _scim_error("User already exists", 409)
    u = models.User(
        tenant_id=tid, email=email, name=_name_from_payload(body, email),
        password_hash=security.hash_password(secrets.token_urlsafe(32)),  # unusable — SSO/SCIM only
        role=settings.oidc_default_role,
        is_active=bool(body.get("active", True)),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return JSONResponse(_to_scim(u), status_code=status.HTTP_201_CREATED, media_type=_SCIM_MEDIA)


@router.put("/Users/{user_id}")
def replace_user(user_id: str, body: dict, db: Session = Depends(get_db), _: None = Depends(require_scim)):
    u = db.get(models.User, user_id)
    if u is None or u.tenant_id != settings.scim_tenant_id:
        return _scim_error("User not found", 404)
    u.name = _name_from_payload(body, u.email)
    if "active" in body:
        u.is_active = bool(body["active"])
    db.commit()
    db.refresh(u)
    return JSONResponse(_to_scim(u), media_type=_SCIM_MEDIA)


@router.patch("/Users/{user_id}")
def patch_user(user_id: str, body: dict, db: Session = Depends(get_db), _: None = Depends(require_scim)):
    u = db.get(models.User, user_id)
    if u is None or u.tenant_id != settings.scim_tenant_id:
        return _scim_error("User not found", 404)
    # SCIM PatchOp: {"Operations":[{"op":"replace","path":"active","value":false}, ...]}
    for op in body.get("Operations", []):
        path = (op.get("path") or "").lower()
        value = op.get("value")
        if path == "active":
            u.is_active = _coerce_bool(value)
        elif path in ("name.formatted", "displayname") and isinstance(value, str):
            u.name = value[:200]
        elif not path and isinstance(value, dict):  # path-less replace
            if "active" in value:
                u.is_active = _coerce_bool(value["active"])
            if value.get("displayName"):
                u.name = str(value["displayName"])[:200]
    db.commit()
    db.refresh(u)
    return JSONResponse(_to_scim(u), media_type=_SCIM_MEDIA)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db), _: None = Depends(require_scim)) -> Response:
    u = db.get(models.User, user_id)
    if u is not None and u.tenant_id == settings.scim_tenant_id:
        # soft-deactivate (de-provisioning) rather than hard-delete, to preserve audit/ownership
        u.is_active = False
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _coerce_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")
