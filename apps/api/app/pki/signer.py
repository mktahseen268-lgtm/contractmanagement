"""Per-signatory PAdES signing — the bridge between the PKI and the executed PDF.

This is what makes the certificates issued in Phase 1 *mean* something. Before this module,
the optional PAdES provider sealed every executed document with one shared organisational
PKCS#12 file — the exact arrangement the RFP forbids ("shared or role-based certificates are
not permitted"). Now each signatory's own certificate and key produce their own signature, and
a document signed by three people carries three independently verifiable signatures.

How it fits together
--------------------
`_KeyStoreSigner` subclasses pyHanko's `Signer` and implements one method, `async_sign_raw`,
by delegating to `KeyStore.sign()`. That single indirection is what lets the same code path
sign with a software key in CI and an HSM-resident key in production — the private key is
never handed to the PDF layer in either case.

Why pyHanko is used here
------------------------
Embedding a signature in a PDF is a byte-range problem, not a cryptographic one: reserve a
/Contents placeholder, hash everything outside it, write the CMS blob back at exactly the right
offset, then repeat for each incremental update. pyHanko does that encoding. **The
cryptography, the certificates, the keys and the trust decisions are all ours** — pyHanko never
sees a private key, only the finished signature bytes that `_KeyStoreSigner` hands back. It is
a PDF-format library in the same sense that `reportlab` is a PDF-drawing library, and it is
listed in the SBOM. See docs/PKI-ARCHITECTURE.md §1.

PAdES-LTV
---------
A signature that is only valid while the signing certificate is valid is worth little on a
ten-year contract. Long-Term Validation embeds, *inside the document*:

  * the signer's certificate and the full chain up to the root;
  * revocation data proving the certificate was good at signing time — an OCSP response we
    generate in-process, plus the CRL;
  * an RFC 3161 timestamp from a TSA, when one is configured, proving *when* it was signed.

The revocation data is produced locally by our own responder rather than fetched over HTTP.
That is not a shortcut — it is strictly better here: no network dependency at signing time, no
foreign egress (which the residency control would block anyway), and the response is signed by
the same responder a relying party would have queried.
"""

from __future__ import annotations

import io
import logging

from ..config import settings
from . import ca as ca_mod
from .keystore import get_keystore

log = logging.getLogger("uvicorn.error")


class SigningUnavailable(RuntimeError):
    """pyHanko is not installed, or the signatory has no usable certificate."""


def _require_pyhanko():  # type: ignore[no-untyped-def]
    try:
        from pyhanko.sign import signers  # noqa: F401
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise SigningUnavailable(
            "Per-signatory PAdES signing needs pyHanko — pip install -r requirements-sign.txt"
        ) from e


def _digest_for(algorithm: str) -> str:
    """Match the digest to the key: SHA-384 for P-384, SHA-256 otherwise. Mirrors
    `ca._hash_for` so a certificate and its signatures use consistent strength."""
    return "sha384" if algorithm in ("ec-p384", "ec-p521") else "sha256"


def _build_signer(db, certificate, chain_pems: list[str]):  # type: ignore[no-untyped-def]
    """A pyHanko `Signer` that computes signatures inside our KeyStore."""
    _require_pyhanko()

    from asn1crypto import x509 as asn1_x509
    from pyhanko.sign.signers import ExternalSigner
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    store = get_keystore()
    key_id = certificate.key_id
    digest_algorithm = _digest_for(certificate.key_algorithm)

    def _asn1(pem: str):
        from cryptography.hazmat.primitives import serialization

        der = ca_mod.from_pem(pem).public_bytes(serialization.Encoding.DER)
        return asn1_x509.Certificate.load(der)

    registry = SimpleCertificateStore()
    registry.register_multiple([_asn1(p) for p in chain_pems])

    # `signing_cert` / `cert_registry` are read-only properties on the `Signer` ABC, so
    # `ExternalSigner` — which takes them as constructor arguments — is the supported
    # extension point. It normally returns a fixed signature value; we override
    # `async_sign_raw` so the value comes from the keystore instead.
    class _KeyStoreSigner(ExternalSigner):
        """The private key never leaves the keystore; pyHanko only ever sees the result."""

        async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run: bool = False) -> bytes:
            if dry_run:
                # pyHanko needs a length estimate to size the /Contents placeholder. ECDSA
                # DER signatures are variable-length, so sign dummy bytes rather than
                # guessing — an estimate that comes out short corrupts the write.
                return store.sign(db, key_id, b"\x00" * 32, hash_alg=digest_algorithm)
            return store.sign(db, key_id, data, hash_alg=digest_algorithm)

    signer = _KeyStoreSigner(
        signing_cert=_asn1(certificate.pem),
        cert_registry=registry,
        signature_value=None,
        prefer_pss=False,
        embed_roots=True,
    )
    return signer, digest_algorithm


def _revocation_material(db, certificate, issuing_ca):  # type: ignore[no-untyped-def]
    """(ocsp_responses, crls) for the signer's certificate, generated locally.

    Best-effort: LTV data missing is a weaker signature, not a failed one, so a problem here
    is logged and the signature still goes out with the chain embedded.
    """
    from asn1crypto import crl as asn1_crl
    from asn1crypto import ocsp as asn1_ocsp

    ocsps, crls = [], []
    try:
        from . import ocsp as ocsp_mod

        request = ocsp_mod.build_request(
            ca_mod.from_pem(certificate.pem), ca_mod.from_pem(issuing_ca.pem)
        )
        raw = ocsp_mod.build_response(db, certificate.tenant_id, request)
        ocsps.append(asn1_ocsp.OCSPResponse.load(raw))
    except Exception:  # noqa: BLE001
        log.warning("pades: could not embed an OCSP response for %s", certificate.serial_number)

    try:
        from . import crl as crl_mod

        crls.append(asn1_crl.CertificateList.load(crl_mod.generate_full_crl(db, issuing_ca)))
    except Exception:  # noqa: BLE001
        log.warning("pades: could not embed a CRL for CA %s", issuing_ca.id)

    return ocsps, crls


