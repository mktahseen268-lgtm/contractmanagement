"""The approval-workflow engine — ordered **stages** of **concurrent** steps.

Phase 4 rebuild. The v1 engine advanced one step at a time; the RFI is built entirely around
parallel multi-stakeholder review — Legal, Finance, Compliance and IS looking at an agreement
at the same time, each marking their own review complete without waiting for the others. That
is not a nicety: sequential review is the main thing making the cycle times the RFI wants to
fix, because every reviewer's queue time is added to every other's.

Shape:

    run
     └── stage 0  policy=all        [Legal] [Finance] [Compliance]   ← all active together
     └── stage 1  policy=quorum(2)  [CFO] [COO] [CRO]                ← any two suffice
     └── stage 2  policy=any        [Owner] [Deputy]

A stage completes per its policy; the next stage then activates as a whole. A rejection or a
changes-requested ends the run immediately, whatever stage it came from — one reviewer saying
"no" should not wait for their colleagues to also say "no".

Backwards compatibility: a legacy flat `steps` definition promotes to one step per stage, which
*is* the old sequential behaviour, so existing definitions and in-flight runs keep working.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import business_calendar, models
from .audit import record
from .config import settings

# Role hierarchy — a step assigned to a role can be decided by that role or anything above it.
_ROLE_RANK = {"viewer": 0, "auditor": 0, "reviewer": 1, "author": 2, "approver": 3,
              "manager": 4, "admin": 5, "owner": 6}
_OVERRIDE_ROLES = {"admin", "owner"}
_DECISIONS = {"approve", "reject", "changes_requested"}

#: Stage completion policies. `all` is the safe default — requiring everyone unless someone
#: deliberately said otherwise.
_POLICIES = {"all", "any", "quorum", "percentage"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class WorkflowError(RuntimeError):
    """A workflow rule was violated. Routers map this to 409."""


# ---------------------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------------------


def active_workflows(db: Session, tenant_id: str) -> list[models.WorkflowDefinition]:
    return list(db.scalars(
        select(models.WorkflowDefinition)
        .where(models.WorkflowDefinition.tenant_id == tenant_id,
               models.WorkflowDefinition.status == "active")
        .order_by(models.WorkflowDefinition.name)
    ).all())


def default_workflow_for(db: Session, tenant_id: str, contract_type: str) -> models.WorkflowDefinition | None:
    for wf in active_workflows(db, tenant_id):
        if contract_type in (wf.default_for_types or []):
            return wf
    return None


def active_run_for_contract(db: Session, contract_id: str) -> models.WorkflowRun | None:
    return db.scalar(
        select(models.WorkflowRun)
        .where(models.WorkflowRun.contract_id == contract_id,
               models.WorkflowRun.status == "running")
        .order_by(models.WorkflowRun.started_at.desc())
    )


def latest_run_for_contract(db: Session, contract_id: str) -> models.WorkflowRun | None:
    return db.scalar(
        select(models.WorkflowRun)
        .where(models.WorkflowRun.contract_id == contract_id)
        .order_by(models.WorkflowRun.started_at.desc())
    )


def run_steps(db: Session, run_id: str) -> list[models.WorkflowRunStep]:
    return list(db.scalars(
        select(models.WorkflowRunStep)
        .where(models.WorkflowRunStep.run_id == run_id)
        .order_by(models.WorkflowRunStep.stage_index, models.WorkflowRunStep.step_index)
    ).all())


def stage_steps(db: Session, run_id: str, stage_index: int) -> list[models.WorkflowRunStep]:
    return [s for s in run_steps(db, run_id) if s.stage_index == stage_index]


def active_steps(db: Session, run: models.WorkflowRun) -> list[models.WorkflowRunStep]:
    """Every step awaiting a decision right now — plural, because that is the point."""
    if run.status != "running":
        return []
    return [s for s in run_steps(db, run.id) if s.status == "active"]


def active_step(db: Session, run: models.WorkflowRun) -> models.WorkflowRunStep | None:
    """First active step. Kept for callers that predate parallel stages."""
    steps = active_steps(db, run)
    return steps[0] if steps else None


def steps_for_user(db: Session, run: models.WorkflowRun, user: models.User) -> list[models.WorkflowRunStep]:
    """The active steps this user may decide — what "my tasks" means on a parallel stage."""
    return [s for s in active_steps(db, run) if can_decide(user, s)]


# ---------------------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------------------


def can_decide(user: models.User, step: models.WorkflowRunStep) -> bool:
    if user.role in _OVERRIDE_ROLES:
        return True
    if step.assignee_kind == "user":
        # A delegate acts for the principal, so either identity may decide.
        return step.assignee_value == user.id or step.delegated_from == user.id
    need = _ROLE_RANK.get((step.assignee_value or "approver").lower(), 3)
    have = _ROLE_RANK.get((user.role or "viewer").lower(), 0)
    return have >= need


# ---------------------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------------------


def resolve_delegate(db: Session, tenant_id: str, user_id: str, *,
                     contract_type: str = "", at: dt.datetime | None = None) -> str | None:
    """The user assignments for `user_id` should route to right now, if anyone.

    Follows one hop only. Chained delegation (A→B→C while both are away) is a policy question
    a bank should answer explicitly rather than something an engine should silently resolve —
    and a cycle would hang the run.
    """
    at = at or _now()
    rows = db.scalars(
        select(models.Delegation).where(
            models.Delegation.tenant_id == tenant_id,
            models.Delegation.from_user_id == user_id,
            models.Delegation.is_active.is_(True),
            models.Delegation.starts_at <= at,
            models.Delegation.ends_at >= at,
        ).order_by(models.Delegation.starts_at.desc())
    ).all()
    for d in rows:
        if d.scope in ("all", "", contract_type):
            return d.to_user_id
    return None


# ---------------------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------------------


def _role_holders(db: Session, tenant_id: str, role: str) -> list[str]:
    need = _ROLE_RANK.get((role or "approver").lower(), 3)
    rows = db.execute(
        select(models.User.id, models.User.role).where(
            models.User.tenant_id == tenant_id, models.User.is_active.is_(True)
        )
    ).all()
    return [r[0] for r in rows if _ROLE_RANK.get((r[1] or "viewer").lower(), 0) >= need]


def step_assignee_ids(db: Session, tenant_id: str, step: models.WorkflowRunStep) -> list[str]:
    if step.assignee_kind == "user":
        return [step.assignee_value] if step.assignee_value else []
    return _role_holders(db, tenant_id, step.assignee_value)


def _notify(db: Session, *, tenant_id: str, user_ids, contract: models.Contract, type_: str,
            title: str, body: str, exclude_user_id: str | None = None) -> None:
    for uid in {u for u in user_ids if u}:
        if uid == exclude_user_id:
            continue
        db.add(models.Notification(
            tenant_id=tenant_id, user_id=uid, type=type_, title=title, body=body,
            object_type="contract", object_id=contract.id,
        ))


def _notify_owner(db: Session, *, tenant_id: str, contract: models.Contract, title: str,
                  body: str, exclude_user_id: str | None = None) -> None:
    if contract.owner_id and contract.owner_id != exclude_user_id:
        _notify(db, tenant_id=tenant_id, user_ids=[contract.owner_id], contract=contract,
                type_="contract.workflow_update", title=title, body=body)


# ---------------------------------------------------------------------------------------
# Starting a run
# ---------------------------------------------------------------------------------------


def _normalise_stage(raw: dict, index: int) -> dict:
    policy = str(raw.get("policy") or "all").lower()
    if policy not in _POLICIES:
        policy = "all"
    steps = list(raw.get("steps") or [])
    if not steps:
        raise WorkflowError(f"Stage {index + 1} has no reviewers.")
    return {
        "name": str(raw.get("name") or f"Stage {index + 1}"),
        "policy": policy,
        "threshold": int(raw.get("threshold") or 0),
        "sla_hours": int(raw.get("sla_hours") or 0),
        "escalate_to_user_id": raw.get("escalate_to_user_id") or None,
        "steps": steps,
    }


def _activate_stage(db: Session, run: models.WorkflowRun, contract: models.Contract,
                    stage_index: int, *, exclude_user_id: str | None = None) -> None:
    """Make every step in a stage active at once, and start their SLA clocks."""
    now = _now()
    stages = run.stages or []
    stage = stages[stage_index] if stage_index < len(stages) else {}
    sla_hours = int(stage.get("sla_hours") or 0)

    for step in stage_steps(db, run.id, stage_index):
        if step.status != "pending":
            continue
        step.status = "active"
        step.activated_at = now
        if sla_hours and not step.sla_hours:
            step.sla_hours = sla_hours
        if step.sla_hours:
            step.due_at = business_calendar.add_business_hours(
                db, contract.tenant_id, now, step.sla_hours
            )
        _notify(
            db, tenant_id=contract.tenant_id,
            user_ids=step_assignee_ids(db, contract.tenant_id, step), contract=contract,
            type_="contract.approval_requested",
            title=f"Review requested: {step.name}",
            body=f'"{contract.title}" needs your review ({contract.reference_no}).',
            exclude_user_id=exclude_user_id,
        )
    run.current_stage = stage_index
    db.flush()


def start_run(db: Session, *, contract: models.Contract, definition: models.WorkflowDefinition,
              user: models.User, ip: str = "") -> models.WorkflowRun:
    """Build the stage graph, apply the approval matrix, and activate the first stage."""
    from . import approval_matrix

    stages = [
        _normalise_stage(s, i)
        for i, s in enumerate(definition.as_stages(non_standard=contract.is_non_standard))
    ]
    if not stages:
        raise WorkflowError("This workflow has no stages.")

    stages, applied_rules, snapshot = approval_matrix.apply(db, contract, stages)

    run = models.WorkflowRun(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        definition_id=definition.id, definition_name=definition.name,
        status="running", current_index=0, current_stage=0,
        started_by=user.id, started_by_name=user.name,
        stages=stages, applied_rule_ids=[r.id for r in applied_rules],
        routing_snapshot=snapshot,
    )
    db.add(run)
    db.flush()

    _materialise_steps(db, run, contract, stages)
    contract.status = "in_review"
    db.flush()

    _activate_stage(db, run, contract, 0, exclude_user_id=user.id)
    record(
        db, tenant_id=contract.tenant_id, action="contract.submitted", actor=user,
        object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
        meta={
            "workflow": definition.name, "run_id": run.id, "stages": len(stages),
            "steps": sum(len(s["steps"]) for s in stages),
            "non_standard": contract.is_non_standard,
            "applied_rules": [{"id": r.id, "name": r.name} for r in applied_rules],
            "parallel": any(len(s["steps"]) > 1 for s in stages),
        },
    )
    return run


def _materialise_steps(db: Session, run: models.WorkflowRun, contract: models.Contract,
                       stages: list[dict]) -> None:
    rows: list[models.WorkflowRunStep] = []
    flat_index = 0
    for stage_index, stage in enumerate(stages):
        for raw in stage["steps"]:
            kind = "user" if raw.get("assignee_kind") == "user" else "role"
            value = str(raw.get("assignee_value") or "approver")
            delegated_from = None
            if kind == "user":
                delegate = resolve_delegate(
                    db, contract.tenant_id, value, contract_type=contract.type
                )
                if delegate and delegate != value:
                    delegated_from, value = value, delegate
            rows.append(models.WorkflowRunStep(
                tenant_id=contract.tenant_id, run_id=run.id,
                stage_index=stage_index, step_index=flat_index,
                name=str(raw.get("name") or f"Step {flat_index + 1}"),
                assignee_kind=kind, assignee_value=value,
                delegated_from=delegated_from,
                sla_hours=int(raw.get("sla_hours") or stage.get("sla_hours") or 0),
                status="pending",
            ))
            flat_index += 1
    db.add_all(rows)
    db.flush()


# ---------------------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------------------


def _stage_satisfied(stage: dict, steps: list[models.WorkflowRunStep]) -> bool:
    """Has this stage met its completion policy?

    Skipped steps are excluded from both sides: a reviewer removed mid-flight is no longer
    required, so counting them in the denominator would make an `all` stage permanently
    unsatisfiable — the review would sit open forever with nobody left to act on it.
    """
    considered = [s for s in steps if s.status != "skipped"]
    if not considered:
        return True
    approvals = sum(1 for s in considered if s.status == "approved")
    total = len(considered)
    policy = stage.get("policy", "all")
    if policy == "any":
        return approvals >= 1
    if policy == "quorum":
        return approvals >= max(1, int(stage.get("threshold") or 1))
    if policy == "percentage":
        needed = max(1, round(total * (int(stage.get("threshold") or 100) / 100.0)))
        return approvals >= needed
    return approvals >= total  # all


def decide(db: Session, *, run: models.WorkflowRun, step: models.WorkflowRunStep,
           contract: models.Contract, user: models.User, decision: str, comment: str = "",
           ip: str = "") -> models.WorkflowRun:
    """Record one reviewer's decision, independently of their colleagues."""
    if decision not in _DECISIONS:
        raise WorkflowError("Unknown decision.")
    if run.status != "running":
        raise WorkflowError("This review is no longer running.")
    if step.status != "active":
        raise WorkflowError("This review step is no longer active.")

    now = _now()
    step.decision = decision
    step.status = "approved" if decision == "approve" else decision
    step.decided_by = user.id
    step.decided_by_name = user.name
    step.decided_at = now
    step.comment = (comment or "").strip()

    stages = run.stages or []
    stage = stages[step.stage_index] if step.stage_index < len(stages) else {"policy": "all"}
    siblings = stage_steps(db, run.id, step.stage_index)

    meta = {
        "step": step.name, "stage": stage.get("name", ""), "stage_index": step.stage_index,
        "decision": decision, "comment": step.comment, "run_id": run.id,
        "policy": stage.get("policy", "all"),
        "on_time": (step.due_at is None or now <= step.due_at),
        "was_escalated": step.escalated_at is not None,
    }
    if step.delegated_from:
        # Both identities, always. An approval given under delegation must never read as
        # though the principal personally gave it.
        principal = db.get(models.User, step.delegated_from)
        meta["delegated_from"] = step.delegated_from
        meta["delegated_from_name"] = principal.name if principal else ""

    if decision == "approve":
        if _stage_satisfied(stage, siblings):
            # Colleagues who had not yet responded are no longer required.
            for s in siblings:
                if s.status == "active":
                    s.status = "skipped"
                    s.decided_at = now
            next_stage = step.stage_index + 1
            if next_stage < len(stages):
                _activate_stage(db, run, contract, next_stage, exclude_user_id=user.id)
                _notify_owner(
                    db, tenant_id=contract.tenant_id, contract=contract,
                    title=f'"{contract.title}" — {stage.get("name", "stage")} complete',
                    body=f'Moving to {stages[next_stage].get("name", "the next stage")}.',
                    exclude_user_id=user.id,
                )
            else:
                run.status = "approved"
                run.completed_at = now
                run.current_stage = len(stages)
                contract.status = "approved"
                _notify_owner(
                    db, tenant_id=contract.tenant_id, contract=contract,
                    title=f'"{contract.title}" is approved',
                    body=f"All review stages complete. {user.name} gave the final approval.",
                    exclude_user_id=user.id,
                )
        else:
            # Stage still open — the other reviewers carry on independently.
            outstanding = [s.name for s in siblings if s.status == "active"]
            meta["awaiting"] = outstanding
            _notify_owner(
                db, tenant_id=contract.tenant_id, contract=contract,
                title=f'"{contract.title}" — {step.name} approved',
                body=f"{user.name} approved. Still awaiting: {', '.join(outstanding)}.",
                exclude_user_id=user.id,
            )
    else:
        # A rejection ends the run immediately. Waiting for the other reviewers to also say
        # no would waste their time and delay the author's rework.
        run.status = "rejected" if decision == "reject" else "changes_requested"
        run.completed_at = now
        contract.status = "rejected" if decision == "reject" else "changes_requested"
        for s in run_steps(db, run.id):
            if s.status in ("active", "pending"):
                s.status = "skipped"
        verb = "rejected" if decision == "reject" else "requested changes on"
        _notify_owner(
            db, tenant_id=contract.tenant_id, contract=contract,
            title=f'"{contract.title}" — {verb} at {step.name}',
            body=f"{user.name} {verb} this agreement."
                 + (f" Note: {step.comment}" if step.comment else ""),
            exclude_user_id=user.id,
        )

    meta["run_status"] = run.status
    record(db, tenant_id=contract.tenant_id, action="contract.workflow_decision", actor=user,
           object_type="contract", object_id=contract.id, object_label=contract.title,
           ip=ip, meta=meta)
    return run


