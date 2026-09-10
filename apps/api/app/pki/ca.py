"""CA hierarchy and the certificate-building primitives everything else is issued through.

    Offline Root CA  ──signs──▶  Online Issuing CA  ──signs──▶  end-entity certificates
                                                    └─signs──▶  OCSP responder certificate

The root is generated once, its certificate exported for cold storage, and its key then
destroyed from the online keystore (`take_root_offline`). After that the root can only sign
again if an operator restores it — which is the point of an offline root, and is why
cross-certification is designed in rather than bolted on later.

ECAC readiness (Electronic Transactions Ordinance 2002)
-------------------------------------------------------
The RFP asks that the issuing CA can later be re-chained to an accredited root **without
re-architecture and without reissuing existing certificates**. Three design choices make that
true, and all three are load-bearing:

1. The issuing CA's **key and subject DN are stable**. A certificate is verified against the
   issuer's *key*, so any certificate that key signed stays verifiable under a new chain.
2. `cross_certify()` issues a *second* CA certificate for the same key and DN, signed by a
   different parent. Both CA certificates coexist as rows; relying parties can build a path
   through either. Nothing already issued changes.
3. Trust anchors live in the `trust_anchors` table, not a file, so the ECAC root is added at
   runtime.

Everything here signs through `KeyStore.signer_for()`, so the same code path runs against a
software key in CI and an HSM-resident key in production.
"""

from __future__ import annotations

import datetime as dt
import secrets

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ..config import settings
from .keystore import KeySpec, KeyStore, get_keystore

# 20 octets of entropy, positive — RFC 5280 §4.1.2.2 requires a positive integer and CA/B
# Forum requires >= 64 bits of entropy. Serials must be unpredictable: a guessable serial
# lets an attacker probe OCSP for certificates that have not been issued yet.
_SERIAL_BITS = 159


def new_serial() -> int:
    return secrets.randbits(_SERIAL_BITS) | 1


def serial_hex(serial: int) -> str:
    return format(serial, "x")


def build_name(common_name: str, *, email: str = "", org_unit: str = "") -> x509.Name:
    parts = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, settings.pki_country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, settings.pki_org),
    ]
    if org_unit:
        parts.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, org_unit))
    parts.append(x509.NameAttribute(NameOID.COMMON_NAME, common_name))
    if email:
        parts.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    return x509.Name(parts)


def _hash_for(spec: KeySpec) -> hashes.HashAlgorithm:
    """SHA-384 for P-384 keys, SHA-256 otherwise. Matching the hash to the curve keeps the
    signature strength consistent instead of bottlenecking a P-384 key on SHA-256."""
    return hashes.SHA384() if spec.name in ("ec-p384", "ec-p521") else hashes.SHA256()


def _utc(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def _naive(value: dt.datetime) -> dt.datetime:
    """The DB columns are naive-UTC (the convention across this codebase)."""
    return _utc(value).astimezone(dt.timezone.utc).replace(tzinfo=None)


def crl_url(ca_id: str) -> str:
    return f"{settings.pki_public_base_url}/pki/crl/{ca_id}.crl"


def delta_crl_url(ca_id: str) -> str:
    return f"{settings.pki_public_base_url}/pki/crl/{ca_id}-delta.crl"


def ocsp_url() -> str:
    return f"{settings.pki_public_base_url}/pki/ocsp"


def aia_url(ca_id: str) -> str:
    return f"{settings.pki_public_base_url}/pki/ca/{ca_id}.cer"


# --------------------------------------------------------------------------------------
# Certificate construction
# --------------------------------------------------------------------------------------


def _revocation_extensions(builder: x509.CertificateBuilder, issuer_ca_id: str) -> x509.CertificateBuilder:
    """CRL Distribution Point + AIA (OCSP and CA issuers).

    Without these a relying party has no way to discover *how* to check revocation, which
    makes the whole CRL/OCSP apparatus unreachable. Every certificate we issue carries them.
    """
    builder = builder.add_extension(
        x509.CRLDistributionPoints([
            x509.DistributionPoint(
                full_name=[x509.UniformResourceIdentifier(crl_url(issuer_ca_id))],
                relative_name=None, reasons=None, crl_issuer=None,
            )
        ]),
        critical=False,
    )
    return builder.add_extension(
        x509.AuthorityInformationAccess([
            x509.AccessDescription(
                x509.oid.AuthorityInformationAccessOID.OCSP,
                x509.UniformResourceIdentifier(ocsp_url()),
            ),
            x509.AccessDescription(
                x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                x509.UniformResourceIdentifier(aia_url(issuer_ca_id)),
            ),
        ]),
        critical=False,
    )


def build_ca_certificate(
    *,
    subject: x509.Name,
    subject_public_key,
    issuer_name: x509.Name,
    issuer_signer,
    issuer_spec: KeySpec,
    not_before: dt.datetime,
    not_after: dt.datetime,
    serial: int,
    path_length: int | None,
    issuer_ca_id: str | None = None,
) -> x509.Certificate:
    """A CA certificate: BasicConstraints CA=true plus the CA-appropriate key usages.

    `path_length=0` on the issuing CA means it may sign end-entity certificates but cannot
    mint further CAs — a sub-CA compromise therefore cannot extend the hierarchy.
    """
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(subject_public_key)
        .serial_number(serial)
        .not_valid_before(_utc(not_before))
        .not_valid_after(_utc(not_after))
        .add_extension(x509.BasicConstraints(ca=True, path_length=path_length), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False,
                key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_public_key), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_signer.public_key()),
            critical=False,
        )
    )
    # A self-signed root has no issuer to point revocation checks at.
    if issuer_ca_id is not None:
        builder = _revocation_extensions(builder, issuer_ca_id)
    return builder.sign(issuer_signer, _hash_for(issuer_spec))


