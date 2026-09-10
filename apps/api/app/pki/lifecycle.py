"""Certificate lifecycle: enrol → issue → renew → suspend → resume → revoke.

The RFP requires all six, and requires that **every signatory has their own certificate with
its own private key** — "shared or role-based certificates are not permitted". That rule is
enforced in two independent places, because it is the kind of constraint that quietly rots if
it only lives in one:

  1. `_assert_no_active_certificate()` here, at issuance time, with a clear error.
  2. A partial unique index over (tenant_id, subject_*) restricted to status='active'
     (migration 0016_pki) — so even a code path that forgot to call this module cannot
     create a second active certificate.

Suspension uses the RFC 5280 `certificateHold` reason, which is the only revocation reason
that is reversible: resuming publishes `removeFromCRL` in the next delta CRL. Everything else
is terminal, and `revoke()` refuses to un-revoke.
"""

from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import select

from .. import audit, models
from ..config import settings
from . import ca as ca_mod
from .keystore import KeySpec, get_keystore

#: RFC 5280 §5.3.1 reason codes we accept. `removeFromCRL` is not user-selectable — it is
#: emitted by `resume()` and only ever appears in a delta CRL.
REVOCATION_REASONS = (
    "unspecified",
    "key_compromise",
    "ca_compromise",
    "affiliation_changed",
    "superseded",
    "cessation_of_operation",
    "certificate_hold",
    "privilege_withdrawn",
    "aa_compromise",
)

TERMINAL_REASONS = tuple(r for r in REVOCATION_REASONS if r != "certificate_hold")