# ---------------------------------------------------------------------------------------
# Mid-flight reviewer changes (RFI §3.6)
# ---------------------------------------------------------------------------------------


def add_reviewer(db: Session, *, run: models.WorkflowRun, contract: models.Contract,
                 stage_index: int, name: str, assignee_kind: str, assignee_value: str,
                 actor: models.User, sla_hours: int = 0, ip: str = "") -> models.WorkflowRunStep:
    """Add a reviewer to a running stage. Audited, because it changes who must approve."""
    if run.status != "running":
        raise WorkflowError("This review is no longer running.")
    if actor.role not in _OVERRIDE_ROLES and actor.id != run.started_by:
        raise WorkflowError("Only the submitter or an admin can change the reviewer set.")
    stages = run.stages or []
    if not 0 <= stage_index < len(stages):
        raise WorkflowError("That stage does not exist on this review.")
    if stage_index < run.current_stage:
        raise WorkflowError("That stage has already completed.")

    kind = "user" if assignee_kind == "user" else "role"
    value = str(assignee_value or "approver")
    delegated_from = None
    if kind == "user":
        delegate = resolve_delegate(db, contract.tenant_id, value, contract_type=contract.type)
        if delegate and delegate != value:
            delegated_from, value = value, delegate

    max_index = max((s.step_index for s in run_steps(db, run.id)), default=-1)
    step = models.WorkflowRunStep(
        tenant_id=contract.tenant_id, run_id=run.id, stage_index=stage_index,
        step_index=max_index + 1, name=name or "Additional reviewer",
        assignee_kind=kind, assignee_value=value, delegated_from=delegated_from,
        sla_hours=sla_hours or int(stages[stage_index].get("sla_hours") or 0),
        status="pending", added_mid_flight=True, added_by=actor.id,
    )
    db.add(step)
    db.flush()

    # Keep the run's stage snapshot in step with reality, so a later re-read of `stages`
    # does not disagree with the rows.
    stages[stage_index].setdefault("steps", []).append(
        {"name": step.name, "assignee_kind": kind, "assignee_value": value}
    )
    run.stages = list(stages)

    if stage_index == run.current_stage:
        _activate_stage(db, run, contract, stage_index, exclude_user_id=actor.id)

    record(db, tenant_id=contract.tenant_id, action="contract.reviewer_added", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"run_id": run.id, "stage_index": stage_index, "step": step.name,
                 "assignee_kind": kind, "assignee_value": value})
    return step