def build_leaf_certificate(
    *,
    subject: x509.Name,
    subject_public_key,
    issuer_name: x509.Name,
    issuer_signer,
    issuer_spec: KeySpec,
    issuer_ca_id: str,
    not_before: dt.datetime,
    not_after: dt.datetime,
    serial: int,
    email: str = "",
    ocsp_signer: bool = False,
) -> x509.Certificate:
    """An end-entity certificate.

    Signatory certificates carry `content_commitment` (non-repudiation) and the
    EMAIL_PROTECTION / CLIENT_AUTH EKUs. `key_cert_sign` is absent and BasicConstraints is
    CA=false — a signatory certificate can never be used to mint another certificate.

    `ocsp_signer=True` produces the responder's own certificate: `id-kp-OCSPSigning` EKU plus
    the `OCSPNoCheck` extension, which tells relying parties not to recurse into checking the
    responder's own revocation status (RFC 6960 §4.2.2.2.1).
    """
    eku = (
        [ExtendedKeyUsageOID.OCSP_SIGNING]
        if ocsp_signer
        else [ExtendedKeyUsageOID.EMAIL_PROTECTION, ExtendedKeyUsageOID.CLIENT_AUTH]
    )
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(subject_public_key)
        .serial_number(serial)
        .not_valid_before(_utc(not_before))
        .not_valid_after(_utc(not_after))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                # Non-repudiation. This is the bit that makes the certificate meaningful for
                # signing an agreement rather than merely authenticating a session.
                content_commitment=not ocsp_signer,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage(eku), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_public_key), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_signer.public_key()),
            critical=False,
        )
    )
    if email:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.RFC822Name(email)]), critical=False
        )
    if ocsp_signer:
        builder = builder.add_extension(x509.OCSPNoCheck(), critical=False)
    else:
        builder = _revocation_extensions(builder, issuer_ca_id)
    return builder.sign(issuer_signer, _hash_for(issuer_spec))


def to_pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def from_pem(pem: str) -> x509.Certificate:
    return x509.load_pem_x509_certificate(pem.encode("ascii"))


# --------------------------------------------------------------------------------------
# Hierarchy provisioning
# --------------------------------------------------------------------------------------


def _years(base: dt.datetime, n: int) -> dt.datetime:
    try:
        return base.replace(year=base.year + n)
    except ValueError:  # 29 Feb
        return base.replace(year=base.year + n, day=28)


