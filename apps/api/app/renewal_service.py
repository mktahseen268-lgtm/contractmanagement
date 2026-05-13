"""Renewals: the engine behind /contracts/{id}/renew + the periodic sweep that flags expiring/
expired contracts and posts owner reminders. v1 keeps the rules simple:

  • sweep flips `active` contracts whose end_date is within RENEWAL_WINDOW_DAYS (default 30) to
    `expiring` and posts a one-time "ending soon" notification to the owner;
  • it also flips `active`/`expiring` contracts whose end_date has already passed to `expired`
    (and posts an "expired" notification);
  • reminders re-fire at the 7-day and 1-day marks, tracked via notification meta so we don't
    double-send.

`renew(contract)` clones the contract metadata into a new `draft` successor with renewed_from_id
back-link, then marks the predecessor `renewed`. A fresh ContractVersion #1 carries the body.
(SLA-driven alerts, multi-year laddering, and price-step renewals are designed in docs/08.)
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import lifecycle, models

RENEWAL_WINDOW_DAYS = 30
REMINDER_DAYS = (30, 7, 1)


def _today() -> dt.date:
    return dt.date.today()


def _next_reference(db: Session, tenant_id: str) -> str:
    year = _today().year
    n = db.scalar(select(func.count(models.Contract.id)).where(models.Contract.tenant_id == tenant_id)) or 0
    return f"C-{year}-{n + 1:04d}"


def _already_notified(db: Session, contract: models.Contract, kind: str, marker: str) -> bool:
    """We track reminder fire-state on Notification.meta so this sweep is safely re-runnable.
    `kind` is the notification.type; `marker` is e.g. "expiring-30d" or "expired".
    """
    if contract.owner_id is None:
        return False
    n = db.scalar(
        select(models.Notification).where(
            models.Notification.tenant_id == contract.tenant_id,
            models.Notification.user_id == contract.owner_id,
            models.Notification.type == kind,
            models.Notification.object_type == "contract",
            models.Notification.object_id == contract.id,
        ).order_by(models.Notification.created_at.desc())
    )
    if n is None:
        return False
    return marker in (n.body or "") or marker in (n.title or "")


def _notify(db: Session, contract: models.Contract, *, kind: str, title: str, body: str) -> bool:
    if not contract.owner_id:
        return False
    db.add(models.Notification(
        tenant_id=contract.tenant_id, user_id=contract.owner_id, type=kind,
        title=title, body=body, object_type="contract", object_id=contract.id,
    ))
    return True


def sweep(db: Session, *, today: dt.date | None = None) -> dict[str, int]:
    """Walk every active/expiring contract in the DB, flip lifecycle as appropriate, and post
    owner reminders. Also flips any pending obligation whose due_date is past to `overdue`.
    Returns counts. Caller commits."""
    today = today or _today()
    horizon = today + dt.timedelta(days=RENEWAL_WINDOW_DAYS)
    flagged_expiring = 0
    moved_to_expired = 0
    reminders_sent = 0
    obligations_overdue = 0

    # NB: no tenant filter — sweep runs across all tenants. RLS is bypassed when GUC is unset
    # (and we don't set it here).

    # 1) active → expiring when within window
    rows = db.scalars(
        select(models.Contract).where(
            models.Contract.status == "active",
            models.Contract.end_date.is_not(None),
            models.Contract.end_date <= horizon,
        )
    ).all()
    for c in rows:
        if c.end_date and c.end_date >= today:
            c.status = "expiring"
            flagged_expiring += 1
            days = (c.end_date - today).days
            marker = f"expiring-{days}d"
            if _notify(db, c, kind="contract.expiring",
                       title=f"\"{c.title}\" is expiring soon",
                       body=f"Ends {c.end_date.isoformat()} (in {days} day{'s' if days != 1 else ''}). [{marker}]"):
                reminders_sent += 1

    # 2) active OR expiring → expired when past the end date
    rows = db.scalars(
        select(models.Contract).where(
            models.Contract.status.in_(["active", "expiring"]),
            models.Contract.end_date.is_not(None),
            models.Contract.end_date < today,
        )
    ).all()
    for c in rows:
        c.status = "expired"
        moved_to_expired += 1
        if not _already_notified(db, c, "contract.expired", "expired"):
            if _notify(db, c, kind="contract.expired",
                       title=f"\"{c.title}\" has expired",
                       body=f"End date was {c.end_date.isoformat() if c.end_date else 'unknown'}. [expired]"):
                reminders_sent += 1

    # 3) follow-up reminders for contracts already in `expiring`: re-fire at 7d and 1d
    rows = db.scalars(
        select(models.Contract).where(
            models.Contract.status == "expiring",
            models.Contract.end_date.is_not(None),
            models.Contract.end_date >= today,
        )
    ).all()
    for c in rows:
        days = (c.end_date - today).days if c.end_date else 999
        for d in REMINDER_DAYS:
            if days == d:
                marker = f"expiring-{d}d"
                if not _already_notified(db, c, "contract.expiring", marker):
                    if _notify(db, c, kind="contract.expiring",
                               title=f"\"{c.title}\" ends in {d} day{'s' if d != 1 else ''}",
                               body=f"Ends {c.end_date.isoformat()}. [{marker}]"):
                        reminders_sent += 1
                break

    # 4) pending obligations whose due date is past → overdue
    o_rows = db.scalars(
        select(models.Obligation).where(
            models.Obligation.status == "pending",
            models.Obligation.due_date.is_not(None),
            models.Obligation.due_date < today,
        )
    ).all()
    for o in o_rows:
        o.status = "overdue"
        obligations_overdue += 1

    return {
        "flagged_expiring": flagged_expiring, "moved_to_expired": moved_to_expired,
        "reminders_sent": reminders_sent, "obligations_overdue": obligations_overdue,
    }


def renew(db: Session, *, contract: models.Contract, by_user: models.User,
          effective_date: dt.date | None = None, end_date: dt.date | None = None,
          change_summary: str = "") -> models.Contract:
    """Create a `draft` successor with the predecessor's metadata + a renewed_from_id link, and
    move the predecessor to `renewed`. The successor inherits owner, type, value, body, etc.
    The new effective_date defaults to old.end_date + 1d (or today); the new end_date defaults
    to effective_date + (old term length) or +12 months."""
    if not lifecycle.can_transition(contract.status, "renewed"):
        raise ValueError(f"A contract that is '{contract.status}' can't be renewed.")

    today = _today()
    new_effective = effective_date or (contract.end_date + dt.timedelta(days=1) if contract.end_date else today)

    if end_date is None:
        if contract.effective_date and contract.end_date and contract.end_date >= contract.effective_date:
            term_days = (contract.end_date - contract.effective_date).days
            end_date = new_effective + dt.timedelta(days=max(term_days, 1))
        else:
            # default 12 months
            end_date = dt.date(new_effective.year + 1, new_effective.month, new_effective.day) if new_effective.month != 2 or new_effective.day != 29 else dt.date(new_effective.year + 1, 3, 1)

    successor = models.Contract(
        tenant_id=contract.tenant_id,
        reference_no=_next_reference(db, contract.tenant_id),
        title=contract.title,
        type=contract.type,
        status="draft",
        owner_id=contract.owner_id,
        counterparty=contract.counterparty,
        department=contract.department,
        value=contract.value,
        currency=contract.currency,
        effective_date=new_effective,
        end_date=end_date,
        renewal_type=contract.renewal_type,
        governing_law=contract.governing_law,
        risk_level=contract.risk_level,
        ai_summary=contract.ai_summary,
        tags=list(contract.tags or []),
        body=contract.body or "",
        source="renewal",
        renewed_from_id=contract.id,
        created_by=by_user.id,
    )
    db.add(successor)
    db.flush()
    db.add(models.ContractVersion(
        tenant_id=contract.tenant_id, contract_id=successor.id, version_no=1,
        body=successor.body, change_summary=(change_summary or f"Renewed from {contract.reference_no}")[:400], created_by=by_user.id,
    ))
    # link the predecessor's lifecycle
    contract.status = "renewed"
    db.add(models.Notification(
        tenant_id=contract.tenant_id, user_id=contract.owner_id, type="contract.renewed",
        title=f"\"{contract.title}\" was renewed",
        body=f"{by_user.name} created a successor ({successor.reference_no}). The original is now marked renewed.",
        object_type="contract", object_id=successor.id,
    )) if contract.owner_id else None
    return successor


def chain_links(db: Session, contract: models.Contract) -> tuple[models.Contract | None, models.Contract | None]:
    """(predecessor, successor) — for surfacing 'renewed from' / 'renewed to' chips in the UI."""
    pred = db.get(models.Contract, contract.renewed_from_id) if contract.renewed_from_id else None
    succ = db.scalar(
        select(models.Contract).where(
            models.Contract.tenant_id == contract.tenant_id,
            models.Contract.renewed_from_id == contract.id,
        ).order_by(models.Contract.created_at.desc())
    )
    return pred, succ
