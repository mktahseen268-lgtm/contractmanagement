"""Session, MFA and lockout mechanics (Phase 10 — coverage on `auth_service`).

`test_lifecycle_and_refresh.py` already proves the headline property: presenting an
already-rotated refresh token burns the whole chain. This covers the rest of the module, where
the interesting failures are quieter — a recovery code that can be spent twice, an OTP whose
attempt counter does not bite, a lockout window that never rolls over.

Requirements: SEC-02, SEC-06.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app import auth_service as svc
from app import models, security
from app.config import settings


class _Request:
    """The two things `auth_service` reads off a request."""

    def __init__(self, ip="203.0.113.9", ua="pytest/1.0"):
        self.headers = {"user-agent": ua}
        self.client = type("C", (), {"host": ip})()


@pytest.fixture()
def req():
    return _Request()


@pytest.fixture()
def user(db, make_user):
    u, _tenant = make_user()
    return db.merge(u)


# ---------------------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------------------


def test_a_new_session_starts_its_own_chain(db, user, req):
    """The chain id is what reuse detection burns. A session that started someone else's chain
    would take their sessions down with it."""
    raw, sid = svc.create_session(db, user, req)
    session = db.get(models.Session, sid)

    assert session.chain_id == sid
    assert session.parent_id is None
    assert session.token_hash == security.hash_token(raw)
    assert session.token_hash != raw          # never the raw value


def test_rotation_links_to_the_parent_and_keeps_the_chain(db, user, req):
    raw, sid = svc.create_session(db, user, req)
    status, new, new_raw = svc.rotate_session(db, raw, req)

    assert status == "ok"
    assert new.parent_id == sid
    assert new.chain_id == sid                 # same chain, new link
    assert new_raw != raw
    assert db.get(models.Session, sid).revoked_reason == "rotated"


def test_an_unknown_token_is_invalid_not_an_error(db, req):
    """A forged or truncated cookie is an ordinary outcome, not an exception — it arrives on
    every scan of the internet."""
    assert svc.rotate_session(db, "not-a-real-token", req) == ("invalid", None, None)


def test_an_expired_session_is_marked_expired_not_reused(db, user, req):
    """The distinction matters: `expired` asks the user to sign in again, `reuse` burns every
    session they have. Conflating them would log people out of everything for sitting idle."""
    raw, sid = svc.create_session(db, user, req)
    db.get(models.Session, sid).expires_at = svc._now() - dt.timedelta(seconds=1)
    db.flush()

    status, _, _ = svc.rotate_session(db, raw, req)
    assert status == "expired"
    assert db.get(models.Session, sid).revoked_reason == "expired"


def test_a_deliberately_revoked_session_is_not_treated_as_theft(db, user, req):
    raw, sid = svc.create_session(db, user, req)
    svc.revoke_session_by_raw(db, raw, reason="logout")
    db.flush()

    assert svc.rotate_session(db, raw, req)[0] == "revoked"


def test_replaying_a_rotated_token_burns_the_whole_chain(db, user, req):
    """The one property this module exists for. A stolen refresh token is only useful once,
    and using it destroys the session it was stolen from — so the theft is loud."""
    raw, sid = svc.create_session(db, user, req)
    _, new, new_raw = svc.rotate_session(db, raw, req)
    db.flush()

    assert svc.rotate_session(db, raw, req)[0] == "reuse"
    db.flush()

    # Both links are gone, including the one the thief did not present.
    assert db.get(models.Session, new.id).revoked_reason == "reuse_detected"
    assert svc.rotate_session(db, new_raw, req)[0] == "revoked"


def test_revoking_by_id_reports_whether_anything_happened(db, user, req):
    _raw, sid = svc.create_session(db, user, req)

    assert svc.revoke_session_by_id(db, sid, "admin") is True
    assert svc.revoke_session_by_id(db, sid, "admin") is False      # already gone
    assert svc.revoke_session_by_id(db, "no-such-session") is False


def test_signing_out_everywhere_can_spare_the_current_device(db, user, req):
    """Otherwise "sign out my other devices" signs you out too, and the person is left
    wondering whether it worked."""
    _r1, s1 = svc.create_session(db, user, req)
    svc.create_session(db, user, req)
    svc.create_session(db, user, req)

    revoked = svc.revoke_all_user_sessions(db, user.id, "password_changed", except_session_id=s1)
    db.flush()

    assert revoked == 2
    assert [s.id for s in svc.active_sessions(db, user.id)] == [s1]


def test_active_sessions_exclude_revoked_and_expired(db, user, req):
    _r1, s1 = svc.create_session(db, user, req)
    _r2, s2 = svc.create_session(db, user, req)
    _r3, s3 = svc.create_session(db, user, req)

    svc.revoke_session_by_id(db, s2)
    db.get(models.Session, s3).expires_at = svc._now() - dt.timedelta(days=1)
    db.flush()

    assert {s.id for s in svc.active_sessions(db, user.id)} == {s1}


def test_revoking_a_chain_leaves_other_chains_alone(db, user, req):
    """Two devices are two chains. Reuse on one must not sign the person out of the other."""
    raw_a, sid_a = svc.create_session(db, user, req)
    _raw_b, sid_b = svc.create_session(db, user, req)
    svc.rotate_session(db, raw_a, req)
    db.flush()

    live_child = db.scalar(
        select(models.Session).where(models.Session.parent_id == sid_a))

    svc.rotate_session(db, raw_a, req)          # reuse on chain A
    db.flush()

    # The still-live link is burned and labelled with why.
    assert db.get(models.Session, live_child.id).revoked_reason == "reuse_detected"
    # The original keeps `rotated` — it was already revoked, and that label is the true one.
    assert db.get(models.Session, sid_a).revoked_reason == "rotated"
    # The other device is untouched: reuse on one chain is not a reason to sign somebody out
    # of a session that was never compromised.
    assert db.get(models.Session, sid_b).revoked_at is None


# ---------------------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------------------


def test_a_current_totp_code_verifies(db):
    import pyotp

    secret = svc.new_totp_secret()
    assert svc.verify_totp(secret, pyotp.TOTP(secret).now()) is True


def test_totp_tolerates_a_space_and_surrounding_whitespace(db):
    """People read the code off a phone and type it with a gap in the middle. Rejecting that
    is a support ticket, not a security control."""
    import pyotp

    secret = svc.new_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert svc.verify_totp(secret, f"  {code[:3]} {code[3:]}  ") is True


def test_totp_without_a_secret_is_false_not_an_exception(db):
    """Called on users who never enrolled. Raising here would turn "MFA not set up" into a 500."""
    assert svc.verify_totp(None, "123456") is False
    assert svc.verify_totp("", "123456") is False


def test_a_malformed_secret_does_not_raise(db):
    assert svc.verify_totp("not-valid-base32!!", "123456") is False


def test_the_provisioning_uri_names_the_account_and_issuer(db):
    uri = svc.totp_uri("JBSWY3DPEHPK3PXP", "person@bank.test", issuer="MMBL")
    assert uri.startswith("otpauth://totp/")
    assert "MMBL" in uri
    assert "person%40bank.test" in uri


# ---------------------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------------------


def test_recovery_codes_are_stored_hashed(db, user):
    codes = svc.regenerate_recovery_codes(db, user, count=4)
    stored = [r.code_hash for r in db.query(models.RecoveryCode).filter(
        models.RecoveryCode.user_id == user.id).all()]

    assert len(codes) == 4
    assert len(stored) == 4
    for code in codes:
        assert code not in stored


def test_a_recovery_code_works_exactly_once(db, user):
    """The whole point. A code that survives use is a permanent password written on paper."""
    codes = svc.regenerate_recovery_codes(db, user, count=3)

    assert svc.consume_recovery_code(db, user, codes[0]) is True
    db.flush()
    assert svc.consume_recovery_code(db, user, codes[0]) is False


def test_recovery_codes_are_normalised_before_matching(db, user):
    """They are printed with separators and read back by hand."""
    codes = svc.regenerate_recovery_codes(db, user, count=1)
    messy = f"  {codes[0].upper()}  "

    assert svc.consume_recovery_code(db, user, messy) is True


def test_regenerating_invalidates_the_previous_set(db, user):
    """Otherwise "regenerate my codes" leaves the old sheet working, which is the opposite of
    what somebody who thinks their codes leaked is asking for."""
    old = svc.regenerate_recovery_codes(db, user, count=3)
    db.flush()
    svc.regenerate_recovery_codes(db, user, count=3)
    db.flush()

    assert svc.consume_recovery_code(db, user, old[0]) is False


def test_another_users_recovery_code_does_not_work(db, user, make_user):
    codes = svc.regenerate_recovery_codes(db, user, count=2)
    db.commit()
    other, _ = make_user()

    assert svc.consume_recovery_code(db, db.merge(other), codes[0]) is False


# ---------------------------------------------------------------------------------------
# Email OTP
# ---------------------------------------------------------------------------------------


def test_an_issued_otp_verifies_once(db, user):
    code = svc.issue_otp(db, user)

    assert svc.verify_otp(db, user, code) is True
    db.flush()
    assert svc.verify_otp(db, user, code) is False      # spent


def test_issuing_a_new_otp_kills_the_previous_one(db, user):
    """A second "send me a code" must invalidate the first. Leaving both live doubles the
    guessing surface for the same window."""
    first = svc.issue_otp(db, user)
    db.flush()
    second = svc.issue_otp(db, user)
    db.flush()

    assert svc.verify_otp(db, user, first) is False
    assert svc.verify_otp(db, user, second) is True


def test_an_expired_otp_is_refused_and_spent(db, user):
    """Spent as well as refused — leaving it usable would make the expiry advisory."""
    code = svc.issue_otp(db, user)
    rec = db.query(models.OtpCode).filter(models.OtpCode.user_id == user.id).one()
    rec.expires_at = svc._now() - dt.timedelta(seconds=1)
    db.flush()

    assert svc.verify_otp(db, user, code) is False
    assert rec.used_at is not None


def test_too_many_wrong_guesses_burns_the_otp(db, user, monkeypatch):
    """A six-digit code with unlimited attempts is a six-digit code with no security."""
    monkeypatch.setattr(settings, "otp_max_attempts", 3)
    code = svc.issue_otp(db, user)

    for _ in range(3):
        assert svc.verify_otp(db, user, "000000") is False
    db.flush()

    # The counter has bitten: even the correct code no longer works.
    assert svc.verify_otp(db, user, code) is False


def test_an_otp_for_another_purpose_does_not_unlock_this_one(db, user):
    """A code emailed to confirm an email change must not satisfy a sign-in challenge."""
    login_code = svc.issue_otp(db, user, purpose="login_2fa")
    db.flush()

    assert svc.verify_otp(db, user, login_code, purpose="email_change") is False
    assert svc.verify_otp(db, user, login_code, purpose="login_2fa") is True


def test_verifying_with_no_outstanding_code_is_false(db, user):
    assert svc.verify_otp(db, user, "123456") is False


# ---------------------------------------------------------------------------------------
# Lockout
# ---------------------------------------------------------------------------------------


def test_repeated_failures_lock_the_account(db, user, req, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 3)
    monkeypatch.setattr(settings, "login_lockout_minutes", 15)

    for _ in range(2):
        locked, _until = svc.record_failed_login(
            db, user=user, email=user.email, reason="bad_password", request=req)
        assert locked is False

    locked, until = svc.record_failed_login(
        db, user=user, email=user.email, reason="bad_password", request=req)
    assert locked is True
    assert until is not None
    assert svc.is_locked_out(db, user)[0] is True


def test_a_failure_for_an_unknown_email_is_logged_without_a_lockout(db, req):
    """There is no account to lock. It still has to be recorded — an attacker enumerating
    addresses leaves no trace otherwise."""
    locked, until = svc.record_failed_login(
        db, user=None, email="nobody@nowhere.test", reason="unknown_user", request=req)
    db.flush()

    assert (locked, until) == (False, None)
    assert db.query(models.LoginAttempt).filter(
        models.LoginAttempt.email == "nobody@nowhere.test").count() == 1


def test_the_failure_window_rolls_over(db, user, req, monkeypatch):
    """Two failures on Monday and one on Friday is not a brute-force attempt. A counter that
    never resets locks out the ordinary forgetful user instead of the attacker."""
    monkeypatch.setattr(settings, "login_max_failures", 3)
    monkeypatch.setattr(settings, "login_failure_window_minutes", 15)

    svc.record_failed_login(db, user=user, email=user.email, reason="bad_password", request=req)
    svc.record_failed_login(db, user=user, email=user.email, reason="bad_password", request=req)
    state = svc._get_lockout(db, user)
    assert state.failure_count == 2

    state.last_failure_at = svc._now() - dt.timedelta(minutes=30)     # long ago
    db.flush()

    locked, _ = svc.record_failed_login(
        db, user=user, email=user.email, reason="bad_password", request=req)
    assert locked is False
    assert svc._get_lockout(db, user).failure_count == 1              # counted from scratch


def test_an_expired_lockout_clears_itself(db, user, req, monkeypatch):
    """Checked lazily rather than swept. A lockout that outlives its window because a beat did
    not run is an outage for the person it locked out."""
    monkeypatch.setattr(settings, "login_max_failures", 1)
    svc.record_failed_login(db, user=user, email=user.email, reason="bad_password", request=req)
    assert svc.is_locked_out(db, user)[0] is True

    svc._get_lockout(db, user).locked_until = svc._now() - dt.timedelta(seconds=1)
    db.flush()

    assert svc.is_locked_out(db, user) == (False, None)
    assert svc._get_lockout(db, user).failure_count == 0


def test_a_successful_login_resets_the_counter(db, user, req, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 5)
    svc.record_failed_login(db, user=user, email=user.email, reason="bad_password", request=req)
    svc.record_failed_login(db, user=user, email=user.email, reason="bad_password", request=req)

    svc.record_successful_login(db, user=user, request=req)
    db.flush()

    state = svc._get_lockout(db, user)
    assert state.failure_count == 0
    assert state.locked_until is None
    assert db.query(models.LoginAttempt).filter(
        models.LoginAttempt.user_id == user.id,
        models.LoginAttempt.success.is_(True)).count() == 1


def test_an_admin_can_release_a_lockout(db, user, req, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 1)
    svc.record_failed_login(db, user=user, email=user.email, reason="bad_password", request=req)
    assert svc.is_locked_out(db, user)[0] is True

    svc.admin_reset_lockout(db, user)
    db.flush()
    assert svc.is_locked_out(db, user) == (False, None)


def test_a_user_who_never_failed_is_not_locked_out(db, user):
    assert svc.is_locked_out(db, user) == (False, None)


def test_admin_reset_on_a_clean_account_is_a_no_op(db, user):
    svc.admin_reset_lockout(db, user)               # must not raise
    assert svc._get_lockout(db, user) is None


def test_reuse_detection_is_written_to_the_audit_log(client, db, make_user):
    """It was not, and that was the gap: a failed password attempt was recorded and an actual
    stolen session was not. Token reuse is the strongest theft signal the system has, so it
    goes into the chain and out to the SIEM at ALERT.
    """
    from app import security
    from app.config import settings

    # A real-looking domain on purpose: `EmailStr` rejects reserved TLDs like `.test`, so the
    # default fixture address cannot go through the HTTP layer.
    import uuid as _uuid

    user, tenant = make_user(email=f"reuse{_uuid.uuid4().hex[:8]}@mmbl-demo.co")
    password = "TestPass!" + "a1b2c3d4"
    with_password = db.merge(user)
    with_password.password_hash = security.hash_password(password)
    db.commit()

    login = client.post("/auth/login", json={"email": user.email, "password": password})
    assert login.status_code == 200, login.text
    stolen = client.cookies.get(settings.refresh_cookie_name)
    assert stolen

    assert client.post("/auth/refresh").status_code == 200          # legitimate rotation

    client.cookies.set(settings.refresh_cookie_name, stolen)        # the thief replays it
    replay = client.post("/auth/refresh")
    assert replay.status_code == 401
    assert "Suspicious activity" in replay.json()["detail"]

    actions = [a.action for a in db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == tenant.id).all()]
    assert "auth.session.reuse_detected" in actions


def test_reuse_is_escalated_for_the_siem():
    """A replayed refresh token means a credential is loose. Nothing about it is routine, so it
    must not be filed under ordinary authentication noise."""
    from app import siem

    category, severity = siem.classify("auth.session.reuse_detected")
    assert category == "security_incident"
    assert severity == siem.ALERT
