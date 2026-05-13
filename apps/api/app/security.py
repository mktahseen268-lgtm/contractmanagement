import datetime as dt
import hashlib
import secrets
from typing import Any

import bcrypt
import jwt

from .config import settings


# ---------- passwords ----------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------- JWTs (access token + the short MFA-pending token) ----------


def _create_token(claims: dict[str, Any], token_type: str, expires_delta: dt.timedelta) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {**claims, "type": token_type, "iat": int(now.timestamp()), "exp": int((now + expires_delta).timestamp())}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(sub: str, tenant_id: str, role: str, session_id: str) -> str:
    return _create_token(
        {"sub": sub, "tid": tenant_id, "role": role, "sid": session_id},
        "access",
        dt.timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_mfa_token(sub: str, tenant_id: str) -> str:
    """Identifies the user *between* the password step and the 2FA step. Cannot access anything."""
    return _create_token({"sub": sub, "tid": tenant_id}, "mfa_pending", dt.timedelta(minutes=settings.mfa_token_expire_minutes))


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


# ---------- opaque tokens / codes (refresh, recovery, OTP) ----------


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def new_recovery_code() -> str:
    # 10 hex chars formatted xxxxx-xxxxx (shown to the user once; stored hashed)
    h = secrets.token_hex(5)
    return f"{h[:5]}-{h[5:]}"


def new_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def normalize_code(code: str) -> str:
    return (code or "").strip().replace(" ", "").replace("-", "").lower()