def remove_reviewer(db: Session, *, run: models.WorkflowRun, contract: models.Contract,
                    step: models.WorkflowRunStep, actor: models.User, reason: str = "",
                    ip: str = "") -> models.WorkflowRun:
    """Remove an undecided reviewer from a running stage.

    A reviewer who has already decided is never removed — that would erase a decision from the
    record. Removing the last outstanding reviewer can complete the stage, so the policy is
    re-evaluated straight after.
    """
    if run.status != "running":
        raise WorkflowError("This review is no longer running.")
    if actor.role not in _OVERRIDE_ROLES and actor.id != run.started_by:
        raise WorkflowError("Only the submitter or an admin can change the reviewer set.")
    if step.status not in ("active", "pending"):
        raise WorkflowError("That reviewer has already responded and cannot be removed.")

    siblings = [s for s in stage_steps(db, run.id, step.stage_index) if s.id != step.id]
    if not siblings:
        raise WorkflowError("A stage must keep at least one reviewer.")

    step.status = "skipped"
    step.decided_at = _now()
    step.comment = (reason or "").strip()
    db.flush()

    record(db, tenant_id=contract.tenant_id, action="contract.reviewer_removed", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"run_id": run.id, "stage_index": step.stage_index, "step": step.name,
                 "reason": reason})

    stages = run.stages or []
    stage = stages[step.stage_index] if step.stage_index < len(stages) else {"policy": "all"}
    remaining = stage_steps(db, run.id, step.stage_index)
    if step.stage_index == run.current_stage and _stage_satisfied(stage, remaining):
        _advance_after_stage(db, run, contract, step.stage_index, actor=actor)
    return run