def provision_hierarchy(db, tenant_id: str, *, actor_id: str = "", now: dt.datetime | None = None):
    """Create the root CA, the issuing CA under it, and the OCSP responder certificate.

    Idempotent: if an active issuing CA already exists for the tenant it is returned as-is.
    Caller commits. Returns (root, issuing).
    """
    from sqlalchemy import select

    from .. import audit, models

    existing = db.scalar(
        select(models.CertificateAuthority).where(
            models.CertificateAuthority.tenant_id == tenant_id,
            models.CertificateAuthority.kind == "issuing",
            models.CertificateAuthority.status == "active",
        )
    )
    if existing is not None:
        root = db.get(models.CertificateAuthority, existing.parent_ca_id) if existing.parent_ca_id else None
        return root, existing

    now = _utc(now or dt.datetime.now(dt.timezone.utc))
    store: KeyStore = get_keystore()

    # ---- root -------------------------------------------------------------------------
    root_spec = KeySpec(settings.pki_root_key_algorithm)
    root_id = f"{tenant_id}-root-{secrets.token_hex(6)}"
    store.generate_keypair(db, root_id, root_spec)
    root_signer = store.signer_for(db, root_id)
    root_name = build_name(settings.pki_root_cn, org_unit="Certificate Authority")
    root_serial = new_serial()
    root_cert = build_ca_certificate(
        subject=root_name, subject_public_key=store.public_key(db, root_id),
        issuer_name=root_name, issuer_signer=root_signer, issuer_spec=root_spec,
        not_before=now, not_after=_years(now, settings.pki_root_validity_years),
        serial=root_serial,
        path_length=1,  # root -> issuing -> leaf, and no deeper
    )
    root = models.CertificateAuthority(
        tenant_id=tenant_id, name=settings.pki_root_cn, kind="root",
        subject_dn=root_name.rfc4514_string(), issuer_dn=root_name.rfc4514_string(),
        parent_ca_id=None, key_id=root_id, key_algorithm=root_spec.name,
        serial_number=serial_hex(root_serial), pem=to_pem(root_cert),
        not_before=_naive(now), not_after=_naive(_years(now, settings.pki_root_validity_years)),
        created_by=actor_id,
    )
    db.add(root)
    db.flush()

    # ---- issuing ----------------------------------------------------------------------
    iss_spec = KeySpec(settings.pki_issuing_key_algorithm)
    iss_id = f"{tenant_id}-issuing-{secrets.token_hex(6)}"
    store.generate_keypair(db, iss_id, iss_spec)
    iss_name = build_name(settings.pki_issuing_cn, org_unit="Certificate Authority")
    iss_serial = new_serial()
    iss_cert = build_ca_certificate(
        subject=iss_name, subject_public_key=store.public_key(db, iss_id),
        issuer_name=root_name, issuer_signer=root_signer, issuer_spec=root_spec,
        not_before=now, not_after=_years(now, settings.pki_issuing_validity_years),
        serial=iss_serial,
        path_length=0,  # may sign leaves, may not create further CAs
        issuer_ca_id=root.id,
    )
    issuing = models.CertificateAuthority(
        tenant_id=tenant_id, name=settings.pki_issuing_cn, kind="issuing",
        subject_dn=iss_name.rfc4514_string(), issuer_dn=root_name.rfc4514_string(),
        parent_ca_id=root.id, key_id=iss_id, key_algorithm=iss_spec.name,
        serial_number=serial_hex(iss_serial), pem=to_pem(iss_cert),
        not_before=_naive(now), not_after=_naive(_years(now, settings.pki_issuing_validity_years)),
        created_by=actor_id,
    )
    db.add(issuing)
    db.flush()

    _provision_ocsp_responder(db, tenant_id, issuing, now=now, actor_id=actor_id)

    audit.record(
        db, tenant_id=tenant_id, action="pki.hierarchy.provisioned",
        object_type="certificate_authority", object_id=issuing.id, object_label=issuing.name,
        meta={
            "root_serial": root.serial_number, "issuing_serial": issuing.serial_number,
            "keystore": store.name, "root_algorithm": root_spec.name,
            "issuing_algorithm": iss_spec.name,
        },
    )
    return root, issuing


def _provision_ocsp_responder(db, tenant_id: str, issuing, *, now: dt.datetime, actor_id: str):
    """A dedicated OCSP signing certificate under the issuing CA.

    Signing OCSP responses with the CA key itself would mean exposing that key to a
    network-facing service. A delegated responder certificate keeps the CA key cold and is
    what RFC 6960 §4.2.2.2 expects.
    """
    from .. import models

    spec = KeySpec(settings.pki_leaf_key_algorithm)
    key_id = f"{tenant_id}-ocsp-{secrets.token_hex(6)}"
    store = get_keystore()
    store.generate_keypair(db, key_id, spec)
    name = build_name(f"{settings.pki_org} OCSP Responder", org_unit="OCSP")
    serial = new_serial()
    # Bounded by the issuing CA's own expiry — a responder certificate outliving its issuer
    # would be unverifiable.
    not_after = min(_years(now, 1), _utc(issuing.not_after))
    cert = build_leaf_certificate(
        subject=name, subject_public_key=store.public_key(db, key_id),
        issuer_name=from_pem(issuing.pem).subject,
        issuer_signer=store.signer_for(db, issuing.key_id),
        issuer_spec=KeySpec(issuing.key_algorithm), issuer_ca_id=issuing.id,
        not_before=now, not_after=not_after, serial=serial, ocsp_signer=True,
    )
    responder = models.CertificateAuthority(
        tenant_id=tenant_id, name="OCSP Responder", kind="ocsp",
        subject_dn=name.rfc4514_string(), issuer_dn=issuing.subject_dn,
        parent_ca_id=issuing.id, key_id=key_id, key_algorithm=spec.name,
        serial_number=serial_hex(serial), pem=to_pem(cert),
        not_before=_naive(now), not_after=_naive(not_after), created_by=actor_id,
    )
    db.add(responder)
    db.flush()
    return responder


