"""Registration Authority — identity vetting before any certificate exists.

The RFP requires an RA workflow tied to HR/identity, with issuance impossible without an
approved request. The flow:

    enrol ──▶ pending ──▶ approved ──▶ (issue) ──▶ issued
                  │
                  └────▶ rejected

Identity evidence differs by subject and is captured at enrolment, not at approval:

  internal signatory  claims carried from OIDC / SCIM / SAML — issuer, subject, email,
                      verified-email flag, groups. The IdP did the vetting; we record what
                      it asserted so an auditor can see it.
  external signatory  the OTP-verified binding from the visitor signing surface (Phase 2):
                      channel, masked identifier, timestamp, IP, user agent.

Two rules that are easy to state and easy to get wrong, so both are enforced here and tested:

  * **Separation of duties** — an RA officer may not approve their own enrolment request.
    Self-issuance defeats the entire point of having an RA.
  * **Dual control** (`RA_DUAL_CONTROL=true`) — two *different* officers must approve. The
    second approval is what moves the request to `approved`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from .. import audit, models
from ..config import settings
from .lifecycle import PkiError

#: Who may act as an RA officer. Deliberately narrow: certificate issuance is a
#: trust-anchor-level power, not general workspace administration.
RA_ROLES = ("owner", "admin")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def assert_ra_officer(user: models.User) -> None:
    if user.role not in RA_ROLES:
        raise PkiError(
            f"Role {user.role!r} cannot act as a Registration Authority officer "
            f"(requires one of: {', '.join(RA_ROLES)})."
        )


# --------------------------------------------------------------------------------------
# Enrolment
# --------------------------------------------------------------------------------------


def enrol(
    db,
    *,
    tenant_id: str,
    subject_email: str,
    common_name: str,
    subject_user_id: str | None = None,
    subject_party_id: str | None = None,
    profile: str = "internal",
    evidence: dict | None = None,
    requested_by: str = "",
    actor: models.User | None = None,
) -> models.CertificateRequest:
    """Raise an enrolment request. Caller commits.

    Rejects a duplicate open request for the same subject: two pending requests would race to
    issuance and the loser would trip the one-active-certificate rule with a confusing error.
    """
    if not (subject_user_id or subject_party_id):
        raise PkiError("An enrolment request must name a user or an external party as the subject.")

    open_request = db.scalar(
        select(models.CertificateRequest).where(
            models.CertificateRequest.tenant_id == tenant_id,
            models.CertificateRequest.status.in_(("pending", "approved")),
            (models.CertificateRequest.subject_user_id == subject_user_id)
            if subject_user_id
            else (models.CertificateRequest.subject_party_id == subject_party_id),
        )
    )
    if open_request is not None:
        raise PkiError(
            f"Subject already has an open enrolment request ({open_request.status}). "
            "Resolve it before raising another."
        )

    from . import ca as ca_mod

    subject_dn = ca_mod.build_name(common_name, email=subject_email, org_unit="Signatories")
    req = models.CertificateRequest(
        tenant_id=tenant_id,
        subject_dn=subject_dn.rfc4514_string(),
        subject_user_id=subject_user_id, subject_party_id=subject_party_id,
        subject_email=subject_email, profile=profile,
        status="pending", evidence=evidence or {},
        requested_by=requested_by or (actor.id if actor else ""),
    )
    db.add(req)
    db.flush()
    audit.record(
        db, tenant_id=tenant_id, action="pki.request.enrolled", actor=actor,
        object_type="certificate_request", object_id=req.id, object_label=req.subject_dn,
        meta={"profile": profile, "evidence": req.evidence, "subject_email": subject_email},
    )
    return req


def enrol_internal_user(db, user: models.User, *, actor: models.User | None = None,
                        claims: dict | None = None) -> models.CertificateRequest:
    """Enrol a workspace user, carrying whatever the IdP asserted about them.

    `claims` is the OIDC/SCIM/SAML payload (Phase 7 adds SAML). When it is absent the request
    records that the binding rests on local password auth — weaker evidence, and the RA
    officer should see that plainly rather than have it hidden.
    """
    evidence = {
        "source": "oidc_or_scim" if claims else "local_account",
        "user_id": user.id, "email": user.email, "name": user.name, "role": user.role,
        "claims": claims or {},
        "captured_at": _now().isoformat(),
    }
    if not claims:
        evidence["caveat"] = (
            "No federated identity claims — binding rests on a local account. "
            "The RA officer must vet this out of band."
        )
    return enrol(
        db, tenant_id=user.tenant_id, subject_email=user.email, common_name=user.name,
        subject_user_id=user.id, profile="internal", evidence=evidence, actor=actor,
    )


# --------------------------------------------------------------------------------------
# Review
# --------------------------------------------------------------------------------------


def approve(db, req: models.CertificateRequest, *, officer: models.User,
            note: str = "") -> models.CertificateRequest:
    """Record an RA approval. With dual control on, the second distinct officer promotes the
    request to `approved`; the first only records their approval."""
    assert_ra_officer(officer)
    if req.status != "pending":
        raise PkiError(f"Request is {req.status!r}; only a pending request can be approved.")

    # Separation of duties: an officer cannot approve their own enrolment.
    if req.subject_user_id and req.subject_user_id == officer.id:
        raise PkiError(
            "An RA officer cannot approve their own certificate request. "
            "Have another officer review it."
        )

    if not settings.ra_dual_control:
        req.reviewed_by, req.reviewed_at = officer.id, _now()
        req.review_note = note
        req.status = "approved"
        _audit_review(db, req, officer, "pki.request.approved", note, stage="single")
        return req

    # --- dual control ---
    if req.reviewed_by is None:
        req.reviewed_by, req.reviewed_at = officer.id, _now()
        req.review_note = note
        _audit_review(db, req, officer, "pki.request.approved_first", note, stage="first")
        return req

    if req.reviewed_by == officer.id:
        raise PkiError(
            "Dual control requires two different RA officers. "
            "You have already approved this request."
        )

    req.second_reviewed_by, req.second_reviewed_at = officer.id, _now()
    if note:
        req.review_note = f"{req.review_note}\n{note}".strip()
    req.status = "approved"
    _audit_review(db, req, officer, "pki.request.approved", note, stage="second")
    return req


def reject(db, req: models.CertificateRequest, *, officer: models.User,
           note: str = "") -> models.CertificateRequest:
    assert_ra_officer(officer)
    if req.status not in ("pending",):
        raise PkiError(f"Request is {req.status!r}; only a pending request can be rejected.")
    req.status = "rejected"
    req.reviewed_by, req.reviewed_at = officer.id, _now()
    req.review_note = note
    _audit_review(db, req, officer, "pki.request.rejected", note, stage="reject")
    return req


def _audit_review(db, req, officer, action: str, note: str, *, stage: str) -> None:
    audit.record(
        db, tenant_id=req.tenant_id, action=action, actor=officer,
        object_type="certificate_request", object_id=req.id, object_label=req.subject_dn,
        meta={
            "stage": stage, "note": note, "profile": req.profile,
            "dual_control": settings.ra_dual_control,
            "first_officer": req.reviewed_by, "second_officer": req.second_reviewed_by,
            "evidence": req.evidence or {},
        },
    )


def pending_queue(db, tenant_id: str, limit: int = 100) -> list[models.CertificateRequest]:
    return list(db.scalars(
        select(models.CertificateRequest)
        .where(
            models.CertificateRequest.tenant_id == tenant_id,
            models.CertificateRequest.status == "pending",
        )
        .order_by(models.CertificateRequest.created_at.asc())
        .limit(limit)
    ).all())