def _advance_after_stage(db: Session, run: models.WorkflowRun, contract: models.Contract,
                         stage_index: int, *, actor: models.User | None = None) -> None:
    """Move past a stage that has just become satisfied without a new decision."""
    now = _now()
    for s in stage_steps(db, run.id, stage_index):
        if s.status == "active":
            s.status = "skipped"
            s.decided_at = now
    stages = run.stages or []
    next_stage = stage_index + 1
    if next_stage < len(stages):
        _activate_stage(db, run, contract, next_stage,
                        exclude_user_id=actor.id if actor else None)
    else:
        run.status = "approved"
        run.completed_at = now
        run.current_stage = len(stages)
        contract.status = "approved"
    db.flush()


# ---------------------------------------------------------------------------------------
# Non-standard classification (RFI §3.1)
# ---------------------------------------------------------------------------------------


def mark_non_standard(db: Session, contract: models.Contract, *, reason: str,
                      actor: models.User | None = None, ip: str = "") -> models.Contract:
    """Flag an agreement as non-standard. Idempotent.

    Called automatically the moment the counterparty edits the document or a tracked change is
    accepted — the classification selects the approval route, so it must not depend on someone
    remembering to tick a box.
    """
    if contract.is_non_standard:
        return contract
    contract.is_non_standard = True
    contract.non_standard_reason = (reason or "")[:400]
    contract.non_standard_at = _now()
    db.flush()
    record(db, tenant_id=contract.tenant_id, action="contract.classified_non_standard",
           actor=actor, object_type="contract", object_id=contract.id,
           object_label=contract.title, ip=ip,
           meta={"reason": contract.non_standard_reason,
                 "note": "Non-standard agreements take the non-standard approval path."})
    return contract


