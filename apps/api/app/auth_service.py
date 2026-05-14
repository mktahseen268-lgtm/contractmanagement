"""Session (rotating refresh token) + MFA (TOTP / recovery codes) + email-OTP helpers +
per-account login lockout (RFI §A.7)."""

import datetime as dt
import uuid

import pyotp
from fastapi import Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession

from . import models, security
from .config import settings
from .deps import client_ip

# ---------- refresh-token sessions ----------


def _now() -> dt.datetime:
    # naive UTC — matches the bare `DateTime` columns (PG `timestamp`), so Python-side
    # comparisons like `expires_at < _now()` don't blow up on tz-awareness mismatch.
    # (Production should migrate all datetime columns to `timestamptz`; tracked in docs/15.)
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def create_session(db: DbSession, user: models.User, request: Request) -> tuple[str, str]:
    """Returns (raw_refresh_token, session_id)."""
    raw, h = security.new_refresh_token()
    sid = uuid.uuid4().hex
    db.add(
        models.Session(
            id=sid,
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=h,
            parent_id=None,
            chain_id=sid,
            user_agent=(request.headers.get("user-agent") or "")[:400],
            ip=client_ip(request),
            expires_at=_now() + dt.timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.flush()
    return raw, sid


def get_session_by_raw(db: DbSession, raw: str) -> models.Session | None:
    return db.scalar(select(models.Session).where(models.Session.token_hash == security.hash_token(raw)))


def rotate_session(db: DbSession, raw: str, request: Request) -> tuple[str, models.Session | None, str | None]:
    """Returns (status, new_session, new_raw). status in {ok, invalid, expired, revoked, reuse}."""
    s = get_session_by_raw(db, raw)
    if s is None:
        return "invalid", None, None
    if s.revoked_at is not None:
        if s.revoked_reason == "rotated":
            # an already-rotated token is being presented again -> token theft. Burn the whole chain.
            revoke_chain(db, s.tenant_id, s.chain_id, reason="reuse_detected")
            return "reuse", None, None
        return "revoked", None, None
    if s.expires_at < _now():
        s.revoked_at = _now()
        s.revoked_reason = "expired"
        return "expired", None, None
    # rotate
    new_raw, new_hash = security.new_refresh_token()
    new_id = uuid.uuid4().hex
    new = models.Session(
        id=new_id,
        tenant_id=s.tenant_id,
        user_id=s.user_id,
        token_hash=new_hash,
        parent_id=s.id,
        chain_id=s.chain_id,
        user_agent=(request.headers.get("user-agent") or "")[:400],
        ip=client_ip(request),
        expires_at=_now() + dt.timedelta(days=settings.refresh_token_expire_days),
        last_used_at=_now(),
    )
    s.revoked_at = _now()
    s.revoked_reason = "rotated"
    db.add(new)
    db.flush()
    return "ok", new, new_raw


def revoke_session_by_raw(db: DbSession, raw: str, reason: str = "logout") -> None:
    s = get_session_by_raw(db, raw)
    if s and s.revoked_at is None:
        s.revoked_at = _now()
        s.revoked_reason = reason


def revoke_session_by_id(db: DbSession, session_id: str, reason: str = "admin") -> bool:
    s = db.get(models.Session, session_id)
    if s and s.revoked_at is None:
        s.revoked_at = _now()
        s.revoked_reason = reason
        return True
    return False


def revoke_chain(db: DbSession, tenant_id: str, chain_id: str, reason: str) -> None:
    db.execute(
        update(models.Session)
        .where(models.Session.tenant_id == tenant_id, models.Session.chain_id == chain_id, models.Session.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason)
    )


def revoke_all_user_sessions(db: DbSession, user_id: str, reason: str, except_session_id: str | None = None) -> int:
    q = update(models.Session).where(models.Session.user_id == user_id, models.Session.revoked_at.is_(None))
    if except_session_id:
        q = q.where(models.Session.id != except_session_id)
    return db.execute(q.values(revoked_at=_now(), revoked_reason=reason)).rowcount or 0


def active_sessions(db: DbSession, user_id: str) -> list[models.Session]:
    return list(
        db.scalars(
            select(models.Session)
            .where(models.Session.user_id == user_id, models.Session.revoked_at.is_(None), models.Session.expires_at > _now())
            .order_by(models.Session.last_used_at.desc())
        ).all()
    )


def set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.refresh_cookie_name, path="/", httponly=True, samesite=settings.cookie_samesite)  # type: ignore[arg-type]


# ---------- MFA: TOTP ----------


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, account: str, issuer: str = "Contract Management") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    try:
        return pyotp.TOTP(secret).verify((code or "").strip().replace(" ", ""), valid_window=1)
    except Exception:  # noqa: BLE001
        return False


# ---------- MFA: recovery codes ----------


def regenerate_recovery_codes(db: DbSession, user: models.User, count: int = 8) -> list[str]:
    db.query(models.RecoveryCode).filter(models.RecoveryCode.user_id == user.id).delete()
    raw_codes: list[str] = []
    for _ in range(count):
        c = security.new_recovery_code()
        raw_codes.append(c)
        db.add(models.RecoveryCode(tenant_id=user.tenant_id, user_id=user.id, code_hash=security.hash_token(security.normalize_code(c))))
    db.flush()
    return raw_codes


