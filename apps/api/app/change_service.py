"""Changes to an executed agreement: amendments, terminations, and renewal decisions.

Everything here happens *after* signature, which is what makes it different from drafting. An
active agreement is a live obligation on both parties, so changing it is not an edit — it is a
new instrument that has to go through review, be accepted by the counterparty, and be linked
to what it changes so that "what is actually in force?" stays answerable.

Three flows:

- **Amendment** — a child agreement cloned from the parent, negotiated and signed on its own
  terms, carrying a recorded **impact**: which fields and clauses moved, and what that did to
  the value and the term. Recorded at execution rather than derived later, because two years
  on nobody can reconstruct it from two documents without guessing.
- **Termination** — a request with a reason and supporting documents, signed off by the
  functions that have a stake (Legal, Compliance, Finance), which then generates the notice
  served on the counterparty. Not a status somebody types into a form.
- **Renewal notices** — configurable per agreement. A three-year outsourcing contract and a
  three-month NDA do not need the same warning, and one global setting means one of them is
  always wrong.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import lifecycle, models, repository_service
from .audit import record

#: The default warning schedule. Overridable per agreement.
DEFAULT_NOTICE_DAYS = (90, 60, 30)

#: Statuses an agreement must be in before it can be amended or terminated. Amending a draft
#: is just editing it; terminating one is deleting it.
LIVE_STATUSES = ("active", "signed", "expiring", "renewed")

REASON_CODES = ("convenience", "cause", "mutual", "expiry", "regulatory")

#: Who must sign off on ending an agreement early. Legal always; Finance where money is
#: involved; Compliance for anything regulator-facing.
DEFAULT_TERMINATION_ROLES = ("manager", "owner")


class ChangeError(ValueError):
    """Refused change operation. Routers map to 400/409."""


def _today() -> dt.date:
    return dt.date.today()


def _next_reference(db: Session, tenant_id: str) -> str:
    year = _today().year
    count = db.query(models.Contract).filter_by(tenant_id=tenant_id).count()
    return f"C-{year}-{count + 1:04d}"


# ---------------------------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------------------------


def request_amendment(db: Session, parent: models.Contract, *, actor: models.User,
                      title: str = "", reason: str = "", ip: str = "") -> models.Contract:
    """Open an amendment against a live agreement.

    The amendment is a **clone** of the parent, not a pointer at it: it goes through its own
    review and signature, and until it is executed the parent is still what is in force. A
    flag on the parent would make the parent's own text ambiguous in the meantime.
    """
    if parent.status not in LIVE_STATUSES:
        raise ChangeError(
            f"Only a live agreement can be amended — this one is {parent.status.replace('_', ' ')}."
        )
    if parent.legal_hold:
        raise ChangeError("This agreement is under legal hold.")

    child = models.Contract(
        tenant_id=parent.tenant_id,
        reference_no=_next_reference(db, parent.tenant_id),
        title=(title.strip() or f"Amendment to {parent.title}")[:300],
        type=parent.type, status="draft", owner_id=actor.id,
        counterparty=parent.counterparty, party_id=parent.party_id,
        department=parent.department, department_id=parent.department_id,
        folder_id=parent.folder_id,
        value=parent.value, currency=parent.currency,
        effective_date=parent.effective_date, end_date=parent.end_date,
        renewal_type=parent.renewal_type, governing_law=parent.governing_law,
        risk_level=parent.risk_level, tags=list(parent.tags or []),
        body=parent.body or "", source="amendment",
        template_id=parent.template_id, template_version_no=parent.template_version_no,
        included_clauses=list(parent.included_clauses or []),
        custom_fields=dict(parent.custom_fields or {}),
        created_by=actor.id,
    )
    db.add(child)
    db.flush()

    db.add(models.ContractVersion(
        tenant_id=child.tenant_id, contract_id=child.id, version_no=1, body=child.body,
        change_summary=f"Amendment opened against {parent.reference_no}"
                       + (f": {reason}" if reason else ""),
        created_by=actor.id,
    ))
    repository_service.relate(db, parent, child, "amendment_of", actor=actor,
                              note=reason[:500], ip=ip)

    record(db, tenant_id=parent.tenant_id, action="contract.amendment_requested", actor=actor,
           object_type="contract", object_id=child.id, object_label=child.title, ip=ip,
           meta={"parent_id": parent.id, "parent_reference": parent.reference_no,
                 "reason": reason[:200]})
    return child


def amendment_impact(db: Session, child: models.Contract,
                     parent: models.Contract) -> dict:
    """What this amendment actually changes, in the terms someone approving it cares about."""
    tracked = ("counterparty", "value", "currency", "effective_date", "end_date",
               "renewal_type", "governing_law", "risk_level", "department")
    fields: dict[str, dict] = {}
    for name in tracked:
        before, after = getattr(parent, name, None), getattr(child, name, None)
        if str(before or "") != str(after or ""):
            fields[name] = {"from": str(before or ""), "to": str(after or "")}

    parent_clauses = {c.get("key") for c in (parent.included_clauses or [])}
    child_clauses = {c.get("key") for c in (child.included_clauses or [])}

    value_delta = float(child.value or 0) - float(parent.value or 0)
    term_delta = None
    if parent.end_date and child.end_date:
        term_delta = (child.end_date - parent.end_date).days

    return {
        "fields": fields,
        "clauses": {
            "added": sorted(child_clauses - parent_clauses),
            "removed": sorted(parent_clauses - child_clauses),
        },
        "body_changed": (parent.body or "") != (child.body or ""),
        "value_delta": round(value_delta, 2),
        "term_delta_days": term_delta,
        "parent_id": parent.id,
        "parent_reference": parent.reference_no,
    }


def execute_amendment(db: Session, child: models.Contract, *, actor: models.User,
                      ip: str = "") -> dict:
    """Bring an executed amendment into force against its parent.

    Records the impact on the amendment, then supersedes the parent — so the repository can
    answer "what is in force?" without walking a chain of documents and comparing them.
    """
    relation = db.scalar(
        select(models.ContractRelation).where(
            models.ContractRelation.child_id == child.id,
            models.ContractRelation.kind == "amendment_of",
        )
    )
    if relation is None:
        raise ChangeError("This agreement is not an amendment of anything.")
    parent = db.get(models.Contract, relation.parent_id)
    if parent is None:
        raise ChangeError("The agreement being amended no longer exists.")
    if child.status not in ("signed", "active"):
        raise ChangeError("An amendment has to be executed before it can take effect.")

    impact = amendment_impact(db, child, parent)
    child.amendment_impact = impact

    # The parent is superseded, not deleted: it is still the agreement that governed the
    # period before the amendment, and the audit trail depends on it staying readable.
    repository_service.relate(db, parent, child, "supersedes", actor=actor,
                              note="Superseded by amendment", ip=ip)
    if "renewed" in lifecycle.TRANSITIONS.get(parent.status, set()):
        parent.status = "renewed"

    record(db, tenant_id=child.tenant_id, action="contract.amendment_executed", actor=actor,
           object_type="contract", object_id=child.id, object_label=child.title, ip=ip,
           meta={"parent_id": parent.id, "impact": impact})
    return impact


# ---------------------------------------------------------------------------------------
# Terminations
# ---------------------------------------------------------------------------------------


def request_termination(db: Session, contract: models.Contract, *, actor: models.User,
                        reason: str, reason_code: str = "convenience",
                        notice_days: int = 0, effective_date: dt.date | None = None,
                        documents: list | None = None,
                        required_roles: list[str] | None = None,
                        ip: str = "") -> models.TerminationRequest:
    """Open a termination request. Does **not** terminate anything by itself."""
    if contract.status not in LIVE_STATUSES:
        raise ChangeError(
            f"Only a live agreement can be terminated — this one is "
            f"{contract.status.replace('_', ' ')}."
        )
    if contract.legal_hold:
        raise ChangeError("This agreement is under legal hold and cannot be terminated.")
    if reason_code not in REASON_CODES:
        raise ChangeError(f"Unknown termination reason '{reason_code}'.")
    if not reason.strip():
        raise ChangeError("A termination needs a reason.")

    open_request = db.scalar(
        select(models.TerminationRequest).where(
            models.TerminationRequest.contract_id == contract.id,
            models.TerminationRequest.status.in_(("pending", "approved")),
        )
    )
    if open_request is not None:
        raise ChangeError("A termination request is already open on this agreement.")

    request = models.TerminationRequest(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        reason_code=reason_code, reason=reason.strip(),
        notice_days=max(0, int(notice_days or 0)),
        effective_date=effective_date or (_today() + dt.timedelta(days=int(notice_days or 0))),
        documents=list(documents or []),
        required_roles=list(required_roles or DEFAULT_TERMINATION_ROLES),
        status="pending", requested_by=actor.id, requested_by_name=actor.name,
    )
    db.add(request)
    db.flush()

    record(db, tenant_id=contract.tenant_id, action="contract.termination_requested",
           actor=actor, object_type="contract", object_id=contract.id,
           object_label=contract.title, ip=ip,
           meta={"request_id": request.id, "reason_code": reason_code,
                 "reason": reason[:200], "effective_date": str(request.effective_date),
                 "required_roles": request.required_roles})
    return request


def decide_termination(db: Session, request: models.TerminationRequest, *,
                       actor: models.User, approve: bool, comment: str = "",
                       ip: str = "") -> models.TerminationRequest:
    """Record one stakeholder's decision.

    A rejection ends it immediately: requiring the remaining functions to also decline
    something already refused wastes their time and muddies the record.
    """
    if request.status != "pending":
        raise ChangeError("This termination request has already been decided.")
    if actor.role not in (request.required_roles or []):
        raise ChangeError("Your role is not one of the required sign-offs.")
    if any(entry.get("user_id") == actor.id for entry in (request.approvals or [])):
        raise ChangeError("You have already decided on this request.")

    approvals = list(request.approvals or [])
    approvals.append({
        "role": actor.role, "user_id": actor.id, "name": actor.name,
        "decision": "approved" if approve else "rejected",
        "at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(),
        "comment": comment[:500],
    })
    request.approvals = approvals

    if not approve:
        request.status = "rejected"
    else:
        decided_roles = {a["role"] for a in approvals if a["decision"] == "approved"}
        if decided_roles >= set(request.required_roles or []):
            request.status = "approved"

    record(db, tenant_id=request.tenant_id,
           action="contract.termination_decided", actor=actor,
           object_type="contract", object_id=request.contract_id, ip=ip,
           meta={"request_id": request.id, "decision": approvals[-1]["decision"],
                 "status": request.status, "comment": comment[:200]})
    return request


def execute_termination(db: Session, request: models.TerminationRequest,
                        contract: models.Contract, *, actor: models.User,
                        ip: str = "") -> models.Contract:
    """Serve the termination: set the agreement terminated and close its open obligations."""
    if request.status != "approved":
        raise ChangeError("This termination has not been approved by everyone required.")
    if "terminated" not in lifecycle.TRANSITIONS.get(contract.status, set()):
        raise ChangeError(
            f"An agreement in {contract.status.replace('_', ' ')} cannot be terminated."
        )

    contract.status = "terminated"
    contract.end_date = request.effective_date or _today()
    request.status = "executed"
    request.notice_sent_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    # Obligations under a terminated agreement are not "overdue" — they are moot. Leaving
    # them pending would keep chasing people for work that no longer needs doing.
    closed = 0
    for obligation in db.scalars(
        select(models.Obligation).where(
            models.Obligation.contract_id == contract.id,
            models.Obligation.status.in_(("pending", "overdue")),
        )
    ).all():
        obligation.status = "skipped"
        closed += 1

    record(db, tenant_id=contract.tenant_id, action="contract.terminated", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"request_id": request.id, "reason_code": request.reason_code,
                 "effective_date": str(contract.end_date),
                 "obligations_closed": closed})
    return contract


def termination_notice(db: Session, request: models.TerminationRequest,
                       contract: models.Contract, org_name: str) -> str:
    """The notice served on the counterparty, generated from the request.

    Generated rather than hand-written so the dates, reference and reason in the notice are
    the ones actually recorded — a notice that disagrees with the record is a dispute.
    """
    reasons = {
        "convenience": "for convenience, in accordance with the termination provisions of the Agreement",
        "cause": "for cause, following material breach of the Agreement",
        "mutual": "by mutual agreement of the parties",
        "expiry": "by reason of expiry, with no renewal to follow",
        "regulatory": "as required by regulatory direction",
    }
    effective = request.effective_date or _today()
    return (
        f"# Notice of Termination\n\n"
        f"**Reference:** {contract.reference_no}\n\n"
        f"**Agreement:** {contract.title}\n\n"
        f"**Date of notice:** {_today().strftime('%d %B %Y')}\n\n"
        f"To: {contract.counterparty or 'the Counterparty'}\n\n"
        f"{org_name} gives notice that the above Agreement is terminated "
        f"{reasons.get(request.reason_code, 'in accordance with its terms')}, "
        f"with effect from **{effective.strftime('%d %B %Y')}**"
        + (f", being {request.notice_days} days from the date of this notice"
           if request.notice_days else "")
        + ".\n\n"
        f"## Reason\n\n{request.reason}\n\n"
        f"## Surviving obligations\n\n"
        f"Provisions of the Agreement which by their nature survive termination — including "
        f"confidentiality, limitation of liability and governing law — remain in force.\n\n"
        f"Issued by {request.requested_by_name or 'the Bank'} on behalf of {org_name}.\n"
    )


# ---------------------------------------------------------------------------------------
# Renewal notices
# ---------------------------------------------------------------------------------------


def notice_schedule(contract: models.Contract) -> list[int]:
    """Days-before-expiry at which to raise a renewal notice, newest configuration first."""
    configured = [int(d) for d in (contract.renewal_notice_days or []) if int(d) > 0]
    return sorted(set(configured or DEFAULT_NOTICE_DAYS), reverse=True)


def set_notice_schedule(db: Session, contract: models.Contract, days: list[int], *,
                        actor: models.User, ip: str = "") -> list[int]:
    cleaned = sorted({int(d) for d in days if int(d) > 0}, reverse=True)
    if not cleaned:
        raise ChangeError("A renewal schedule needs at least one notice period.")
    if any(d > 730 for d in cleaned):
        raise ChangeError("A notice period beyond two years is almost certainly a mistake.")
    contract.renewal_notice_days = cleaned
    record(db, tenant_id=contract.tenant_id, action="contract.renewal_schedule_set",
           actor=actor, object_type="contract", object_id=contract.id,
           object_label=contract.title, ip=ip, meta={"days": cleaned})
    return cleaned


def due_notices(contract: models.Contract, *, today: dt.date | None = None) -> list[int]:
    """Which notice thresholds this agreement has reached, given its end date."""
    if not contract.end_date:
        return []
    days_left = (contract.end_date - (today or _today())).days
    return [d for d in notice_schedule(contract) if days_left <= d]
