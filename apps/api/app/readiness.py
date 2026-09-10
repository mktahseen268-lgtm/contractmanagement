"""Sign-off readiness pack — the one document a signatory reads before committing.

Closes the last Phase 4 item. Everything in it was already recorded; what was missing was a
single place that answers "is this safe to sign, and who said so?" without the signatory
opening five tabs.

Deliberately **not** a status dump. It leads with the blockers, because the failure mode this
prevents is an authorised signatory executing an agreement whose policy deviations nobody
resolved — the information existed, it just wasn't in front of them.

Three sections, in priority order:

1. **Blockers** — anything that should stop execution: policy deviations, an incomplete
   approval run, a template that was never approved, an unresolved amendment thread.
2. **Approvals** — who approved what, when, and against which SLA. This is the accountability
   record a regulator asks for.
3. **Provenance** — which template revision and which clause versions produced the wording,
   and whether it was edited after generation.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, playbook_service


def _fmt(value: dt.datetime | None) -> str:
    return value.strftime("%d %b %Y %H:%M") if value else "—"


def _approval_rows(db: Session, contract: models.Contract) -> tuple[list[dict], list[str]]:
    """(decisions, blockers) from the contract's approval runs."""
    runs = list(db.scalars(
        select(models.WorkflowRun)
        .where(models.WorkflowRun.contract_id == contract.id,
               models.WorkflowRun.tenant_id == contract.tenant_id)
        .order_by(models.WorkflowRun.started_at.asc())
    ).all())

    decisions: list[dict] = []
    blockers: list[str] = []

    for run in runs:
        steps = list(db.scalars(
            select(models.WorkflowRunStep)
            .where(models.WorkflowRunStep.run_id == run.id)
            .order_by(models.WorkflowRunStep.stage_index.asc(),
                      models.WorkflowRunStep.step_index.asc())
        ).all())
        for step in steps:
            if step.status == "skipped":
                continue
            on_time = None
            if step.due_at and step.decided_at:
                on_time = step.decided_at <= step.due_at
            decisions.append({
                "stage": step.stage_index + 1,
                "name": step.name,
                "who": step.decided_by_name or step.assignee_value or "—",
                "decision": (step.decision or step.status or "pending").replace("_", " "),
                "at": _fmt(step.decided_at),
                "on_time": on_time,
                "escalated": step.escalated_at is not None,
                "delegated": step.delegated_from is not None,
                "comment": (step.comment or "")[:300],
            })
        if run.status == "running":
            waiting = [s.name for s in steps if s.status == "active"]
            blockers.append(
                "The approval workflow is still running"
                + (f" — waiting on {', '.join(waiting)}." if waiting else ".")
            )
        elif run.status in ("rejected", "changes_requested"):
            blockers.append(f"The approval workflow ended as {run.status.replace('_', ' ')}.")

    if not runs:
        blockers.append("No approval workflow has been run against this agreement.")

    return decisions, blockers


def _provenance(db: Session, contract: models.Contract) -> tuple[dict, list[str]]:
    """Where the wording came from, and whether it still matches."""
    notes: list[str] = []
    info: dict = {
        "source": (contract.source or "manual").replace("_", " "),
        "template": "—",
        "template_version": "—",
        "clauses": [],
        "edited_since_generation": None,
    }

    if contract.template_id:
        template = db.get(models.ContractTemplate, contract.template_id)
        info["template"] = template.name if template else "(deleted template)"
        info["template_version"] = (f"v{contract.template_version_no}"
                                    if contract.template_version_no else "unversioned")
        if contract.template_version_no is None:
            notes.append(
                "This agreement was raised before the template was approval-gated, so the "
                "exact wording it started from cannot be proven."
            )
    else:
        notes.append("This agreement was not generated from a template.")

    for entry in (contract.included_clauses or []):
        clause = db.get(models.Clause, entry.get("clause_id", ""))
        current = clause.version_no if clause is not None else None
        used = entry.get("version_no")
        info["clauses"].append({
            "key": entry.get("key", ""),
            "title": entry.get("title", "") or entry.get("key", ""),
            "used": used,
            "current": current,
            "stale": current is not None and used is not None and current != used,
        })
        if current is not None and used is not None and current != used:
            notes.append(
                f"Clause '{entry.get('key')}' has been revised since this draft was generated "
                f"(used v{used}, current v{current})."
            )

    # Was the body edited after the draft was generated? The first version row is the
    # as-generated text, so comparing it to the live body answers it directly.
    first = db.scalar(
        select(models.ContractVersion)
        .where(models.ContractVersion.contract_id == contract.id,
               models.ContractVersion.version_no == 1)
    )
    if first is not None and contract.template_id:
        info["edited_since_generation"] = (first.body or "") != (contract.body or "")

    return info, notes


def build(db: Session, contract: models.Contract) -> dict:
    """The readiness assessment. `ready` is the whole answer; the rest is why."""
    decisions, blockers = _approval_rows(db, contract)
    provenance, notes = _provenance(db, contract)
    policy = playbook_service.review(db, contract)

    for finding in policy["findings"]:
        if finding["status"] in ("missing", "altered", "prohibited"):
            line = (f"Policy: {finding['title']} is {finding['status']} "
                    f"({finding['playbook']}).")
            (blockers if finding["severity"] == "blocker" else notes).append(line)

    if contract.is_non_standard:
        notes.append(
            f"Classified non-standard: {contract.non_standard_reason or 'no reason recorded'}"
        )

    open_amendments = list(db.scalars(
        select(models.Comment)
        .where(models.Comment.contract_id == contract.id,
               models.Comment.kind == "amendment",
               models.Comment.resolved.is_(False))
    ).all())
    if open_amendments:
        blockers.append(
            f"{len(open_amendments)} amendment thread"
            f"{'s are' if len(open_amendments) != 1 else ' is'} still open."
        )

    if contract.legal_hold:
        notes.append("This agreement is under legal hold.")

    return {
        "contract_id": contract.id,
        "reference_no": contract.reference_no,
        "title": contract.title,
        "status": contract.status,
        "ready": not blockers,
        "blockers": blockers,
        "notes": notes,
        "decisions": decisions,
        "provenance": provenance,
        "policy": {
            "checked": policy["checked"],
            "deviation_count": policy["deviation_count"],
            "blocker_count": policy["blocker_count"],
            "playbooks": policy["playbooks"],
        },
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }
