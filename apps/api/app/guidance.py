"""Guided actions: what to do next, and where this agreement is (Phase 9, item 4).

Derived, never stored. A stored "next action" is a second copy of the truth that drifts the
moment somebody approves something in a different tab, and a suggestion that is confidently
wrong is worse than none — people stop reading the panel after the second time it tells them to
do something that has already been done.

Everything here reads current state and returns a fresh answer. Nothing in this module writes.

Suggestions are also **honest about permission**. Telling a reviewer to send an agreement for
signature when they cannot is how a helper panel becomes noise; each suggestion carries the
permission it needs so the caller can show it as guidance rather than an offer.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

#: The stage tracker the RFP asks for: Intake → Drafting → Review → Approval → Sign.
#: Deliberately coarser than `lifecycle.SPINE` — this is the progress bar a business reader
#: follows, not the state machine. The mapping between them lives in `STAGE_OF_STATUS`.
STAGES = ["intake", "drafting", "review", "approval", "signature", "active"]

STAGE_LABELS = {
    "intake": "Intake",
    "drafting": "Drafting",
    "review": "Review",
    "approval": "Approval",
    "signature": "Signature",
    "active": "Active",
}

STAGE_OF_STATUS: dict[str, str] = {
    "draft": "drafting",
    "changes_requested": "drafting",
    "rejected": "drafting",
    "in_review": "review",
    "approved": "approval",
    "out_for_signature": "signature",
    "declined": "signature",
    "signed": "signature",
    "active": "active",
    "expiring": "active",
    "expired": "active",
    "renewed": "active",
    "terminated": "active",
    "voided": "drafting",
    "superseded": "active",
}

#: Statuses that ended the agreement's life. A closed agreement gets no next-best-action —
#: suggesting work on something that is over is the fastest way to have the panel ignored.
CLOSED = {"terminated", "voided", "expired", "renewed", "superseded", "rejected"}


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def stage_of(status: str) -> str:
    return STAGE_OF_STATUS.get(status, "drafting")


def stage_progress(contract: models.Contract) -> dict:
    """Where the agreement is, for the progress tracker."""
    stage = stage_of(contract.status)
    index = STAGES.index(stage) if stage in STAGES else 0
    return {
        "stage": stage,
        "label": STAGE_LABELS.get(stage, stage.title()),
        "index": index,
        "total": len(STAGES),
        "stages": [{"key": s, "label": STAGE_LABELS[s],
                    "state": ("done" if i < index else "current" if i == index else "todo")}
                   for i, s in enumerate(STAGES)],
        "is_closed": contract.status in CLOSED,
    }


def _suggest(key: str, title: str, detail: str, *, action: str = "", permission: str = "",
             severity: str = "info", href: str = "") -> dict:
    return {"key": key, "title": title, "detail": detail, "action": action,
            "permission": permission, "severity": severity, "href": href}


def next_actions(db: Session, contract: models.Contract, user: models.User) -> list[dict]:
    """What to do next with this agreement, most urgent first.

    Ordered by severity then by how close the suggestion is to unblocking the agreement. The
    list is short on purpose: five suggestions is a to-do list, fifteen is wallpaper.
    """
    out: list[dict] = []
    status = contract.status

    if status in CLOSED:
        return out

    # ---- data completeness, which blocks things later and is cheap to fix now ----
    if not contract.counterparty and not contract.party_id:
        out.append(_suggest(
            "set_counterparty", "Add the counterparty",
            "Sanctions screening and reporting both key off the party record, and neither can "
            "run until there is one.",
            action="edit", permission="contract.edit", severity="warning"))

    if not contract.effective_date:
        out.append(_suggest(
            "set_effective_date", "Set the effective date",
            "Renewal notices and every obligation reminder are counted from this date. Without "
            "it nothing is scheduled.",
            action="edit", permission="contract.edit", severity="warning"))

    if not contract.end_date and contract.status in ("active", "signed", "approved"):
        out.append(_suggest(
            "set_end_date", "Set the expiry date",
            "An active agreement with no expiry never appears in the renewal sweep, so nobody "
            "is warned before it lapses or rolls over.",
            action="edit", permission="contract.edit", severity="warning"))

    if contract.renewal_type == "auto" and not contract.end_date:
        out.append(_suggest(
            "auto_renew_no_end", "This auto-renews but has no expiry date",
            "It will roll over silently and no notice-period reminder can be calculated.",
            action="edit", permission="contract.edit", severity="critical"))

    # ---- where it is in the flow ----
    run = db.scalar(select(models.WorkflowRun).where(
        models.WorkflowRun.tenant_id == contract.tenant_id,
        models.WorkflowRun.contract_id == contract.id,
        models.WorkflowRun.status == "running"))

    if run is not None:
        out.append(_suggest(
            "awaiting_approval", "Waiting on approval",
            "An approval run is in progress. Decide it from the workflow rather than changing "
            "the status directly — a status change here would step around the approvers.",
            action="open_workflow", permission="", severity="info",
            href=f"/workflows/{run.id}"))
    elif status == "draft":
        out.append(_suggest(
            "submit_for_review", "Send it for approval",
            "The draft is ready to go to reviewers.",
            action="in_review", permission="contract.submit", severity="info"))
    elif status == "changes_requested":
        out.append(_suggest(
            "address_changes", "Address the requested changes",
            "A reviewer sent this back. Their comments are on the agreement.",
            action="edit", permission="contract.edit", severity="warning"))
    elif status == "approved":
        out.append(_suggest(
            "send_for_signature", "Send it for signature",
            "Approved and ready to go out.",
            action="out_for_signature", permission="contract.send", severity="info"))
    elif status == "signed":
        out.append(_suggest(
            "activate", "Activate it",
            "Everyone has signed. Activating starts the obligations and the renewal clock.",
            action="active", permission="contract.edit", severity="info"))

    # ---- signature chase ----
    if status == "out_for_signature":
        pending = db.scalars(select(models.SignatureRecipient)
                             .join(models.SignatureEnvelope,
                                   models.SignatureRecipient.envelope_id == models.SignatureEnvelope.id)
                             .where(models.SignatureEnvelope.contract_id == contract.id,
                                    models.SignatureEnvelope.tenant_id == contract.tenant_id,
                                    models.SignatureRecipient.status.in_(("created", "sent", "viewed")))).all()
        if pending:
            names = ", ".join(sorted({r.name or r.email for r in pending})[:3])
            out.append(_suggest(
                "chase_signature", f"Waiting on {len(pending)} signature(s)",
                f"Still to sign: {names}. A reminder can be sent from the signature panel.",
                action="remind", permission="contract.send", severity="info"))

    # ---- obligations and dates ----
    today = _today()
    overdue = db.scalars(select(models.Obligation).where(
        models.Obligation.tenant_id == contract.tenant_id,
        models.Obligation.contract_id == contract.id,
        # `pending` as well as `overdue`: the sweep that flips one to the other runs on a beat,
        # so between the due date passing and the next sweep an obligation is late and still
        # says `pending`. Reading the date is the truth; the status is a cached view of it.
        models.Obligation.status.in_(("pending", "overdue")),
        models.Obligation.due_date.is_not(None),
        models.Obligation.due_date < today)).all()
    if overdue:
        out.append(_suggest(
            "overdue_obligations", f"{len(overdue)} obligation(s) overdue",
            "An obligation past its date is the most common way an agreement quietly goes into "
            "breach.",
            action="open_obligations", permission="", severity="critical",
            href=f"/contracts/{contract.id}#obligations"))

    if contract.end_date and status in ("active", "expiring"):
        days_left = (contract.end_date - today).days
        if 0 <= days_left <= 90:
            out.append(_suggest(
                "expiring_soon", f"Expires in {days_left} day(s)",
                "Decide now whether to renew, renegotiate or let it lapse — the notice period "
                "may be shorter than the time left.",
                action="renew", permission="contract.edit",
                severity="critical" if days_left <= 30 else "warning"))
        elif days_left < 0:
            out.append(_suggest(
                "past_expiry", "This is past its expiry date",
                "It is still marked active. Either it was renewed and the record was not "
                "updated, or it has lapsed.",
                action="edit", permission="contract.edit", severity="critical"))

    order = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda s: order.get(s["severity"], 3))
    return out[:6]


def prefill_for(db: Session, tenant_id: str, user: models.User,
                contract_type: str = "") -> dict:
    """Sensible starting values for a new agreement.

    Taken from what this user actually did last, not from a configured default — the last
    agreement somebody created is a far better guess at the next one than anything an
    administrator would think to configure, and it costs one query.

    Returns only fields it has evidence for. Pre-filling a field with a guess the user does not
    notice is worse than leaving it empty: an empty field gets filled in, a wrong one gets
    signed.
    """
    conditions = [models.Contract.tenant_id == tenant_id,
                  models.Contract.owner_id == user.id]
    if contract_type:
        conditions.append(models.Contract.type == contract_type)

    last = db.scalar(select(models.Contract).where(*conditions).order_by(
        models.Contract.created_at.desc()).limit(1))
    if last is None:
        return {}

    prefill: dict = {}
    if last.department:
        prefill["department"] = last.department
    if last.department_id:
        prefill["department_id"] = last.department_id
    if last.currency:
        prefill["currency"] = last.currency
    if last.governing_law:
        prefill["governing_law"] = last.governing_law
    if last.folder_id:
        prefill["folder_id"] = last.folder_id
    if contract_type and last.type == contract_type and last.renewal_type != "none":
        # Only carried across within the same agreement type. Vendor agreements auto-renew and
        # employment contracts do not; copying that across types would be a guess, not a hint.
        prefill["renewal_type"] = last.renewal_type

    prefill["_source"] = "your last agreement"
    return prefill


def workspace_actions(db: Session, tenant_id: str, user: models.User) -> list[dict]:
    """Next-best-actions across the workspace, for the dashboard.

    Counts only. The dashboard says how many and where; deciding what to do about each one
    happens on the agreement, where the context is.
    """
    today = _today()
    out: list[dict] = []

    # `active`, not `pending`: a pending step is one the run has not reached yet, and telling
    # somebody to decide a step that is not their turn is how the panel loses credibility.
    # Eligibility goes through `workflow_service.can_decide` — the same check the inbox and the
    # decide endpoint use, so the count here cannot disagree with what they can actually act on.
    from . import workflow_service as wf

    steps = db.scalars(
        select(models.WorkflowRunStep)
        .join(models.WorkflowRun, models.WorkflowRunStep.run_id == models.WorkflowRun.id)
        .where(models.WorkflowRunStep.tenant_id == tenant_id,
               models.WorkflowRunStep.status == "active",
               models.WorkflowRun.status == "running")).all()
    waiting = [s for s in steps if wf.can_decide(user, s)]
    if waiting:
        out.append(_suggest(
            "my_approvals", f"{len(waiting)} approval(s) waiting on you",
            "Nothing moves until these are decided.",
            action="open_inbox", severity="critical", href="/inbox"))

    mine_overdue = db.scalars(select(models.Obligation).where(
        models.Obligation.tenant_id == tenant_id,
        models.Obligation.owner_id == user.id,
        models.Obligation.status.in_(("pending", "overdue")),
        models.Obligation.due_date.is_not(None),
        models.Obligation.due_date < today)).all()
    if mine_overdue:
        out.append(_suggest(
            "my_overdue", f"{len(mine_overdue)} obligation(s) of yours are overdue",
            "These are commitments the bank has already made.",
            action="open_obligations", severity="critical", href="/obligations"))

    soon = today + dt.timedelta(days=30)
    expiring = db.scalars(select(models.Contract).where(
        models.Contract.tenant_id == tenant_id,
        models.Contract.owner_id == user.id,
        models.Contract.status.in_(("active", "expiring")),
        models.Contract.end_date.is_not(None),
        models.Contract.end_date <= soon,
        models.Contract.end_date >= today)).all()
    if expiring:
        out.append(_suggest(
            "expiring_30", f"{len(expiring)} of your agreements expire within 30 days",
            "Check the notice period on each — it may already have passed.",
            action="open_contracts", severity="warning",
            href="/contracts?status=expiring"))

    stalled_before = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=14)
    stalled = db.scalars(select(models.Contract).where(
        models.Contract.tenant_id == tenant_id,
        models.Contract.owner_id == user.id,
        models.Contract.status == "draft",
        models.Contract.updated_at < stalled_before)).all()
    if stalled:
        out.append(_suggest(
            "stalled_drafts", f"{len(stalled)} draft(s) untouched for two weeks",
            "Either they need finishing or they should be voided, so they stop appearing in "
            "everyone's counts.",
            action="open_contracts", severity="info", href="/contracts?status=draft"))

    order = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda s: order.get(s["severity"], 3))
    return out
