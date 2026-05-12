import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from .. import lifecycle, models, schemas
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/contracts", tags=["contracts"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}
_APPROVE_ROLES = {"owner", "admin", "manager", "approver"}


# ---------- helpers ----------


def _owner_names(db: Session, tenant_id: str) -> dict[str, str]:
    rows = db.execute(select(models.User.id, models.User.name).where(models.User.tenant_id == tenant_id)).all()
    return {r[0]: r[1] for r in rows}


def _to_list_item(c: models.Contract, owner_name: str) -> schemas.ContractListItem:
    item = schemas.ContractListItem.model_validate(c)
    item.owner_name = owner_name
    return item


def _next_reference(db: Session, tenant_id: str) -> str:
    year = dt.date.today().year
    n = db.scalar(select(func.count(models.Contract.id)).where(models.Contract.tenant_id == tenant_id)) or 0
    return f"C-{year}-{n + 1:04d}"


def _get_owned_contract(db: Session, user: models.User, contract_id: str) -> models.Contract:
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


# ---------- list ----------


@router.get("", response_model=schemas.ContractListOut)
def list_contracts(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    q: str | None = None,
    status_: str | None = Query(None, alias="status"),
    type_: str | None = Query(None, alias="type"),
    owner_id: str | None = None,
    risk: str | None = None,
    mine: bool = False,
    sort: str = "-updated_at",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> schemas.ContractListOut:
    stmt = select(models.Contract).where(models.Contract.tenant_id == user.tenant_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(models.Contract.title).like(like), func.lower(models.Contract.reference_no).like(like), func.lower(models.Contract.counterparty).like(like)))
    if status_:
        stmt = stmt.where(models.Contract.status == status_)
    if type_:
        stmt = stmt.where(models.Contract.type == type_)
    if risk:
        stmt = stmt.where(models.Contract.risk_level == risk)
    if mine or owner_id == "me":
        stmt = stmt.where(models.Contract.owner_id == user.id)
    elif owner_id:
        stmt = stmt.where(models.Contract.owner_id == owner_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    col_map = {"updated_at": models.Contract.updated_at, "created_at": models.Contract.created_at, "title": models.Contract.title, "end_date": models.Contract.end_date, "value": models.Contract.value}
    key = sort.lstrip("-")
    col = col_map.get(key, models.Contract.updated_at)
    stmt = stmt.order_by(desc(col) if sort.startswith("-") else col)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    names = _owner_names(db, user.tenant_id)
    items = [_to_list_item(c, names.get(c.owner_id, "")) for c in db.scalars(stmt).all()]
    return schemas.ContractListOut(items=items, total=total, page=page, page_size=page_size)


# ---------- detail ----------


def _detail(db: Session, c: models.Contract) -> schemas.ContractDetail:
    names = _owner_names(db, c.tenant_id)
    d = schemas.ContractDetail.model_validate(c)
    d.owner_name = names.get(c.owner_id, "")
    d.available_transitions = lifecycle.available(c.status)
    return d


@router.get("/{contract_id}", response_model=schemas.ContractDetail)
def get_contract(contract_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    return _detail(db, _get_owned_contract(db, user, contract_id))


# ---------- create ----------


@router.post("", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
def create_contract(data: schemas.ContractCreateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to create contracts.")
    owner_id = data.owner_id or user.id
    if owner_id != user.id:
        owner = db.get(models.User, owner_id)
        if owner is None or owner.tenant_id != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid owner.")
    c = models.Contract(
        tenant_id=user.tenant_id,
        reference_no=_next_reference(db, user.tenant_id),
        title=data.title,
        type=data.type,
        status="draft",
        owner_id=owner_id,
        counterparty=data.counterparty,
        department=data.department,
        value=data.value,
        currency=data.currency or user.tenant.currency,
        effective_date=data.effective_date,
        end_date=data.end_date,
        renewal_type=data.renewal_type,
        governing_law=data.governing_law,
        risk_level=data.risk_level or "low",
        ai_summary=data.ai_summary,
        tags=data.tags,
        body=data.body,
        source=data.source,
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    db.add(models.ContractVersion(tenant_id=user.tenant_id, contract_id=c.id, version_no=1, body=c.body, change_summary="Created", created_by=user.id))
    record(db, tenant_id=user.tenant_id, action="contract.created", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"source": c.source})
    db.commit()
    db.refresh(c)
    return _detail(db, c)


# ---------- update ----------


@router.patch("/{contract_id}", response_model=schemas.ContractDetail)
def update_contract(contract_id: str, data: schemas.ContractUpdateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    c = _get_owned_contract(db, user, contract_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit contracts.")
    if c.status not in {"draft", "changes_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This contract is '{c.status}' and can't be edited. Return it to draft first.")
    changes: dict = {}
    body_changed = False
    for field, val in data.model_dump(exclude_unset=True).items():
        if val is None and field not in {"effective_date", "end_date"}:
            continue
        if getattr(c, field) != val:
            changes[field] = val
            setattr(c, field, val)
            if field == "body":
                body_changed = True
    if changes:
        if body_changed:
            last = db.scalar(select(func.max(models.ContractVersion.version_no)).where(models.ContractVersion.contract_id == c.id)) or 0
            db.add(models.ContractVersion(tenant_id=user.tenant_id, contract_id=c.id, version_no=last + 1, body=c.body, change_summary="Edited document", created_by=user.id))
        record(db, tenant_id=user.tenant_id, action="contract.updated", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"fields": list(changes.keys())})
        db.commit()
        db.refresh(c)
    return _detail(db, c)


# ---------- delete ----------


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(contract_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    c = _get_owned_contract(db, user, contract_id)
    if user.role not in {"owner", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete contracts.")
    label = c.title
    db.query(models.Comment).filter(models.Comment.contract_id == c.id).delete()
    db.query(models.ContractVersion).filter(models.ContractVersion.contract_id == c.id).delete()
    db.delete(c)
    record(db, tenant_id=user.tenant_id, action="contract.deleted", actor=user, object_type="contract", object_id=contract_id, object_label=label, ip=client_ip(request))
    db.commit()


# ---------- lifecycle transition ----------


@router.post("/{contract_id}/transition", response_model=schemas.ContractDetail)
def transition(contract_id: str, data: schemas.TransitionIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    c = _get_owned_contract(db, user, contract_id)
    target = data.status
    if not lifecycle.can_transition(c.status, target):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Can't move a '{c.status}' contract to '{target}'. Allowed: {lifecycle.available(c.status) or 'none (terminal state)'}.")
    # light role gates on the consequential moves
    if target in {"approved", "rejected", "changes_requested"} and user.role not in _APPROVE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an approver/manager/admin can approve, reject, or request changes.")
    if target in {"out_for_signature", "in_review", "active", "voided", "renewed", "terminated", "draft", "signed", "declined", "expiring", "expired"} and user.role not in _EDIT_ROLES and user.role not in _APPROVE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to change this contract's status.")
    prev = c.status
    c.status = target
    if data.comment.strip():
        db.add(models.Comment(tenant_id=user.tenant_id, contract_id=c.id, author_id=user.id, author_name=user.name, body=f"[{prev} → {target}] {data.comment.strip()}"))
    notify_user_id = c.owner_id if c.owner_id != user.id else None
    record(
        db,
        tenant_id=user.tenant_id,
        action="contract.status_changed",
        actor=user,
        object_type="contract",
        object_id=c.id,
        object_label=c.title,
        ip=client_ip(request),
        meta={"from": prev, "to": target, "comment": data.comment.strip()},
        notify_user_id=notify_user_id,
        notify_title=f"\"{c.title}\" is now {target.replace('_', ' ')}",
        notify_body=f"{user.name} moved it from {prev.replace('_', ' ')}.",
    )
    db.commit()
    db.refresh(c)
    return _detail(db, c)


# ---------- comments ----------


@router.get("/{contract_id}/comments", response_model=list[schemas.CommentOut])
def list_comments(contract_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.CommentOut]:
    _get_owned_contract(db, user, contract_id)
    rows = db.scalars(select(models.Comment).where(models.Comment.contract_id == contract_id).order_by(models.Comment.created_at)).all()
    return [schemas.CommentOut.model_validate(r) for r in rows]


@router.post("/{contract_id}/comments", response_model=schemas.CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(contract_id: str, data: schemas.CommentIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.CommentOut:
    c = _get_owned_contract(db, user, contract_id)
    comment = models.Comment(tenant_id=user.tenant_id, contract_id=c.id, author_id=user.id, author_name=user.name, body=data.body)
    db.add(comment)
    record(db, tenant_id=user.tenant_id, action="contract.commented", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request))
    db.commit()
    db.refresh(comment)
    return schemas.CommentOut.model_validate(comment)


# ---------- versions ----------


@router.get("/{contract_id}/versions", response_model=list[schemas.VersionOut])
def list_versions(contract_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.VersionOut]:
    _get_owned_contract(db, user, contract_id)
    rows = db.scalars(select(models.ContractVersion).where(models.ContractVersion.contract_id == contract_id).order_by(desc(models.ContractVersion.version_no))).all()
    return [schemas.VersionOut.model_validate(r) for r in rows]


# ---------- per-contract activity ----------


@router.get("/{contract_id}/activity", response_model=list[schemas.ActivityItem])
def contract_activity(contract_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.ActivityItem]:
    _get_owned_contract(db, user, contract_id)
    rows = db.scalars(
        select(models.AuditLog).where(models.AuditLog.tenant_id == user.tenant_id, models.AuditLog.object_type == "contract", models.AuditLog.object_id == contract_id).order_by(desc(models.AuditLog.at)).limit(200)
    ).all()
    return [schemas.ActivityItem(id=r.id, at=r.at, actor_name=r.actor_name, action=r.action, object_type=r.object_type, object_id=r.object_id, object_label=r.object_label) for r in rows]
