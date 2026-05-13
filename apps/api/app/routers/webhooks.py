"""Outbound webhooks — CRUD + delivery history + a manual test-fire."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import models, schemas, webhook_service
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_ADMIN_ROLES = {"owner", "admin"}


def _get_owned(db: Session, user: models.User, eid: str) -> models.WebhookEndpoint:
    e = db.get(models.WebhookEndpoint, eid)
    if e is None or e.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found")
    return e


@router.get("", response_model=list[schemas.WebhookEndpointOut])
def list_endpoints(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.WebhookEndpointOut]:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can manage webhooks.")
    rows = db.scalars(select(models.WebhookEndpoint).where(models.WebhookEndpoint.tenant_id == user.tenant_id).order_by(desc(models.WebhookEndpoint.created_at))).all()
    return [schemas.WebhookEndpointOut.model_validate(r) for r in rows]


@router.post("", response_model=schemas.WebhookEndpointCreateOut, status_code=status.HTTP_201_CREATED)
def create_endpoint(data: schemas.WebhookEndpointIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.WebhookEndpointCreateOut:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can create webhooks.")
    if not (data.url.startswith("http://") or data.url.startswith("https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL must start with http:// or https://")
    e = models.WebhookEndpoint(
        tenant_id=user.tenant_id, url=data.url.strip()[:800], description=(data.description or "").strip()[:300],
        secret=webhook_service.new_secret(),
        events=[ev for ev in (data.events or ["*"]) if isinstance(ev, str)][:30] or ["*"],
        is_active=True, created_by=user.id,
    )
    db.add(e)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="webhook.created", actor=user, object_type="webhook", object_id=e.id, object_label=e.url[:200], ip=client_ip(request), meta={"events": e.events})
    db.commit()
    db.refresh(e)
    out = schemas.WebhookEndpointCreateOut.model_validate(e)
    out.secret = e.secret
    return out


@router.patch("/{eid}", response_model=schemas.WebhookEndpointOut)
def update_endpoint(eid: str, data: schemas.WebhookEndpointUpdateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.WebhookEndpointOut:
    e = _get_owned(db, user, eid)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can update webhooks.")
    payload = data.model_dump(exclude_unset=True)
    changed = False
    if "url" in payload and payload["url"] is not None:
        u = payload["url"].strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL must start with http:// or https://")
        e.url = u[:800]; changed = True
    if "description" in payload and payload["description"] is not None:
        e.description = payload["description"].strip()[:300]; changed = True
    if "events" in payload and payload["events"] is not None:
        e.events = [ev for ev in payload["events"] if isinstance(ev, str)][:30] or ["*"]; changed = True
    if "is_active" in payload and payload["is_active"] is not None:
        e.is_active = bool(payload["is_active"]); changed = True
    if changed:
        record(db, tenant_id=user.tenant_id, action="webhook.updated", actor=user, object_type="webhook", object_id=e.id, object_label=e.url[:200], ip=client_ip(request))
        db.commit()
        db.refresh(e)
    return schemas.WebhookEndpointOut.model_validate(e)


@router.delete("/{eid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(eid: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    e = _get_owned(db, user, eid)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can delete webhooks.")
    db.query(models.WebhookDelivery).filter(models.WebhookDelivery.endpoint_id == e.id).delete()
    db.delete(e)
    record(db, tenant_id=user.tenant_id, action="webhook.deleted", actor=user, object_type="webhook", object_id=eid, ip=client_ip(request))
    db.commit()


@router.post("/{eid}/test", response_model=schemas.WebhookDeliveryOut)
def test_endpoint(eid: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.WebhookDeliveryOut:
    e = _get_owned(db, user, eid)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can test webhooks.")
    webhook_service.dispatch(db, tenant_id=user.tenant_id, event="webhook.test", data={"hello": "from contract management", "tested_by": user.email})
    db.commit()
    latest = db.scalar(select(models.WebhookDelivery).where(models.WebhookDelivery.endpoint_id == e.id).order_by(desc(models.WebhookDelivery.created_at)))
    if latest is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No delivery recorded.")
    return schemas.WebhookDeliveryOut.model_validate(latest)


@router.get("/{eid}/deliveries", response_model=list[schemas.WebhookDeliveryOut])
def list_deliveries(eid: str, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.WebhookDeliveryOut]:
    _get_owned(db, user, eid)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can view deliveries.")
    rows = db.scalars(select(models.WebhookDelivery).where(models.WebhookDelivery.endpoint_id == eid).order_by(desc(models.WebhookDelivery.created_at)).limit(limit)).all()
    return [schemas.WebhookDeliveryOut.model_validate(r) for r in rows]
