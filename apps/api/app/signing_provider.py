"""Pluggable e-signature *sealing* provider (RFI T-4 / docs/19).

Two layers of "signature" exist in this product:
  1. The **business e-signature flow** (recipients adopt a typed signature; the executed PDF
     gets a Signatures page + a Certificate of Completion). That lives in `signing_service` and
     is unchanged — it's the workflow + evidence trail.
  2. The **cryptographic document seal** applied to the final executed PDF. THAT is what this
     module makes pluggable, because it's where government/eIDAS requirements (PAdES, RFC-3161
     timestamps, a real signing certificate) come in.

Selection is config-driven (`SIGNING_PROVIDER`):
  - `internal` (default) — no cryptographic seal; the visual Signatures page + Certificate of
    Completion are the evidence. Zero deps; the honest default for dev + non-regulated use.
  - `pades` — REAL PAdES digital signature on the executed PDF via `pyhanko`, using a configured
    PKCS#12 certificate, with an optional RFC-3161 timestamp (TSA). Activates only when
    `SIGNING_CERT_PATH` is set and `pyhanko` is installed (requirements-sign.txt).

A NIFT eSign / Adobe Sign / DocuSign-trust adapter is a new `SigningProvider` subclass + a
factory branch — no changes to the sealing task.
"""

from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod

from .config import settings

log = logging.getLogger("uvicorn.error")


class SigningProvider(ABC):
    name: str
    #: True if this provider applies a real cryptographic signature (vs. visual-only evidence).
    cryptographic: bool = False
    #: True if each signatory signs with *their own* certificate rather than one shared
    #: organisational certificate. The RFP forbids shared/role certificates, so this is the
    #: property that distinguishes a compliant configuration from a merely cryptographic one.
    per_signatory: bool = False

    @abstractmethod
    def seal_pdf(self, pdf_bytes: bytes, *, contract_ref: str = "", reason: str = "") -> bytes:
        """Return the (possibly cryptographically-signed) executed PDF bytes."""
        raise NotImplementedError

    def sign_for_recipients(self, db, pdf_bytes: bytes, signers: list, *,
                            contract_ref: str = "") -> tuple[bytes, list[dict]]:
        """Apply one signature per signatory. Returns (pdf, per-signature receipts).

        `signers` is a list of (recipient, certificate) pairs. The default implementation is a
        no-op for providers that cannot do this, so `seal_envelope` has one code path.
        """
        return pdf_bytes, []


class InternalSigningProvider(SigningProvider):
    """No cryptographic seal — the executed PDF already carries the Signatures page + the
    Certificate of Completion produced by `pdf.py`, which is the evidence trail."""

    name = "internal"
    cryptographic = False

    def seal_pdf(self, pdf_bytes: bytes, *, contract_ref: str = "", reason: str = "") -> bytes:
        return pdf_bytes


class PadesSigningProvider(SigningProvider):
    """Real PAdES (PDF Advanced Electronic Signature) via pyhanko + a PKCS#12 certificate.
    Adds an RFC-3161 timestamp when a TSA URL is configured (PAdES-B-T). Verifiable in Adobe
    Acrobat / any PAdES validator."""

    name = "pades"
    cryptographic = True

    def __init__(self, cert_path: str, cert_password: str, field_name: str, reason: str, tsa_url: str) -> None:
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.field_name = field_name or "Signature1"
        self.reason = reason or "Executed via Contract Management"
        self.tsa_url = tsa_url

    def seal_pdf(self, pdf_bytes: bytes, *, contract_ref: str = "", reason: str = "") -> bytes:
        try:
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.sign import signers
            from pyhanko.sign.timestamps import HTTPTimeStamper
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("SIGNING_PROVIDER=pades but `pyhanko` isn't installed (pip install -r requirements-sign.txt).") from e

        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=self.cert_path,
            passphrase=self.cert_password.encode("utf-8") if self.cert_password else None,
        )
        if signer is None:
            raise RuntimeError(f"Could not load the signing certificate at {self.cert_path}.")

        meta = signers.PdfSignatureMetadata(
            field_name=self.field_name,
            reason=(reason or self.reason),
            location="Contract Management",
            name=(f"Contract Management — {contract_ref}" if contract_ref else "Contract Management"),
        )
        timestamper = HTTPTimeStamper(self.tsa_url) if self.tsa_url else None
        pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper)

        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
        out = io.BytesIO()
        pdf_signer.sign_pdf(writer, output=out)
        return out.getvalue()


