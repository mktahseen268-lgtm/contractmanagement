"""Obligations — a per-contract checklist (renewal notices, deliverables, invoice schedules, …).
v1 is a flat list per contract with status pending|done|skipped|overdue. A periodic sweep
(renewal_service.sweep) flips pending→overdue when due_date < today; the Inbox surfaces
obligations the current user owns that are due ≤7d or overdue. (docs/08)"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(tags=["obligations"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _owner_names(db: Session, tenant_id: str) -> dict[str, str]:
    return {r[0]: r[1] for r in db.execute(select(models.User.id, models.User.name).where(models.User.tenant_id == tenant_id)).all()}


def _get_owned_contract(db: Session, user: models.User, contract_id: str) -> models.Contract:
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


def _get_owned_obligation(db: Session, user: models.User, contract_id: str, oid: str) -> models.Obligation:
    o = db.get(models.Obligation, oid)
    if o is None or o.tenant_id != user.tenant_id or o.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    return o


def _out(db: Session, o: models.Obligation, names: dict[str, str] | None = None) -> schemas.ObligationOut:
    names = names if names is not None else _owner_names(db, o.tenant_id)
    d = schemas.ObligationOut.model_validate(o)
    d.owner_name = names.get(o.owner_id or "", "")
    return d


def _validate_status(target: str) -> str:
    if target not in {"pending", "done", "skipped"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status must be pending, done, or skipped.")
    return target


@router.get("/contracts/{contract_id}/obligations", response_model=list[schemas.ObligationOut])
def list_obligations(contract_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.ObligationOut]:
    _get_owned_contract(db, user, contract_id)
    rows = db.scalars(
        select(models.Obligation).where(
            models.Obligation.tenant_id == user.tenant_id,
            models.Obligation.contract_id == contract_id,
        ).order_by(models.Obligation.due_date.is_(None), models.Obligation.due_date, models.Obligation.created_at)
    ).all()
    names = _owner_names(db, user.tenant_id)
    return [_out(db, o, names) for o in rows]


@router.post("/contracts/{contract_id}/obligations", response_model=schemas.ObligationOut, status_code=status.HTTP_201_CREATED)
def create_obligation(contract_id: str, data: schemas.ObligationIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ObligationOut:
    c = _get_owned_contract(db, user, contract_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to add obligations.")
    owner_id = data.owner_id
    if owner_id:
        u = db.get(models.User, owner_id)
        if u is None or u.tenant_id != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid owner.")
    o = models.Obligation(
        tenant_id=user.tenant_id, contract_id=c.id,
        title=data.title.strip()[:300], description=(data.description or "").strip(),
        due_date=data.due_date, owner_id=owner_id, status="pending", created_by=user.id,
    )
    db.add(o)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="obligation.created", actor=user,
           object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request),
           meta={"obligation_id": o.id, "title": o.title})
    db.commit()
    db.refresh(o)
    return _out(db, o)


@router.patch("/contracts/{contract_id}/obligations/{obligation_id}", response_model=schemas.ObligationOut)
def update_obligation(contract_id: str, obligation_id: str, data: schemas.ObligationUpdateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ObligationOut:
    c = _get_owned_contract(db, user, contract_id)
    o = _get_owned_obligation(db, user, contract_id, obligation_id)
    if user.role not in _EDIT_ROLES and user.id != o.owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to update this obligation.")
    changes: dict = {}
    payload = data.model_dump(exclude_unset=True)
    if "title" in payload and payload["title"] is not None:
        o.title = payload["title"].strip()[:300]
        changes["title"] = o.title
    if "description" in payload and payload["description"] is not None:
        o.description = payload["description"].strip()
        changes["description"] = True
    if "due_date" in payload:
        o.due_date = payload["due_date"]
        changes["due_date"] = o.due_date.isoformat() if o.due_date else None
    if "owner_id" in payload:
        new_owner = payload["owner_id"]
        if new_owner:
            u = db.get(models.User, new_owner)
            if u is None or u.tenant_id != user.tenant_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid owner.")
        o.owner_id = new_owner
        changes["owner_id"] = new_owner
    if "status" in payload and payload["status"] is not None:
        st = _validate_status(payload["status"])
        if st != o.status:
            o.status = st
            if st in {"done", "skipped"}:
                o.completed_at = _now()
                o.completed_by_id = user.id
                o.completed_by_name = user.name
            else:
                o.completed_at = None
                o.completed_by_id = None
                o.completed_by_name = ""
            changes["status"] = st
    if changes:
        record(db, tenant_id=user.tenant_id, action="obligation.updated", actor=user,
               object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request),
               meta={"obligation_id": o.id, "changes": changes})
        db.commit()
        db.refresh(o)
    return _out(db, o)


@router.delete("/contracts/{contract_id}/obligations/{obligation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_obligation(contract_id: str, obligation_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    c = _get_owned_contract(db, user, contract_id)
    o = _get_owned_obligation(db, user, contract_id, obligation_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete obligations.")
    title = o.title
    db.delete(o)
    record(db, tenant_id=user.tenant_id, action="obligation.deleted", actor=user,
           object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request),
           meta={"obligation_id": obligation_id, "title": title})
    db.commit()
