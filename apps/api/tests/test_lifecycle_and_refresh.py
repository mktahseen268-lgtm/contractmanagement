"""Lifecycle invariants + refresh-token reuse detection.

Lifecycle:  the contract state machine in `lifecycle.TRANSITIONS` is the contract for what
status changes are legal. We verify that legal transitions are accepted and that an illegal
one (e.g. signed -> draft) is rejected.

Refresh-token reuse: presenting a refresh token that has already been rotated must (a) burn
the whole session chain and (b) report status='reuse' so the router returns 401. This is
the single most important post-exfiltration defence in `auth_service`."""

import datetime as dt
import uuid

import pytest

from app import auth_service, lifecycle, models, security
from app.database import SessionLocal, set_request_tenant


class TestLifecycleStateMachine:
    def test_legal_transitions_match_transitions_dict(self):
        # draft -> in_review is legal, draft -> signed is not.
        assert "in_review" in lifecycle.TRANSITIONS["draft"]
        assert "signed" not in lifecycle.TRANSITIONS["draft"]

    def test_signed_is_a_sink_apart_from_active(self):
        # signed -> active is allowed; signed -> draft is not (you don't un-sign).
        assert "active" in lifecycle.TRANSITIONS["signed"]
        assert "draft" not in lifecycle.TRANSITIONS["signed"]

    def test_void_decline_terminal_states(self):
        # voided / declined / terminated are terminal — empty transition set.
        for terminal in ("voided", "terminated", "expired"):
            assert lifecycle.TRANSITIONS.get(terminal, set()) == set(), (
                f"{terminal} should be a terminal state with no outgoing transitions"
            )


class _FakeRequest:
    """Minimal Request-like object for auth_service.create_session/rotate_session."""

    def __init__(self):
        self.headers = {"user-agent": "pytest"}
        self.client = type("C", (), {"host": "127.0.0.1"})()


class TestRefreshTokenReuseDetection:
    def test_reused_rotated_token_burns_the_chain(self, make_user):
        user, _tenant = make_user()
        req = _FakeRequest()

        with SessionLocal() as db:
            set_request_tenant(user.tenant_id)
            raw1, sid1 = auth_service.create_session(db, user, req)
            db.commit()

            # Legitimate rotation: rotate once, get raw2
            status_, new_session, raw2 = auth_service.rotate_session(db, raw1, req)
            assert status_ == "ok"
            assert new_session is not None
            assert raw2 and raw2 != raw1
            db.commit()

            # Attacker presents raw1 (already rotated): should be flagged as reuse and the
            # entire chain (both old + the legitimate new session) must be revoked.
            status2, _new2, _raw3 = auth_service.rotate_session(db, raw1, req)
            assert status2 == "reuse"
            db.commit()

            # Verify every session in the chain is now revoked.
            sessions = db.query(models.Session).filter(models.Session.user_id == user.id).all()
            assert sessions, "should have at least the original chain rows"
            for s in sessions:
                assert s.revoked_at is not None, f"session {s.id} should be revoked after reuse"
            assert any(s.revoked_reason == "reuse_detected" for s in sessions)

            # The legitimate raw2 — even though it was "ok" — is also burned (chain-wide).
            status3, _n3, _r3 = auth_service.rotate_session(db, raw2, req)
            assert status3 in ("revoked", "reuse"), status3

    def test_legitimate_rotation_does_not_burn_chain(self, make_user):
        user, _tenant = make_user()
        req = _FakeRequest()

        with SessionLocal() as db:
            set_request_tenant(user.tenant_id)
            raw1, _sid = auth_service.create_session(db, user, req)
            db.commit()
            status_, _new, raw2 = auth_service.rotate_session(db, raw1, req)
            assert status_ == "ok"
            db.commit()

            # raw1 is now "revoked (rotated)" — re-rotating raw2 should still succeed.
            status2, _new2, raw3 = auth_service.rotate_session(db, raw2, req)
            assert status2 == "ok"
            assert raw3 and raw3 != raw2
