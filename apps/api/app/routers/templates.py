"""Contract templates — a library of pre-fab contracts the workspace can spawn drafts from.
Save-as-template + use-template are the two common shapes (DocuSign / PandaDoc / Deel pattern)."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/templates", tags=["templates"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}


def _get_owned(db: Session, user: models.User, tid: str) -> models.ContractTemplate:
    t = db.get(models.ContractTemplate, tid)
    if t is None or t.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return t


def _next_reference(db: Session, tenant_id: str) -> str:
    year = dt.date.today().year
    n = db.scalar(select(func.count(models.Contract.id)).where(models.Contract.tenant_id == tenant_id)) or 0
    return f"C-{year}-{n + 1:04d}"


@router.get("", response_model=list[schemas.ContractTemplateOut])
def list_templates(
    active: bool | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.ContractTemplateOut]:
    stmt = select(models.ContractTemplate).where(models.ContractTemplate.tenant_id == user.tenant_id)
    if active is True:
        stmt = stmt.where(models.ContractTemplate.is_active.is_(True))
    rows = db.scalars(stmt.order_by(desc(models.ContractTemplate.updated_at))).all()
    return [schemas.ContractTemplateOut.model_validate(r) for r in rows]


@router.post("", response_model=schemas.ContractTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(data: schemas.ContractTemplateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to create templates.")
    t = models.ContractTemplate(
        tenant_id=user.tenant_id, name=data.name.strip()[:200], description=(data.description or "").strip()[:500],
        contract_type=data.contract_type, body=data.body or "", default_currency=data.default_currency,
        default_term_months=max(1, int(data.default_term_months or 12)), default_renewal_type=data.default_renewal_type,
        default_risk_level=data.default_risk_level, default_governing_law=data.default_governing_law,
        default_tags=list(data.default_tags or []), is_active=bool(data.is_active), created_by=user.id,
    )
    db.add(t)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="template.created", actor=user, object_type="template", object_id=t.id, object_label=t.name, ip=client_ip(request))
    db.commit()
    db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.get("/{tid}", response_model=schemas.ContractTemplateOut)
def get_template(tid: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    return schemas.ContractTemplateOut.model_validate(_get_owned(db, user, tid))


@router.patch("/{tid}", response_model=schemas.ContractTemplateOut)
def update_template(tid: str, data: schemas.ContractTemplateUpdateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    t = _get_owned(db, user, tid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit templates.")
    payload = data.model_dump(exclude_unset=True)
    changed = False
    for k, v in payload.items():
        if v is None:
            continue
        if isinstance(v, str) and k in {"name", "description", "default_governing_law"}:
            v = v.strip()
        if k == "default_term_months":
            v = max(1, int(v))
        setattr(t, k, v)
        changed = True
    if changed:
        record(db, tenant_id=user.tenant_id, action="template.updated", actor=user, object_type="template", object_id=t.id, object_label=t.name, ip=client_ip(request), meta={"fields": list(payload.keys())})
        db.commit()
        db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.delete("/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(tid: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    t = _get_owned(db, user, tid)
    if user.role not in {"owner", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete templates.")
    name = t.name
    db.delete(t)
    record(db, tenant_id=user.tenant_id, action="template.deleted", actor=user, object_type="template", object_id=tid, object_label=name, ip=client_ip(request))
    db.commit()


@router.post("/{tid}/use", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
def use_template(tid: str, data: schemas.UseTemplateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    """Spawn a new DRAFT contract from a template — body + metadata defaults copied, caller can
    override title/counterparty/value/dates/owner."""
    t = _get_owned(db, user, tid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to create contracts.")
    if not t.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This template is archived.")
    owner_id = data.owner_id or user.id
    if owner_id != user.id:
        ou = db.get(models.User, owner_id)
        if ou is None or ou.tenant_id != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid owner.")
    # date defaults
    effective = data.effective_date or dt.date.today()
    end = data.end_date or (dt.date(effective.year + (t.default_term_months // 12), ((effective.month - 1 + (t.default_term_months % 12)) % 12) + 1, effective.day) if t.default_term_months else None)
    c = models.Contract(
        tenant_id=user.tenant_id,
        reference_no=_next_reference(db, user.tenant_id),
        title=data.title.strip()[:300],
        type=t.contract_type, status="draft", owner_id=owner_id,
        counterparty=(data.counterparty or "").strip()[:200], department="",
        value=float(data.value or 0.0), currency=t.default_currency,
        effective_date=effective, end_date=end,
        renewal_type=t.default_renewal_type, governing_law=t.default_governing_law,
        risk_level=t.default_risk_level, ai_summary="",
        tags=list(t.default_tags or []), body=t.body or "", source="template",
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    db.add(models.ContractVersion(tenant_id=user.tenant_id, contract_id=c.id, version_no=1, body=c.body, change_summary=f"Created from template “{t.name}”", created_by=user.id))
    t.usage_count = (t.usage_count or 0) + 1
    record(db, tenant_id=user.tenant_id, action="contract.created", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"source": "template", "template_id": t.id})
    db.commit()
    db.refresh(c)
    # avoid a circular import — build the detail dict here, _detail() lives in contracts.py
    from .contracts import _detail

    return _detail(db, c)
