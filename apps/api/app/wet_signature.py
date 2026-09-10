"""Hybrid execution — some parties sign electronically, some sign on paper.

RFP §4a "Hybrid flexibility": e-signature and wet signature in one unbroken digital trail.
Government counterparties in particular will not sign electronically; they need a printed
pack, a wet signature, a company stamp, and the executed paper scanned back.

The design decision that matters here is **where the evidence lives**. A scanned page proves
nothing on its own — anyone can scan anything. What carries weight is a named person inside
the bank asserting, in the append-only audit chain, that this file (by SHA-256) is the
executed copy of this agreement, received on this date, optionally witnessed. So:

  * the scan is an artefact, stored like any other file;
  * the **attestation** is the evidence, and it names an accountable human;
  * the Certificate of Completion presents wet signatures **distinctly** from cryptographic
    ones — presenting a scan as though it were a PAdES signature would be a lie of layout.

Status flows converge: a wet-signed recipient moves to `signed` exactly like an electronic
one, so `sign()`, the envelope status machine, the sealer and the repository all keep working
without a parallel code path. Only the *evidence* differs.
"""

from __future__ import annotations

import datetime as dt
import io
import logging

from sqlalchemy import select

from . import audit, models

log = logging.getLogger("uvicorn.error")


class WetSignatureError(RuntimeError):
    """A hybrid-execution rule was violated. Routers map this to 409."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------------------
# Marking an envelope hybrid
# ---------------------------------------------------------------------------------------


def set_execution_mode(db, envelope: models.SignatureEnvelope, *,
                       wet_recipient_ids: list[str], actor: models.User | None = None) -> dict:
    """Route named recipients down the paper path. Caller commits.

    Passing every signer makes the envelope `wet`; passing some makes it `hybrid`; passing
    none returns it to `electronic`.
    """
    if envelope.status in ("completed", "voided", "declined"):
        raise WetSignatureError(f"Envelope is {envelope.status}; its execution mode is settled.")

    recipients = list(db.scalars(
        select(models.SignatureRecipient).where(
            models.SignatureRecipient.envelope_id == envelope.id,
            models.SignatureRecipient.kind == "signer",
        ).order_by(models.SignatureRecipient.sequence)
    ).all())
    if not recipients:
        raise WetSignatureError("This envelope has no signers.")

    known = {r.id for r in recipients}
    unknown = [rid for rid in wet_recipient_ids if rid not in known]
    if unknown:
        raise WetSignatureError("Those recipients are not signers on this envelope.")

    already_signed = [
        r for r in recipients if r.id in wet_recipient_ids and r.status == "signed"
    ]
    if already_signed:
        raise WetSignatureError(
            f"{already_signed[0].name} has already signed electronically and cannot be "
            "switched to the paper path."
        )

    for r in recipients:
        r.signing_mode = "wet" if r.id in wet_recipient_ids else "electronic"

    wet_count = len(wet_recipient_ids)
    envelope.execution_mode = (
        "wet" if wet_count == len(recipients) else "hybrid" if wet_count else "electronic"
    )
    db.flush()

    audit.record(
        db, tenant_id=envelope.tenant_id, action="signature.execution_mode_set", actor=actor,
        object_type="contract", object_id=envelope.contract_id, object_label=envelope.id,
        meta={
            "envelope_id": envelope.id, "execution_mode": envelope.execution_mode,
            "wet_signers": [
                {"id": r.id, "name": r.name} for r in recipients if r.signing_mode == "wet"
            ],
            "electronic_signers": [
                {"id": r.id, "name": r.name} for r in recipients if r.signing_mode == "electronic"
            ],
        },
    )
    return {
        "execution_mode": envelope.execution_mode,
        "wet": [r.id for r in recipients if r.signing_mode == "wet"],
        "electronic": [r.id for r in recipients if r.signing_mode == "electronic"],
    }


# ---------------------------------------------------------------------------------------
# Print pack
# ---------------------------------------------------------------------------------------


def build_print_pack(db, envelope: models.SignatureEnvelope, contract: models.Contract,
                     org_name: str) -> bytes:
    """A cover sheet plus the agreement, ready to print, sign by hand and scan back.

    The cover sheet is the useful part: it carries the reference the returned scan is matched
    on, who must sign, and a QR pointing at the upload page. A pack that comes back without
    the operator knowing which agreement it belongs to is the failure mode this prevents.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from .pdf import _LINE, _styles

    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Print pack — {contract.reference_no or contract.title}",
    )

    wet_signers = [
        r for r in db.scalars(
            select(models.SignatureRecipient).where(
                models.SignatureRecipient.envelope_id == envelope.id,
                models.SignatureRecipient.kind == "signer",
                models.SignatureRecipient.signing_mode == "wet",
            ).order_by(models.SignatureRecipient.sequence)
        ).all()
    ]

    small = ParagraphStyle("packSmall", parent=st["body"], fontSize=8.5, leading=11)
    story: list = [
        Paragraph("Physical signature pack", st["h1"]),
        Paragraph(org_name, small),
        Spacer(1, 8),
        Paragraph(
            f"<b>{contract.title}</b><br/>Reference: <b>{contract.reference_no or contract.id}</b>",
            st["body"],
        ),
        Spacer(1, 10),
        Paragraph("What to do", st["h3"]),
        Paragraph(
            "1. Print this pack in full, including the agreement that follows this page.<br/>"
            "2. The signatories named below sign by hand and apply the company stamp where "
            "required.<br/>"
            "3. Scan the <b>complete</b> signed document, including this cover sheet.<br/>"
            "4. Return the scan to the sender, or upload it using the reference above.",
            small,
        ),
        Spacer(1, 10),
    ]

    if wet_signers:
        rows = [["#", "Signatory", "Email", "Signature", "Date"]]
        for index, r in enumerate(wet_signers, start=1):
            rows.append([str(index), r.name, r.email, "", ""])
        table = Table(rows, colWidths=[10 * mm, 42 * mm, 48 * mm, 40 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _LINE),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 22),  # room to actually sign
            ("BACKGROUND", (0, 0), (-1, 0), _LINE),
        ]))
        story += [Paragraph("Signatories", st["h3"]), table, Spacer(1, 10)]

    story.append(Paragraph(
        "This pack was generated by an electronic contract management system. The scanned "
        "executed copy will be attached to the digital record and certified on receipt, so "
        "the agreement's history remains complete and auditable.",
        small,
    ))

    doc.build(story)
    cover = buf.getvalue()

    # Append the agreement itself, so one file is everything the counterparty needs.
    document_bytes = _document_bytes(db, envelope)
    if not document_bytes:
        return cover
    try:
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        for source in (cover, document_bytes):
            for page in PdfReader(io.BytesIO(source)).pages:
                writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        # A cover sheet alone is still useful; never fail the download over the merge.
        log.exception("wet: could not merge the agreement into the print pack")
        return cover


