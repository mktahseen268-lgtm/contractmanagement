import datetime as dt
import hashlib
import re
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


# A very small built-in blocklist of obviously bad passwords. The intent is to catch the
# "demo / sample / test" passwords that leak into staging — not to replace a real Have-I-Been-
# Pwned check (that's a future integration). Lowercase, no spaces.
_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "passw0rd", "qwerty", "qwerty123",
    "12345678", "123456789", "1234567890", "11111111", "iloveyou",
    "letmein", "welcome", "welcome1", "admin", "admin123", "administrator",
    "changeme", "default", "abc12345", "sunshine", "monkey123",
    "demo1234", "test1234", "trustno1", "dragon", "baseball",
    "football", "master", "shadow", "superman", "batman",
})

# Character classes for the "must contain N of 4" rule.
_RE_LOWER = re.compile(r"[a-z]")
_RE_UPPER = re.compile(r"[A-Z]")
_RE_DIGIT = re.compile(r"\d")
_RE_SYMBOL = re.compile(r"[^A-Za-z0-9]")


def validate_password_strength(password: str, *, email: str | None = None, name: str | None = None) -> list[str]:
    """Returns a list of human-readable failure reasons. Empty list = OK.

    Policy (see config: `password_min_length`, `password_require_classes`):
      - Length between `effective_password_min_length` and `password_max_length`.
      - Must contain >= N of {lowercase, uppercase, digit, symbol} (default N=3).
      - Must not be in the built-in common-password blocklist (case-insensitive).
      - Must not contain the user's email local-part or name as a substring (case-insensitive).
      - Must not be a trivial repeating or sequential string (e.g. "aaaaaaaa", "12345678").
    """
    errors: list[str] = []
    p = password or ""
    min_len = settings.effective_password_min_length
    max_len = settings.password_max_length

    if len(p) < min_len:
        errors.append(f"Password must be at least {min_len} characters.")
    if len(p) > max_len:
        errors.append(f"Password must be at most {max_len} characters.")

    classes = sum(bool(rx.search(p)) for rx in (_RE_LOWER, _RE_UPPER, _RE_DIGIT, _RE_SYMBOL))
    if classes < settings.password_require_classes:
        errors.append(
            f"Password must contain at least {settings.password_require_classes} of: "
            "lowercase letter, uppercase letter, digit, symbol."
        )

    low = p.lower()
    if low in _COMMON_PASSWORDS:
        errors.append("This password is too common — pick something unique.")

    if email:
        local = email.split("@", 1)[0].lower().strip()
        if local and len(local) >= 4 and local in low:
            errors.append("Password must not contain your email.")
    if name:
        n = (name or "").lower().strip()
        if n and len(n) >= 4 and n in low:
            errors.append("Password must not contain your name.")

    if p and _is_trivial(p):
        errors.append("Password is too simple (sequential or repeating characters).")

    return errors


def _is_trivial(p: str) -> bool:
    """Detects sequential ('12345678', 'abcdefgh') or single-repeating ('aaaaaaaa') strings."""
    if len(set(p)) <= 2:
        return True
    if len(p) >= 6:
        # ascending sequence (e.g. 12345678, abcdefgh)
        if all(ord(p[i + 1]) - ord(p[i]) == 1 for i in range(len(p) - 1)):
            return True
        # descending sequence
        if all(ord(p[i + 1]) - ord(p[i]) == -1 for i in range(len(p) - 1)):
            return True
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


# ---------- signing-portal access tokens ----------


def new_signing_token() -> tuple[str, str]:
    """Mint a fresh signing-link token for `/sign/{token}`. Returns (raw, sha256_hash).

    The raw value is what we embed in the email URL and never persist; only the hash is stored
    for lookup. We also persist the raw value encrypted at rest in `access_token_secret` so
    server-side reminders can decrypt it (see models.SignatureRecipient and 0013_hardening)."""
    raw = secrets.token_urlsafe(40)
    return raw, hash_token(raw)
