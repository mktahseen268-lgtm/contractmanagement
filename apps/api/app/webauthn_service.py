"""FIDO2 / WebAuthn — passkeys as a first-class MFA factor.

The one thing TOTP cannot do: **resist phishing**. A TOTP code can be read out over the phone
to somebody claiming to be IT, or typed into a convincing replica of the login page. A passkey
cannot, because the browser will only sign for the origin the credential was registered
against — the credential is bound to `cm.mmbl.test` and simply will not respond to
`cm-mmbl.test.evil`. That binding is the entire point, which is why the relying-party
configuration below is checked at registration *and* at every assertion.

**Verification is `py_webauthn`'s, deliberately.** Same reasoning as SAML: verifying an
attestation means parsing CBOR, decoding a COSE key, checking the authenticator data flags and
validating a signature over a specific concatenation. Getting any of that subtly wrong
produces an authenticator that appears to work and authenticates nothing.

What this module owns is the part around it — challenge storage, credential lifecycle, the
sign counter, and the rule that a user cannot delete their last factor and lock themselves out.
"""

from __future__ import annotations

import base64
import datetime as dt
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .audit import record
from .config import settings

#: How long a registration or authentication challenge stays valid. Short: a challenge is a
#: single-use nonce, and a long window is a replay window.
CHALLENGE_TTL = dt.timedelta(minutes=5)

#: In-process challenge store, keyed by user.
# ponytail: in-process, so a multi-replica deployment can land the finish request on a
# different worker than the begin. The fix is the Redis store the rate limiter already uses;
# documented in docs/RFI-COMPLIANCE.md rather than left to be discovered.
_challenges: dict[str, tuple[bytes, dt.datetime]] = {}


class WebAuthnError(ValueError):
    """Registration or authentication failed. Routers map to 400."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def is_enabled() -> bool:
    return bool(settings.webauthn_enabled and settings.webauthn_rp_id)


def _rp_id() -> str:
    return settings.webauthn_rp_id


def _origin() -> str:
    return settings.webauthn_origin or f"https://{settings.webauthn_rp_id}"


def _b64(raw: bytes) -> str:
    """URL-safe base64 without padding — what WebAuthn uses on the wire."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _remember_challenge(user_id: str, challenge: bytes) -> None:
    now = _now()
    for key, (_c, expires) in list(_challenges.items()):
        if expires < now:
            del _challenges[key]
    _challenges[user_id] = (challenge, now + CHALLENGE_TTL)


def _take_challenge(user_id: str) -> bytes:
    """Consume the pending challenge. Single-use: leaving it would allow a replay."""
    entry = _challenges.pop(user_id, None)
    if entry is None:
        raise WebAuthnError("No pending challenge — start again.")
    challenge, expires = entry
    if expires < _now():
        raise WebAuthnError("That challenge expired — start again.")
    return challenge


# ---------------------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------------------


def begin_registration(db: Session, user: models.User) -> dict:
    """Options for `navigator.credentials.create()`.

    Existing credentials are sent as `excludeCredentials` so an authenticator the user has
    already enrolled refuses to enrol twice — otherwise somebody ends up with three entries
    for one key and no idea which is which.
    """
    if not is_enabled():
        raise WebAuthnError("Passkeys are not configured.")

    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    existing = credentials_for(db, user)
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=settings.webauthn_rp_name or "Contract Management",
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.name or user.email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=_unb64(c.credential_id)) for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Discoverable credentials are preferred, not required: requiring them excludes
            # older security keys that a bank may already have deployed, and a factor nobody
            # can enrol is not a factor.
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _remember_challenge(user.id, options.challenge)
    import json

    return json.loads(options_to_json(options))


def finish_registration(db: Session, user: models.User, credential: dict, *,
                        label: str = "", ip: str = "") -> models.WebAuthnCredential:
    """Verify the attestation and store the credential."""
    if not is_enabled():
        raise WebAuthnError("Passkeys are not configured.")

    from webauthn import verify_registration_response

    challenge = _take_challenge(user.id)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_origin(),
            expected_rp_id=_rp_id(),
        )
    except Exception as e:  # noqa: BLE001 — the library raises a family of validation errors
        raise WebAuthnError(f"That passkey could not be registered: {e}") from e

    credential_id = _b64(verified.credential_id)
    if db.scalar(select(models.WebAuthnCredential).where(
            models.WebAuthnCredential.credential_id == credential_id)) is not None:
        raise WebAuthnError("That passkey is already registered.")

    row = models.WebAuthnCredential(
        tenant_id=user.tenant_id, user_id=user.id,
        credential_id=credential_id,
        public_key=_b64(verified.credential_public_key),
        sign_count=verified.sign_count,
        label=(label or "Security key")[:120],
        transports=",".join(credential.get("transports") or [])[:120],
        backed_up=bool(getattr(verified, "credential_backed_up", False)),
        aaguid=str(getattr(verified, "aaguid", "") or "")[:64],
    )
    db.add(row)
    db.flush()

    record(db, tenant_id=user.tenant_id, action="webauthn.registered", actor=user,
           object_type="user", object_id=user.id, object_label=user.email, ip=ip,
           meta={"label": row.label, "aaguid": row.aaguid, "backed_up": row.backed_up})
    return row


# ---------------------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------------------


