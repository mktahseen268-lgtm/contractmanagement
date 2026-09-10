"""Legal hold — matter-scoped preservation that blocks deletion, purge and archival.

`Contract.legal_hold` already existed as a boolean and every retention path already checks it.
What was missing is the thing that makes a hold defensible: **which matter, placed by whom,
when, and what it covers**. A boolean cannot answer any of those, and it cannot represent two
matters covering the same agreement — so releasing one silently released the other.

So holds are records, and the boolean is *derived* from whether any active hold covers the
agreement. That keeps every existing retention check working unchanged while making the hold
itself auditable.

**A hold beats retention, always.** `archive_service` already treats `legal_hold` as an
unconditional block; this module never clears the flag while another matter still covers the
agreement, which is the failure that would quietly destroy evidence.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .audit import record


class LegalHoldError(ValueError):
    """Refused hold operation. Routers map to 400/409."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def active_holds_for(db: Session, contract: models.Contract) -> list[models.LegalHold]:
    """Every active matter covering this agreement."""
    return [
        hold for hold in db.scalars(
            select(models.LegalHold).where(
                models.LegalHold.tenant_id == contract.tenant_id,
                models.LegalHold.status == "active",
            )
        ).all()
        if contract.id in (hold.contract_ids or [])
    ]


def _sync_flag(db: Session, contract: models.Contract) -> None:
    """Set the fast boolean from the holds that actually exist.

    Derived, never set by hand: two matters can cover one agreement, and releasing one must
    not clear a flag the other still depends on. That is the bug this whole module exists to
    make impossible.
    """
    contract.legal_hold = bool(active_holds_for(db, contract))


def place(db: Session, tenant_id: str, *, matter: str, contract_ids: list[str],
          actor: models.User, reason: str = "", reference: str = "",
          custodian: str = "", ip: str = "") -> models.LegalHold:
    """Place a hold over a set of agreements."""
    if not matter.strip():
        raise LegalHoldError("A legal hold needs a matter name.")
    if not contract_ids:
        raise LegalHoldError("A legal hold needs at least one agreement.")

    contracts = db.scalars(select(models.Contract).where(
        models.Contract.tenant_id == tenant_id,
        models.Contract.id.in_(contract_ids))).all()
    found = {c.id for c in contracts}
    missing = sorted(set(contract_ids) - found)
    if missing:
        raise LegalHoldError(f"{len(missing)} of those agreements do not exist here.")

    hold = models.LegalHold(
        tenant_id=tenant_id, matter=matter.strip()[:200], reference=reference[:100],
        reason=reason, contract_ids=sorted(found), status="active",
        custodian=custodian[:200], placed_by=actor.id,
    )
    db.add(hold)
    db.flush()

    for contract in contracts:
        _sync_flag(db, contract)

    record(db, tenant_id=tenant_id, action="legalhold.placed", actor=actor,
           object_type="legal_hold", object_id=hold.id, object_label=hold.matter, ip=ip,
           meta={"contracts": len(found), "reference": reference[:100],
                 "custodian": custodian[:100], "reason": reason[:300]})
    return hold


def add_contracts(db: Session, hold: models.LegalHold, contract_ids: list[str], *,
                  actor: models.User, ip: str = "") -> models.LegalHold:
    if hold.status != "active":
        raise LegalHoldError("That hold has been released.")
    contracts = db.scalars(select(models.Contract).where(
        models.Contract.tenant_id == hold.tenant_id,
        models.Contract.id.in_(contract_ids))).all()
    added = [c for c in contracts if c.id not in (hold.contract_ids or [])]
    hold.contract_ids = sorted(set(hold.contract_ids or []) | {c.id for c in added})
    db.flush()
    for contract in added:
        _sync_flag(db, contract)
    if added:
        record(db, tenant_id=hold.tenant_id, action="legalhold.extended", actor=actor,
               object_type="legal_hold", object_id=hold.id, object_label=hold.matter, ip=ip,
               meta={"added": len(added)})
    return hold


def release(db: Session, hold: models.LegalHold, *, actor: models.User, reason: str,
            ip: str = "") -> models.LegalHold:
    """Release a matter.

    Requires a reason, and only clears an agreement's flag if **no other active hold** still
    covers it — releasing a hold that shares agreements with a live matter must not expose
    those agreements to the retention sweep.
    """
    if hold.status != "active":
        raise LegalHoldError("That hold has already been released.")
    if not reason.strip():
        raise LegalHoldError("Releasing a legal hold needs a reason.")

    hold.status = "released"
    hold.released_by = actor.id
    hold.released_at = _now()
    hold.release_reason = reason.strip()[:500]
    db.flush()

    still_held = 0
    for contract in db.scalars(select(models.Contract).where(
        models.Contract.tenant_id == hold.tenant_id,
        models.Contract.id.in_(hold.contract_ids or ["__none__"]))).all():
        _sync_flag(db, contract)
        if contract.legal_hold:
            still_held += 1

    record(db, tenant_id=hold.tenant_id, action="legalhold.released", actor=actor,
           object_type="legal_hold", object_id=hold.id, object_label=hold.matter, ip=ip,
           meta={"reason": reason[:300], "contracts": len(hold.contract_ids or []),
                 "still_held_by_another_matter": still_held})
    return hold


def export_set(db: Session, hold: models.LegalHold) -> dict:
    """Everything preserved under this matter, for handing to counsel.

    Includes the audit chain positions rather than the audit text: the point of an export is
    that the recipient can verify what they were given against the record it came from.
    """
    contracts = db.scalars(select(models.Contract).where(
        models.Contract.tenant_id == hold.tenant_id,
        models.Contract.id.in_(hold.contract_ids or ["__none__"]))).all()

    items = []
    for contract in contracts:
        entries = db.scalars(select(models.AuditLog).where(
            models.AuditLog.tenant_id == hold.tenant_id,
            models.AuditLog.object_type == "contract",
            models.AuditLog.object_id == contract.id,
        ).order_by(models.AuditLog.seq.asc())).all()
        versions = db.scalars(select(models.ContractVersion).where(
            models.ContractVersion.contract_id == contract.id)).all()
        items.append({
            "contract_id": contract.id,
            "reference_no": contract.reference_no,
            "title": contract.title,
            "status": contract.status,
            "counterparty": contract.counterparty,
            "versions": len(versions),
            "audit_entries": len(entries),
            "audit_seq_from": entries[0].seq if entries else None,
            "audit_seq_to": entries[-1].seq if entries else None,
        })

    return {
        "hold_id": hold.id,
        "matter": hold.matter,
        "reference": hold.reference,
        "status": hold.status,
        "custodian": hold.custodian,
        "placed_at": hold.placed_at,
        "released_at": hold.released_at,
        "contracts": items,
        "contract_count": len(items),
    }


def blocks_deletion(db: Session, contract: models.Contract) -> str | None:
    """The matter preventing this agreement being deleted, purged or archived, if any."""
    holds = active_holds_for(db, contract)
    if not holds:
        return None
    return holds[0].matter


def reconcile(db: Session, tenant_id: str) -> dict:
    """Recompute every agreement's hold flag from the holds that exist.

    A repair path rather than something the normal flow needs. Worth having because the flag
    is derived state, and derived state that has drifted is the kind of problem discovered
    during a legal matter — the worst possible moment.
    """
    corrected = 0
    for contract in db.scalars(select(models.Contract).where(
            models.Contract.tenant_id == tenant_id)).all():
        before = contract.legal_hold
        _sync_flag(db, contract)
        if before != contract.legal_hold:
            corrected += 1
    return {"corrected": corrected}
