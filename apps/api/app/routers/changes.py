"""Amendments, terminations, renewal schedules, obligation rollup and legal checklists.

Everything that happens to an agreement after it has been signed, plus the two operational
views (obligations across the repository, and the checklists Legal publishes) that only make
sense at workspace level rather than per contract.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import change_service, models, obligation_service, schemas
from ..audit import record
from ..change_service import ChangeError
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(tags=["changes"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}
_ADMIN_ROLES = {"owner", "admin", "manager"}


def _guard(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return action(*args, **kwargs)
    except ChangeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


def _contract(db: Session, user: models.User, cid: str) -> models.Contract:
    c = db.get(models.Contract, cid)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


# ---------------------------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------------------------


@router.post("/contracts/{contract_id}/amend", response_model=schemas.ContractDetail,
             status_code=status.HTTP_201_CREATED)
def request_amendment(contract_id: str, data: schemas.AmendmentIn, request: Request,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    """Open an amendment against a live agreement.

    Returns the **new** draft: the amendment is negotiated and signed on its own terms, and
    until it is executed the parent is still what is in force.
    """
    from .contracts import _detail

    parent = _contract(db, user, contract_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to amend agreements.")
    child = _guard(change_service.request_amendment, db, parent, actor=user,
                   title=data.title, reason=data.reason, ip=client_ip(request))
    db.commit()
    db.refresh(child)
    return _detail(db, child)


@router.get("/contracts/{contract_id}/amendment-impact", response_model=schemas.AmendmentImpactOut)
def preview_impact(contract_id: str, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.AmendmentImpactOut:
    """What this amendment changes relative to what it amends — before executing it."""
    child = _contract(db, user, contract_id)
    relation = db.scalar(
        select(models.ContractRelation).where(
            models.ContractRelation.child_id == child.id,
            models.ContractRelation.kind == "amendment_of",
        )
    )
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="This agreement is not an amendment of anything.")
    parent = db.get(models.Contract, relation.parent_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="The agreement being amended no longer exists.")
    return schemas.AmendmentImpactOut(**change_service.amendment_impact(db, child, parent))


@router.post("/contracts/{contract_id}/amendment-impact", response_model=schemas.AmendmentImpactOut)
def execute_amendment(contract_id: str, request: Request, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.AmendmentImpactOut:
    """Bring an executed amendment into force: record its impact and supersede the parent."""
    child = _contract(db, user, contract_id)
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to bring an amendment into force.")
    impact = _guard(change_service.execute_amendment, db, child, actor=user,
                    ip=client_ip(request))
    db.commit()
    return schemas.AmendmentImpactOut(**impact)


# ---------------------------------------------------------------------------------------
# Terminations
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/terminations",
            response_model=list[schemas.TerminationOut])
def list_terminations(contract_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> list[schemas.TerminationOut]:
    contract = _contract(db, user, contract_id)
    rows = db.scalars(
        select(models.TerminationRequest)
        .where(models.TerminationRequest.contract_id == contract.id,
               models.TerminationRequest.tenant_id == user.tenant_id)
        .order_by(desc(models.TerminationRequest.created_at))
    ).all()
    return [schemas.TerminationOut.model_validate(r) for r in rows]


@router.post("/contracts/{contract_id}/terminations", response_model=schemas.TerminationOut,
             status_code=status.HTTP_201_CREATED)
def request_termination(contract_id: str, data: schemas.TerminationIn, request: Request,
                        db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> schemas.TerminationOut:
    """Open a termination request. Terminates nothing by itself — it needs sign-off first."""
    contract = _contract(db, user, contract_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to request termination.")
    req = _guard(change_service.request_termination, db, contract, actor=user,
                 reason=data.reason, reason_code=data.reason_code,
                 notice_days=data.notice_days, effective_date=data.effective_date,
                 documents=data.documents, required_roles=data.required_roles,
                 ip=client_ip(request))
    db.commit()
    db.refresh(req)
    return schemas.TerminationOut.model_validate(req)


@router.post("/terminations/{request_id}/decide", response_model=schemas.TerminationOut)
def decide_termination(request_id: str, data: schemas.TerminationDecisionIn,
                       request: Request, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> schemas.TerminationOut:
    """Record one stakeholder's sign-off. A rejection ends the request immediately."""
    req = db.get(models.TerminationRequest, request_id)
    if req is None or req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Termination request not found")
    _guard(change_service.decide_termination, db, req, actor=user, approve=data.approve,
           comment=data.comment, ip=client_ip(request))
    db.commit()
    db.refresh(req)
    return schemas.TerminationOut.model_validate(req)


