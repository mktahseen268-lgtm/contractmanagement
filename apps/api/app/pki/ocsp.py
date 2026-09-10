"""RFC 6960 OCSP responder.

A relying party sends a DER-encoded OCSPRequest naming (issuer name hash, issuer key hash,
serial); we answer `good`, `revoked` or `unknown`, signed by the delegated responder
certificate provisioned in `ca.provision_hierarchy`.

Three details that separate a correct responder from one that merely returns bytes:

* **The response is signed by a delegated responder, not the CA key.** The CA key stays cold;
  the responder certificate carries `id-kp-OCSPSigning` and `OCSPNoCheck` (see `ca.py`).
* **The nonce is echoed.** RFC 6960 §4.4.1 — without it, an attacker can replay a stale
  `good` response for a certificate that has since been revoked. This is the single most
  commonly skipped requirement and it is a real attack, not a formality.
* **`unknown` means "not ours", not "not found".** A certificate this CA never issued gets
  `unknown`; one it issued and has no revocation record for gets `good`. Conflating them
  would let an attacker distinguish issued-from-unissued serials.

Performance: the RFP asks for p95 < 200 ms. The lookup is a single indexed query on
(tenant_id, serial_number); the signing operation dominates, which is why the responder key
is EC (P-256 by default) rather than RSA.
"""

from __future__ import annotations

import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp
from sqlalchemy import select

from .. import models
from . import ca as ca_mod
from .keystore import KeySpec, get_keystore

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
}

#: How long a relying party may cache the answer. Short, because the whole point of OCSP
#: over CRLs is freshness.
_VALIDITY_MINUTES = 15


class OcspError(RuntimeError):
    pass


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def _match_issuer(db, tenant_id: str | None, req: ocsp.OCSPRequest):
    """Find the CA whose name and key hashes match the request.

    `tenant_id=None` searches every tenant. That is not a shortcut — the OCSP URL is baked
    into each certificate's AIA extension at issuance and carries no tenant, so the responder
    has to identify the issuer from the request itself. Matching on the issuer name and key
    hashes is what makes that safe: a request can only ever resolve to the CA that actually
    signed the certificate, so one tenant's responder cannot answer for another's serial.
    """
    stmt = select(models.CertificateAuthority).where(
        models.CertificateAuthority.kind == "issuing",
    )
    if tenant_id is not None:
        stmt = stmt.where(models.CertificateAuthority.tenant_id == tenant_id)
    cas = list(db.scalars(stmt).all())
    for ca in cas:
        cert = ca_mod.from_pem(ca.pem)
        try:
            name_hash, key_hash = _issuer_hashes(cert, req.hash_algorithm)
        except Exception:  # noqa: BLE001 - unsupported hash in the request
            continue
        if name_hash == req.issuer_name_hash and key_hash == req.issuer_key_hash:
            return ca
    return None


def _issuer_hashes(issuer_cert: x509.Certificate, algorithm) -> tuple[bytes, bytes]:
    """(issuerNameHash, issuerKeyHash) as RFC 6960 §4.1.1 defines them.

    Both are easy to get subtly wrong. The name hash is over the DER of the issuer's *subject*
    name; the key hash is over the subjectPublicKey BIT STRING **contents** — not over the
    whole SubjectPublicKeyInfo, which is the usual mistake and yields a responder that never
    matches any request.
    """
    name_digest = hashes.Hash(algorithm)
    name_digest.update(issuer_cert.subject.public_bytes())

    key_digest = hashes.Hash(algorithm)
    key_digest.update(_spki_bit_string(issuer_cert.public_key()))

    return name_digest.finalize(), key_digest.finalize()


def _spki_bit_string(public_key) -> bytes:
    """The subjectPublicKey BIT STRING contents from a DER SubjectPublicKeyInfo.

    Minimal DER walk: SEQUENCE { AlgorithmIdentifier, BIT STRING }. Skip to the BIT STRING and
    drop its leading unused-bits octet.
    """
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def read_len(data: bytes, i: int) -> tuple[int, int]:
        first = data[i]
        if first < 0x80:
            return first, i + 1
        n = first & 0x7F
        return int.from_bytes(data[i + 1:i + 1 + n], "big"), i + 1 + n

    if der[0] != 0x30:
        raise OcspError("SubjectPublicKeyInfo is not a SEQUENCE")
    _, idx = read_len(der, 1)
    if der[idx] != 0x30:
        raise OcspError("AlgorithmIdentifier is not a SEQUENCE")
    alg_len, after_alg_len = read_len(der, idx + 1)
    idx = after_alg_len + alg_len
    if der[idx] != 0x03:
        raise OcspError("subjectPublicKey is not a BIT STRING")
    bit_len, after_bit_len = read_len(der, idx + 1)
    return der[after_bit_len + 1: after_bit_len + bit_len]