# ---------------------------------------------------------------------------------------
# SLA sweep
# ---------------------------------------------------------------------------------------


def sla_sweep(db: Session, *, now: dt.datetime | None = None,
              tenant_id: str | None = None) -> dict:
    """Send reminders and escalate breaches. Idempotent; run from a Celery beat.

    Two thresholds: a reminder once `SLA_REMINDER_FRACTION` of the window has elapsed, and an
    escalation at the due time. Both stamp the step, so re-running the sweep does not spam.

    `tenant_id` narrows the sweep — used by the admin "run now" action, where sweeping every
    tenant to service one workspace would be both slow and surprising.
    """
    now = now or _now()
    counts = {"reminded": 0, "escalated": 0, "breached": 0}

    stmt = select(models.WorkflowRunStep).where(
        models.WorkflowRunStep.status == "active",
        models.WorkflowRunStep.due_at.is_not(None),
    )
    if tenant_id:
        stmt = stmt.where(models.WorkflowRunStep.tenant_id == tenant_id)
    steps = db.scalars(stmt).all()

    for step in steps:
        run = db.get(models.WorkflowRun, step.run_id)
        if run is None or run.status != "running":
            continue
        contract = db.get(models.Contract, run.contract_id)
        if contract is None:
            continue

        if step.due_at and now >= step.due_at:
            counts["breached"] += 1
            if step.escalated_at is None:
                _escalate(db, run, contract, step, now)
                counts["escalated"] += 1
            continue

        if step.reminded_at is None and step.activated_at and step.sla_hours:
            elapsed = business_calendar.business_hours_between(
                db, contract.tenant_id, step.activated_at, now
            )
            if elapsed >= step.sla_hours * settings.sla_reminder_fraction:
                step.reminded_at = now
                _notify(
                    db, tenant_id=contract.tenant_id,
                    user_ids=step_assignee_ids(db, contract.tenant_id, step),
                    contract=contract, type_="contract.approval_reminder",
                    title=f"Reminder: {step.name} is due soon",
                    body=f'"{contract.title}" is awaiting your review '
                         f"(due {step.due_at:%d %b %H:%M}).",
                )
                counts["reminded"] += 1
    db.flush()
    return counts


