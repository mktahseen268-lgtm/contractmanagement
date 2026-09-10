"""Public visitor eSigning endpoints — **unauthenticated by design**.

Everything under `/esign/{token}` is reachable without an account, because that is the entire
point: a merchant at a branch counter scans a QR code and signs. The controls that replace
authentication are, in order of how much they actually do:

  1. the invitation token itself (256-bit, hashed at rest, expiring, use-capped)
  2. OTP identity binding before anything irreversible happens
  3. per-invitation-per-IP session rate limiting
  4. a proof-of-work challenge on `start` (self-hosted; a CAPTCHA SaaS would be foreign egress)
  5. the global Redis rate limiter, and an edge WAF in front of all of it

Admin endpoints for minting invitations live under `/signatures/invitations` in the
authenticated `signatures` router — not here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .. import models, schemas, visitor_service
from ..config import settings
from ..database import get_db
from ..deps import client_ip

router = APIRouter(prefix="/esign", tags=["esign"])

# The public portal must not distinguish "never existed" from "expired" or "used up" — each
# distinction is a probe an attacker can make against a link they do not have.
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="This signing link is not valid. It may have expired or already been used.",
)


def _invitation(db: Session, token: str) -> models.SigningInvitation:
    if not settings.esign_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="External signing is not enabled on this deployment.",
        )
    invitation = visitor_service.invitation_by_token(db, token)
    if invitation is None:
        raise _NOT_FOUND
    return invitation


def _session(db: Session, invitation: models.SigningInvitation, session_id: str):
    session = visitor_service.session_by_id(db, invitation, session_id)
    if session is None:
        raise _NOT_FOUND
    return session


def _visitor_error(e: Exception) -> HTTPException:
    code = (status.HTTP_429_TOO_MANY_REQUESTS
            if isinstance(e, visitor_service.VisitorBlocked)
            else status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=str(e))


@router.get("/{token}", response_model=schemas.EsignLandingOut)
def landing(token: str, request: Request, db: Session = Depends(get_db)) -> schemas.EsignLandingOut:
    """What am I being asked to sign, and by whom. No identity required yet."""
    invitation = _invitation(db, token)
    contract = db.get(models.Contract, invitation.contract_id)
    tenant = db.get(models.Tenant, invitation.tenant_id)
    return schemas.EsignLandingOut(
        label=invitation.label,
        organisation=tenant.name if tenant else "",
        contract_title=contract.title if contract else "",
        contract_reference=contract.reference_no if contract else "",
        require_otp=invitation.require_otp,
        otp_channel=invitation.otp_channel,
        collect_cnic=invitation.collect_cnic,
        require_scroll=settings.esign_require_scroll,
        proof_of_work=visitor_service.pow_challenge(invitation.id, client_ip(request)),
    )


@router.post("/{token}/start", response_model=schemas.EsignStartOut,
             status_code=status.HTTP_201_CREATED)
def start(token: str, data: schemas.EsignStartIn, request: Request,
          db: Session = Depends(get_db)) -> schemas.EsignStartOut:
    """Record the identity claim and send a one-time code."""
    invitation = _invitation(db, token)
    ip = client_ip(request)

    if not visitor_service.verify_pow(invitation.id, ip, data.pow_challenge, data.pow_solution):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification challenge failed. Please reload the page and try again.",
        )

    try:
        session, masked = visitor_service.start_session(
            db, invitation,
            name=data.name, email=data.email, phone=data.phone, channel=data.channel,
            cnic=data.cnic, ip=ip, user_agent=request.headers.get("user-agent", ""),
            entry_point=data.entry_point, device_fingerprint=data.device_fingerprint,
        )
    except visitor_service.VisitorError as e:
        db.rollback()
        raise _visitor_error(e) from e
    db.commit()
    return schemas.EsignStartOut(
        session_id=session.id, masked_identifier=masked, channel=session.otp_channel,
        otp_required=invitation.require_otp,
        expires_in=settings.esign_otp_ttl_minutes * 60,
    )


@router.post("/{token}/resend", response_model=schemas.EsignStartOut)
def resend(token: str, data: schemas.EsignSessionIn, db: Session = Depends(get_db)) -> schemas.EsignStartOut:
    invitation = _invitation(db, token)
    session = _session(db, invitation, data.session_id)
    try:
        masked = visitor_service.resend_otp(db, invitation, session)
    except visitor_service.VisitorError as e:
        db.rollback()
        raise _visitor_error(e) from e
    db.commit()
    return schemas.EsignStartOut(
        session_id=session.id, masked_identifier=masked, channel=session.otp_channel,
        otp_required=True, expires_in=settings.esign_otp_ttl_minutes * 60,
    )


@router.post("/{token}/verify", response_model=schemas.EsignVerifyOut)
def verify(token: str, data: schemas.EsignVerifyIn, db: Session = Depends(get_db)) -> schemas.EsignVerifyOut:
    """Prove the identity, mint the visitor's certificate, and hand back a signing link."""
    invitation = _invitation(db, token)
    session = _session(db, invitation, data.session_id)
    try:
        visitor_service.verify_session(db, invitation, session, data.code)
        recipient, signing_token = visitor_service.attach_recipient(db, invitation, session)
    except visitor_service.VisitorError as e:
        db.commit()  # keep the attempt counter and the audit trail
        raise _visitor_error(e) from e
    db.commit()

    certificate = db.get(models.Certificate, session.certificate_id) if session.certificate_id else None
    return schemas.EsignVerifyOut(
        session_id=session.id,
        signing_token=signing_token,
        signing_url=f"{settings.frontend_url.rstrip('/')}/sign/{signing_token}",
        recipient_id=recipient.id,
        certificate_serial=certificate.serial_number if certificate else "",
        certificate_expires_at=certificate.not_after if certificate else None,
    )


@router.post("/{token}/consent", response_model=schemas.EsignConsentOut)
def consent(token: str, data: schemas.EsignConsentIn, db: Session = Depends(get_db)) -> schemas.EsignConsentOut:
    """Record that the document was actually read. Evidence, not telemetry — it is printed on
    the Certificate of Completion and is what gets challenged when a signature is disputed."""
    invitation = _invitation(db, token)
    session = _session(db, invitation, data.session_id)
    visitor_service.record_consent(
        db, session, pages_viewed=data.pages_viewed, total_pages=data.total_pages,
        scrolled_to_end=data.scrolled_to_end,
    )
    # Keep the recipient's evidence bundle in step, so the sealed Certificate reflects what
    # the visitor actually did rather than what they had done at verification time.
    if session.recipient_id:
        recipient = db.get(models.SignatureRecipient, session.recipient_id)
        if recipient is not None:
            recipient.identity_evidence = visitor_service.identity_evidence(session)
    db.commit()
    unlocked, reason = visitor_service.may_sign(session)
    return schemas.EsignConsentOut(may_sign=unlocked, reason=reason,
                                   pages_viewed=session.pages_viewed,
                                   total_pages=session.total_pages)


@router.get("/{token}/qr", include_in_schema=False)
def qr(token: str, db: Session = Depends(get_db)) -> Response:
    """The invitation as a QR code — for a branch handout or an on-screen display."""
    _invitation(db, token)
    svg = visitor_service.qr_svg(token)
    if not svg:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="QR generation is unavailable (the `segno` package is not installed).",
        )
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})
