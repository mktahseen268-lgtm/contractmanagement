"""Audit-log tamper-evidence chain — verifies that every audit row is HMAC-linked, that
verification detects deletions and in-place edits, and that pre-chain rows are ignored.

Requirements: SEC-12, AC-07.
"""

import datetime as dt
import uuid
import pytest

from app import audit, models
from app.database import SessionLocal, set_request_tenant


@pytest.fixture()
def tenant(make_user):
    _user, t = make_user()
    return t


def _append(db, tenant_id: str, action: str, label: str = "x") -> models.AuditLog:
    entry = audit.record(
        db, tenant_id=tenant_id, action=action, actor=None,
        object_type="test", object_id="o1", object_label=label, meta={"k": "v"}, ip="1.2.3.4",
    )
    db.commit()
    db.refresh(entry)
    return entry


class TestAuditChain:
    def test_each_row_chains_to_the_previous(self, tenant):
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            a = _append(db, tenant.id, "test.one")
            b = _append(db, tenant.id, "test.two")
            c = _append(db, tenant.id, "test.three")

            # Genesis row has prev_hash = "0" * 64
            assert a.prev_hash == "0" * 64
            assert a.row_hash and len(a.row_hash) == 64
            assert b.prev_hash == a.row_hash
            assert c.prev_hash == b.row_hash

    def test_verify_chain_is_ok_on_clean_data(self, tenant):
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            _append(db, tenant.id, "a")
            _append(db, tenant.id, "b")
            _append(db, tenant.id, "c")

            ok, problems = audit.verify_chain(db, tenant.id)
            assert ok, f"chain should be intact; got: {problems}"
            assert problems == []

    def test_verify_detects_in_place_edit(self, tenant):
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            _append(db, tenant.id, "a")
            edited = _append(db, tenant.id, "b")
            _append(db, tenant.id, "c")

            # Tamper: change a field without recomputing the hash
            edited.object_label = "tampered-value"
            db.commit()

            ok, problems = audit.verify_chain(db, tenant.id)
            assert not ok
            assert any(p["kind"] == "hmac_mismatch" for p in problems), problems

    def test_verify_detects_row_deletion(self, tenant):
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            _append(db, tenant.id, "a")
            middle = _append(db, tenant.id, "b")
            _append(db, tenant.id, "c")

            # Tamper: silently delete the middle row
            db.delete(middle)
            db.commit()

            ok, problems = audit.verify_chain(db, tenant.id)
            assert not ok
            assert any(p["kind"] == "prev_mismatch" for p in problems), problems

    def test_chain_is_per_tenant(self, make_user):
        _u1, t1 = make_user()
        _u2, t2 = make_user()
        with SessionLocal() as db:
            set_request_tenant(t1.id)
            a1 = _append(db, t1.id, "t1.a")
        with SessionLocal() as db:
            set_request_tenant(t2.id)
            a2 = _append(db, t2.id, "t2.a")

        # Both tenants get their own genesis row — neither row references the other.
        assert a1.prev_hash == "0" * 64
        assert a2.prev_hash == "0" * 64
        assert a1.row_hash != a2.row_hash