def _escalate(db: Session, run: models.WorkflowRun, contract: models.Contract,
              step: models.WorkflowRunStep, now: dt.datetime) -> None:
    """Record the breach and, when configured, move the assignment up the escalation path."""
    stages = run.stages or []
    stage = stages[step.stage_index] if step.stage_index < len(stages) else {}
    escalate_to = stage.get("escalate_to_user_id") or None

    step.escalated_at = now
    step.escalated_to = escalate_to

    if escalate_to and settings.sla_auto_escalate:
        # Reassign, but keep the original assignee visible as the principal so the trail
        # shows whose deadline was missed.
        if step.assignee_kind == "user" and not step.delegated_from:
            step.delegated_from = step.assignee_value
        step.assignee_kind = "user"
        step.assignee_value = escalate_to
        recipients = [escalate_to]
    else:
        recipients = step_assignee_ids(db, contract.tenant_id, step)
        if contract.owner_id:
            recipients.append(contract.owner_id)

    _notify(
        db, tenant_id=contract.tenant_id, user_ids=recipients, contract=contract,
        type_="contract.approval_escalated",
        title=f"Escalated: {step.name} is overdue",
        body=f'"{contract.title}" ({contract.reference_no}) passed its review deadline.',
    )
    record(
        db, tenant_id=contract.tenant_id, action="contract.workflow_escalated",
        object_type="contract", object_id=contract.id, object_label=contract.title,
        meta={
            "run_id": run.id, "step": step.name, "stage_index": step.stage_index,
            "due_at": step.due_at.isoformat() if step.due_at else None,
            "escalated_to": escalate_to, "auto_reassigned": bool(escalate_to and settings.sla_auto_escalate),
            "sla_hours": step.sla_hours,
        },
    )


