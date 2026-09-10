"""Clause library and playbooks — approved language, and the policy a draft is measured against.

Two resources in one router because they are one feature: the library supplies the wording, the
playbook says which of it is compulsory. Splitting them would mean a router that can only ever
be used alongside the other.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from .. import clause_service, models, playbook_service, schemas
from ..audit import record
from ..clause_service import ClauseError
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(tags=["clauses"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}
_ADMIN_ROLES = {"owner", "admin", "manager"}


def _owned_clause(db: Session, user: models.User, cid: str) -> models.Clause:
    c = db.get(models.Clause, cid)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    return c


def _owned_playbook(db: Session, user: models.User, pid: str) -> models.Playbook:
    p = db.get(models.Playbook, pid)
    if p is None or p.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return p


def _guard(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return action(*args, **kwargs)
    except (ClauseError, playbook_service.PlaybookError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


def _out(db: Session, c: models.Clause, *, with_alternatives: bool = False) -> schemas.ClauseOut:
    out = schemas.ClauseOut.model_validate(c)
    if with_alternatives:
        out.alternatives = [schemas.ClauseOut.model_validate(a)
                            for a in clause_service.alternatives(db, c)]
    return out


# ---------------------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------------------


@router.get("/clauses", response_model=list[schemas.ClauseOut])
def list_clauses(
    q: str = "", category: str = "", status_filter: str = "", include_alternatives: bool = False,
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user),
) -> list[schemas.ClauseOut]:
    """The library. Alternatives are excluded from the top level — they belong under the
    clause they soften, not as siblings competing with it in a search."""
    stmt = select(models.Clause).where(models.Clause.tenant_id == user.tenant_id,
                                       models.Clause.parent_id.is_(None))
    if category:
        stmt = stmt.where(models.Clause.category == category)
    if status_filter:
        stmt = stmt.where(models.Clause.status == status_filter)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(models.Clause.title.ilike(pattern),
                              models.Clause.key.ilike(pattern),
                              models.Clause.body.ilike(pattern)))
    rows = db.scalars(stmt.order_by(models.Clause.category.asc(),
                                    models.Clause.title.asc())).all()
    return [_out(db, c, with_alternatives=include_alternatives) for c in rows]


@router.get("/clauses/{cid}", response_model=schemas.ClauseOut)
def get_clause(cid: str, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    return _out(db, _owned_clause(db, user, cid), with_alternatives=True)


@router.post("/clauses", response_model=schemas.ClauseOut,
             status_code=status.HTTP_201_CREATED)
def create_clause(data: schemas.ClauseIn, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to write clauses.")
    if clause_service.by_key(db, user.tenant_id, data.key) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"A clause with the key '{data.key}' already exists.")
    parent = None
    if data.parent_id:
        parent = _owned_clause(db, user, data.parent_id)
        if parent.parent_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="An alternative cannot itself have alternatives.")
    c = models.Clause(
        tenant_id=user.tenant_id, key=data.key, title=data.title.strip()[:200],
        category=data.category.strip()[:80], body=data.body,
        position=data.position, risk_level=data.risk_level,
        parent_id=parent.id if parent else None, fallback_rank=data.fallback_rank,
        guidance=data.guidance, jurisdiction=data.jurisdiction.strip()[:100],
        tags=list(data.tags or []), status="draft", created_by=user.id,
    )
    problems = clause_service.validate(c)
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="; ".join(problems))
    db.add(c)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="clause.created", actor=user,
           object_type="clause", object_id=c.id, object_label=c.title or c.key,
           ip=client_ip(request), meta={"key": c.key, "parent_id": c.parent_id})
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.patch("/clauses/{cid}", response_model=schemas.ClauseOut)
def update_clause(cid: str, data: schemas.ClauseUpdateIn, request: Request,
                  db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    c = _owned_clause(db, user, cid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to edit clauses.")
    payload = data.model_dump(exclude_unset=True)
    if "key" in payload and payload["key"] != c.key and c.status == "active":
        # Templates in the wild point at this key. Renaming it would break them silently,
        # which is the one failure mode a reference is supposed to rule out.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An approved clause's key cannot change — templates refer to it.")
    for k, v in payload.items():
        if v is None:
            continue
        setattr(c, k, v.strip() if isinstance(v, str) and k in {"title", "category", "jurisdiction"} else v)
    problems = clause_service.validate(c)
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="; ".join(problems))
    if {"body", "title", "position", "risk_level"} & set(payload):
        clause_service.edit_unapproves(c)
    record(db, tenant_id=user.tenant_id, action="clause.updated", actor=user,
           object_type="clause", object_id=c.id, object_label=c.title or c.key,
           ip=client_ip(request), meta={"fields": list(payload.keys())})
    db.commit()
    db.refresh(c)
    return _out(db, c, with_alternatives=True)


@router.post("/clauses/{cid}/submit", response_model=schemas.ClauseOut)
def submit_clause(cid: str, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    c = _owned_clause(db, user, cid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to edit clauses.")
    _guard(clause_service.submit_for_approval, db, c, actor=user, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.post("/clauses/{cid}/approve", response_model=schemas.ClauseOut)
def approve_clause(cid: str, data: schemas.TemplateApprovalIn, request: Request,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    c = _owned_clause(db, user, cid)
    _guard(clause_service.approve, db, c, actor=user, note=data.note, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.post("/clauses/{cid}/reject", response_model=schemas.ClauseOut)
def reject_clause(cid: str, data: schemas.TemplateRejectIn, request: Request,
                  db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    c = _owned_clause(db, user, cid)
    _guard(clause_service.reject, db, c, actor=user, reason=data.reason, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.post("/clauses/{cid}/retire", response_model=schemas.ClauseOut)
def retire_clause(cid: str, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ClauseOut:
    c = _owned_clause(db, user, cid)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to retire clauses.")
    clause_service.retire(db, c, actor=user, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.get("/clauses/{cid}/versions", response_model=list[schemas.ClauseVersionOut])
def clause_versions(cid: str, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> list[schemas.ClauseVersionOut]:
    c = _owned_clause(db, user, cid)
    rows = db.scalars(
        select(models.ClauseVersion)
        .where(models.ClauseVersion.clause_id == c.id,
               models.ClauseVersion.tenant_id == user.tenant_id)
        .order_by(desc(models.ClauseVersion.version_no))
    ).all()
    return [schemas.ClauseVersionOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------------------


@router.get("/playbooks", response_model=list[schemas.PlaybookOut])
def list_playbooks(db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> list[schemas.PlaybookOut]:
    rows = db.scalars(
        select(models.Playbook)
        .where(models.Playbook.tenant_id == user.tenant_id)
        .order_by(models.Playbook.contract_type.asc(), models.Playbook.name.asc())
    ).all()
    return [schemas.PlaybookOut.model_validate(r) for r in rows]


@router.post("/playbooks", response_model=schemas.PlaybookOut,
             status_code=status.HTTP_201_CREATED)
def create_playbook(data: schemas.PlaybookIn, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.PlaybookOut:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to write policy.")
    problems = playbook_service.validate_rules(db, user.tenant_id, data.rules)
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="; ".join(problems))
    p = models.Playbook(
        tenant_id=user.tenant_id, name=data.name.strip()[:200],
        description=data.description.strip()[:500], contract_type=data.contract_type,
        applies_when=dict(data.applies_when or {}), rules=list(data.rules or []),
        status=data.status, created_by=user.id,
    )
    db.add(p)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="playbook.created", actor=user,
           object_type="playbook", object_id=p.id, object_label=p.name,
           ip=client_ip(request), meta={"rules": len(p.rules or [])})
    db.commit()
    db.refresh(p)
    return schemas.PlaybookOut.model_validate(p)


@router.patch("/playbooks/{pid}", response_model=schemas.PlaybookOut)
def update_playbook(pid: str, data: schemas.PlaybookUpdateIn, request: Request,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.PlaybookOut:
    p = _owned_playbook(db, user, pid)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to write policy.")
    payload = data.model_dump(exclude_unset=True)
    if payload.get("rules") is not None:
        problems = playbook_service.validate_rules(db, user.tenant_id, payload["rules"])
        if problems:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="; ".join(problems))
    for k, v in payload.items():
        if v is not None:
            setattr(p, k, v)
    record(db, tenant_id=user.tenant_id, action="playbook.updated", actor=user,
           object_type="playbook", object_id=p.id, object_label=p.name,
           ip=client_ip(request), meta={"fields": list(payload.keys())})
    db.commit()
    db.refresh(p)
    return schemas.PlaybookOut.model_validate(p)


@router.delete("/playbooks/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playbook(pid: str, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> None:
    p = _owned_playbook(db, user, pid)
    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to delete policy.")
    name = p.name
    db.delete(p)
    record(db, tenant_id=user.tenant_id, action="playbook.deleted", actor=user,
           object_type="playbook", object_id=pid, object_label=name, ip=client_ip(request))
    db.commit()


@router.get("/contracts/{contract_id}/policy-review", response_model=schemas.PolicyReviewOut)
def policy_review(contract_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.PolicyReviewOut:
    """Measure the draft against policy. Read-only — see `POST` to act on the result."""
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return schemas.PolicyReviewOut(**playbook_service.review(db, c))


@router.post("/contracts/{contract_id}/policy-review", response_model=schemas.PolicyReviewOut)
def run_policy_review(contract_id: str, request: Request, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.PolicyReviewOut:
    """Review and act: a blocking deviation classifies the agreement non-standard, which
    selects the non-standard approval route."""
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    result = playbook_service.review_and_classify(db, c, actor=user, ip=client_ip(request))
    record(db, tenant_id=user.tenant_id, action="contract.policy_reviewed", actor=user,
           object_type="contract", object_id=c.id, object_label=c.title,
           ip=client_ip(request),
           meta={"checked": result["checked"], "deviations": result["deviation_count"],
                 "blockers": result["blocker_count"]})
    db.commit()
    return schemas.PolicyReviewOut(**result)
