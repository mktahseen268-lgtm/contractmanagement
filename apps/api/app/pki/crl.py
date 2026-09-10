"""Certificate Revocation Lists — full and delta, signed by the issuing CA.

A full CRL lists every unexpired revoked certificate. A delta CRL lists only what changed
since a named base CRL number, which is what makes frequent publication affordable: relying
parties fetch the full list daily and the delta hourly.

Delta CRLs are also the only way to publish a *resumption*. RFC 5280 §5.3.1 reason code 8
(`removeFromCRL`) says "this serial was on hold and no longer is", and it is meaningful only
in a delta. That is why `suspend`/`resume` are implemented as hold/remove rather than as an
application-level flag: a relying party checking the CRL sees the hold lift without having to
understand anything about this product.

CRL numbers are monotonic per CA and stored on the CA row. `base_crl_number` records which
full CRL the current deltas are relative to.
"""

from __future__ import annotations

import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from sqlalchemy import select

from .. import models
from ..config import settings
from . import ca as ca_mod
from .keystore import KeySpec, get_keystore

#: Our reason strings → the RFC 5280 enum `cryptography` expects.
_REASONS = {
    "unspecified": x509.ReasonFlags.unspecified,
    "key_compromise": x509.ReasonFlags.key_compromise,
    "ca_compromise": x509.ReasonFlags.ca_compromise,
    "affiliation_changed": x509.ReasonFlags.affiliation_changed,
    "superseded": x509.ReasonFlags.superseded,
    "cessation_of_operation": x509.ReasonFlags.cessation_of_operation,
    "certificate_hold": x509.ReasonFlags.certificate_hold,
    "privilege_withdrawn": x509.ReasonFlags.privilege_withdrawn,
    "aa_compromise": x509.ReasonFlags.aa_compromise,
    "remove_from_crl": x509.ReasonFlags.remove_from_crl,
}


def _revoked_entries(db, ca, *, since: dt.datetime | None = None) -> list[models.Certificate]:
    """Revoked or suspended certificates issued by this CA.

    Expired certificates are dropped: RFC 5280 §5 allows removing an entry once the
    certificate is past its own validity, and keeping them would make the CRL grow without
    bound over a ten-year retention window.
    """
    stmt = select(models.Certificate).where(
        models.Certificate.ca_id == ca.id,
        models.Certificate.tenant_id == ca.tenant_id,
        models.Certificate.status.in_(("revoked", "suspended")),
        models.Certificate.not_after > dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    )
    if since is not None:
        stmt = stmt.where(models.Certificate.revoked_at >= since)
    return list(db.scalars(stmt).all())


def _resumed_since(db, ca, since: dt.datetime) -> list[models.Certificate]:
    """Certificates that were on hold and are active again — published as `removeFromCRL`.

    We identify them by "active, but audited as resumed since the base CRL". The audit log is
    the source of truth here precisely because the certificate row no longer carries the hold.
    """
    resumed_ids = [
        row.object_id
        for row in db.scalars(
            select(models.AuditLog).where(
                models.AuditLog.tenant_id == ca.tenant_id,
                models.AuditLog.action == "pki.certificate.resumed",
                models.AuditLog.at >= since,
            )
        ).all()
        if row.object_id
    ]
    if not resumed_ids:
        return []
    return list(db.scalars(
        select(models.Certificate).where(
            models.Certificate.id.in_(resumed_ids),
            models.Certificate.ca_id == ca.id,
            models.Certificate.status == "active",
        )
    ).all())


def _build(db, ca, entries: list[tuple[int, dt.datetime, str]], *, now: dt.datetime,
           valid_hours: int, crl_number: int, delta_base: int | None) -> bytes:
    """Sign a CRL. `entries` is (serial, revocation_date, reason)."""
    store = get_keystore()
    issuer_cert = ca_mod.from_pem(ca.pem)
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(issuer_cert.subject)
        .last_update(now)
        .next_update(now + dt.timedelta(hours=valid_hours))
        .add_extension(x509.CRLNumber(crl_number), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_cert.public_key()),
            critical=False,
        )
    )
    if delta_base is not None:
        # Marks this as a delta and names the full CRL it applies to.
        builder = builder.add_extension(x509.DeltaCRLIndicator(delta_base), critical=True)

    for serial, revoked_at, reason in entries:
        revoked = (
            x509.RevokedCertificateBuilder()
            .serial_number(serial)
            .revocation_date(revoked_at)
        )
        flag = _REASONS.get(reason)
        if flag is not None and reason != "unspecified":
            revoked = revoked.add_extension(x509.CRLReason(flag), critical=False)
        builder = builder.add_revoked_certificate(revoked.build())

    crl = builder.sign(
        store.signer_for(db, ca.key_id),
        ca_mod._hash_for(KeySpec(ca.key_algorithm)),
    )
    return crl.public_bytes(serialization.Encoding.DER)


