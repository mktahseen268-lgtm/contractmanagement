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


def _sorted(items: list[schemas.InboxItem]) -> list[schemas.InboxItem]:
    # high priority first, then oldest waiting first
    return sorted(items, key=lambda i: (0 if i.priority == "high" else 1, -i.waiting_hours))


@router.get("/summary", response_model=schemas.InboxSummary)
def inbox_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.InboxSummary:
    items = _collect_approvals(db, user) + _collect_signatures(db, user)
    approvals = sum(1 for x in items if x.kind == "approval")
    signatures = sum(1 for x in items if x.kind == "signature")
    high = sum(1 for x in items if x.priority == "high")
    return schemas.InboxSummary(approvals=approvals, signatures=signatures, total=len(items), high_priority=high)


@router.get("", response_model=list[schemas.InboxItem])
def inbox(
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.InboxItem]:
    """All items waiting on you. ?kind=approval or ?kind=signature to filter."""
    items: list[schemas.InboxItem] = []
    if kind in (None, "", "approval"):
        items.extend(_collect_approvals(db, user))
    if kind in (None, "", "signature"):
        items.extend(_collect_signatures(db, user))
    return _sorted(items)
