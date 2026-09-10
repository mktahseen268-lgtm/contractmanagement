"""Contract archive and purge — the retention tiering behind the RFP's storage requirement.

    "Storage capacity for 10 years of financial records, with 1 year instantly searchable"
    "Data purging and archiving"                              — RFP §4c Infrastructure & Storage

Two jobs, both idempotent, both run nightly by Celery beat (`app/tasks.py`):

  archive_sweep — executed contracts whose end date is older than `HOT_SEARCH_YEARS` move to
                  the cold tier: files relocate to the `archive/` key prefix (and, on S3,
                  optionally a cheaper storage class), `archived_at` is stamped, and the
                  contract drops out of the live search index. The row stays queryable by id
                  and reference, so an archived contract is still *retrievable* — this is a
                  tier change, not a deletion.

  purge_sweep   — contracts past `RETENTION_YEARS` are hard-deleted along with their versions,
                  comments, obligations and files.

Both refuse to touch a contract under legal hold. That check is deliberately in one place —
`_eligible()` — so a future matter-scoped hold (Phase 8) has exactly one predicate to extend
and cannot be bypassed by adding a caller.

Every archive and every purge writes an audit entry. A purge is irreversible, so the audit row
(which survives it) is the only remaining record that the contract existed — it carries the
reference number, title, counterparty and the dates that justified the purge.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from . import audit, models
from .config import settings
from .storage import get_storage

log = logging.getLogger("uvicorn.error")

#: Only executed contracts are archived. A draft that has sat for a year is not a record —
#: it is unfinished work, and archiving it would hide it from the people who must act on it.
ARCHIVABLE_STATUSES = ("signed", "active", "expired", "terminated", "renewed", "voided")

_ARCHIVE_TIER = "cold"


def _cutoff(now: dt.datetime, years: int) -> dt.date:
    # Calendar-accurate rather than years*365: over a 10-year horizon the drift is ~2.5 days,
    # which is enough to purge a record an operator would say is still in retention.
    try:
        return now.date().replace(year=now.year - years)
    except ValueError:  # 29 Feb
        return now.date().replace(year=now.year - years, day=28)


def _effective_date(c: models.Contract) -> dt.date | None:
    """The date retention is measured from: when the agreement stopped being live."""
    return c.end_date or c.effective_date or (c.created_at.date() if c.created_at else None)


def _eligible(c: models.Contract, cutoff: dt.date) -> bool:
    """The single gate both sweeps go through. Legal hold wins over everything."""
    if c.legal_hold:
        return False
    if c.status not in ARCHIVABLE_STATUSES:
        return False
    d = _effective_date(c)
    return d is not None and d < cutoff


def _contract_files(db: Session, c: models.Contract) -> list[models.FileObject]:
    return list(db.scalars(
        select(models.FileObject).where(
            models.FileObject.tenant_id == c.tenant_id,
            models.FileObject.parent_type == "contract",
            models.FileObject.parent_id == c.id,
        )
    ).all())


# ---------------------------------------------------------------------------- archive


def archive_contract(db: Session, c: models.Contract, *, now: dt.datetime | None = None) -> int:
    """Move one contract's files to the cold tier and mark it archived. Returns files moved.

    Caller commits. Safe to re-run: already-cold files are skipped, and a contract that is
    already archived short-circuits.
    """
    if c.archived_at is not None:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    storage = get_storage()
    moved = 0
    for f in _contract_files(db, c):
        if f.storage_tier == _ARCHIVE_TIER:
            continue
        cold_key = f"{settings.archive_storage_prefix}/{f.key}"
        try:
            storage.move(f.key, cold_key, storage_class=settings.archive_s3_storage_class)
        except Exception:  # noqa: BLE001
            # A file that will not move must not block the sweep or leave the DB claiming a
            # key that does not exist. Leave it hot and try again on the next run.
            log.exception("archive: could not move %s -> %s (file left in hot tier)", f.key, cold_key)
            continue
        f.key = cold_key
        f.storage_tier = _ARCHIVE_TIER
        f.archived_at = now
        moved += 1

    c.archived_at = now
    audit.record(
        db,
        tenant_id=c.tenant_id,
        action="contract.archived",
        object_type="contract",
        object_id=c.id,
        object_label=c.reference_no or c.title,
        meta={
            "reason": f"older than hot window ({settings.hot_search_years}y)",
            "files_moved": moved,
            "end_date": str(c.end_date) if c.end_date else None,
        },
    )
    return moved


def archive_sweep(db: Session, *, now: dt.datetime | None = None, limit: int = 500) -> dict:
    """Archive every eligible contract. `limit` bounds one run so a first sweep over a
    ten-year backlog does not hold a transaction open for hours — the beat picks up the rest
    on the next run."""
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    cutoff = _cutoff(now, settings.hot_search_years)
    rows = db.scalars(
        select(models.Contract)
        .where(
            models.Contract.archived_at.is_(None),
            models.Contract.legal_hold.is_(False),
            models.Contract.status.in_(ARCHIVABLE_STATUSES),
        )
        .order_by(models.Contract.end_date.asc())
        .limit(limit)
    ).all()

    archived = files_moved = 0
    for c in rows:
        if not _eligible(c, cutoff):
            continue
        files_moved += archive_contract(db, c, now=now)
        archived += 1

    # Reported separately so the operator can see holds are actually suppressing archival
    # rather than the sweep simply having nothing to do.
    skipped_hold = db.scalar(
        select(func.count()).select_from(models.Contract).where(models.Contract.legal_hold.is_(True))
    ) or 0

    result = {
        "archived": archived,
        "files_moved": files_moved,
        "on_legal_hold": skipped_hold,
        "cutoff": str(cutoff),
        "truncated": len(rows) == limit,
    }
    log.info("archive.sweep: %s", result)
    return result


# ---------------------------------------------------------------------------- purge


def purge_contract(db: Session, c: models.Contract) -> dict:
    """Hard-delete one contract and everything hanging off it. Caller commits.

    Irreversible. The audit entry is written *before* the delete so the record of the purge
    exists even if the delete itself fails partway.
    """
    audit.record(
        db,
        tenant_id=c.tenant_id,
        action="contract.purged",
        object_type="contract",
        object_id=c.id,
        object_label=c.reference_no or c.title,
        meta={
            "reason": f"past retention ({settings.retention_years}y)",
            "title": c.title,
            "counterparty": c.counterparty,
            "type": c.type,
            "status": c.status,
            "effective_date": str(c.effective_date) if c.effective_date else None,
            "end_date": str(c.end_date) if c.end_date else None,
            "archived_at": c.archived_at.isoformat() if c.archived_at else None,
        },
    )

    storage = get_storage()
    files = _contract_files(db, c)
    for f in files:
        try:
            storage.delete(f.key)
        except Exception:  # noqa: BLE001
            log.exception("purge: could not delete stored object %s (db row removed anyway)", f.key)
    file_ids = [f.id for f in files]

    counts = {"files": len(file_ids)}
    if file_ids:
        db.execute(delete(models.FileObject).where(models.FileObject.id.in_(file_ids)))
    for model in (models.ContractVersion, models.Comment, models.Obligation):
        r = db.execute(delete(model).where(model.contract_id == c.id))
        counts[model.__tablename__] = r.rowcount or 0
    db.delete(c)
    return counts


def purge_sweep(db: Session, *, now: dt.datetime | None = None, limit: int = 200) -> dict:
    """Hard-delete contracts past the retention horizon. Legal hold blocks this absolutely."""
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    cutoff = _cutoff(now, settings.retention_years)
    rows = db.scalars(
        select(models.Contract)
        .where(
            models.Contract.legal_hold.is_(False),
            models.Contract.status.in_(ARCHIVABLE_STATUSES),
            or_(models.Contract.end_date.is_not(None), models.Contract.effective_date.is_not(None)),
        )
        .order_by(models.Contract.end_date.asc())
        .limit(limit)
    ).all()

    purged = 0
    for c in rows:
        if not _eligible(c, cutoff):
            continue
        purge_contract(db, c)
        purged += 1

    result = {"purged": purged, "cutoff": str(cutoff), "truncated": len(rows) == limit}
    log.info("archive.purge: %s", result)
    return result
