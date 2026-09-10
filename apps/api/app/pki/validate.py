"""RFC 5280 path validation for certificates this CA did not issue.

The RFP requires that overseas signatories who cannot be issued an MMBL certificate can still
sign — with their own certificate from DigiCert, GlobalSign, Sectigo, Entrust or similar. That
means validating a chain we did not build, against a trust store we control.

What is checked, in order:

  1. **Chain construction** — walk issuer links from the leaf up to a configured trust anchor.
  2. **Signatures** — each certificate is verified against its issuer's public key. This is the
     step that actually matters; everything else is a policy check on top of it.
  3. **Validity windows** — every certificate in the path, not just the leaf.
  4. **Basic constraints** — every intermediate must be a CA, and `path_length` is enforced.
  5. **Key usage** — intermediates must carry `keyCertSign`; the leaf must be usable for
     signing (`digitalSignature` or `contentCommitment`).
  6. **Revocation** — OCSP first (fresher), CRL as fallback, per `PKI_REVOCATION_CHECK`.

`cryptography` ships `x509.verification` but it targets TLS server-auth semantics and does no
revocation checking, so it does not fit. This is a deliberate, narrow implementation of the
parts RFC 5280 requires for document-signing certificates — name constraints and certificate
policies are **not** implemented; see the caveat in `docs/PKI-ARCHITECTURE.md`.

Revocation responses are cached in-process, respecting `nextUpdate`, so a signing session does
not re-fetch a CRL for every signatory.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import urllib.request
from dataclasses import dataclass, field

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509 import ocsp as ocsp_mod
from cryptography.x509.oid import ExtensionOID
from sqlalchemy import select

from .. import models
from ..config import settings

log = logging.getLogger("uvicorn.error")

_HTTP_TIMEOUT = 5  # seconds — a slow CRL host must not stall a signing session


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    chain: list[str] = field(default_factory=list)   # subject DNs, leaf first
    revocation_checked: bool = False
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


# --------------------------------------------------------------------------------------
# Trust store
# --------------------------------------------------------------------------------------


def load_trust_anchors(db, tenant_id: str) -> list[x509.Certificate]:
    rows = db.scalars(
        select(models.TrustAnchor).where(
            models.TrustAnchor.tenant_id == tenant_id,
            models.TrustAnchor.is_active.is_(True),
        )
    ).all()
    anchors: list[x509.Certificate] = []
    for r in rows:
        try:
            anchors.append(x509.load_pem_x509_certificate(r.pem.encode("ascii")))
        except Exception:  # noqa: BLE001
            log.warning("trust anchor %s (%s) is not loadable — skipping", r.id, r.name)
    return anchors


def add_trust_anchor(db, tenant_id: str, pem: str, *, name: str = "", source: str = "external",
                     actor=None) -> models.TrustAnchor:
    """Add a root to the trust store. This is a trust decision — always audited."""
    from .. import audit

    cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    fp = cert.fingerprint(hashes.SHA256()).hex()

    existing = db.scalar(
        select(models.TrustAnchor).where(
            models.TrustAnchor.tenant_id == tenant_id,
            models.TrustAnchor.fingerprint_sha256 == fp,
        )
    )
    if existing is not None:
        existing.is_active = True
        return existing

    row = models.TrustAnchor(
        tenant_id=tenant_id, name=name or cert.subject.rfc4514_string(),
        subject_dn=cert.subject.rfc4514_string(), fingerprint_sha256=fp,
        pem=pem, source=source, added_by=actor.id if actor else "",
    )
    db.add(row)
    db.flush()
    audit.record(
        db, tenant_id=tenant_id, action="pki.trust_anchor.added", actor=actor,
        object_type="trust_anchor", object_id=row.id, object_label=row.name,
        meta={
            "subject_dn": row.subject_dn, "fingerprint_sha256": fp, "source": source,
            "not_after": cert.not_valid_after_utc.isoformat(),
        },
    )
    return row


# --------------------------------------------------------------------------------------
# Signature + chain
# --------------------------------------------------------------------------------------


def _verify_signature(cert: x509.Certificate, issuer_public_key) -> bool:
    try:
        if isinstance(issuer_public_key, ec.EllipticCurvePublicKey):
            issuer_public_key.verify(
                cert.signature, cert.tbs_certificate_bytes,
                ec.ECDSA(cert.signature_hash_algorithm),
            )
        elif isinstance(issuer_public_key, rsa.RSAPublicKey):
            issuer_public_key.verify(
                cert.signature, cert.tbs_certificate_bytes,
                padding.PKCS1v15(), cert.signature_hash_algorithm,
            )
        else:
            # Ed25519 and friends take no padding/hash arguments.
            issuer_public_key.verify(cert.signature, cert.tbs_certificate_bytes)
        return True
    except (InvalidSignature, Exception):  # noqa: BLE001
        return False


def _build_chain(leaf: x509.Certificate, intermediates: list[x509.Certificate],
                 anchors: list[x509.Certificate]) -> list[x509.Certificate] | None:
    """Leaf → … → anchor, or None if no path exists.

    Depth-limited to 8: a longer path is either a misconfiguration or an attempt to make
    validation expensive, and no legitimate document-signing chain is that deep.
    """
    pool = list(intermediates) + list(anchors)
    chain = [leaf]
    current = leaf
    for _ in range(8):
        if any(current.fingerprint(hashes.SHA256()) == a.fingerprint(hashes.SHA256()) for a in anchors):
            return chain
        issuer = next(
            (c for c in pool
             if c.subject == current.issuer and _verify_signature(current, c.public_key())),
            None,
        )
        if issuer is None:
            return None
        if issuer.fingerprint(hashes.SHA256()) == current.fingerprint(hashes.SHA256()):
            return None  # self-signed but not an anchor — loop
        chain.append(issuer)
        current = issuer
    return None


def validate(db, tenant_id: str, leaf_pem: str, *, intermediate_pems: list[str] | None = None,
             now: dt.datetime | None = None, check_revocation: bool | None = None) -> ValidationResult:
    """Validate a third-party certificate against the configured trust store."""
    at = now or dt.datetime.now(dt.timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt.timezone.utc)

    try:
        leaf = x509.load_pem_x509_certificate(leaf_pem.encode("ascii"))
    except Exception as e:  # noqa: BLE001
        return ValidationResult(False, f"Certificate could not be parsed: {e}")

    intermediates = []
    for pem in intermediate_pems or []:
        try:
            intermediates.append(x509.load_pem_x509_certificate(pem.encode("ascii")))
        except Exception:  # noqa: BLE001
            return ValidationResult(False, "An intermediate certificate could not be parsed.")

    anchors = load_trust_anchors(db, tenant_id)
    if not anchors:
        return ValidationResult(
            False,
            "No trust anchors configured. Add the issuing roots (DigiCert, GlobalSign, "
            "Sectigo, Entrust, …) before accepting third-party certificates.",
        )

    chain = _build_chain(leaf, intermediates, anchors)
    if chain is None:
        return ValidationResult(
            False,
            f"No trusted path from {leaf.subject.rfc4514_string()} to a configured trust anchor.",
        )

    warnings: list[str] = []

    # --- validity windows, across the whole path
    for cert in chain:
        if cert.not_valid_before_utc > at:
            return ValidationResult(False, f"{cert.subject.rfc4514_string()} is not yet valid.")
        if cert.not_valid_after_utc <= at:
            return ValidationResult(
                False,
                f"{cert.subject.rfc4514_string()} expired on {cert.not_valid_after_utc:%Y-%m-%d}.",
            )

    # --- basic constraints + key usage on the CAs
    for depth, cert in enumerate(chain[1:], start=0):
        try:
            bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value
        except x509.ExtensionNotFound:
            return ValidationResult(
                False, f"{cert.subject.rfc4514_string()} has no BasicConstraints — cannot act as a CA."
            )
        if not bc.ca:
            return ValidationResult(
                False, f"{cert.subject.rfc4514_string()} is not a CA but is used as an issuer."
            )
        if bc.path_length is not None and bc.path_length < depth:
            return ValidationResult(
                False,
                f"Path length constraint violated at {cert.subject.rfc4514_string()} "
                f"(allows {bc.path_length}, needs {depth}).",
            )
        try:
            ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
            if not ku.key_cert_sign:
                return ValidationResult(
                    False, f"{cert.subject.rfc4514_string()} lacks the keyCertSign key usage."
                )
        except x509.ExtensionNotFound:
            warnings.append(f"{cert.subject.rfc4514_string()} has no KeyUsage extension.")

    # --- the leaf must actually be usable for signing
    try:
        ku = leaf.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        if not (ku.digital_signature or ku.content_commitment):
            return ValidationResult(
                False,
                "Certificate carries neither digitalSignature nor contentCommitment — "
                "it cannot be used to sign a document.",
            )
        if not ku.content_commitment:
            warnings.append(
                "Certificate lacks contentCommitment (non-repudiation); it is a general "
                "signing certificate rather than a dedicated signature certificate."
            )
    except x509.ExtensionNotFound:
        warnings.append("Certificate has no KeyUsage extension.")

    # --- revocation
    do_check = (
        check_revocation
        if check_revocation is not None
        else settings.pki_revocation_check != "off"
    )
    checked = False
    if do_check:
        status, detail = check_revocation_status(leaf, chain[1])
        checked = status != "unavailable"
        if status == "revoked":
            return ValidationResult(False, f"Certificate is revoked: {detail}", warnings=warnings)
        if status == "unavailable":
            if settings.pki_revocation_check == "hard_fail":
                return ValidationResult(
                    False,
                    f"Revocation status could not be determined ({detail}) and "
                    "PKI_REVOCATION_CHECK=hard_fail.",
                    warnings=warnings,
                )
            warnings.append(f"Revocation status unavailable ({detail}); accepted under soft-fail.")

    return ValidationResult(
        True, "", chain=[c.subject.rfc4514_string() for c in chain],
        revocation_checked=checked, warnings=warnings,
    )


# --------------------------------------------------------------------------------------
# Revocation checking (OCSP, then CRL)
# --------------------------------------------------------------------------------------

_cache: dict[str, tuple[dt.datetime, str, str]] = {}   # key -> (expires_at, status, detail)
_cache_lock = threading.Lock()


def _cache_get(key: str) -> tuple[str, str] | None:
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        expires, status, detail = hit
        if expires <= dt.datetime.now(dt.timezone.utc):
            _cache.pop(key, None)
            return None
        return status, detail


def _cache_put(key: str, expires: dt.datetime, status: str, detail: str) -> None:
    with _cache_lock:
        _cache[key] = (expires, status, detail)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _urls(cert: x509.Certificate, oid) -> list[str]:
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return []
    return [
        d.access_location.value for d in aia
        if d.access_method == oid and isinstance(d.access_location, x509.UniformResourceIdentifier)
    ]


def _crl_urls(cert: x509.Certificate) -> list[str]:
    try:
        cdp = cert.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS).value
    except x509.ExtensionNotFound:
        return []
    out = []
    for point in cdp:
        for name in point.full_name or []:
            if isinstance(name, x509.UniformResourceIdentifier):
                out.append(name.value)
    return out


def check_revocation_status(cert: x509.Certificate, issuer: x509.Certificate) -> tuple[str, str]:
    """Returns (status, detail) where status is `good` | `revoked` | `unavailable`.

    OCSP is tried first because it is fresher and cheaper than downloading a CRL that may hold
    hundreds of thousands of entries.
    """
    key = f"{issuer.subject.rfc4514_string()}::{cert.serial_number:x}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    for url in _urls(cert, x509.oid.AuthorityInformationAccessOID.OCSP):
        result = _ocsp_check(url, cert, issuer)
        if result is not None:
            status, detail, expires = result
            _cache_put(key, expires, status, detail)
            return status, detail

    for url in _crl_urls(cert):
        result = _crl_check(url, cert, issuer)
        if result is not None:
            status, detail, expires = result
            _cache_put(key, expires, status, detail)
            return status, detail

    return "unavailable", "no reachable OCSP responder or CRL distribution point"


def _fetch(url: str, *, data: bytes | None = None, content_type: str = "") -> bytes | None:
    """HTTP(S) only. `file://` and other schemes are refused: a CDP/AIA URL comes from an
    untrusted certificate, and following arbitrary schemes there is an SSRF primitive."""
    if not url.lower().startswith(("http://", "https://")):
        log.warning("pki.validate: refusing non-HTTP revocation URL %r", url)
        return None
    try:
        req = urllib.request.Request(url, data=data)  # noqa: S310 - scheme checked above
        if content_type:
            req.add_header("Content-Type", content_type)
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310
            return resp.read()
    except Exception as e:  # noqa: BLE001
        log.info("pki.validate: fetch failed for %s: %s", url, e)
        return None


def _ocsp_check(url: str, cert: x509.Certificate, issuer: x509.Certificate):
    from .ocsp import build_request

    body = _fetch(url, data=build_request(cert, issuer), content_type="application/ocsp-request")
    if body is None:
        return None
    try:
        resp = ocsp_mod.load_der_ocsp_response(body)
        if resp.response_status != ocsp_mod.OCSPResponseStatus.SUCCESSFUL:
            return None
        expires = resp.next_update_utc or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5))
        if resp.certificate_status == ocsp_mod.OCSPCertStatus.REVOKED:
            reason = getattr(resp.revocation_reason, "value", "unspecified")
            return "revoked", f"OCSP says revoked ({reason}) at {resp.revocation_time_utc}", expires
        if resp.certificate_status == ocsp_mod.OCSPCertStatus.GOOD:
            return "good", f"OCSP good via {url}", expires
        return None  # UNKNOWN — fall through to the CRL
    except Exception as e:  # noqa: BLE001
        log.info("pki.validate: bad OCSP response from %s: %s", url, e)
        return None


def _crl_check(url: str, cert: x509.Certificate, issuer: x509.Certificate):
    body = _fetch(url)
    if body is None:
        return None
    try:
        try:
            crl = x509.load_der_x509_crl(body)
        except Exception:  # noqa: BLE001
            crl = x509.load_pem_x509_crl(body)
        # An unsigned-by-the-issuer CRL proves nothing.
        if not crl.is_signature_valid(issuer.public_key()):
            log.warning("pki.validate: CRL at %s is not signed by the expected issuer", url)
            return None
        expires = crl.next_update_utc or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1))
        entry = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
        if entry is not None:
            return "revoked", f"listed in the CRL at {url} (revoked {entry.revocation_date_utc})", expires
        return "good", f"absent from the CRL at {url}", expires
    except Exception as e:  # noqa: BLE001
        log.info("pki.validate: bad CRL from %s: %s", url, e)
        return None
