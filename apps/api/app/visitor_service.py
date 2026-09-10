"""Visitor eSigning — external signatories who sign without ever having an account.

RFP §4a: merchants, customers and counterparties must be able to sign with **no per-visitor
user provisioning**, reached by web link, branch-tablet kiosk, mobile link or QR code, sized
for 100,000 external signatories a year.

The flow, and what each step is actually for:

    open      GET  /esign/{token}            what am I being asked to sign, and by whom
    start     POST /esign/{token}/start      identity CLAIM (name + email/phone) -> OTP sent
    verify    POST /esign/{token}/verify     identity PROOF -> certificate issued, link minted
    consent   POST /esign/{token}/consent    the document was actually read
    sign      POST /sign/{signing_token}     the existing portal takes over unchanged

The important property is that `start` collects a *claim* and `verify` turns it into *proof*.
Nothing irreversible happens in between: no certificate, no recipient row, no signature. A
bot that floods `start` produces abandoned sessions and nothing else.

On successful verification the visitor gets their own short-lived certificate (7 days by
default) through the normal RA path with a `visitor` policy profile — auto-approved, because
the OTP *is* the identity vetting for this profile and a human RA officer cannot be in the
loop for a walk-in at a branch counter. That is recorded explicitly in the request evidence so
an auditor sees exactly what the certificate rests on.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import secrets

from sqlalchemy import func, select

from . import audit, models, sms
from .config import settings
from .email import send_email

log = logging.getLogger("uvicorn.error")


class VisitorError(RuntimeError):
    """A rule in the visitor flow was violated. Routers map this to 400/409."""


class VisitorBlocked(VisitorError):
    """Too many failed attempts, or rate-limited. Mapped to 429."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------------------