class PkiSigningProvider(SigningProvider):
    """**Per-signatory** PAdES-LTV signing using the in-platform PKI (Phase 1 + 2).

    This is the RFP-compliant configuration. Each signatory signs with the certificate issued
    to them by the internal CA, whose private key lives in the keystore (HSM in production and
    never exported). A document signed by three people carries three independently verifiable
    signatures, each naming its own certificate serial.

    Contrast with `PadesSigningProvider`, which seals the whole document once with a single
    shared organisational PKCS#12 — the arrangement the RFP explicitly forbids. That provider
    is kept for deployments without an internal CA, and `/pki/health` warns when it is active.
    """

    name = "pki"
    cryptographic = True
    per_signatory = True

    def seal_pdf(self, pdf_bytes: bytes, *, contract_ref: str = "", reason: str = "") -> bytes:
        # There is no org-level seal in this mode — the per-signatory signatures *are* the
        # cryptographic evidence. Returning the document unchanged is correct, not a no-op bug.
        return pdf_bytes

    def sign_for_recipients(self, db, pdf_bytes: bytes, signers: list, *,
                            contract_ref: str = "") -> tuple[bytes, list[dict]]:
        from .pki import signer as pki_signer

        receipts: list[dict] = []
        out = pdf_bytes
        for index, (recipient, certificate) in enumerate(signers, start=1):
            # A unique field per signature: pyHanko refuses to reuse a signed field, which
            # stops a later signature silently replacing an earlier one.
            field = f"Signature_{index}_{recipient.id[:8]}"
            try:
                out = pki_signer.sign_pdf_as(
                    db, out, certificate,
                    field_name=field,
                    reason=f"Executed: {contract_ref}" if contract_ref else settings.signing_reason,
                    signer_name=recipient.signed_name or recipient.name,
                )
                receipts.append({
                    "recipient_id": recipient.id,
                    "recipient_name": recipient.name,
                    "field_name": field,
                    "certificate_id": certificate.id,
                    "certificate_serial": certificate.serial_number,
                    "subject_dn": certificate.subject_dn,
                    "algorithm": certificate.key_algorithm,
                    "ok": True,
                })
            except Exception as e:  # noqa: BLE001
                # One signatory's signature failing must not discard the others. Record it and
                # keep going; `seal_envelope` surfaces partial results to the dead-letter view.
                log.exception("pki signing failed for recipient %s", recipient.id)
                receipts.append({
                    "recipient_id": recipient.id,
                    "recipient_name": recipient.name,
                    "certificate_serial": getattr(certificate, "serial_number", ""),
                    "ok": False,
                    "error": str(e)[:400],
                })
        return out, receipts


def get_signing_provider() -> SigningProvider:
    """Pick the sealing provider from config; falls back to internal when a cryptographic
    provider isn't fully configured, so envelope sealing always succeeds."""
    if settings.signing_provider == "pki":
        return PkiSigningProvider()
    if settings.signing_provider == "pades" and settings.signing_cert_path:
        return PadesSigningProvider(
            cert_path=settings.signing_cert_path,
            cert_password=settings.signing_cert_password,
            field_name=settings.signing_field_name,
            reason=settings.signing_reason,
            tsa_url=settings.signing_tsa_url,
        )
    return InternalSigningProvider()