class TestChainOrderingUnderClockTies:
    """Two audit rows written inside the same clock tick.

    Regression for a real hole: the chain used to pick its predecessor by
    `ORDER BY (at DESC, id DESC)`. When `at` tied, that fell through to a random uuid, so a row
    could chain past its true predecessor — and silently deleting the skipped row left a chain
    that verified perfectly. The chain now walks a monotonic per-tenant `seq` instead.

    The ids below are forced so that sort order (b, a, c) differs from insertion order
    (a, b, c). `id` is not part of the canonical row, so overriding it after `record()` does
    not disturb the hashes.
    """

    FROZEN = dt.datetime(2026, 8, 26, 12, 0, 0)
    #: Sort order (b, a, c) deliberately differs from insertion order (a, b, c).
    ID_SUFFIX = {"a": "b", "b": "a", "c": "c"}

    @staticmethod
    def _ids(prefix: str) -> dict:
        """Ids unique per test but with a fixed relative order — a shared prefix keeps them
        sorted together, the suffix decides which comes first."""
        return {k: (prefix + v).ljust(32, "0")[:32]
                for k, v in TestChainOrderingUnderClockTies.ID_SUFFIX.items()}

    def _append_at_frozen_time(self, db, tenant_id, action, monkeypatch, ids):
        monkeypatch.setattr(audit, "_utcnow", lambda: self.FROZEN)
        entry = audit.record(
            db, tenant_id=tenant_id, action=action, actor=None,
            object_type="test", object_id="o1", object_label="x",
            meta={"k": "v"}, ip="1.2.3.4",
        )
        entry.id = ids[action]
        db.commit()
        return entry

    def test_rows_in_the_same_tick_still_chain_in_insertion_order(self, tenant, monkeypatch):
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            ids = self._ids(uuid.uuid4().hex[:8])
            a = self._append_at_frozen_time(db, tenant.id, "a", monkeypatch, ids)
            b = self._append_at_frozen_time(db, tenant.id, "b", monkeypatch, ids)
            c = self._append_at_frozen_time(db, tenant.id, "c", monkeypatch, ids)
            assert ids["b"] < ids["a"] < ids["c"], "the id ordering is the trap being tested"

            assert a.at == b.at == c.at, "the tie is the point of this test"
            assert [a.seq, b.seq, c.seq] == [1, 2, 3]
            assert b.prev_hash == a.row_hash
            assert c.prev_hash == b.row_hash, "the chain must not skip the middle row"

    def test_deleting_a_row_written_in_a_tied_tick_is_still_detected(self, tenant, monkeypatch):
        """The failure this closes: the deletion used to be invisible."""
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            ids = self._ids(uuid.uuid4().hex[:8])
            self._append_at_frozen_time(db, tenant.id, "a", monkeypatch, ids)
            middle = self._append_at_frozen_time(db, tenant.id, "b", monkeypatch, ids)
            self._append_at_frozen_time(db, tenant.id, "c", monkeypatch, ids)

            db.delete(middle)
            db.commit()

            ok, problems = audit.verify_chain(db, tenant.id)
            assert not ok, "a deleted audit row must never verify clean"
            assert any(p["kind"] == "prev_mismatch" for p in problems), problems

    def test_an_edit_in_a_tied_tick_is_still_detected(self, tenant, monkeypatch):
        with SessionLocal() as db:
            set_request_tenant(tenant.id)
            ids = self._ids(uuid.uuid4().hex[:8])
            self._append_at_frozen_time(db, tenant.id, "a", monkeypatch, ids)
            middle = self._append_at_frozen_time(db, tenant.id, "b", monkeypatch, ids)
            self._append_at_frozen_time(db, tenant.id, "c", monkeypatch, ids)

            middle.object_label = "quietly changed"
            db.commit()

            ok, problems = audit.verify_chain(db, tenant.id)
            assert not ok
            assert any(p["kind"] == "hmac_mismatch" for p in problems), problems


def test_two_entries_in_one_transaction_chain_correctly(db, make_user):
    """Regression: the chain must not depend on when the caller commits.

    Recording two actions before a single commit is ordinary — a workflow decision that also
    notifies, a grant followed by a break-glass. Before this was fixed both rows claimed
    sequence 1 and both chained to the genesis hash, so `verify_chain` reported tampering on a
    log nobody had touched. A tamper-evidence mechanism that cries wolf on the common path is
    worse than none, because the first real alert gets dismissed with the rest.
    """
    from app import audit, models

    user, tenant = make_user()
    user = db.merge(user)

    audit.record(db, tenant_id=tenant.id, action="test.first", actor=user,
                 object_type="contract", object_id="c1")
    audit.record(db, tenant_id=tenant.id, action="test.second", actor=user,
                 object_type="contract", object_id="c2")
    db.commit()

    rows = db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == tenant.id).order_by(models.AuditLog.seq).all()
    assert [r.seq for r in rows] == [1, 2]
    assert rows[1].prev_hash == rows[0].row_hash

    ok, problems = audit.verify_chain(db, tenant.id)
    assert ok, problems
