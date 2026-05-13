"""The "My approvals" inbox — one cross-contract list of things waiting on YOU:
  • workflow approval steps where you can decide
  • signature recipients whose turn it is and whose email matches yours
v1 returns a flat list (sorted: high priority first, then oldest). docs/10 calls for SLA badges,
auto-escalation, and a "Sent — waiting on others" tab — both designed and planned."""

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from .. import workflow_service as wf
from .. import signing_service as sig
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/inbox", tags=["inbox"])

_HIGH_RISK = {"high", "critical"}
_HIGH_WAIT_HOURS = 24.0


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _waiting_hours(since: dt.datetime | None) -> float:
    if not since:
        return 0.0
    return max((_now() - since).total_seconds() / 3600.0, 0.0)


def _priority(*, waiting_hours: float, risk_level: str) -> str:
    if waiting_hours >= _HIGH_WAIT_HOURS or (risk_level or "").lower() in _HIGH_RISK:
        return "high"
    return "normal"


def _collect_approvals(db: Session, user: models.User) -> list[schemas.InboxItem]:
    """All ACTIVE workflow run steps in the tenant the user has permission to decide on."""
    rows = db.execute(
        select(
            models.WorkflowRunStep, models.WorkflowRun, models.Contract,
        )
        .join(models.WorkflowRun, models.WorkflowRunStep.run_id == models.WorkflowRun.id)
        .join(models.Contract, models.WorkflowRun.contract_id == models.Contract.id)
        .where(
            models.WorkflowRunStep.tenant_id == user.tenant_id,
            models.WorkflowRunStep.status == "active",
            models.WorkflowRun.status == "running",
        )
    ).all()
    items: list[schemas.InboxItem] = []
    for step, run, c in rows:
        if not wf.can_decide(user, step):
            continue
        # total step count + 1-based position for the subtitle
        total_steps = db.scalar(select(func.count(models.WorkflowRunStep.id)).where(models.WorkflowRunStep.run_id == run.id)) or 0
        since = step.created_at or run.started_at
        waiting_h = _waiting_hours(since)
        items.append(schemas.InboxItem(
            id=f"step:{step.id}",
            kind="approval",
            contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no, contract_status=c.status,
            contract_type=c.type, risk_level=c.risk_level, value=c.value or 0.0, currency=c.currency,
            title=f"Approve “{c.title}”",
            subtitle=f"Step {step.step_index + 1} of {total_steps} — {step.name} · {run.definition_name or 'Approval'}",
            since=since, waiting_hours=round(waiting_h, 2),
            priority=_priority(waiting_hours=waiting_h, risk_level=c.risk_level),
            href=f"/contracts/{c.id}?tab=approvals",
        ))
    return items


def _collect_signatures(db: Session, user: models.User) -> list[schemas.InboxItem]:
    """Signature recipients whose email matches the user's and whose turn it is to sign."""
    email_lc = (user.email or "").lower()
    if not email_lc:
        return []
    rows = db.execute(
        select(models.SignatureRecipient, models.SignatureEnvelope, models.Contract)
        .join(models.SignatureEnvelope, models.SignatureRecipient.envelope_id == models.SignatureEnvelope.id)
        .join(models.Contract, models.SignatureEnvelope.contract_id == models.Contract.id)
        .where(
            models.SignatureRecipient.tenant_id == user.tenant_id,
            models.SignatureRecipient.kind == "signer",
            models.SignatureRecipient.status.in_(["sent", "viewed"]),
            func.lower(models.SignatureRecipient.email) == email_lc,
            models.SignatureEnvelope.status.in_(["sent", "partially_signed"]),
        )
    ).all()
    items: list[schemas.InboxItem] = []
    for rcpt, env, c in rows:
        # is this recipient's turn?
        recips = sig.recipients(db, env.id)
        if not sig.is_recipients_turn(env, rcpt, recips):
            continue
        since = env.sent_at or env.created_at
        waiting_h = _waiting_hours(since)
        items.append(schemas.InboxItem(
            id=f"sig:{rcpt.id}",
            kind="signature",
            contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no, contract_status=c.status,
            contract_type=c.type, risk_level=c.risk_level, value=c.value or 0.0, currency=c.currency,
            title=f"Sign “{c.title}”",
            subtitle=f"Signature request · {env.signing_order} order",
            since=since, waiting_hours=round(waiting_h, 2),
            priority=_priority(waiting_hours=waiting_h, risk_level=c.risk_level),
            href=f"/contracts/{c.id}?tab=signatures",
        ))
    return items


def _collect_obligations(db: Session, user: models.User) -> list[schemas.InboxItem]:
    """Obligations owned by this user that are overdue, or due within OBLIGATION_DUE_WINDOW days."""
    today = dt.date.today()
    horizon = today + dt.timedelta(days=7)
    rows = db.execute(
        select(models.Obligation, models.Contract)
        .join(models.Contract, models.Obligation.contract_id == models.Contract.id)
        .where(
            models.Obligation.tenant_id == user.tenant_id,
            models.Obligation.owner_id == user.id,
            models.Obligation.status.in_(["pending", "overdue"]),
            models.Obligation.due_date.is_not(None),
            models.Obligation.due_date <= horizon,
        )
    ).all()
    items: list[schemas.InboxItem] = []
    for o, c in rows:
        days_to_due = (o.due_date - today).days if o.due_date else 0
        is_overdue = o.status == "overdue" or days_to_due < 0
        # treat overdue or due-today as high priority; risk also bumps to high
        waiting_h = max(-days_to_due, 0) * 24.0  # days overdue → "waiting" hours for sorting
        priority = "high" if is_overdue or days_to_due <= 0 or (c.risk_level or "").lower() in _HIGH_RISK else "normal"
        subtitle = (
            f"Overdue by {-days_to_due} day{'s' if days_to_due != -1 else ''}"
            if is_overdue else
            f"Due {'today' if days_to_due == 0 else f'in {days_to_due} day{'s' if days_to_due != 1 else ''}'}"
        )
        items.append(schemas.InboxItem(
            id=f"obl:{o.id}",
            kind="obligation",
            contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no, contract_status=c.status,
            contract_type=c.type, risk_level=c.risk_level, value=c.value or 0.0, currency=c.currency,
            title=o.title,
            subtitle=subtitle,
            since=dt.datetime.combine(o.due_date, dt.time.min) if o.due_date else o.created_at,
            waiting_hours=round(waiting_h, 2),
            priority=priority,
            href=f"/contracts/{c.id}?tab=obligations",
        ))
    return items