def build_response(db, tenant_id: str | None, der_request: bytes, *,
                   now: dt.datetime | None = None) -> bytes:
    """Handle one OCSP request and return the DER response.

    `tenant_id=None` lets the responder identify the issuing CA from the request's issuer
    hashes — which is what the public endpoint needs, since a certificate's AIA URL has no
    tenant in it.

    Malformed input yields a `malformed_request` response rather than an exception: this is a
    public, unauthenticated endpoint and a parse error must not become a 500.
    """
    now = _aware(now) or dt.datetime.now(dt.timezone.utc)

    try:
        req = ocsp.load_der_ocsp_request(der_request)
    except Exception:  # noqa: BLE001
        return _unsuccessful(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    issuing = _match_issuer(db, tenant_id, req)
    if issuing is None:
        # We are not the authority for this issuer. `unauthorized` is the honest answer.
        return _unsuccessful(ocsp.OCSPResponseStatus.UNAUTHORIZED)

    # The responder must belong to the CA we just matched, not to whoever asked.
    tenant_id = issuing.tenant_id
    responder = ca_mod.get_ocsp_responder(db, tenant_id)
    if responder is None:
        return _unsuccessful(ocsp.OCSPResponseStatus.INTERNAL_ERROR)

    cert = db.scalar(
        select(models.Certificate).where(
            models.Certificate.tenant_id == tenant_id,
            models.Certificate.ca_id == issuing.id,
            models.Certificate.serial_number == format(req.serial_number, "x"),
        )
    )

    issuer_cert = ca_mod.from_pem(issuing.pem)
    responder_cert = ca_mod.from_pem(responder.pem)

    if cert is None:
        status, revoked_at, reason = ocsp.OCSPCertStatus.UNKNOWN, None, None
    elif cert.status in ("revoked", "suspended"):
        status = ocsp.OCSPCertStatus.REVOKED
        revoked_at = _aware(cert.revoked_at) or now
        reason = _REASONS.get(cert.revocation_reason or "unspecified")
    else:
        status, revoked_at, reason = ocsp.OCSPCertStatus.GOOD, None, None

    builder = ocsp.OCSPResponseBuilder().add_response(
        cert=ca_mod.from_pem(cert.pem) if cert is not None else responder_cert,
        issuer=issuer_cert,
        algorithm=hashes.SHA256(),
        cert_status=status,
        this_update=now,
        next_update=now + dt.timedelta(minutes=_VALIDITY_MINUTES),
        revocation_time=revoked_at.replace(tzinfo=None) if revoked_at else None,
        revocation_reason=reason,
    ).responder_id(ocsp.OCSPResponderEncoding.HASH, responder_cert)

    # Echo the nonce. Without it the response is replayable.
    try:
        nonce = req.extensions.get_extension_for_class(x509.OCSPNonce)
        builder = builder.add_extension(nonce.value, critical=False)
    except x509.ExtensionNotFound:
        pass

    store = get_keystore()
    response = builder.sign(
        store.signer_for(db, responder.key_id),
        ca_mod._hash_for(KeySpec(responder.key_algorithm)),
    )
    return response.public_bytes(serialization.Encoding.DER)


def _unsuccessful(status) -> bytes:
    return ocsp.OCSPResponseBuilder.build_unsuccessful(status).public_bytes(serialization.Encoding.DER)


def build_request(cert: x509.Certificate, issuer: x509.Certificate, *, nonce: bytes | None = None) -> bytes:
    """Client-side helper — used by `validate.py` for third-party revocation checks and by the
    tests to drive the responder."""
    builder = ocsp.OCSPRequestBuilder().add_certificate(cert, issuer, hashes.SHA256())
    if nonce:
        builder = builder.add_extension(x509.OCSPNonce(nonce), critical=False)
    return builder.build().public_bytes(serialization.Encoding.DER)