def create_invitation(db, *, contract: models.Contract, actor: models.User, label: str = "",
                      otp_channel: str = "any", require_otp: bool = True,
                      collect_cnic: bool = False, max_signatures: int = 0,
                      ttl_days: int | None = None) -> tuple[models.SigningInvitation, str]:
    """Mint a public signing link. Returns (invitation, raw_token) — the raw token is shown
    once and embedded in the URL and QR code."""
    raw = secrets.token_urlsafe(32)
    ttl = ttl_days if ttl_days is not None else settings.esign_invitation_ttl_days
    invitation = models.SigningInvitation(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        label=label or contract.title,
        token_hash=_hash(raw), token_secret=raw,  # EncryptedString encrypts on flush
        otp_channel=otp_channel if otp_channel in ("email", "sms", "any") else "any",
        require_otp=require_otp, collect_cnic=collect_cnic,
        max_signatures=max(0, max_signatures),
        expires_at=_now() + dt.timedelta(days=max(1, ttl)),
        created_by=actor.id,
    )
    db.add(invitation)
    db.flush()
    audit.record(
        db, tenant_id=contract.tenant_id, action="esign.invitation_created", actor=actor,
        object_type="contract", object_id=contract.id,
        object_label=contract.reference_no or contract.title,
        meta={
            "invitation_id": invitation.id, "label": invitation.label,
            "otp_channel": invitation.otp_channel, "require_otp": require_otp,
            "max_signatures": invitation.max_signatures,
            "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        },
    )
    return invitation, raw


def invitation_by_token(db, raw_token: str) -> models.SigningInvitation | None:
    """Resolve a public link. Expired, revoked and exhausted links all return None — a visitor
    must not be able to distinguish "never existed" from "used up"."""
    if not raw_token:
        return None
    invitation = db.scalar(
        select(models.SigningInvitation).where(
            models.SigningInvitation.token_hash == _hash(raw_token)
        )
    )
    if invitation is None or not invitation.is_active:
        return None
    if invitation.expires_at and invitation.expires_at <= _now():
        return None
    if invitation.max_signatures and invitation.signature_count >= invitation.max_signatures:
        return None
    return invitation


def invitation_url(raw_token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/esign/{raw_token}"


def qr_svg(raw_token: str) -> str:
    """An inline SVG QR for the invitation URL — for the portal, a branch handout, or the
    print pack. Returns '' when the optional `segno` dependency is absent, so the rest of the
    flow keeps working without it."""
    try:
        import segno
    except ImportError:
        log.info("esign: segno not installed; QR generation skipped")
        return ""
    import io

    buf = io.StringIO()
    segno.make(invitation_url(raw_token), error="m").save(buf, kind="svg", scale=4, border=2)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------
# Anti-automation
# ---------------------------------------------------------------------------------------


def pow_challenge(invitation_id: str, ip: str) -> dict:
    """A proof-of-work challenge, issued with the invitation.

    Not a CAPTCHA: a CAPTCHA service is a foreign-hosted runtime dependency, which the
    residency control forbids. This costs a real client ~50 ms and costs a bulk automation run
    the same per attempt, which is what actually matters. An edge WAF CAPTCHA complements it;
    the Redis rate limiter and `esign_sessions_per_hour` are the other layers.
    """
    if settings.esign_pow_bits <= 0:
        return {"required": False, "challenge": "", "bits": 0}
    nonce = secrets.token_hex(8)
    issued = str(int(_now().timestamp()))
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"{invitation_id}:{ip}:{nonce}:{issued}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return {
        "required": True,
        "challenge": f"{nonce}.{issued}.{signature}",
        "bits": settings.esign_pow_bits,
    }


def verify_pow(invitation_id: str, ip: str, challenge: str, solution: str) -> bool:
    """Check that `sha256(challenge + solution)` starts with `bits` zero bits, and that the
    challenge is ours and recent."""
    if settings.esign_pow_bits <= 0:
        return True
    try:
        nonce, issued, signature = challenge.split(".")
    except ValueError:
        return False
    expected = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"{invitation_id}:{ip}:{nonce}:{issued}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    if not hmac.compare_digest(expected, signature):
        return False
    if abs(int(_now().timestamp()) - int(issued)) > 900:  # 15 minutes
        return False
    digest = hashlib.sha256(f"{challenge}{solution}".encode()).digest()
    bits = settings.esign_pow_bits
    whole, remainder = divmod(bits, 8)
    if any(digest[i] for i in range(whole)):
        return False
    return not (remainder and digest[whole] >> (8 - remainder))


def _rate_limit(db, invitation: models.SigningInvitation, ip: str) -> None:
    """Cap sessions per invitation per IP per hour. Cheap and effective against the naive
    flood; the Redis limiter in middleware handles the distributed case."""
    if not ip:
        return
    since = _now() - dt.timedelta(hours=1)
    recent = db.scalar(
        select(func.count()).select_from(models.VisitorSession).where(
            models.VisitorSession.invitation_id == invitation.id,
            models.VisitorSession.ip == ip,
            models.VisitorSession.created_at >= since,
        )
    ) or 0
    if recent >= settings.esign_sessions_per_hour:
        raise VisitorBlocked(
            "Too many signing attempts from this device in the last hour. "
            "Please try again later, or ask a branch officer for help."
        )


# ---------------------------------------------------------------------------------------
# Identity: claim, then proof
# ---------------------------------------------------------------------------------------


def start_session(db, invitation: models.SigningInvitation, *, name: str, email: str = "",
                  phone: str = "", channel: str = "", cnic: str = "", ip: str = "",
                  user_agent: str = "", entry_point: str = "web",
                  device_fingerprint: str = "") -> tuple[models.VisitorSession, str]:
    """Record the identity *claim* and send an OTP. Returns (session, masked_identifier).

    Nothing irreversible happens here — no certificate, no recipient, no signature.
    """
    _rate_limit(db, invitation, ip)

    name = (name or "").strip()[:200]
    if not name:
        raise VisitorError("Please enter your full name as it should appear on the agreement.")

    channel = channel or (invitation.otp_channel if invitation.otp_channel != "any" else "")
    email = (email or "").strip().lower()[:320]
    phone = sms.normalise_msisdn(phone) if phone else ""

    if not channel:
        channel = "sms" if phone else "email"
    if channel == "sms" and not phone:
        raise VisitorError("Enter a mobile number to receive the verification code by SMS.")
    if channel == "email" and not email:
        raise VisitorError("Enter an email address to receive the verification code.")
    if invitation.otp_channel != "any" and channel != invitation.otp_channel:
        raise VisitorError(f"This link requires verification by {invitation.otp_channel}.")

    session = models.VisitorSession(
        tenant_id=invitation.tenant_id, invitation_id=invitation.id,
        name=name, email=email, phone=phone,
        # Only the last four digits of a CNIC are kept: enough to reconcile against a branch
        # record, and not a copy of a national identity number sitting in a contract database.
        cnic_last4=("".join(ch for ch in cnic if ch.isdigit())[-4:] if cnic else ""),
        otp_channel=channel, ip=ip, user_agent=(user_agent or "")[:400],
        device_fingerprint=(device_fingerprint or "")[:64],
        entry_point=entry_point if entry_point in ("web", "kiosk", "mobile", "qr") else "web",
        party_ref=_party_ref(invitation.tenant_id, channel, email or phone),
        status="started",
    )
    db.add(session)
    db.flush()

    if not invitation.require_otp:
        session.verified_at = _now()
        session.status = "verified"
        return session, ""

    masked = _send_otp(db, invitation, session)
    return session, masked


def _party_ref(tenant_id: str, channel: str, identifier: str) -> str:
    """A stable, non-reversible id for this external signatory.

    Derived from the verified identifier so the same person returning next month resolves to
    the same party — which is what makes "one active certificate per signatory" hold for
    external parties too. Hashed rather than stored raw so the certificate register does not
    become a directory of customer phone numbers.
    """
    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"{tenant_id}:{channel}:{identifier.lower()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"v_{digest[:40]}"


def _send_otp(db, invitation: models.SigningInvitation, session: models.VisitorSession) -> str:
    if session.otp_sent_count >= settings.esign_otp_max_sends:
        raise VisitorBlocked("Too many codes requested. Please start again in a few minutes.")

    code = "".join(secrets.choice("0123456789") for _ in range(settings.esign_otp_length))
    session.otp_code_hash = _hash(code)
    session.otp_expires_at = _now() + dt.timedelta(minutes=settings.esign_otp_ttl_minutes)
    session.otp_sent_count += 1
    session.otp_attempts = 0
    session.status = "otp_sent"

    contract = db.get(models.Contract, invitation.contract_id)
    title = contract.title if contract else "an agreement"
    message = (
        f"{code} is your verification code to sign \"{title}\". "
        f"It expires in {settings.esign_otp_ttl_minutes} minutes. Do not share it."
    )

    if session.otp_channel == "sms":
        if not sms.send_sms(db, session.tenant_id, session.phone, message):
            # Never leave the visitor waiting for a code that is not coming.
            raise VisitorError(
                "We could not send the code to that number. Check it and try again, "
                "or use email instead."
            )
        masked = sms.mask_msisdn(session.phone)
    else:
        # `db=` so the outbox row joins THIS transaction — otherwise the code is
        # committed even if the session write is rolled back.
        send_email(session.email, f"Your code to sign {title}", message,
                   tenant_id=session.tenant_id, db=db)
        masked = sms.mask_email(session.email)

    audit.record(
        db, tenant_id=session.tenant_id, action="esign.otp_sent",
        object_type="visitor_session", object_id=session.id, object_label=session.name,
        ip=session.ip,
        meta={"channel": session.otp_channel, "masked": masked,
              "invitation_id": invitation.id, "attempt": session.otp_sent_count},
    )
    return masked


def resend_otp(db, invitation: models.SigningInvitation, session: models.VisitorSession) -> str:
    if session.verified_at is not None:
        raise VisitorError("This session is already verified.")
    return _send_otp(db, invitation, session)


def verify_session(db, invitation: models.SigningInvitation, session: models.VisitorSession,
                   code: str) -> models.VisitorSession:
    """Turn the identity claim into proof, then mint the certificate and the signing link."""
    if session.verified_at is not None:
        return session
    if session.status == "blocked":
        raise VisitorBlocked("This session is locked. Please start again.")
    if not session.otp_code_hash or not session.otp_expires_at:
        raise VisitorError("No verification code has been sent yet.")
    if session.otp_expires_at <= _now():
        raise VisitorError("That code has expired. Request a new one.")

    session.otp_attempts += 1
    if session.otp_attempts > settings.esign_otp_max_attempts:
        session.status = "blocked"
        audit.record(
            db, tenant_id=session.tenant_id, action="esign.otp_blocked",
            object_type="visitor_session", object_id=session.id, object_label=session.name,
            ip=session.ip, meta={"attempts": session.otp_attempts},
        )
        raise VisitorBlocked("Too many incorrect codes. Please start again.")

    if not hmac.compare_digest(session.otp_code_hash, _hash((code or "").strip())):
        raise VisitorError("That code is not correct. Check it and try again.")

    session.verified_at = _now()
    session.status = "verified"
    session.otp_code_hash = None  # single use

    masked = (sms.mask_msisdn(session.phone) if session.otp_channel == "sms"
              else sms.mask_email(session.email))
    audit.record(
        db, tenant_id=session.tenant_id, action="esign.identity_verified",
        object_type="visitor_session", object_id=session.id, object_label=session.name,
        ip=session.ip,
        meta={"channel": session.otp_channel, "masked": masked, "party_ref": session.party_ref,
              "entry_point": session.entry_point, "user_agent": session.user_agent[:200]},
    )
    return session


def identity_evidence(session: models.VisitorSession) -> dict:
    """The evidence bundle bound into the signature and printed on the Certificate of
    Completion. Masked identifiers only — this ends up in a document that gets emailed."""
    return {
        "method": f"{session.otp_channel}_otp",
        "channel": session.otp_channel,
        "masked_identifier": (
            sms.mask_msisdn(session.phone) if session.otp_channel == "sms"
            else sms.mask_email(session.email)
        ),
        "verified_at": session.verified_at.isoformat() if session.verified_at else None,
        "ip": session.ip,
        "user_agent": session.user_agent[:200],
        "device_fingerprint": session.device_fingerprint,
        "entry_point": session.entry_point,
        "cnic_last4": session.cnic_last4,
        "geo": session.geo or {},
        "scroll_completed_at": (
            session.scroll_completed_at.isoformat() if session.scroll_completed_at else None
        ),
        "pages_viewed": session.pages_viewed,
        "total_pages": session.total_pages,
    }


# ---------------------------------------------------------------------------------------
# Certificate + recipient
# ---------------------------------------------------------------------------------------


def issue_visitor_certificate(db, session: models.VisitorSession) -> models.Certificate | None:
    """Auto-enrol the verified visitor and issue a short-lived certificate.

    Auto-approved under the `visitor` policy profile: the OTP binding *is* the identity vetting
    for this profile, and a human RA officer cannot be in the loop for a walk-in at a branch
    counter. The request records that explicitly, so an auditor sees what the certificate
    rests on rather than having to infer it.

    Returns None when the PKI is not provisioned — the visitor can still sign, they just get
    the visual-evidence signature instead of a cryptographic one. Refusing to let a merchant
    sign because the CA is not set up would be the wrong failure mode.
    """
    from .pki import ca as ca_mod
    from .pki import lifecycle as pki_lifecycle
    from .pki import ra as pki_ra

    if session.verified_at is None:
        raise VisitorError("Identity must be verified before a certificate can be issued.")
    if ca_mod.get_issuing_ca(db, session.tenant_id) is None:
        log.warning("esign: no issuing CA for tenant %s — visitor signs without a certificate",
                    session.tenant_id)
        return None

    existing = pki_lifecycle.active_certificate_for(db, session.tenant_id,
                                                    party_id=session.party_ref)
    if existing is not None:
        session.certificate_id = existing.id
        return existing

    evidence = identity_evidence(session)
    evidence["auto_approved"] = True
    evidence["auto_approval_basis"] = (
        "OTP-verified identity binding under the `visitor` policy profile. No human RA "
        "review — this profile exists for walk-in external signatories."
    )
    try:
        request = pki_ra.enrol(
            db, tenant_id=session.tenant_id,
            subject_email=session.email or "",
            common_name=session.name,
            subject_party_id=session.party_ref,
            profile="visitor", evidence=evidence,
            requested_by=session.id,
        )
        request.status = "approved"
        request.reviewed_at = _now()
        request.review_note = "Auto-approved: OTP-verified visitor enrolment."
        db.flush()
        certificate = pki_lifecycle.issue_from_request(db, request)
    except Exception as e:  # noqa: BLE001
        log.exception("esign: visitor certificate issuance failed for session %s", session.id)
        audit.record(
            db, tenant_id=session.tenant_id, action="esign.certificate_failed",
            object_type="visitor_session", object_id=session.id, object_label=session.name,
            meta={"error": str(e)[:400], "party_ref": session.party_ref},
        )
        return None

    session.certificate_id = certificate.id
    return certificate


def attach_recipient(db, invitation: models.SigningInvitation,
                     session: models.VisitorSession) -> tuple[models.SignatureRecipient, str]:
    """Create this visitor's recipient row on the live envelope and mint their signing link.

    Returns (recipient, raw_signing_token). From here the existing `/sign/{token}` portal takes
    over unchanged — the visitor flow is an on-ramp to it, not a parallel implementation.
    """
    from . import signing_service

    if session.verified_at is None:
        raise VisitorError("Verify your identity before opening the document.")
    if session.recipient_id:
        recipient = db.get(models.SignatureRecipient, session.recipient_id)
        if recipient is not None:
            token = signing_service.decrypt_token_for(recipient)
            if token:
                return recipient, token

    envelope = signing_service.active_envelope(db, invitation.contract_id)
    if envelope is None:
        raise VisitorError(
            "This agreement is not currently out for signature. Please contact the sender."
        )

    max_sequence = db.scalar(
        select(func.max(models.SignatureRecipient.sequence)).where(
            models.SignatureRecipient.envelope_id == envelope.id
        )
    ) or 0
    certificate = issue_visitor_certificate(db, session)

    recipient = models.SignatureRecipient(
        tenant_id=session.tenant_id, envelope_id=envelope.id, sequence=max_sequence + 1,
        name=session.name, email=session.email or f"{session.party_ref}@visitor.local",
        kind="signer", status="sent",
        party_ref=session.party_ref,
        certificate_id=certificate.id if certificate is not None else None,
        identity_method=f"{session.otp_channel}_otp",
        identity_verified_at=session.verified_at,
        identity_evidence=identity_evidence(session),
        ip=session.ip, user_agent=session.user_agent,
    )
    db.add(recipient)
    db.flush()
    raw_token = signing_service._mint_token_for(recipient)
    session.recipient_id = recipient.id
    db.flush()

    audit.record(
        db, tenant_id=session.tenant_id, action="esign.recipient_attached",
        object_type="contract", object_id=invitation.contract_id, object_label=session.name,
        ip=session.ip,
        meta={
            "session_id": session.id, "recipient_id": recipient.id, "envelope_id": envelope.id,
            "party_ref": session.party_ref,
            "certificate_serial": certificate.serial_number if certificate else None,
            "identity": identity_evidence(session),
        },
    )
    return recipient, raw_token


def record_consent(db, session: models.VisitorSession, *, pages_viewed: int,
                   total_pages: int, scrolled_to_end: bool) -> models.VisitorSession:
    """Record that the document was actually read.

    This is evidence, not telemetry: "the signatory reached the end of the document before
    signing" is exactly what gets challenged when a signature is disputed, and it is printed
    on the Certificate of Completion.
    """
    session.opened_at = session.opened_at or _now()
    session.pages_viewed = max(session.pages_viewed or 0, max(0, pages_viewed))
    session.total_pages = max(session.total_pages or 0, max(0, total_pages))
    if scrolled_to_end and session.scroll_completed_at is None:
        session.scroll_completed_at = _now()
    return session


def may_sign(session: models.VisitorSession) -> tuple[bool, str]:
    """Whether the sign action should be unlocked, and why not if it should not."""
    if session.verified_at is None:
        return False, "Verify your identity first."
    if settings.esign_require_scroll and session.scroll_completed_at is None:
        return False, "Please read to the end of the document before signing."
    return True, ""


def mark_signed(db, invitation: models.SigningInvitation,
                session: models.VisitorSession) -> None:
    """Called once the signature lands, to count the invitation use."""
    session.status = "signed"
    invitation.signature_count = (invitation.signature_count or 0) + 1
    if invitation.max_signatures and invitation.signature_count >= invitation.max_signatures:
        invitation.is_active = False


def session_by_id(db, invitation: models.SigningInvitation, session_id: str):
    """Look up a session, scoped to its invitation — a session id from one link must never
    resolve against another."""
    session = db.get(models.VisitorSession, session_id or "")
    if session is None or session.invitation_id != invitation.id:
        return None
    return session


__all__ = [
    "VisitorBlocked", "VisitorError", "attach_recipient", "create_invitation",
    "identity_evidence", "invitation_by_token", "invitation_url", "issue_visitor_certificate",
    "may_sign", "mark_signed", "pow_challenge", "qr_svg", "record_consent", "resend_otp",
    "session_by_id", "start_session", "verify_pow", "verify_session",
]