def _sorted(items: list[schemas.InboxItem]) -> list[schemas.InboxItem]:
    # high priority first, then oldest waiting first
    return sorted(items, key=lambda i: (0 if i.priority == "high" else 1, -i.waiting_hours))


@router.get("/summary", response_model=schemas.InboxSummary)
def inbox_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.InboxSummary:
    items = _collect_approvals(db, user) + _collect_signatures(db, user) + _collect_obligations(db, user)
    approvals = sum(1 for x in items if x.kind == "approval")
    signatures = sum(1 for x in items if x.kind == "signature")
    obligations = sum(1 for x in items if x.kind == "obligation")
    high = sum(1 for x in items if x.priority == "high")
    return schemas.InboxSummary(approvals=approvals, signatures=signatures, obligations=obligations, total=len(items), high_priority=high)


@router.get("", response_model=list[schemas.InboxItem])
def inbox(
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.InboxItem]:
    """All items waiting on you. ?kind=approval|signature|obligation to filter."""
    items: list[schemas.InboxItem] = []
    if kind in (None, "", "approval"):
        items.extend(_collect_approvals(db, user))
    if kind in (None, "", "signature"):
        items.extend(_collect_signatures(db, user))
    if kind in (None, "", "obligation"):
        items.extend(_collect_obligations(db, user))
    return _sorted(items)


def _describe_assignee(step: models.WorkflowRunStep, names_by_id: dict[str, str]) -> str:
    if step.assignee_kind == "user":
        return f"@{names_by_id.get(step.assignee_value, 'a specific user')}"
    role = (step.assignee_value or "").capitalize()
    return f"any {role.lower()} (or above)"


@router.get("/sent", response_model=list[schemas.InboxItem])
def inbox_sent(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.InboxItem]:
    """Things YOU started that are waiting on someone else — workflow runs you submitted that
    are still running, and signature envelopes you created that are still out for signature."""
    items: list[schemas.InboxItem] = []
    names_by_id = {r[0]: r[1] for r in db.execute(select(models.User.id, models.User.name).where(models.User.tenant_id == user.tenant_id)).all()}

    # --- workflow runs I started, still running
    rows = db.execute(
        select(models.WorkflowRun, models.WorkflowRunStep, models.Contract)
        .join(models.WorkflowRunStep, models.WorkflowRunStep.run_id == models.WorkflowRun.id)
        .join(models.Contract, models.WorkflowRun.contract_id == models.Contract.id)
        .where(
            models.WorkflowRun.tenant_id == user.tenant_id,
            models.WorkflowRun.started_by == user.id,
            models.WorkflowRun.status == "running",
            models.WorkflowRunStep.status == "active",
        )
    ).all()
    for run, step, c in rows:
        since = step.created_at or run.started_at
        waiting_h = _waiting_hours(since)
        items.append(schemas.InboxItem(
            id=f"sent-step:{step.id}",
            kind="approval",
            contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no, contract_status=c.status,
            contract_type=c.type, risk_level=c.risk_level, value=c.value or 0.0, currency=c.currency,
            title=f"Waiting on approval — “{c.title}”",
            subtitle=f"Step {step.step_index + 1}: {step.name} · {_describe_assignee(step, names_by_id)}",
            since=since, waiting_hours=round(waiting_h, 2),
            priority=_priority(waiting_hours=waiting_h, risk_level=c.risk_level),
            href=f"/contracts/{c.id}?tab=approvals",
        ))

    # --- envelopes I created, still out for signature
    envs = db.scalars(
        select(models.SignatureEnvelope).where(
            models.SignatureEnvelope.tenant_id == user.tenant_id,
            models.SignatureEnvelope.created_by == user.id,
            models.SignatureEnvelope.status.in_(["sent", "partially_signed"]),
        )
    ).all()
    for env in envs:
        c = db.get(models.Contract, env.contract_id)
        if c is None:
            continue
        pending = list(db.scalars(
            select(models.SignatureRecipient).where(
                models.SignatureRecipient.envelope_id == env.id,
                models.SignatureRecipient.kind == "signer",
                models.SignatureRecipient.status.in_(["sent", "viewed", "created"]),
            )
        ).all())
        if not pending:
            continue
        names = ", ".join(p.name for p in pending[:3]) + (f" +{len(pending) - 3}" if len(pending) > 3 else "")
        since = env.sent_at or env.created_at
        waiting_h = _waiting_hours(since)
        items.append(schemas.InboxItem(
            id=f"sent-env:{env.id}",
            kind="signature",
            contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no, contract_status=c.status,
            contract_type=c.type, risk_level=c.risk_level, value=c.value or 0.0, currency=c.currency,
            title=f"Waiting on signers — “{c.title}”",
            subtitle=f"{len(pending)} pending: {names}",
            since=since, waiting_hours=round(waiting_h, 2),
            priority=_priority(waiting_hours=waiting_h, risk_level=c.risk_level),
            href=f"/contracts/{c.id}?tab=signatures",
        ))

    return _sorted(items)
