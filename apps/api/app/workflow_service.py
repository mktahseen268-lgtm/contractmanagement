"""The approval-workflow engine. v1: linear (sequential) steps; one approval per step; assignee
is either a specific user or "any user with role X (or higher)"; owner/admin can always decide.
Parallel/conditional steps, SLAs and escalation are planned (docs/10)."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .audit import record

# role hierarchy — a step assigned to a role can be decided by that role or anything above it
_ROLE_RANK = {"viewer": 0, "reviewer": 1, "author": 2, "approver": 3, "manager": 4, "admin": 5, "owner": 6}
_OVERRIDE_ROLES = {"admin", "owner"}
_DECISIONS = {"approve", "reject", "changes_requested"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ---------- queries ----------


def active_workflows(db: Session, tenant_id: str) -> list[models.WorkflowDefinition]:
    return list(
        db.scalars(
            select(models.WorkflowDefinition)
            .where(models.WorkflowDefinition.tenant_id == tenant_id, models.WorkflowDefinition.status == "active")
            .order_by(models.WorkflowDefinition.name)
        ).all()
    )


def default_workflow_for(db: Session, tenant_id: str, contract_type: str) -> models.WorkflowDefinition | None:
    for wf in active_workflows(db, tenant_id):
        if contract_type in (wf.default_for_types or []):
            return wf
    return None


def active_run_for_contract(db: Session, contract_id: str) -> models.WorkflowRun | None:
    return db.scalar(
        select(models.WorkflowRun)
        .where(models.WorkflowRun.contract_id == contract_id, models.WorkflowRun.status == "running")
        .order_by(models.WorkflowRun.started_at.desc())
    )


def latest_run_for_contract(db: Session, contract_id: str) -> models.WorkflowRun | None:
    return db.scalar(
        select(models.WorkflowRun).where(models.WorkflowRun.contract_id == contract_id).order_by(models.WorkflowRun.started_at.desc())
    )


def run_steps(db: Session, run_id: str) -> list[models.WorkflowRunStep]:
    return list(db.scalars(select(models.WorkflowRunStep).where(models.WorkflowRunStep.run_id == run_id).order_by(models.WorkflowRunStep.step_index)).all())


def active_step(db: Session, run: models.WorkflowRun) -> models.WorkflowRunStep | None:
    if run.status != "running":
        return None
    return db.scalar(select(models.WorkflowRunStep).where(models.WorkflowRunStep.run_id == run.id, models.WorkflowRunStep.status == "active"))


# ---------- permissions ----------


def can_decide(user: models.User, step: models.WorkflowRunStep) -> bool:
    if user.role in _OVERRIDE_ROLES:
        return True
    if step.assignee_kind == "user":
        return step.assignee_value == user.id
    # role
    need = _ROLE_RANK.get((step.assignee_value or "approver").lower(), 3)
    have = _ROLE_RANK.get((user.role or "viewer").lower(), 0)
    return have >= need


# ---------- runtime ----------


def _notify_step_assignees(db: Session, *, tenant_id: str, contract: models.Contract, step: models.WorkflowRunStep, exclude_user_id: str | None = None) -> None:
    if step.assignee_kind == "user":
        user_ids = [step.assignee_value]
    else:
        need = _ROLE_RANK.get((step.assignee_value or "approver").lower(), 3)
        rows = db.execute(select(models.User.id, models.User.role).where(models.User.tenant_id == tenant_id, models.User.is_active.is_(True))).all()
        user_ids = [r[0] for r in rows if _ROLE_RANK.get((r[1] or "viewer").lower(), 0) >= need]
    for uid in set(user_ids):
        if not uid or uid == exclude_user_id:
            continue
        db.add(
            models.Notification(
                tenant_id=tenant_id,
                user_id=uid,
                type="contract.approval_requested",
                title=f"Approval requested: {step.name}",
                body=f"\"{contract.title}\" needs your approval ({contract.reference_no}).",
                object_type="contract",
                object_id=contract.id,
            )
        )


def _notify_owner(db: Session, *, tenant_id: str, contract: models.Contract, title: str, body: str, exclude_user_id: str | None = None) -> None:
    if contract.owner_id and contract.owner_id != exclude_user_id:
        db.add(models.Notification(tenant_id=tenant_id, user_id=contract.owner_id, type="contract.workflow_update", title=title, body=body, object_type="contract", object_id=contract.id))


def start_run(db: Session, *, contract: models.Contract, definition: models.WorkflowDefinition, user: models.User, ip: str = "") -> models.WorkflowRun:
    steps = definition.steps or []
    if not steps:
        raise ValueError("workflow has no steps")
    run = models.WorkflowRun(
        tenant_id=contract.tenant_id,
        contract_id=contract.id,
        definition_id=definition.id,
        definition_name=definition.name,
        status="running",
        current_index=0,
        started_by=user.id,
        started_by_name=user.name,
    )
    db.add(run)
    db.flush()
    step_rows: list[models.WorkflowRunStep] = []
    for i, s in enumerate(steps):
        step_rows.append(
            models.WorkflowRunStep(
                tenant_id=contract.tenant_id,
                run_id=run.id,
                step_index=i,
                name=str(s.get("name") or f"Step {i + 1}"),
                assignee_kind=("user" if s.get("assignee_kind") == "user" else "role"),
                assignee_value=str(s.get("assignee_value") or "approver"),
                status=("active" if i == 0 else "pending"),
            )
        )
    db.add_all(step_rows)
    contract.status = "in_review"
    db.flush()
    _notify_step_assignees(db, tenant_id=contract.tenant_id, contract=contract, step=step_rows[0], exclude_user_id=user.id)
    record(db, tenant_id=contract.tenant_id, action="contract.submitted", actor=user, object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip, meta={"workflow": definition.name, "run_id": run.id, "steps": len(step_rows)})
    return run


def decide(db: Session, *, run: models.WorkflowRun, step: models.WorkflowRunStep, contract: models.Contract, user: models.User, decision: str, comment: str = "", ip: str = "") -> models.WorkflowRun:
    if decision not in _DECISIONS:
        raise ValueError("invalid decision")
    if run.status != "running" or step.status != "active":
        raise ValueError("this approval step is no longer active")
    now = _now()
    step.decision = decision
    step.status = "approved" if decision == "approve" else decision
    step.decided_by = user.id
    step.decided_by_name = user.name
    step.decided_at = now
    step.comment = (comment or "").strip()

    steps = run_steps(db, run.id)
    if decision == "approve":
        nxt = next((s for s in steps if s.step_index == step.step_index + 1), None)
        if nxt is not None:
            nxt.status = "active"
            run.current_index = nxt.step_index
            _notify_step_assignees(db, tenant_id=contract.tenant_id, contract=contract, step=nxt, exclude_user_id=user.id)
            _notify_owner(db, tenant_id=contract.tenant_id, contract=contract, title=f"\"{contract.title}\" — “{step.name}” approved", body=f"{user.name} approved. Next: {nxt.name}.", exclude_user_id=user.id)
        else:
            run.status = "approved"
            run.completed_at = now
            run.current_index = len(steps)
            contract.status = "approved"
            _notify_owner(db, tenant_id=contract.tenant_id, contract=contract, title=f"\"{contract.title}\" is approved", body=f"All approval steps complete. {user.name} gave the final approval.", exclude_user_id=user.id)
    elif decision == "reject":
        run.status = "rejected"
        run.completed_at = now
        contract.status = "rejected"
        _notify_owner(db, tenant_id=contract.tenant_id, contract=contract, title=f"\"{contract.title}\" was rejected", body=f"{user.name} rejected at “{step.name}”." + (f" Note: {step.comment}" if step.comment else ""), exclude_user_id=user.id)
    else:  # changes_requested
        run.status = "changes_requested"
        run.completed_at = now
        contract.status = "changes_requested"
        _notify_owner(db, tenant_id=contract.tenant_id, contract=contract, title=f"Changes requested on \"{contract.title}\"", body=f"{user.name} requested changes at “{step.name}”." + (f" Note: {step.comment}" if step.comment else ""), exclude_user_id=user.id)

    record(db, tenant_id=contract.tenant_id, action="contract.workflow_decision", actor=user, object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip, meta={"step": step.name, "step_index": step.step_index, "decision": decision, "comment": step.comment, "run_id": run.id, "run_status": run.status})
    return run


def cancel_runs_for_contract(db: Session, contract_id: str, reason: str = "contract_voided") -> None:
    runs = db.scalars(select(models.WorkflowRun).where(models.WorkflowRun.contract_id == contract_id, models.WorkflowRun.status == "running")).all()
    now = _now()
    for r in runs:
        r.status = "cancelled"
        r.completed_at = now
        for s in run_steps(db, r.id):
            if s.status in ("active", "pending"):
                s.status = "skipped"


def delete_runs_for_contract(db: Session, contract_id: str) -> None:
    run_ids = [r[0] for r in db.execute(select(models.WorkflowRun.id).where(models.WorkflowRun.contract_id == contract_id)).all()]
    if run_ids:
        db.query(models.WorkflowRunStep).filter(models.WorkflowRunStep.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(models.WorkflowRun).filter(models.WorkflowRun.contract_id == contract_id).delete(synchronize_session=False)