def escalations(db: Session, tenant_id: str, *, since: dt.datetime | None = None,
                limit: int = 200) -> list[models.WorkflowRunStep]:
    """The escalations feed — and the source for "escalations per month" and "mean time to
    resolve" in the KPI dashboard (Phase 6)."""
    stmt = select(models.WorkflowRunStep).where(
        models.WorkflowRunStep.tenant_id == tenant_id,
        models.WorkflowRunStep.escalated_at.is_not(None),
    )
    if since is not None:
        stmt = stmt.where(models.WorkflowRunStep.escalated_at >= since)
    return list(db.scalars(
        stmt.order_by(models.WorkflowRunStep.escalated_at.desc()).limit(limit)
    ).all())


# ---------------------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------------------


def cancel_runs_for_contract(db: Session, contract_id: str, reason: str = "contract_voided") -> None:
    runs = db.scalars(
        select(models.WorkflowRun).where(
            models.WorkflowRun.contract_id == contract_id,
            models.WorkflowRun.status == "running",
        )
    ).all()
    now = _now()
    for r in runs:
        r.status = "cancelled"
        r.completed_at = now
        for s in run_steps(db, r.id):
            if s.status in ("active", "pending"):
                s.status = "skipped"


def delete_runs_for_contract(db: Session, contract_id: str) -> None:
    run_ids = [
        r[0] for r in db.execute(
            select(models.WorkflowRun.id).where(models.WorkflowRun.contract_id == contract_id)
        ).all()
    ]
    if run_ids:
        db.query(models.WorkflowRunStep).filter(
            models.WorkflowRunStep.run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        db.query(models.WorkflowRun).filter(
            models.WorkflowRun.contract_id == contract_id
        ).delete(synchronize_session=False)