def begin_authentication(db: Session, user: models.User) -> dict:
    """Options for `navigator.credentials.get()`."""
    if not is_enabled():
        raise WebAuthnError("Passkeys are not configured.")

    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    credentials = credentials_for(db, user)
    if not credentials:
        raise WebAuthnError("You have no passkeys registered.")

    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=_unb64(c.credential_id)) for c in credentials
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _remember_challenge(user.id, options.challenge)
    import json

    return json.loads(options_to_json(options))


def finish_authentication(db: Session, user: models.User, credential: dict, *,
                          ip: str = "") -> models.WebAuthnCredential:
    """Verify an assertion.

    The **sign counter** is checked and advanced. An authenticator that reports a counter no
    higher than the one we last saw has either been cloned or is replaying — both are reasons
    to refuse, and a system that ignores the counter throws away the one clone-detection
    signal WebAuthn provides. Authenticators that always report zero are exempt, because that
    is a legitimate and common choice.
    """
    if not is_enabled():
        raise WebAuthnError("Passkeys are not configured.")

    from webauthn import verify_authentication_response

    raw_id = credential.get("id") or credential.get("rawId") or ""
    row = db.scalar(select(models.WebAuthnCredential).where(
        models.WebAuthnCredential.credential_id == raw_id,
        models.WebAuthnCredential.user_id == user.id))
    if row is None:
        raise WebAuthnError("That passkey is not registered to you.")

    challenge = _take_challenge(user.id)
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_origin(),
            expected_rp_id=_rp_id(),
            credential_public_key=_unb64(row.public_key),
            # Zero deliberately: the library would reject a stale counter itself, but as an
            # indistinguishable "verification failed". A cloned authenticator and a mistyped
            # PIN would then look identical in the audit log, and the clone is the one worth
            # paging somebody about. The comparison is done below instead — the same
            # comparison, with an outcome that says what happened.
            credential_current_sign_count=0,
        )
    except Exception as e:  # noqa: BLE001
        record(db, tenant_id=user.tenant_id, action="webauthn.failed", actor=user,
               object_type="user", object_id=user.id, ip=ip, meta={"reason": str(e)[:200]})
        raise WebAuthnError("That passkey did not verify.") from e

    if row.sign_count and verified.new_sign_count <= row.sign_count:
        record(db, tenant_id=user.tenant_id, action="webauthn.counter_regression", actor=user,
               object_type="user", object_id=user.id, ip=ip,
               meta={"stored": row.sign_count, "presented": verified.new_sign_count,
                     "note": "possible cloned authenticator"})
        raise WebAuthnError("That passkey looks cloned and was refused.")

    row.sign_count = verified.new_sign_count
    row.last_used_at = _now()
    record(db, tenant_id=user.tenant_id, action="webauthn.authenticated", actor=user,
           object_type="user", object_id=user.id, object_label=user.email, ip=ip,
           meta={"label": row.label})
    return row


# ---------------------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------------------


def credentials_for(db: Session, user: models.User) -> list[models.WebAuthnCredential]:
    return list(db.scalars(select(models.WebAuthnCredential).where(
        models.WebAuthnCredential.user_id == user.id,
        models.WebAuthnCredential.tenant_id == user.tenant_id,
    ).order_by(models.WebAuthnCredential.created_at.asc())).all())


def remove(db: Session, user: models.User, credential_row_id: str, *,
           ip: str = "") -> None:
    """Delete a passkey.

    Refuses to remove the last remaining factor when the account has no password and no TOTP.
    An SSO- or passkey-only account that deletes its only credential is locked out with no
    recovery path, and the support ticket that follows is worse than the inconvenience of
    keeping one.
    """
    row = db.get(models.WebAuthnCredential, credential_row_id)
    if row is None or row.user_id != user.id or row.tenant_id != user.tenant_id:
        raise WebAuthnError("That passkey is not registered to you.")

    remaining = [c for c in credentials_for(db, user) if c.id != row.id]
    has_other_factor = bool(user.password_hash) or bool(getattr(user, "mfa_secret", None))
    if not remaining and not has_other_factor:
        raise WebAuthnError(
            "That is your only way to sign in. Add a password or another passkey first."
        )

    label = row.label
    db.delete(row)
    record(db, tenant_id=user.tenant_id, action="webauthn.removed", actor=user,
           object_type="user", object_id=user.id, object_label=user.email, ip=ip,
           meta={"label": label, "remaining": len(remaining)})


def rename(db: Session, user: models.User, credential_row_id: str, label: str) -> models.WebAuthnCredential:
    row = db.get(models.WebAuthnCredential, credential_row_id)
    if row is None or row.user_id != user.id or row.tenant_id != user.tenant_id:
        raise WebAuthnError("That passkey is not registered to you.")
    row.label = (label or "Security key")[:120]
    return row


def status(db: Session, user: models.User) -> dict:
    """What the settings screen needs."""
    credentials = credentials_for(db, user)
    return {
        "enabled": is_enabled(),
        "rp_id": _rp_id() if is_enabled() else "",
        "credentials": [{
            "id": c.id,
            "label": c.label,
            "transports": [t for t in (c.transports or "").split(",") if t],
            "backed_up": c.backed_up,
            "created_at": c.created_at,
            "last_used_at": c.last_used_at,
        } for c in credentials],
        "count": len(credentials),
        #: Whether this account could survive losing every passkey.
        "has_fallback": bool(user.password_hash) or bool(getattr(user, "mfa_secret", None)),
    }


def new_challenge_bytes() -> bytes:
    """Exposed for tests; the library generates its own in the normal path."""
    return secrets.token_bytes(32)