def consume_recovery_code(db: DbSession, user: models.User, code: str) -> bool:
    h = security.hash_token(security.normalize_code(code))
    rc = db.scalar(
        select(models.RecoveryCode).where(
            models.RecoveryCode.user_id == user.id, models.RecoveryCode.code_hash == h, models.RecoveryCode.used_at.is_(None)
        )
    )
    if rc is None:
        return False
    rc.used_at = _now()
    return True


# ---------- email OTP ----------


def issue_otp(db: DbSession, user: models.User, purpose: str = "login_2fa") -> str:
    # invalidate any prior unused codes for this purpose
    db.execute(
        update(models.OtpCode)
        .where(models.OtpCode.user_id == user.id, models.OtpCode.purpose == purpose, models.OtpCode.used_at.is_(None))
        .values(used_at=_now())
    )
    code = security.new_otp_code()
    db.add(
        models.OtpCode(
            tenant_id=user.tenant_id,
            user_id=user.id,
            purpose=purpose,
            code_hash=security.hash_token(code),
            expires_at=_now() + dt.timedelta(minutes=settings.otp_expire_minutes),
        )
    )
    db.flush()
    return code


def verify_otp(db: DbSession, user: models.User, code: str, purpose: str = "login_2fa") -> bool:
    rec = db.scalar(
        select(models.OtpCode)
        .where(models.OtpCode.user_id == user.id, models.OtpCode.purpose == purpose, models.OtpCode.used_at.is_(None))
        .order_by(models.OtpCode.created_at.desc())
    )
    if rec is None:
        return False
    if rec.expires_at < _now():
        rec.used_at = _now()
        return False
    rec.attempts += 1
    if rec.attempts > settings.otp_max_attempts:
        rec.used_at = _now()
        return False
    if rec.code_hash == security.hash_token((code or "").strip().replace(" ", "")):
        rec.used_at = _now()
        return True
    return False


# ---------- login lockout (RFI §A.7) ----------


def _get_lockout(db: DbSession, user: models.User) -> models.LockoutState | None:
    return db.scalar(select(models.LockoutState).where(models.LockoutState.user_id == user.id))


def is_locked_out(db: DbSession, user: models.User) -> tuple[bool, dt.datetime | None]:
    """Returns (locked, until_naive_utc)."""
    state = _get_lockout(db, user)
    if state is None or state.locked_until is None:
        return False, None
    if state.locked_until <= _now():
        # lockout expired — clear it so the next failed attempt starts a fresh window
        state.failure_count = 0
        state.locked_until = None
        db.flush()
        return False, None
    return True, state.locked_until


def record_failed_login(db: DbSession, *, user: models.User | None, email: str, reason: str, request: Request) -> tuple[bool, dt.datetime | None]:
    """Log the failure + bump the lockout counter. Returns the new lockout state (locked,
    until). Caller commits."""
    now = _now()
    db.add(models.LoginAttempt(
        tenant_id=(user.tenant_id if user else ""),
        user_id=(user.id if user else None), email=(email or "").lower()[:255],
        success=False, reason=reason,
        ip=client_ip(request), user_agent=(request.headers.get("user-agent", "") or "")[:400], at=now,
    ))
    if user is None:
        return False, None
    state = _get_lockout(db, user)
    if state is None:
        state = models.LockoutState(tenant_id=user.tenant_id, user_id=user.id, failure_count=0, locked_until=None, last_failure_at=now)
        db.add(state)
        db.flush()
    # rolling window: if the last failure was older than the window, reset the counter
    window = dt.timedelta(minutes=settings.login_failure_window_minutes)
    if state.last_failure_at is None or (now - state.last_failure_at) > window:
        state.failure_count = 0
    state.failure_count = (state.failure_count or 0) + 1
    state.last_failure_at = now
    if state.failure_count >= settings.login_max_failures:
        state.locked_until = now + dt.timedelta(minutes=settings.login_lockout_minutes)
    db.flush()
    return (state.locked_until is not None and state.locked_until > now), state.locked_until


def record_successful_login(db: DbSession, *, user: models.User, request: Request) -> None:
    """Reset lockout state, log success. Caller commits."""
    now = _now()
    db.add(models.LoginAttempt(
        tenant_id=user.tenant_id, user_id=user.id, email=user.email.lower()[:255],
        success=True, reason="ok",
        ip=client_ip(request), user_agent=(request.headers.get("user-agent", "") or "")[:400], at=now,
    ))
    state = _get_lockout(db, user)
    if state is not None:
        state.failure_count = 0
        state.locked_until = None
        state.last_failure_at = None


def admin_reset_lockout(db: DbSession, user: models.User) -> None:
    """Admin-side reset (e.g. user locked out, can prove identity over support channel)."""
    state = _get_lockout(db, user)
    if state is not None:
        state.failure_count = 0
        state.locked_until = None
        state.last_failure_at = None