def _document_bytes(db, envelope: models.SignatureEnvelope) -> bytes | None:
    if not envelope.document_file_id:
        return None
    fo = db.get(models.FileObject, envelope.document_file_id)
    if fo is None:
        return None
    from .storage import get_storage

    try:
        stream = get_storage().open_stream(fo.key)
        try:
            return stream.read()
        finally:
            stream.close()
    except Exception:  # noqa: BLE001
        log.exception("wet: could not read the envelope document")
        return None


# ---------------------------------------------------------------------------------------
# Attestation
# ---------------------------------------------------------------------------------------


def attest(db, *, envelope: models.SignatureEnvelope, contract: models.Contract,
           file_obj: models.FileObject, actor: models.User,
           recipient: models.SignatureRecipient | None = None,
           declared_execution_date: dt.date | None = None,
           signatory_name: str = "", signatory_designation: str = "",
           witness_name: str = "", witness_designation: str = "",
           notes: str = "", ip: str = "") -> models.WetSignatureAttestation:
    """Certify a scanned executed copy and advance the signer(s). Caller commits.

    `recipient=None` attests the whole envelope, which is the common case: one paper copy
    carries every wet signature.
    """
    if envelope.execution_mode == "electronic":
        raise WetSignatureError(
            "This envelope is set to electronic execution. Mark the paper signatories first."
        )
    if envelope.status in ("voided", "declined"):
        raise WetSignatureError(f"Envelope is {envelope.status}.")

    targets = [recipient] if recipient is not None else list(db.scalars(
        select(models.SignatureRecipient).where(
            models.SignatureRecipient.envelope_id == envelope.id,
            models.SignatureRecipient.kind == "signer",
            models.SignatureRecipient.signing_mode == "wet",
        )
    ).all())
    if not targets:
        raise WetSignatureError("No paper signatories on this envelope to attest for.")
    if recipient is not None and recipient.signing_mode != "wet":
        raise WetSignatureError(
            f"{recipient.name} is signing electronically — upload is not the right path."
        )

    outstanding = [r for r in targets if r.status != "signed"]
    if not outstanding:
        raise WetSignatureError("Those signatories are already recorded as signed.")

    attestation = models.WetSignatureAttestation(
        tenant_id=envelope.tenant_id, envelope_id=envelope.id,
        recipient_id=recipient.id if recipient is not None else None,
        file_id=file_obj.id, file_sha256=file_obj.sha256 or "",
        declared_execution_date=declared_execution_date,
        signatory_name=signatory_name[:200], signatory_designation=signatory_designation[:200],
        witness_name=witness_name[:200], witness_designation=witness_designation[:200],
        notes=notes[:1000], attested_by=actor.id, attested_by_name=actor.name, ip=ip,
    )
    db.add(attestation)

    now = _now()
    for r in outstanding:
        r.status = "signed"
        r.signed_at = now
        r.consent_at = r.consent_at or now
        r.signed_name = (signatory_name or r.name)[:200]
        r.identity_method = "wet_attested"
        r.identity_verified_at = now
        # Keep the evidence bundle honest about what this is: a countersigned scan, not a
        # cryptographic signature.
        r.identity_evidence = {
            "method": "wet_signature",
            "attestation_id": attestation.id,
            "file_sha256": attestation.file_sha256,
            "declared_execution_date": (
                declared_execution_date.isoformat() if declared_execution_date else None
            ),
            "attested_by": actor.name,
            "attested_at": now.isoformat(),
            "witness_name": witness_name,
            "witness_designation": witness_designation,
        }
        db.add(models.SignatureEvent(
            tenant_id=envelope.tenant_id, envelope_id=envelope.id, recipient_id=r.id,
            recipient_name=r.name, event="wet_signed", ip=ip,
            meta={
                "attestation_id": attestation.id, "file_id": file_obj.id,
                "file_sha256": attestation.file_sha256, "attested_by": actor.name,
                "declared_execution_date": (
                    declared_execution_date.isoformat() if declared_execution_date else None
                ),
            },
        ))
    db.flush()

    audit.record(
        db, tenant_id=envelope.tenant_id, action="signature.wet_attested", actor=actor,
        object_type="contract", object_id=contract.id,
        object_label=contract.reference_no or contract.title, ip=ip,
        meta={
            "envelope_id": envelope.id, "attestation_id": attestation.id,
            "file_id": file_obj.id, "file_sha256": attestation.file_sha256,
            "recipients": [{"id": r.id, "name": r.name} for r in outstanding],
            "declared_execution_date": (
                declared_execution_date.isoformat() if declared_execution_date else None
            ),
            "witness_name": witness_name,
            "note": "Scanned executed copy certified by a named employee.",
        },
    )
    _converge(db, envelope, contract)
    return attestation