class PkiError(RuntimeError):
    """A lifecycle rule was violated. Routers map this to 409."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _subject_filter(stmt, *, user_id: str | None, party_id: str | None):
    if user_id:
        return stmt.where(models.Certificate.subject_user_id == user_id)
    if party_id:
        return stmt.where(models.Certificate.subject_party_id == party_id)
    raise PkiError("A certificate must be bound to a user or an external party.")


def active_certificate_for(db, tenant_id: str, *, user_id: str | None = None,
                           party_id: str | None = None) -> models.Certificate | None:
    stmt = select(models.Certificate).where(
        models.Certificate.tenant_id == tenant_id,
        models.Certificate.status == "active",
    )
    return db.scalar(_subject_filter(stmt, user_id=user_id, party_id=party_id))


def _assert_no_active_certificate(db, tenant_id: str, *, user_id, party_id) -> None:
    existing = active_certificate_for(db, tenant_id, user_id=user_id, party_id=party_id)
    if existing is not None:
        raise PkiError(
            f"Subject already holds active certificate {existing.serial_number}. "
            "Each signatory gets exactly one — renew or revoke the existing certificate instead."
        )


# --------------------------------------------------------------------------------------
# Issue
# --------------------------------------------------------------------------------------


def issue_from_request(db, request: models.CertificateRequest, *, actor: models.User | None = None,
                       now: dt.datetime | None = None) -> models.Certificate:
    """Issue the certificate an approved RA request authorises.

    Refuses anything that is not in `approved` state — the RA workflow is the only door to
    issuance, and this is the lock on it. Caller commits.
    """
    if request.status != "approved":
        raise PkiError(
            f"Certificate request is {request.status!r}; only an approved request can be issued. "
            "Route it through the Registration Authority first."
        )

    issuing = ca_mod.get_issuing_ca(db, request.tenant_id)
    if issuing is None:
        raise PkiError("No active issuing CA for this workspace — provision the PKI hierarchy first.")

    _assert_no_active_certificate(
        db, request.tenant_id,
        user_id=request.subject_user_id, party_id=request.subject_party_id,
    )

    now_aware = dt.datetime.now(dt.timezone.utc) if now is None else now
    validity_days = (
        settings.pki_visitor_validity_days if request.profile == "visitor"
        else settings.pki_leaf_validity_days
    )
    not_after = now_aware + dt.timedelta(days=validity_days)
    # Never outlive the issuer: a leaf valid past its CA's expiry is unverifiable.
    issuer_expiry = ca_mod._utc(issuing.not_after)
    if not_after > issuer_expiry:
        not_after = issuer_expiry

    store = get_keystore()
    spec = KeySpec(settings.pki_leaf_key_algorithm)
    key_id = f"{request.tenant_id}-{request.id}-{secrets.token_hex(4)}"
    store.generate_keypair(db, key_id, spec)

    subject = ca_mod.build_name(
        _common_name(request), email=request.subject_email,
        org_unit="Signatories" if request.profile != "ocsp" else "OCSP",
    )
    serial = ca_mod.new_serial()
    cert = ca_mod.build_leaf_certificate(
        subject=subject,
        subject_public_key=store.public_key(db, key_id),
        issuer_name=ca_mod.from_pem(issuing.pem).subject,
        issuer_signer=store.signer_for(db, issuing.key_id),
        issuer_spec=KeySpec(issuing.key_algorithm),
        issuer_ca_id=issuing.id,
        not_before=now_aware, not_after=not_after, serial=serial,
        email=request.subject_email,
    )

    row = models.Certificate(
        tenant_id=request.tenant_id, ca_id=issuing.id, request_id=request.id,
        subject_dn=subject.rfc4514_string(),
        subject_user_id=request.subject_user_id, subject_party_id=request.subject_party_id,
        subject_email=request.subject_email, profile=request.profile,
        serial_number=ca_mod.serial_hex(serial), key_id=key_id, key_algorithm=spec.name,
        pem=ca_mod.to_pem(cert),
        not_before=ca_mod._naive(now_aware), not_after=ca_mod._naive(not_after),
        status="active", issued_by=actor.id if actor else "",
    )
    db.add(row)
    request.status = "issued"
    db.flush()

    audit.record(
        db, tenant_id=request.tenant_id, action="pki.certificate.issued", actor=actor,
        object_type="certificate", object_id=row.id, object_label=row.serial_number,
        meta={
            "subject_dn": row.subject_dn, "profile": row.profile, "request_id": request.id,
            "ca_id": issuing.id, "not_after": row.not_after.isoformat(),
            "keystore": store.name, "algorithm": spec.name,
            # The evidence that bound this subject's identity, carried forward from the RA
            # request so the audit trail explains *why* the CA believed the subject.
            "identity_evidence": request.evidence or {},
        },
    )
    return row


def _common_name(request: models.CertificateRequest) -> str:
    if request.subject_dn:
        # An RA officer may have set an explicit DN; honour the CN inside it.
        for part in request.subject_dn.split(","):
            if part.strip().upper().startswith("CN="):
                return part.strip()[3:]
    return request.subject_email or request.id


# --------------------------------------------------------------------------------------
# Renew
# --------------------------------------------------------------------------------------


def renew(db, cert: models.Certificate, *, actor: models.User | None = None,
          now: dt.datetime | None = None) -> models.Certificate:
    """Issue a replacement certificate for the same subject, then supersede the old one.

    A renewal is a **new certificate with a new serial and a new key**, never a re-dated one.
    Re-dating would leave two certificates sharing a serial, which breaks CRL and OCSP lookup
    outright. The subject binding is preserved; `renewed_from_id` links the chain.

    The old certificate is revoked with reason `superseded`, which is what puts it on the CRL
    and keeps "one active certificate per signatory" true.
    """
    if cert.status not in ("active", "suspended", "expired"):
        raise PkiError(f"Cannot renew a {cert.status} certificate.")

    request = models.CertificateRequest(
        tenant_id=cert.tenant_id, subject_dn=cert.subject_dn,
        subject_user_id=cert.subject_user_id, subject_party_id=cert.subject_party_id,
        subject_email=cert.subject_email, profile=cert.profile,
        status="approved",  # renewal inherits the original request's approval
        evidence={"renewal_of": cert.serial_number, "original_request_id": cert.request_id},
        requested_by=actor.id if actor else "",
        reviewed_by=actor.id if actor else "", reviewed_at=_now(),
        review_note="Auto-approved: renewal of an existing, already-vetted binding.",
    )
    db.add(request)
    db.flush()

    # Free the uniqueness slot before issuing the replacement.
    _mark_revoked(cert, "superseded")
    db.flush()

    fresh = issue_from_request(db, request, actor=actor, now=now)
    fresh.renewed_from_id = cert.id
    db.flush()

    audit.record(
        db, tenant_id=cert.tenant_id, action="pki.certificate.renewed", actor=actor,
        object_type="certificate", object_id=fresh.id, object_label=fresh.serial_number,
        meta={
            "previous_serial": cert.serial_number, "previous_id": cert.id,
            "subject_dn": fresh.subject_dn,
            "note": "new serial and new key; subject binding preserved",
        },
    )
    return fresh


# --------------------------------------------------------------------------------------
# Suspend / resume / revoke
# --------------------------------------------------------------------------------------


def _mark_revoked(cert: models.Certificate, reason: str) -> None:
    cert.status = "suspended" if reason == "certificate_hold" else "revoked"
    cert.revocation_reason = reason
    cert.revoked_at = _now()


def suspend(db, cert: models.Certificate, *, actor: models.User | None = None,
            note: str = "") -> models.Certificate:
    """Put the certificate on hold. Reversible — this is RFC 5280 `certificateHold`.

    A suspended certificate must not be usable for signing; `assert_usable_for_signing()`
    below is what the signing path calls to enforce that.
    """
    if cert.status == "revoked":
        raise PkiError("Certificate is revoked; revocation is permanent and cannot be downgraded to a hold.")
    if cert.status == "suspended":
        return cert
    _mark_revoked(cert, "certificate_hold")
    audit.record(
        db, tenant_id=cert.tenant_id, action="pki.certificate.suspended", actor=actor,
        object_type="certificate", object_id=cert.id, object_label=cert.serial_number,
        meta={"reason": "certificate_hold", "note": note, "subject_dn": cert.subject_dn},
    )
    return cert


def resume(db, cert: models.Certificate, *, actor: models.User | None = None,
           note: str = "") -> models.Certificate:
    """Lift a hold. The serial is published with `removeFromCRL` in the next delta CRL."""
    if cert.status != "suspended":
        raise PkiError(f"Only a suspended certificate can be resumed (this one is {cert.status}).")
    if cert.not_after <= _now():
        raise PkiError("Certificate expired while suspended — renew it instead of resuming.")
    cert.status = "active"
    cert.revocation_reason = ""
    cert.revoked_at = None
    audit.record(
        db, tenant_id=cert.tenant_id, action="pki.certificate.resumed", actor=actor,
        object_type="certificate", object_id=cert.id, object_label=cert.serial_number,
        meta={"note": note, "subject_dn": cert.subject_dn, "crl_reason": "remove_from_crl"},
    )
    return cert


def revoke(db, cert: models.Certificate, *, reason: str = "unspecified",
           actor: models.User | None = None, note: str = "") -> models.Certificate:
    """Permanently revoke. Terminal — there is no un-revoke, by design."""
    if reason not in TERMINAL_REASONS:
        raise PkiError(
            f"Unknown revocation reason {reason!r}. Use one of: {', '.join(TERMINAL_REASONS)} "
            "(use suspend() for a reversible hold)."
        )
    if cert.status == "revoked":
        raise PkiError(f"Certificate is already revoked ({cert.revocation_reason}).")
    _mark_revoked(cert, reason)
    audit.record(
        db, tenant_id=cert.tenant_id, action="pki.certificate.revoked", actor=actor,
        object_type="certificate", object_id=cert.id, object_label=cert.serial_number,
        meta={"reason": reason, "note": note, "subject_dn": cert.subject_dn},
    )
    return cert


# --------------------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------------------


def assert_usable_for_signing(cert: models.Certificate, *, now: dt.datetime | None = None) -> None:
    """The gate the signing path calls before using a certificate (Phase 2).

    Kept here rather than in the signing service so that suspension, revocation and expiry
    are decided in exactly one place.
    """
    at = now or _now()
    if cert.status == "revoked":
        raise PkiError(f"Certificate {cert.serial_number} is revoked ({cert.revocation_reason}).")
    if cert.status == "suspended":
        raise PkiError(f"Certificate {cert.serial_number} is suspended and cannot be used to sign.")
    if cert.not_before > at:
        raise PkiError(f"Certificate {cert.serial_number} is not yet valid.")
    if cert.not_after <= at:
        raise PkiError(f"Certificate {cert.serial_number} expired on {cert.not_after:%Y-%m-%d}.")


def expire_sweep(db, tenant_id: str | None = None, *, now: dt.datetime | None = None) -> int:
    """Flip past-validity certificates to `expired`.

    Expiry is a fact about the clock, not an event, so nothing depends on this having run —
    `assert_usable_for_signing` checks dates directly. This exists so the register and the
    uniqueness index reflect reality, and so an expired certificate stops occupying its
    subject's one active slot.
    """
    at = now or _now()
    stmt = select(models.Certificate).where(
        models.Certificate.status.in_(("active", "suspended")),
        models.Certificate.not_after <= at,
    )
    if tenant_id:
        stmt = stmt.where(models.Certificate.tenant_id == tenant_id)
    rows = list(db.scalars(stmt).all())
    for c in rows:
        c.status = "expired"
        audit.record(
            db, tenant_id=c.tenant_id, action="pki.certificate.expired",
            object_type="certificate", object_id=c.id, object_label=c.serial_number,
            meta={"not_after": c.not_after.isoformat(), "subject_dn": c.subject_dn},
        )
    return len(rows)