def get_issuing_ca(db, tenant_id: str):
    from sqlalchemy import select

    from .. import models

    return db.scalar(
        select(models.CertificateAuthority).where(
            models.CertificateAuthority.tenant_id == tenant_id,
            models.CertificateAuthority.kind == "issuing",
            models.CertificateAuthority.status == "active",
        ).order_by(models.CertificateAuthority.created_at.desc())
    )


def get_ocsp_responder(db, tenant_id: str):
    from sqlalchemy import select

    from .. import models

    return db.scalar(
        select(models.CertificateAuthority).where(
            models.CertificateAuthority.tenant_id == tenant_id,
            models.CertificateAuthority.kind == "ocsp",
            models.CertificateAuthority.status == "active",
        ).order_by(models.CertificateAuthority.created_at.desc())
    )


def chain_pems(db, ca) -> list[str]:
    """The CA certificate followed by its ancestors, leaf-first — the order a relying party
    expects in a PKCS#7 or PAdES chain."""
    from .. import models

    out: list[str] = []
    seen: set[str] = set()
    node = ca
    while node is not None and node.id not in seen:
        seen.add(node.id)
        out.append(node.pem)
        node = db.get(models.CertificateAuthority, node.parent_ca_id) if node.parent_ca_id else None
    return out


# --------------------------------------------------------------------------------------
# ECAC readiness
# --------------------------------------------------------------------------------------


def take_root_offline(db, root, *, actor_id: str = "") -> str:
    """Export the root's key, destroy it from the online keystore, and mark the CA offline.

    Returns the PKCS#8 PEM **once**, for the operator to write to offline media during the
    key ceremony. It is never persisted after this call and never appears in an audit entry.
    Only meaningful for the software keystore: with an HSM the key was never online in the
    first place, so this only flips the flag.
    """
    from .. import audit, models
    from .keystore import SoftKeyStore

    store = get_keystore()
    exported = ""
    if isinstance(store, SoftKeyStore):
        row = db.get(models.PkiKey, root.key_id)
        exported = row.material if row is not None else ""
    store.destroy(db, root.key_id)
    root.is_offline = True
    audit.record(
        db, tenant_id=root.tenant_id, action="pki.root.offlined",
        object_type="certificate_authority", object_id=root.id, object_label=root.name,
        actor=None, meta={"keystore": store.name, "exported": bool(exported)},
    )
    return exported


def cross_certify(db, issuing, *, parent_pem: str, parent_key_id: str, parent_algorithm: str,
                  actor_id: str = "", now: dt.datetime | None = None):
    """Issue a second CA certificate for an existing issuing CA under a different parent.

    This is the ECAC path. The issuing CA keeps its key and its subject DN, so every
    certificate it has already signed continues to verify — the new CA certificate simply
    offers relying parties a second chain, up to the accredited root. Nothing is reissued and
    no signature already collected is invalidated.

    `parent_key_id` must resolve in this deployment's keystore, i.e. the accredited root has
    delegated a signing key here, or this is run during a ceremony where it is temporarily
    available.
    """
    from .. import audit, models

    now = _utc(now or dt.datetime.now(dt.timezone.utc))
    store = get_keystore()
    parent_cert = from_pem(parent_pem)
    parent_spec = KeySpec(parent_algorithm)
    issuing_cert = from_pem(issuing.pem)

    serial = new_serial()
    not_after = min(_utc(issuing.not_after), _utc(parent_cert.not_valid_after_utc))
    cross = build_ca_certificate(
        # Identical subject and public key — this is the same CA, re-anchored.
        subject=issuing_cert.subject,
        subject_public_key=store.public_key(db, issuing.key_id),
        issuer_name=parent_cert.subject,
        issuer_signer=store.signer_for(db, parent_key_id),
        issuer_spec=parent_spec,
        not_before=now, not_after=not_after, serial=serial, path_length=0,
    )
    row = models.CertificateAuthority(
        tenant_id=issuing.tenant_id, name=f"{issuing.name} (cross-certified)", kind="issuing",
        subject_dn=issuing.subject_dn, issuer_dn=parent_cert.subject.rfc4514_string(),
        parent_ca_id=None, key_id=issuing.key_id, key_algorithm=issuing.key_algorithm,
        serial_number=serial_hex(serial), pem=to_pem(cross),
        not_before=_naive(now), not_after=_naive(not_after), created_by=actor_id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db, tenant_id=issuing.tenant_id, action="pki.ca.cross_certified",
        object_type="certificate_authority", object_id=row.id, object_label=row.name,
        meta={
            "issuing_ca_id": issuing.id, "new_serial": row.serial_number,
            "new_issuer_dn": row.issuer_dn,
            "note": "same key and subject DN — previously issued certificates remain valid",
        },
    )
    return row
