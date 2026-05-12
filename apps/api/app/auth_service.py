"""Session (rotating refresh token) + MFA (TOTP / recovery codes) + email-OTP helpers."""

import datetime as dt
import uuid

import pyotp
from fastapi import Request, Response
from sqlalchemy import select, update
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