def _converge(db, envelope: models.SignatureEnvelope, contract: models.Contract) -> None:
    """Complete the envelope once every signer is done, whichever path they took.

    This is the join point that keeps hybrid from becoming a second status machine: the
    electronic path already calls the same logic from `signing_service.sign`.
    """
    signers = list(db.scalars(
        select(models.SignatureRecipient).where(
            models.SignatureRecipient.envelope_id == envelope.id,
            models.SignatureRecipient.kind == "signer",
        )
    ).all())
    pending = [r for r in signers if r.status != "signed"]
    if pending:
        envelope.status = "partially_signed"
        return

    envelope.status = "completed"
    envelope.completed_at = _now()
    db.add(models.SignatureEvent(
        tenant_id=envelope.tenant_id, envelope_id=envelope.id, event="completed",
        meta={"execution_mode": envelope.execution_mode},
    ))
    if contract.status == "out_for_signature":
        contract.status = "signed"
    if contract.owner_id:
        db.add(models.Notification(
            tenant_id=contract.tenant_id, user_id=contract.owner_id,
            type="contract.signature_update",
            title=f'"{contract.title}" is fully executed',
            body=(
                "All signatories have signed — including the paper copy. The executed record "
                "and certificate are being prepared."
            ),
            object_type="contract", object_id=contract.id,
        ))
    db.flush()


def attestations_for(db, envelope_id: str) -> list[models.WetSignatureAttestation]:
    return list(db.scalars(
        select(models.WetSignatureAttestation)
        .where(models.WetSignatureAttestation.envelope_id == envelope_id)
        .order_by(models.WetSignatureAttestation.attested_at.asc())
    ).all())


def evidence_summary(db, envelope: models.SignatureEnvelope) -> dict:
    """What kind of evidence backs this execution — for the Certificate of Completion and the
    admin UI. Kept explicit so a scan is never presented as a cryptographic signature."""
    signers = list(db.scalars(
        select(models.SignatureRecipient).where(
            models.SignatureRecipient.envelope_id == envelope.id,
            models.SignatureRecipient.kind == "signer",
        )
    ).all())
    attestations = attestations_for(db, envelope.id)
    return {
        "execution_mode": envelope.execution_mode,
        "electronic_signers": [r.name for r in signers if r.signing_mode != "wet"],
        "wet_signers": [r.name for r in signers if r.signing_mode == "wet"],
        "attestations": [
            {
                "id": a.id,
                "file_id": a.file_id,
                "file_sha256": a.file_sha256,
                "declared_execution_date": (
                    a.declared_execution_date.isoformat() if a.declared_execution_date else None
                ),
                "attested_by": a.attested_by_name,
                "attested_at": a.attested_at.isoformat() if a.attested_at else None,
                "witness_name": a.witness_name,
            }
            for a in attestations
        ],
        "note": (
            "Wet signatures are evidenced by a countersigned scan certified by a named "
            "employee, not by a cryptographic signature."
            if attestations else ""
        ),
    }


__all__ = [
    "WetSignatureError", "attest", "attestations_for", "build_print_pack",
    "evidence_summary", "set_execution_mode",
]
