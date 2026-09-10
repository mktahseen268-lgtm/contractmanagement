"""Workflow administration and the parallel-review surface (Phase 4).

Split from `routers/workflows.py`, which owns definitions and the decide endpoint. This module
covers what the rebuilt engine added:

    /workflow/runs/{id}                 the stage graph, with each reviewer's live status
    /workflow/runs/{id}/reviewers       add / remove a reviewer mid-flight (RFI §3.6)
    /workflow/rules                     the dynamic approval matrix
    /workflow/delegations               out-of-office proxies
    /workflow/holidays                  the SLA business calendar
    /workflow/escalations               the escalations feed + mean-time-to-resolve
    /workflow/sla-sweep                 run the sweep now (admin)
    /contracts/{id}/review              the consolidated internal review view (RFI §3.3)
    /contracts/{id}/comments            post a comment or amendment, with @mentions
    /mentions                           the "mentions me" inbox filter (RFI §3.4)
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import business_calendar, comment_service, models, schemas
from .. import workflow_service as wf
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(tags=["workflow"])

_ADMIN_ROLES = {"owner", "admin"}


def _require_admin(user: models.User) -> models.User:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only owners and admins can change workflow configuration.")
    return user


def _wf_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


def _owned_contract(db: Session, user: models.User, contract_id: str) -> models.Contract:
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


def _owned_run(db: Session, user: models.User, run_id: str) -> models.WorkflowRun:
    run = db.get(models.WorkflowRun, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return run


def _names(db: Session, tenant_id: str) -> dict[str, str]:
    return {
        u.id: u.name
        for u in db.scalars(select(models.User).where(models.User.tenant_id == tenant_id)).all()
    }


# ---------------------------------------------------------------------------------------
# The run, as a stage graph
# ---------------------------------------------------------------------------------------


def _step_out(step: models.WorkflowRunStep, names: dict[str, str],
              now: dt.datetime) -> schemas.RunStepOut:
    item = schemas.RunStepOut.model_validate(step)
    item.is_overdue = bool(step.due_at and step.status == "active" and now > step.due_at)
    item.assignee_name = (
        names.get(step.assignee_value, "") if step.assignee_kind == "user"
        else f"Any {step.assignee_value}"
    )
    item.delegated_from_name = names.get(step.delegated_from or "", "")
    return item


def _run_out(db: Session, run: models.WorkflowRun, user: models.User) -> schemas.WorkflowRunGraphOut:
    names = _names(db, run.tenant_id)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    steps = wf.run_steps(db, run.id)
    stages_def = run.stages or []

    stages: list[schemas.RunStageOut] = []
    for index, stage in enumerate(stages_def):
        rows = [s for s in steps if s.stage_index == index]
        considered = [s for s in rows if s.status != "skipped"]
        approvals = sum(1 for s in considered if s.status == "approved")
        policy = stage.get("policy", "all")
        if policy == "any":
            required = 1
        elif policy == "quorum":
            required = max(1, int(stage.get("threshold") or 1))
        elif policy == "percentage":
            required = max(1, round(len(considered) * (int(stage.get("threshold") or 100) / 100.0)))
        else:
            required = len(considered)

        if any(s.status == "active" for s in rows):
            stage_status = "active"
        elif rows and all(s.status not in ("pending", "active") for s in rows):
            stage_status = "complete"
        else:
            stage_status = "pending"

        stages.append(schemas.RunStageOut(
            index=index, name=stage.get("name", f"Stage {index + 1}"), policy=policy,
            threshold=int(stage.get("threshold") or 0), status=stage_status,
            approvals=approvals, required=required,
            steps=[_step_out(s, names, now) for s in rows],
        ))

    rule_names: list[str] = []
    for rule_id in run.applied_rule_ids or []:
        rule = db.get(models.ApprovalRule, rule_id)
        if rule is not None:
            rule_names.append(rule.name)

    return schemas.WorkflowRunGraphOut(
        id=run.id, contract_id=run.contract_id, definition_name=run.definition_name,
        status=run.status, current_stage=run.current_stage or 0,
        started_by_name=run.started_by_name, started_at=run.started_at,
        completed_at=run.completed_at, stages=stages,
        my_steps=[s.id for s in wf.steps_for_user(db, run, user)],
        applied_rules=rule_names,
    )


@router.get("/workflow/runs/{run_id}", response_model=schemas.WorkflowRunGraphOut)
def get_run(run_id: str, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)) -> schemas.WorkflowRunGraphOut:
    """The stage graph with every reviewer's live status — the parallel-review screen."""
    return _run_out(db, _owned_run(db, user, run_id), user)


