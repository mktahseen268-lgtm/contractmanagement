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

    @abstractmethod
    def seal_pdf(self, pdf_bytes: bytes, *, contract_ref: str = "", reason: str = "") -> bytes:
        """Return the (possibly cryptographically-signed) executed PDF bytes."""
        raise NotImplementedError


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


def get_signing_provider() -> SigningProvider:
    """Pick the sealing provider from config; falls back to internal when PAdES isn't fully
    configured so envelope sealing always succeeds."""
    if settings.signing_provider == "pades" and settings.signing_cert_path:
        return PadesSigningProvider(
            cert_path=settings.signing_cert_path,
            cert_password=settings.signing_cert_password,
            field_name=settings.signing_field_name,
            reason=settings.signing_reason,
            tsa_url=settings.signing_tsa_url,
        )
    return InternalSigningProvider()