@router.post("/terminations/{request_id}/execute", response_model=schemas.ContractDetail)
def execute_termination(request_id: str, request: Request, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    """Serve the termination: set the agreement terminated and close its open obligations."""
    from .contracts import _detail

    req = db.get(models.TerminationRequest, request_id)
    if req is None or req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Termination request not found")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to execute a termination.")
    contract = _contract(db, user, req.contract_id)
    _guard(change_service.execute_termination, db, req, contract, actor=user,
           ip=client_ip(request))
    db.commit()
    db.refresh(contract)
    return _detail(db, contract)


@router.get("/terminations/{request_id}/notice", response_model=schemas.TerminationNoticeOut)
def termination_notice(request_id: str, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> schemas.TerminationNoticeOut:
    """The notice served on the counterparty, generated from the recorded request.

    Generated rather than hand-written so the dates and reason in the notice are the ones
    actually recorded — a notice that disagrees with the record is a dispute.
    """
    req = db.get(models.TerminationRequest, request_id)
    if req is None or req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Termination request not found")
    contract = _contract(db, user, req.contract_id)
    tenant = db.get(models.Tenant, user.tenant_id)
    return schemas.TerminationNoticeOut(
        request_id=req.id, contract_id=contract.id,
        body=change_service.termination_notice(
            db, req, contract, tenant.name if tenant else "the Bank"),
    )


# ---------------------------------------------------------------------------------------
# Renewal notice schedule
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/renewal-schedule",
            response_model=schemas.RenewalScheduleOut)
def get_renewal_schedule(contract_id: str, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)) -> schemas.RenewalScheduleOut:
    contract = _contract(db, user, contract_id)
    return schemas.RenewalScheduleOut(
        notice_days=change_service.notice_schedule(contract),
        due=change_service.due_notices(contract),
        end_date=contract.end_date,
        renewal_type=contract.renewal_type,
    )


@router.put("/contracts/{contract_id}/renewal-schedule",
            response_model=schemas.RenewalScheduleOut)
