"""Archive and purge — the 10-year retention tier with a 1-year hot search window.

Every test drives a frozen clock through the `now=` parameter rather than mutating the system
clock, so the suite is deterministic and can exercise a ten-year horizon in milliseconds.

The cases that matter most here are the negative ones. `purge_contract` is irreversible: a bug
that purges a contract under legal hold, or one still inside retention, destroys a bank's
records with no undo. Those are tested first-class, not as an afterthought.

Requirements: SOW-25, TEC-06.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app import archive_service, models

NOW = dt.datetime(2026, 8, 25, 12, 0, 0)


def _contract(db, tenant_id, owner_id, *, end_date, status="active", legal_hold=False, title="Agreement"):
    c = models.Contract(
        tenant_id=tenant_id,
        reference_no=f"CM-{end_date.year}-{title[:3].upper()}",
        title=title,
        status=status,
        owner_id=owner_id,
        created_by=owner_id,
        end_date=end_date,
        legal_hold=legal_hold,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture()
def tenant_user(make_user):
    user, tenant = make_user()
    return tenant.id, user.id


# ------------------------------------------------------------------ archive


def test_archives_contract_past_the_hot_window(db, tenant_user):
    tid, uid = tenant_user
    old = _contract(db, tid, uid, end_date=dt.date(2023, 1, 1))

    archive_service.archive_sweep(db, now=NOW)
    db.commit()
    db.refresh(old)

    assert old.archived_at is not None


def test_leaves_contracts_inside_the_hot_window_alone(db, tenant_user):
    """HOT_SEARCH_YEARS defaults to 1 — a contract that ended last month is still hot."""
    tid, uid = tenant_user
    recent = _contract(db, tid, uid, end_date=dt.date(2026, 7, 1))

    archive_service.archive_sweep(db, now=NOW)
    db.commit()
    db.refresh(recent)

    assert recent.archived_at is None


def test_legal_hold_blocks_archival(db, tenant_user):
    tid, uid = tenant_user
    held = _contract(db, tid, uid, end_date=dt.date(2015, 1, 1), legal_hold=True)

    result = archive_service.archive_sweep(db, now=NOW)
    db.commit()
    db.refresh(held)

    assert held.archived_at is None
    assert result["on_legal_hold"] >= 1


def test_drafts_are_never_archived(db, tenant_user):
    """An unfinished draft is work-in-progress, not a record. Archiving it would hide it from
    the people who still have to act on it."""
    tid, uid = tenant_user
    draft = _contract(db, tid, uid, end_date=dt.date(2015, 1, 1), status="draft")

    archive_service.archive_sweep(db, now=NOW)
    db.commit()
    db.refresh(draft)

    assert draft.archived_at is None


def test_archive_is_idempotent(db, tenant_user):
    tid, uid = tenant_user
    c = _contract(db, tid, uid, end_date=dt.date(2020, 1, 1))

    archive_service.archive_sweep(db, now=NOW)
    db.commit()
    first = c.archived_at

    second_run = archive_service.archive_sweep(db, now=NOW + dt.timedelta(days=1))
    db.commit()
    db.refresh(c)

    assert c.archived_at == first
    assert second_run["archived"] == 0


def test_archive_writes_an_audit_entry(db, tenant_user):
    tid, uid = tenant_user
    c = _contract(db, tid, uid, end_date=dt.date(2020, 1, 1))

    archive_service.archive_sweep(db, now=NOW)
    db.commit()

    entry = db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == tid, models.AuditLog.action == "contract.archived"
    ).one()
    assert entry.object_id == c.id


def test_archived_files_move_to_the_cold_prefix(db, tenant_user, tmp_path):
    tid, uid = tenant_user
    c = _contract(db, tid, uid, end_date=dt.date(2020, 1, 1))

    from app.storage import get_storage

    storage = get_storage()
    storage.ensure_ready()
    key = f"tenants/{tid}/contracts/{c.id}/executed.pdf"
    storage.put(key, b"%PDF-1.4 executed", "application/pdf")
    f = models.FileObject(
        tenant_id=tid, key=key, kind="contract_pdf",
        parent_type="contract", parent_id=c.id, created_by=uid,
    )
    db.add(f)
    db.commit()

    archive_service.archive_sweep(db, now=NOW)
    db.commit()
    db.refresh(f)

    assert f.storage_tier == "cold"
    assert f.key.startswith("archive/")
    # The point of a *tier* change: the bytes are still there.
    assert storage.exists(f.key)
    with storage.open_stream(f.key) as fh:
        assert fh.read() == b"%PDF-1.4 executed"


# ------------------------------------------------------------------ purge


def test_purges_contract_past_retention(db, tenant_user):
    tid, uid = tenant_user
    ancient = _contract(db, tid, uid, end_date=dt.date(2010, 1, 1))
    cid = ancient.id

    archive_service.purge_sweep(db, now=NOW)
    db.commit()

    assert db.get(models.Contract, cid) is None


def test_does_not_purge_inside_retention(db, tenant_user):
    """RETENTION_YEARS defaults to 10 — a 2020 contract has years left to run."""
    tid, uid = tenant_user
    c = _contract(db, tid, uid, end_date=dt.date(2020, 1, 1))
    cid = c.id

    archive_service.purge_sweep(db, now=NOW)
    db.commit()

    assert db.get(models.Contract, cid) is not None


def test_legal_hold_blocks_purge(db, tenant_user):
    """The single most destructive path in the codebase. A hold must survive it absolutely."""
    tid, uid = tenant_user
    held = _contract(db, tid, uid, end_date=dt.date(2005, 1, 1), legal_hold=True)
    cid = held.id

    archive_service.purge_sweep(db, now=NOW)
    db.commit()

    assert db.get(models.Contract, cid) is not None


def test_purge_removes_children_and_records_evidence(db, tenant_user):
    tid, uid = tenant_user
    c = _contract(db, tid, uid, end_date=dt.date(2010, 1, 1), title="Vendor Agreement")
    cid = c.id
    db.add(models.ContractVersion(tenant_id=tid, contract_id=cid, version_no=1, body="x", created_by=uid))
    db.add(models.Comment(tenant_id=tid, contract_id=cid, author_id=uid, author_name="Test Owner", body="note"))
    db.commit()

    archive_service.purge_sweep(db, now=NOW)
    db.commit()

    assert db.query(models.ContractVersion).filter_by(contract_id=cid).count() == 0
    assert db.query(models.Comment).filter_by(contract_id=cid).count() == 0
    # The audit row is the only surviving record that the contract ever existed.
    entry = db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == tid, models.AuditLog.action == "contract.purged"
    ).one()
    assert entry.meta["title"] == "Vendor Agreement"


def test_eligibility_gate_is_shared_by_both_sweeps(db, tenant_user):
    """Archive and purge must not drift apart on what they are allowed to touch — a hold that
    stops one but not the other is a data-loss bug waiting to happen."""
    tid, uid = tenant_user
    held = _contract(db, tid, uid, end_date=dt.date(2000, 1, 1), legal_hold=True)
    cutoff = dt.date(2026, 1, 1)

    assert archive_service._eligible(held, cutoff) is False
    held.legal_hold = False
    assert archive_service._eligible(held, cutoff) is True
