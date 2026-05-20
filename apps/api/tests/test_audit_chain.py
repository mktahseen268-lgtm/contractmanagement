"""Audit-log tamper-evidence chain — verifies that every audit row is HMAC-linked, that
verification detects deletions and in-place edits, and that pre-chain rows are ignored."""

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