def set_renewal_schedule(contract_id: str, data: schemas.RenewalScheduleIn, request: Request,
                         db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)) -> schemas.RenewalScheduleOut:
    """Set when this agreement raises renewal notices.

    Per agreement because a three-year outsourcing contract and a three-month NDA do not need
    the same warning, and one global setting means one of them is always wrong.
    """
    contract = _contract(db, user, contract_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You cannot edit this contract.")
    _guard(change_service.set_notice_schedule, db, contract, data.notice_days, actor=user,
           ip=client_ip(request))
    db.commit()
    db.refresh(contract)
    return schemas.RenewalScheduleOut(
        notice_days=change_service.notice_schedule(contract),
        due=change_service.due_notices(contract),
        end_date=contract.end_date,
        renewal_type=contract.renewal_type,
    )


# ---------------------------------------------------------------------------------------
# Obligations across the repository
# ---------------------------------------------------------------------------------------


@router.get("/obligations", response_model=schemas.ObligationRollupOut)
def obligations_rollup(owner_id: str = "", status_filter: str = "", contract_id: str = "",
                       department_id: str = "", due_within_days: int | None = None,
                       overdue_only: bool = False, mine: bool = False,
                       db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> schemas.ObligationRollupOut:
    """Every obligation in the workspace, with the counts an operations view needs.

    An obligation tracker you can only read one contract at a time is a list nobody checks.
    """
    result = obligation_service.rollup(
        db, user.tenant_id, owner_id=(user.id if mine else owner_id),
        status=status_filter, contract_id=contract_id, department_id=department_id,
        due_within_days=due_within_days, overdue_only=overdue_only,
    )
    return schemas.ObligationRollupOut(**result)


@router.post("/obligations/sweep", response_model=dict)
def run_obligation_sweep(request: Request, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)) -> dict:
    """Run the reminder/escalation sweep for this workspace now.

    Normally a scheduled beat; exposed so an operator can run it on demand and so the
    behaviour is testable through the API rather than only through Celery.
    """
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to run the sweep.")
    result = obligation_service.sweep(db, tenant_id=user.tenant_id)
    record(db, tenant_id=user.tenant_id, action="obligation.sweep_run", actor=user,
           object_type="tenant", object_id=user.tenant_id, ip=client_ip(request),
           meta=result)
    db.commit()
    return result


# ---------------------------------------------------------------------------------------
# Legal checklists
# ---------------------------------------------------------------------------------------


@router.get("/checklists", response_model=list[schemas.ChecklistOut])
def list_checklists(contract_type: str = Query(default=""), include_drafts: bool = False,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> list[schemas.ChecklistOut]:
    stmt = select(models.LegalChecklist).where(
        models.LegalChecklist.tenant_id == user.tenant_id)
    if not include_drafts:
        stmt = stmt.where(models.LegalChecklist.status == "published")
    rows = db.scalars(stmt.order_by(models.LegalChecklist.owner_function.asc(),
                                    models.LegalChecklist.title.asc())).all()
    if contract_type:
        rows = [r for r in rows if r.contract_type in ("", contract_type)]
    return [schemas.ChecklistOut.model_validate(r) for r in rows]


@router.post("/checklists", response_model=schemas.ChecklistOut,
             status_code=status.HTTP_201_CREATED)
def create_checklist(data: schemas.ChecklistIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.ChecklistOut:
    """Publish a checklist for the workspace to work against.

    Any function can own one — the brief is explicit that Legal owns theirs but other
    stakeholders publish their own.
    """
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to publish checklists.")
    checklist = models.LegalChecklist(
        tenant_id=user.tenant_id, created_by=user.id, **data.model_dump())
    db.add(checklist)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="checklist.created", actor=user,
           object_type="checklist", object_id=checklist.id, object_label=checklist.title,
           ip=client_ip(request), meta={"items": len(checklist.items or [])})
    db.commit()
    db.refresh(checklist)
    return schemas.ChecklistOut.model_validate(checklist)


@router.patch("/checklists/{cid}", response_model=schemas.ChecklistOut)
def update_checklist(cid: str, data: schemas.ChecklistUpdateIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.ChecklistOut:
    """Edit a checklist. Changing a published one bumps its version.

    A checklist that changes silently cannot be used as evidence that a given agreement met
    the requirements in force at the time.
    """
    checklist = db.get(models.LegalChecklist, cid)
    if checklist is None or checklist.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to edit checklists.")
    payload = data.model_dump(exclude_unset=True)
    substantive = {"items", "title", "description", "contract_type"} & set(payload)
    for k, v in payload.items():
        if v is not None:
            setattr(checklist, k, v)
    if substantive and checklist.status == "published":
        checklist.version_no += 1
    if payload.get("status") == "published" and checklist.published_at is None:
        checklist.published_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    record(db, tenant_id=user.tenant_id, action="checklist.updated", actor=user,
           object_type="checklist", object_id=checklist.id, object_label=checklist.title,
           ip=client_ip(request),
           meta={"fields": list(payload.keys()), "version_no": checklist.version_no})
    db.commit()
    db.refresh(checklist)
    return schemas.ChecklistOut.model_validate(checklist)