def sign_pdf_as(
    db,
    pdf_bytes: bytes,
    certificate,
    *,
    field_name: str,
    reason: str = "",
    location: str = "",
    signer_name: str = "",
    embed_ltv: bool = True,
) -> bytes:
    """Apply one signatory's PAdES signature to `pdf_bytes` and return the new document.

    Each call is an incremental update, so calling it once per signatory accumulates
    independently verifiable signatures rather than replacing the previous one.

    `field_name` must be unique per signature within a document — pyHanko refuses to reuse an
    already-signed field, which is the behaviour we want (it stops a second signature silently
    overwriting the first).
    """
    _require_pyhanko()

    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.fields import SigSeedSubFilter
    from pyhanko.sign.timestamps import HTTPTimeStamper

    issuing_ca = ca_mod.get_issuing_ca(db, certificate.tenant_id)
    if issuing_ca is None:
        raise SigningUnavailable("No active issuing CA — cannot build a signing chain.")

    chain = ca_mod.chain_pems(db, issuing_ca)
    signer, digest_algorithm = _build_signer(db, certificate, chain)

    timestamper = HTTPTimeStamper(settings.signing_tsa_url) if settings.signing_tsa_url else None

    meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        md_algorithm=digest_algorithm,
        reason=reason or settings.signing_reason,
        location=location or settings.pki_org,
        name=signer_name or certificate.subject_dn,
        # We embed validation info ourselves below, from our own CA, rather than letting
        # pyHanko fetch it over the network — see the module docstring.
        embed_validation_info=False,
        subfilter=SigSeedSubFilter.PADES,
    )

    pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper)
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    out = io.BytesIO()
    # pyHanko's sync entry point runs its own loop; call it directly unless we are already
    # inside one (we are not — sealing happens in a Celery task).
    pdf_signer.sign_pdf(writer, output=out)
    signed = out.getvalue()

    if embed_ltv:
        signed = _embed_ltv(db, signed, certificate, issuing_ca, chain)
    return signed


def _embed_ltv(db, pdf_bytes: bytes, certificate, issuing_ca, chain_pems: list[str]) -> bytes:
    """Add the chain plus locally-generated revocation data to the Document Security Store."""
    try:
        from asn1crypto import x509 as asn1_x509
        from cryptography.hazmat.primitives import serialization
        from pyhanko.sign.validation import DocumentSecurityStore

        ocsps, crls = _revocation_material(db, certificate, issuing_ca)
        certs = [
            asn1_x509.Certificate.load(
                ca_mod.from_pem(pem).public_bytes(serialization.Encoding.DER)
            )
            for pem in [certificate.pem, *chain_pems]
        ]
        # `add_dss` builds its own incremental writer over this stream and writes the DSS
        # back into it in place — so it takes the PDF bytes, not a writer.
        stream = io.BytesIO(pdf_bytes)
        DocumentSecurityStore.add_dss(
            output_stream=stream,
            sig_contents=None,
            certs=certs,
            ocsps=ocsps or None,
            crls=crls or None,
            force_write=True,
        )
        return stream.getvalue()
    except Exception:  # noqa: BLE001
        # A signature without LTV is still a valid signature — it just stops being verifiable
        # once the certificate expires. Never fail the execution over it.
        log.exception("pades: could not embed LTV data; signature stands without it")
        return pdf_bytes


def verify(pdf_bytes: bytes, *, trust_roots_pem: list[str] | None = None) -> list[dict]:
    """Parse and check every signature in a PDF. Used by the tests and the admin UI, so the
    claim "this document carries N valid per-signatory signatures" is checkable rather than
    asserted."""
    _require_pyhanko()

    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    ctx = None
    if trust_roots_pem:
        from asn1crypto import x509 as asn1_x509
        from cryptography.hazmat.primitives import serialization

        roots = [
            asn1_x509.Certificate.load(
                ca_mod.from_pem(pem).public_bytes(serialization.Encoding.DER)
            )
            for pem in trust_roots_pem
        ]
        ctx = ValidationContext(trust_roots=roots, allow_fetching=False, revocation_mode="soft-fail")

    out: list[dict] = []
    reader = PdfFileReader(io.BytesIO(pdf_bytes))
    for sig in reader.embedded_signatures:
        status = validate_pdf_signature(sig, signer_validation_context=ctx)
        signer_cert = status.signing_cert
        out.append({
            "field_name": sig.field_name,
            "intact": bool(status.intact),
            "valid": bool(status.valid),
            "trusted": bool(getattr(status, "trusted", False)),
            "covers_whole_document": bool(getattr(status, "coverage", None)
                                          and status.coverage.name == "ENTIRE_FILE"),
            "signer_subject": signer_cert.subject.human_friendly if signer_cert else "",
            "signer_serial": format(signer_cert.serial_number, "x") if signer_cert else "",
            "timestamp": getattr(status, "timestamp_validity", None) is not None,
        })
    return out