@router.post("/workflow/runs/{run_id}/reviewers", response_model=schemas.WorkflowRunGraphOut,
             status_code=status.HTTP_201_CREATED)
def add_reviewer(run_id: str, data: schemas.AddReviewerIn, request: Request,
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.WorkflowRunGraphOut:
    """Add a reviewer to a stage that has not finished (RFI §3.6)."""
    run = _owned_run(db, user, run_id)
    contract = _owned_contract(db, user, run.contract_id)
    try:
        wf.add_reviewer(
            db, run=run, contract=contract, stage_index=data.stage_index,
            name=data.name, assignee_kind=data.assignee_kind,
            assignee_value=data.assignee_value, actor=user, sla_hours=data.sla_hours,
            ip=client_ip(request),
        )
    except wf.WorkflowError as e:
        db.rollback()
        raise _wf_error(e) from e
    db.commit()
    return _run_out(db, run, user)


@router.delete("/workflow/runs/{run_id}/reviewers/{step_id}", response_model=schemas.WorkflowRunGraphOut)
def remove_reviewer(run_id: str, step_id: str, data: schemas.RemoveReviewerIn, request: Request,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.WorkflowRunGraphOut:
    run = _owned_run(db, user, run_id)
    contract = _owned_contract(db, user, run.contract_id)
    step = db.get(models.WorkflowRunStep, step_id)
    if step is None or step.run_id != run.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer not found")
    try:
        wf.remove_reviewer(db, run=run, contract=contract, step=step, actor=user,
                           reason=data.reason, ip=client_ip(request))
    except wf.WorkflowError as e:
        db.rollback()
        raise _wf_error(e) from e
    db.commit()
    return _run_out(db, run, user)


# ---------------------------------------------------------------------------------------
# Approval matrix
# ---------------------------------------------------------------------------------------


@router.get("/workflow/rules", response_model=list[schemas.ApprovalRuleOut])
def list_rules(db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> list[schemas.ApprovalRuleOut]:
    rows = db.scalars(
        select(models.ApprovalRule)
        .where(models.ApprovalRule.tenant_id == user.tenant_id)
        .order_by(models.ApprovalRule.priority.desc(), models.ApprovalRule.name)
    ).all()
    return [schemas.ApprovalRuleOut.model_validate(r) for r in rows]


@router.post("/workflow/rules", response_model=schemas.ApprovalRuleOut,
             status_code=status.HTTP_201_CREATED)
def create_rule(data: schemas.ApprovalRuleIn, request: Request, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.ApprovalRuleOut:
    _require_admin(user)
    payload = data.model_dump()
    payload["stage_steps"] = [s.model_dump() for s in data.stage_steps]
    rule = models.ApprovalRule(tenant_id=user.tenant_id, created_by=user.id, **payload)
    db.add(rule)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="workflow.rule_created", actor=user,
           object_type="approval_rule", object_id=rule.id, object_label=rule.name,
           ip=client_ip(request), meta=payload)
    db.commit()
    return schemas.ApprovalRuleOut.model_validate(rule)


@router.patch("/workflow/rules/{rule_id}", response_model=schemas.ApprovalRuleOut)
def update_rule(rule_id: str, data: schemas.ApprovalRuleIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.ApprovalRuleOut:
    _require_admin(user)
    rule = db.get(models.ApprovalRule, rule_id)
    if rule is None or rule.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    payload = data.model_dump()
    payload["stage_steps"] = [s.model_dump() for s in data.stage_steps]
    for key, value in payload.items():
        setattr(rule, key, value)
    record(db, tenant_id=user.tenant_id, action="workflow.rule_updated", actor=user,
           object_type="approval_rule", object_id=rule.id, object_label=rule.name,
           ip=client_ip(request), meta=payload)
    db.commit()
    return schemas.ApprovalRuleOut.model_validate(rule)


@router.delete("/workflow/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, request: Request, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> Response:
    _require_admin(user)
    rule = db.get(models.ApprovalRule, rule_id)
    if rule is None or rule.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    # Deactivated, not deleted: an auditor reviewing a past approval needs to see the rule
    # that was in force at the time.
    rule.is_active = False
    record(db, tenant_id=user.tenant_id, action="workflow.rule_deactivated", actor=user,
           object_type="approval_rule", object_id=rule.id, object_label=rule.name,
           ip=client_ip(request))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------------------


@router.get("/workflow/delegations", response_model=list[schemas.DelegationOut])
def list_delegations(mine: bool = Query(False), db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> list[schemas.DelegationOut]:
    stmt = select(models.Delegation).where(models.Delegation.tenant_id == user.tenant_id)
    if mine or user.role not in _ADMIN_ROLES:
        # A non-admin sees only delegations they are party to — who else is on leave is not
        # their business.
        stmt = stmt.where(
            (models.Delegation.from_user_id == user.id)
            | (models.Delegation.to_user_id == user.id)
        )
    rows = db.scalars(stmt.order_by(models.Delegation.starts_at.desc())).all()
    names = _names(db, user.tenant_id)
    out = []
    for r in rows:
        item = schemas.DelegationOut.model_validate(r)
        item.from_user_name = names.get(r.from_user_id, "")
        item.to_user_name = names.get(r.to_user_id, "")
        out.append(item)
    return out


@router.post("/workflow/delegations", response_model=schemas.DelegationOut,
             status_code=status.HTTP_201_CREATED)
def create_delegation(data: schemas.DelegationIn, request: Request, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.DelegationOut:
    """Delegate your own approvals while you are away. Admins may delegate for anyone."""
    if data.ends_at <= data.starts_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The delegation must end after it starts.")
    target = db.get(models.User, data.to_user_id)
    if target is None or target.tenant_id != user.tenant_id or not target.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delegate not found")
    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You cannot delegate to yourself.")

    row = models.Delegation(
        tenant_id=user.tenant_id, from_user_id=user.id, to_user_id=data.to_user_id,
        scope=data.scope or "all", starts_at=data.starts_at, ends_at=data.ends_at,
        reason=data.reason, created_by=user.id,
    )
    db.add(row)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="workflow.delegation_created", actor=user,
           object_type="delegation", object_id=row.id, object_label=target.name,
           ip=client_ip(request),
           meta={"to_user_id": target.id, "to_user_name": target.name, "scope": row.scope,
                 "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(),
                 "reason": row.reason})
    db.commit()
    out = schemas.DelegationOut.model_validate(row)
    out.from_user_name, out.to_user_name = user.name, target.name
    return out


@router.delete("/workflow/delegations/{delegation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_delegation(delegation_id: str, request: Request, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> Response:
    row = db.get(models.Delegation, delegation_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delegation not found")
    if row.from_user_id != user.id and user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only revoke your own delegations.")
    row.is_active = False
    record(db, tenant_id=user.tenant_id, action="workflow.delegation_revoked", actor=user,
           object_type="delegation", object_id=row.id, object_label=row.to_user_id,
           ip=client_ip(request))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------
# Business calendar
# ---------------------------------------------------------------------------------------


@router.get("/workflow/holidays", response_model=list[schemas.HolidayOut])
def list_holidays(year: int | None = None, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> list[schemas.HolidayOut]:
    stmt = select(models.Holiday).where(models.Holiday.tenant_id == user.tenant_id)
    if year:
        stmt = stmt.where(models.Holiday.day >= dt.date(year, 1, 1),
                          models.Holiday.day <= dt.date(year, 12, 31))
    rows = db.scalars(stmt.order_by(models.Holiday.day)).all()
    return [schemas.HolidayOut.model_validate(r) for r in rows]


@router.post("/workflow/holidays", response_model=schemas.HolidayOut,
             status_code=status.HTTP_201_CREATED)
def create_holiday(data: schemas.HolidayIn, request: Request, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.HolidayOut:
    """Add a non-working day. This changes what every open SLA means, so it is admin-only
    and audited."""
    _require_admin(user)
    existing = db.scalar(
        select(models.Holiday).where(models.Holiday.tenant_id == user.tenant_id,
                                     models.Holiday.day == data.day)
    )
    if existing is not None:
        return schemas.HolidayOut.model_validate(existing)
    row = models.Holiday(tenant_id=user.tenant_id, day=data.day, name=data.name)
    db.add(row)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="workflow.holiday_added", actor=user,
           object_type="holiday", object_id=row.id, object_label=row.name or str(row.day),
           ip=client_ip(request), meta={"day": row.day.isoformat(), "name": row.name})
    db.commit()
    return schemas.HolidayOut.model_validate(row)


@router.delete("/workflow/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(holiday_id: str, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> Response:
    _require_admin(user)
    row = db.get(models.Holiday, holiday_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------
# Escalations
# ---------------------------------------------------------------------------------------


@router.get("/workflow/escalations", response_model=list[schemas.EscalationOut])
def escalations(days: int = Query(90, ge=1, le=730), db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> list[schemas.EscalationOut]:
    """The escalations feed, and the source for "escalations per month" and "mean time to
    resolve" in the KPI pack. Resolution time is measured in **business** hours, for the same
    reason the deadline is."""
    since = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=days)
    steps = wf.escalations(db, user.tenant_id, since=since)
    names = _names(db, user.tenant_id)

    out: list[schemas.EscalationOut] = []
    for step in steps:
        run = db.get(models.WorkflowRun, step.run_id)
        contract = db.get(models.Contract, run.contract_id) if run else None
        hours = None
        if step.decided_at and step.escalated_at:
            hours = business_calendar.business_hours_between(
                db, user.tenant_id, step.escalated_at, step.decided_at
            )
        out.append(schemas.EscalationOut(
            step_id=step.id, run_id=step.run_id,
            contract_id=run.contract_id if run else "",
            contract_title=contract.title if contract else "",
            contract_reference=contract.reference_no if contract else "",
            step_name=step.name, stage_index=step.stage_index, sla_hours=step.sla_hours,
            due_at=step.due_at, escalated_at=step.escalated_at, escalated_to=step.escalated_to,
            escalated_to_name=names.get(step.escalated_to or "", ""),
            resolved_at=step.decided_at, hours_to_resolve=hours, status=step.status,
        ))
    return out


@router.post("/workflow/sla-sweep", response_model=schemas.SlaSweepOut)
def run_sla_sweep(db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.SlaSweepOut:
    """Run the SLA sweep for this workspace now. Normally a Celery beat; exposed so an
    operator can verify the configuration without waiting for the next tick."""
    _require_admin(user)
    result = wf.sla_sweep(db, tenant_id=user.tenant_id)
    db.commit()
    return schemas.SlaSweepOut(**result)


# ---------------------------------------------------------------------------------------
# Consolidated review, comments, mentions
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/review", response_model=schemas.ConsolidatedReviewOut)
def consolidated_review(contract_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> schemas.ConsolidatedReviewOut:
    """Every internal stakeholder's comments and proposed amendments in one view, grouped by
    function — the screen the user department reads before deciding what goes back to the
    counterparty (RFI §3.3)."""
    contract = _owned_contract(db, user, contract_id)
    data = comment_service.consolidated_review(db, contract,
                                               audience=comment_service.INTERNAL_AUDIENCE)
    return schemas.ConsolidatedReviewOut(
        contract_id=data["contract_id"], audience=data["audience"], total=data["total"],
        internal_only_count=data["internal_only_count"], amendments=data["amendments"],
        groups=[
            schemas.ConsolidatedGroupOut(
                department=g["department"],
                comments=[schemas.CommentOut.model_validate(c) for c in g["comments"]],
                amendments=g["amendments"], unresolved=g["unresolved"],
            )
            for g in data["groups"]
        ],
    )


@router.post("/contracts/{contract_id}/comments", response_model=schemas.CommentOut,
             status_code=status.HTTP_201_CREATED)
def add_comment(contract_id: str, data: schemas.CommentIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.CommentOut:
    """Post a comment or a proposed amendment. `@name` mentions notify and land in the
    mentioned user's inbox filter."""
    contract = _owned_contract(db, user, contract_id)
    comment = comment_service.create(
        db, contract=contract, author=user, body=data.body,
        internal_only=data.internal_only, kind=data.kind, department=data.department,
        anchor_start=data.anchor_start, anchor_end=data.anchor_end, ip=client_ip(request),
    )
    db.commit()
    return schemas.CommentOut.model_validate(comment)


@router.get("/mentions", response_model=list[schemas.MentionOut])
def my_mentions(unread_only: bool = Query(False), db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> list[schemas.MentionOut]:
    """The "mentions me" inbox filter (RFI §3.4)."""
    rows = comment_service.mentions_for_user(db, user.tenant_id, user.id,
                                             unread_only=unread_only)
    out: list[schemas.MentionOut] = []
    for m in rows:
        item = schemas.MentionOut.model_validate(m)
        contract = db.get(models.Contract, m.contract_id)
        comment = db.get(models.Comment, m.comment_id)
        item.contract_title = contract.title if contract else ""
        item.body = (comment.body[:300] if comment else "")
        out.append(item)
    return out


@router.post("/mentions/read", response_model=dict)
def mark_mentions_read(db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> dict:
    count = comment_service.mark_mentions_read(db, user.tenant_id, user.id)
    db.commit()
    return {"marked_read": count}