def _aware(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def generate_full_crl(db, ca, *, now: dt.datetime | None = None) -> bytes:
    """Build, sign and return a full CRL in DER. Bumps the CA's CRL number and resets the
    delta base to it. Caller commits."""
    now = _aware(now or dt.datetime.now(dt.timezone.utc))
    ca.crl_number = (ca.crl_number or 0) + 1
    ca.base_crl_number = ca.crl_number
    entries = [
        (int(c.serial_number, 16), _aware(c.revoked_at or c.created_at), c.revocation_reason or "unspecified")
        for c in _revoked_entries(db, ca)
    ]
    return _build(
        db, ca, entries, now=now, valid_hours=settings.crl_validity_hours,
        crl_number=ca.crl_number, delta_base=None,
    )


def generate_delta_crl(db, ca, *, now: dt.datetime | None = None) -> bytes:
    """Build a delta CRL covering changes since the current base.

    Includes resumptions as `removeFromCRL` — the one thing a full CRL structurally cannot
    express, since a full CRL says what *is* revoked, not what stopped being.
    """
    now = _aware(now or dt.datetime.now(dt.timezone.utc))
    base = ca.base_crl_number or 0
    if base == 0:
        # Nothing to be relative to. Publishing a delta against a base that was never issued
        # would be rejected by any correct client.
        raise ValueError("No base CRL has been issued for this CA — generate a full CRL first.")

    ca.crl_number = (ca.crl_number or 0) + 1
    since = _base_crl_time(db, ca)
    entries = [
        (int(c.serial_number, 16), _aware(c.revoked_at or c.created_at), c.revocation_reason or "unspecified")
        for c in _revoked_entries(db, ca, since=since)
    ]
    entries += [
        (int(c.serial_number, 16), now, "remove_from_crl")
        for c in _resumed_since(db, ca, since)
    ]
    return _build(
        db, ca, entries, now=now, valid_hours=settings.crl_delta_validity_hours,
        crl_number=ca.crl_number, delta_base=base,
    )


def _base_crl_time(db, ca) -> dt.datetime:
    """When the current base CRL was published, from the audit trail. Falls back to the CA's
    creation date, which over-includes rather than under-includes — a delta that repeats an
    entry is harmless; one that omits a revocation is not."""
    row = db.scalar(
        select(models.AuditLog)
        .where(
            models.AuditLog.tenant_id == ca.tenant_id,
            models.AuditLog.action == "pki.crl.published",
            models.AuditLog.object_id == ca.id,
        )
        .order_by(models.AuditLog.at.desc())
        .limit(1)
    )
    return _aware(row.at if row is not None else ca.created_at)


def publish(db, ca, *, delta: bool = False, actor=None, now: dt.datetime | None = None) -> bytes:
    """Generate a CRL and audit the publication. Caller commits."""
    from .. import audit

    der = generate_delta_crl(db, ca, now=now) if delta else generate_full_crl(db, ca, now=now)
    loaded = x509.load_der_x509_crl(der)
    audit.record(
        db, tenant_id=ca.tenant_id,
        action="pki.crl.published_delta" if delta else "pki.crl.published",
        actor=actor, object_type="certificate_authority", object_id=ca.id, object_label=ca.name,
        meta={
            "crl_number": ca.crl_number, "base_crl_number": ca.base_crl_number,
            "entries": len(list(loaded)), "delta": delta,
            "next_update": loaded.next_update_utc.isoformat(),
        },
    )
    return der


def fingerprint(der: bytes) -> str:
    digest = hashes.Hash(hashes.SHA256())
    digest.update(der)
    return digest.finalize().hex()
