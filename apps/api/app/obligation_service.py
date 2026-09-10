"""Obligations across the whole repository, not one agreement at a time.

The per-contract endpoints already existed; what was missing is the view that matters
operationally — "what is due, by whom, and what has slipped" across every agreement. An
obligation tracker you can only read one contract at a time is a list nobody checks.

The sweep is deliberately idempotent and clock-driven: it marks what is overdue, raises the
configured reminders once each, and escalates to the contract owner when something is
comfortably past due. Running it twice must not send two reminders, because a reminder system
that cries wolf gets filtered into a folder nobody opens.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .audit import record

#: Days before an obligation is due at which to remind the owner.
REMINDER_DAYS = (14, 7, 1)

#: Days past due at which the contract owner is told, not just the obligation owner.
ESCALATE_AFTER_DAYS = 7


def _today() -> dt.date:
    return dt.date.today()


def rollup(db: Session, tenant_id: str, *, owner_id: str = "", status: str = "",
           contract_id: str = "", department_id: str = "", due_within_days: int | None = None,
           overdue_only: bool = False, today: dt.date | None = None) -> dict:
    """Obligations across every agreement, with the counts an operations view needs."""
    day = today or _today()

    stmt = select(models.Obligation).where(models.Obligation.tenant_id == tenant_id)
    if owner_id:
        stmt = stmt.where(models.Obligation.owner_id == owner_id)
    if status:
        stmt = stmt.where(models.Obligation.status == status)
    if contract_id:
        stmt = stmt.where(models.Obligation.contract_id == contract_id)
    if overdue_only:
        stmt = stmt.where(
            models.Obligation.status.in_(("pending", "overdue")),
            models.Obligation.due_date.is_not(None),
            models.Obligation.due_date < day,
        )
    if due_within_days is not None:
        stmt = stmt.where(
            models.Obligation.due_date.is_not(None),
            models.Obligation.due_date <= day + dt.timedelta(days=int(due_within_days)),
        )

    rows = list(db.scalars(stmt.order_by(
        models.Obligation.due_date.is_(None),
        models.Obligation.due_date.asc(),
    )).all())

    # One query for the contracts involved rather than one per obligation — this view is
    # the whole repository, so an N+1 here is the difference between instant and unusable.
    contract_ids = {r.contract_id for r in rows}
    contracts = {
        c.id: c for c in db.scalars(
            select(models.Contract).where(models.Contract.id.in_(contract_ids or ["__none__"]))
        ).all()
    } if contract_ids else {}

    if department_id:
        rows = [r for r in rows
                if (contracts.get(r.contract_id) is not None
                    and contracts[r.contract_id].department_id == department_id)]

    owners = {
        u.id: u for u in db.scalars(
            select(models.User).where(models.User.tenant_id == tenant_id)
        ).all()
    }

    items = []
    for row in rows:
        contract = contracts.get(row.contract_id)
        days_left = (row.due_date - day).days if row.due_date else None
        items.append({
            "id": row.id,
            "contract_id": row.contract_id,
            "contract_reference": contract.reference_no if contract else "",
            "contract_title": contract.title if contract else "(deleted)",
            "contract_status": contract.status if contract else "",
            "title": row.title,
            "description": row.description,
            "due_date": row.due_date,
            "days_left": days_left,
            "overdue": bool(row.due_date and row.due_date < day
                            and row.status in ("pending", "overdue")),
            "status": row.status,
            "owner_id": row.owner_id,
            "owner_name": owners[row.owner_id].name if row.owner_id in owners else "",
        })

    open_items = [i for i in items if i["status"] in ("pending", "overdue")]
    return {
        "items": items,
        "total": len(items),
        "summary": {
            "open": len(open_items),
            "overdue": sum(1 for i in open_items if i["overdue"]),
            "due_this_week": sum(1 for i in open_items
                                 if i["days_left"] is not None and 0 <= i["days_left"] <= 7),
            "due_this_month": sum(1 for i in open_items
                                  if i["days_left"] is not None and 0 <= i["days_left"] <= 30),
            "unassigned": sum(1 for i in open_items if not i["owner_id"]),
            "done": sum(1 for i in items if i["status"] == "done"),
        },
    }


def sweep(db: Session, *, today: dt.date | None = None, tenant_id: str = "") -> dict:
    """Mark what is overdue, remind once per threshold, escalate what has really slipped.

    Idempotent by construction: a reminder is recorded as a notification and the sweep will
    not raise the same one twice. A reminder system that repeats itself gets filtered into a
    folder nobody opens, which is worse than not reminding at all.
    """
    day = today or _today()
    stmt = select(models.Obligation).where(
        models.Obligation.status.in_(("pending", "overdue")),
        models.Obligation.due_date.is_not(None),
    )
    if tenant_id:
        stmt = stmt.where(models.Obligation.tenant_id == tenant_id)

    marked = reminded = escalated = 0
    sent: dict[str, set[str]] = {}

    for obligation in db.scalars(stmt).all():
        if obligation.tenant_id not in sent:
            sent[obligation.tenant_id] = _sent_markers(db, obligation.tenant_id)
        already = sent[obligation.tenant_id]
        days_left = (obligation.due_date - day).days

        if days_left < 0 and obligation.status != "overdue":
            obligation.status = "overdue"
            marked += 1

        contract = db.get(models.Contract, obligation.contract_id)
        if contract is None or contract.status in ("terminated", "expired", "voided"):
            continue

        # Exactly one reminder per threshold crossed, and only for the *tightest* threshold
        # reached. Walking the list and skipping already-sent markers would fire the 7-day
        # reminder immediately after the 14-day one on the very next sweep — two emails the
        # same morning, which is how a reminder system trains people to ignore it.
        crossed = [t for t in REMINDER_DAYS if 0 <= days_left <= t]
        if crossed:
            threshold = min(crossed)
            marker = f"obligation.reminder:{obligation.id}:{threshold}"
            if marker not in already:
                if obligation.owner_id:
                    db.add(models.Notification(
                        tenant_id=obligation.tenant_id, user_id=obligation.owner_id,
                        type="obligation.due",
                        title=f"Due in {days_left} day(s): {obligation.title}",
                        body=f"On {contract.reference_no} — {contract.title}",
                        object_type="contract", object_id=contract.id,
                    ))
                record(db, tenant_id=obligation.tenant_id, action="obligation.reminded",
                       actor=None, object_type="contract", object_id=contract.id,
                       object_label=obligation.title,
                       meta={"marker": marker, "days_left": days_left,
                             "obligation_id": obligation.id})
                already.add(marker)
                reminded += 1

        # Escalation: the contract owner hears about it once, when it is properly late.
        if days_left <= -ESCALATE_AFTER_DAYS:
            marker = f"obligation.escalation:{obligation.id}"
            if marker not in already:
                db.add(models.Notification(
                    tenant_id=obligation.tenant_id, user_id=contract.owner_id,
                    type="obligation.overdue",
                    title=f"Overdue by {abs(days_left)} days: {obligation.title}",
                    body=f"On {contract.reference_no} — {contract.title}",
                    object_type="contract", object_id=contract.id,
                ))
                record(db, tenant_id=obligation.tenant_id, action="obligation.escalated",
                       actor=None, object_type="contract", object_id=contract.id,
                       object_label=obligation.title,
                       meta={"marker": marker, "days_overdue": abs(days_left),
                             "obligation_id": obligation.id,
                             "escalated_to": contract.owner_id})
                already.add(marker)
                escalated += 1

    return {"marked_overdue": marked, "reminded": reminded, "escalated": escalated}


def _sent_markers(db: Session, tenant_id: str) -> set[str]:
    """Every reminder marker already recorded for this tenant.

    Loaded once per sweep rather than queried per obligation: the sweep walks every open
    obligation in the workspace, and a query inside that loop is the difference between a
    beat that finishes and one that does not.

    The audit log is the record of what was sent, so it is also the right place to ask — a
    separate "sent" table would be a second source of truth for the same fact.
    """
    rows = db.scalars(
        select(models.AuditLog).where(
            models.AuditLog.tenant_id == tenant_id,
            models.AuditLog.action.in_(("obligation.reminded", "obligation.escalated")),
        )
    ).all()
    return {marker for marker in ((r.meta or {}).get("marker") for r in rows) if marker}
