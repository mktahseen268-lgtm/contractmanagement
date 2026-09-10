"""Hybrid execution — some parties sign electronically, some on paper.

The property under test is **convergence**: a wet-signed party must advance the same envelope
status machine as an electronic one, so there is exactly one definition of "executed". The
second property is **honesty**: the evidence must stay distinguishable, because presenting a
scanned page as though it were a cryptographic signature would be a lie the Certificate of
Completion carries forever.

Requirements: SOW-23.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import models, security, wet_signature
from app.wet_signature import WetSignatureError


@pytest.fixture()
def envelope(db, make_user):
    officer, tenant = make_user(name="Contract Officer")
    contract = models.Contract(
        tenant_id=tenant.id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Government Services Agreement", type="service", status="out_for_signature",
        owner_id=officer.id, created_by=officer.id, value=5_000_000, currency="PKR",
    )
    db.add(contract)
    db.flush()
    env = models.SignatureEnvelope(
        tenant_id=tenant.id, contract_id=contract.id, status="sent", created_by=officer.id,
    )
    db.add(env)
    db.flush()
    bank = models.SignatureRecipient(
        tenant_id=tenant.id, envelope_id=env.id, sequence=0, name="Bank Signatory",
        email="bank@mmbl.test", kind="signer", status="sent",
    )
    ministry = models.SignatureRecipient(
        tenant_id=tenant.id, envelope_id=env.id, sequence=1, name="Ministry Signatory",
        email="secretary@ministry.example", kind="signer", status="sent",
    )
    db.add_all([bank, ministry])
    db.commit()
    return {"tenant": tenant, "officer": officer, "contract": contract, "env": env,
            "bank": bank, "ministry": ministry}


def _scan(db, ws, content: bytes = b"%PDF-1.4 scanned executed copy"):
    import hashlib

    fo = models.FileObject(
        tenant_id=ws["tenant"].id, key=f"tenants/{ws['tenant'].id}/scan-{uuid.uuid4().hex}.pdf",
        content_type="application/pdf", size=len(content),
        sha256=hashlib.sha256(content).hexdigest(), original_name="executed.pdf",
        kind="attachment", parent_type="contract", parent_id=ws["contract"].id,
        created_by=ws["officer"].id,
    )
    db.add(fo)
    db.flush()
    return fo


# ---------------------------------------------------------------------------- mode


class TestExecutionMode:
    def test_marking_one_party_makes_the_envelope_hybrid(self, db, envelope):
        result = wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        assert result["execution_mode"] == "hybrid"
        assert envelope["ministry"].signing_mode == "wet"
        assert envelope["bank"].signing_mode == "electronic", (
            "one paper counterparty must not force everyone else off the electronic path"
        )

    def test_marking_every_party_makes_it_wet(self, db, envelope):
        result = wet_signature.set_execution_mode(
            db, envelope["env"],
            wet_recipient_ids=[envelope["bank"].id, envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        assert result["execution_mode"] == "wet"

    def test_clearing_returns_to_electronic(self, db, envelope):
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        result = wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[], actor=envelope["officer"],
        )
        db.commit()
        assert result["execution_mode"] == "electronic"
        assert envelope["ministry"].signing_mode == "electronic"

    def test_cannot_switch_someone_who_already_signed(self, db, envelope):
        """Retro-fitting a paper path onto a completed electronic signature would rewrite the
        evidence for a signature that already exists."""
        envelope["bank"].status = "signed"
        envelope["bank"].signed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        db.commit()
        with pytest.raises(WetSignatureError, match="already signed electronically"):
            wet_signature.set_execution_mode(
                db, envelope["env"], wet_recipient_ids=[envelope["bank"].id],
                actor=envelope["officer"],
            )

    def test_unknown_recipient_is_rejected(self, db, envelope):
        with pytest.raises(WetSignatureError, match="not signers"):
            wet_signature.set_execution_mode(
                db, envelope["env"], wet_recipient_ids=["not-a-recipient"],
                actor=envelope["officer"],
            )

    def test_completed_envelope_is_settled(self, db, envelope):
        envelope["env"].status = "completed"
        db.commit()
        with pytest.raises(WetSignatureError, match="settled"):
            wet_signature.set_execution_mode(
                db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
                actor=envelope["officer"],
            )

    def test_mode_change_is_audited(self, db, envelope):
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        entry = db.query(models.AuditLog).filter(
            models.AuditLog.tenant_id == envelope["tenant"].id,
            models.AuditLog.action == "signature.execution_mode_set",
        ).one()
        assert entry.meta["execution_mode"] == "hybrid"
        assert [s["name"] for s in entry.meta["wet_signers"]] == ["Ministry Signatory"]


# ---------------------------------------------------------------------------- print pack


class TestPrintPack:
    def test_pack_is_a_pdf_naming_the_paper_signatories(self, db, envelope):
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        pdf = wet_signature.build_print_pack(
            db, envelope["env"], envelope["contract"], "MMBL",
        )
        assert pdf.startswith(b"%PDF")

        from pypdf import PdfReader
        import io

        text = "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
        assert envelope["contract"].reference_no in text, (
            "the reference is how a returned scan gets matched to its agreement"
        )
        assert "Ministry Signatory" in text
        assert "Bank Signatory" not in text, "electronic signers do not belong on the paper pack"

    def test_pack_survives_a_missing_document(self, db, envelope):
        """No rendered document yet: the cover sheet alone is still useful, so never fail."""
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        assert envelope["env"].document_file_id is None
        pdf = wet_signature.build_print_pack(db, envelope["env"], envelope["contract"], "MMBL")
        assert pdf.startswith(b"%PDF")


# ---------------------------------------------------------------------------- attestation


class TestAttestation:
    def _hybrid(self, db, envelope):
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()

    def test_attesting_advances_the_paper_signatory(self, db, envelope):
        self._hybrid(db, envelope)
        scan = _scan(db, envelope)
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"], file_obj=scan,
            actor=envelope["officer"], recipient=envelope["ministry"],
            declared_execution_date=dt.date(2026, 8, 20),
            signatory_name="Mr Secretary", witness_name="Ms Witness",
        )
        db.commit()
        assert envelope["ministry"].status == "signed"
        assert envelope["ministry"].identity_method == "wet_attested"
        # The envelope must NOT complete — the bank signatory has not signed yet.
        assert envelope["env"].status == "partially_signed"

    def test_evidence_records_the_file_hash_and_the_accountable_person(self, db, envelope):
        """The scan is the artefact; the attestation is the evidence."""
        self._hybrid(db, envelope)
        scan = _scan(db, envelope)
        attestation = wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"], file_obj=scan,
            actor=envelope["officer"], recipient=envelope["ministry"],
            declared_execution_date=dt.date(2026, 8, 20),
        )
        db.commit()
        assert attestation.file_sha256 == scan.sha256
        assert attestation.attested_by == envelope["officer"].id
        assert attestation.attested_by_name == envelope["officer"].name
        assert attestation.declared_execution_date == dt.date(2026, 8, 20)

        evidence = envelope["ministry"].identity_evidence
        assert evidence["method"] == "wet_signature"
        assert evidence["file_sha256"] == scan.sha256
        assert evidence["declared_execution_date"] == "2026-08-20"

    def test_declared_execution_date_is_not_the_upload_date(self, db, envelope):
        """The date the parties signed the paper governs the agreement — not the day someone
        got round to scanning it."""
        self._hybrid(db, envelope)
        scan = _scan(db, envelope)
        attestation = wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"], file_obj=scan,
            actor=envelope["officer"], recipient=envelope["ministry"],
            declared_execution_date=dt.date(2026, 8, 1),
        )
        db.commit()
        assert attestation.declared_execution_date == dt.date(2026, 8, 1)
        assert attestation.attested_at.date() != dt.date(2026, 8, 1)

    def test_attestation_is_audited(self, db, envelope):
        self._hybrid(db, envelope)
        scan = _scan(db, envelope)
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"], file_obj=scan,
            actor=envelope["officer"], recipient=envelope["ministry"],
            witness_name="Ms Witness",
        )
        db.commit()
        entry = db.query(models.AuditLog).filter(
            models.AuditLog.tenant_id == envelope["tenant"].id,
            models.AuditLog.action == "signature.wet_attested",
        ).one()
        assert entry.meta["file_sha256"] == scan.sha256
        assert entry.meta["witness_name"] == "Ms Witness"

    def test_cannot_attest_for_an_electronic_signer(self, db, envelope):
        self._hybrid(db, envelope)
        scan = _scan(db, envelope)
        with pytest.raises(WetSignatureError, match="signing electronically"):
            wet_signature.attest(
                db, envelope=envelope["env"], contract=envelope["contract"], file_obj=scan,
                actor=envelope["officer"], recipient=envelope["bank"],
            )

    def test_cannot_attest_on_an_electronic_envelope(self, db, envelope):
        scan = _scan(db, envelope)
        with pytest.raises(WetSignatureError, match="electronic execution"):
            wet_signature.attest(
                db, envelope=envelope["env"], contract=envelope["contract"], file_obj=scan,
                actor=envelope["officer"],
            )

    def test_double_attestation_is_refused(self, db, envelope):
        self._hybrid(db, envelope)
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"],
            file_obj=_scan(db, envelope), actor=envelope["officer"],
            recipient=envelope["ministry"],
        )
        db.commit()
        with pytest.raises(WetSignatureError, match="already recorded as signed"):
            wet_signature.attest(
                db, envelope=envelope["env"], contract=envelope["contract"],
                file_obj=_scan(db, envelope), actor=envelope["officer"],
                recipient=envelope["ministry"],
            )

    def test_one_scan_can_cover_every_paper_signatory(self, db, envelope):
        """The usual case: one printed copy carries all the wet signatures."""
        wet_signature.set_execution_mode(
            db, envelope["env"],
            wet_recipient_ids=[envelope["bank"].id, envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"],
            file_obj=_scan(db, envelope), actor=envelope["officer"],
        )
        db.commit()
        assert envelope["bank"].status == "signed"
        assert envelope["ministry"].status == "signed"


# ---------------------------------------------------------------------------- convergence


class TestConvergence:
    def test_hybrid_envelope_completes_once_both_paths_finish(self, db, envelope):
        """The point of the whole feature: one definition of 'executed', whichever way each
        party signed."""
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()

        # The bank signs electronically.
        envelope["bank"].status = "signed"
        envelope["bank"].signed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        db.commit()

        # The ministry returns paper.
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"],
            file_obj=_scan(db, envelope), actor=envelope["officer"],
            recipient=envelope["ministry"],
        )
        db.commit()

        assert envelope["env"].status == "completed"
        assert envelope["env"].completed_at is not None
        assert envelope["contract"].status == "signed", (
            "the contract lifecycle must advance identically for a hybrid execution"
        )

    def test_completion_emits_the_same_event_as_the_electronic_path(self, db, envelope):
        wet_signature.set_execution_mode(
            db, envelope["env"],
            wet_recipient_ids=[envelope["bank"].id, envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"],
            file_obj=_scan(db, envelope), actor=envelope["officer"],
        )
        db.commit()
        events = {
            e.event for e in db.query(models.SignatureEvent).filter(
                models.SignatureEvent.envelope_id == envelope["env"].id
            ).all()
        }
        assert "wet_signed" in events
        assert "completed" in events


# ---------------------------------------------------------------------------- honesty


class TestEvidenceIsNotOverstated:
    def test_summary_separates_scanned_from_cryptographic(self, db, envelope):
        """A scanned page must never be presented as though it were a PAdES signature."""
        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"],
            file_obj=_scan(db, envelope), actor=envelope["officer"],
            recipient=envelope["ministry"],
        )
        db.commit()

        summary = wet_signature.evidence_summary(db, envelope["env"])
        assert summary["execution_mode"] == "hybrid"
        assert summary["wet_signers"] == ["Ministry Signatory"]
        assert summary["electronic_signers"] == ["Bank Signatory"]
        assert len(summary["attestations"]) == 1
        assert "not by a cryptographic signature" in summary["note"]

    def test_electronic_only_envelope_carries_no_wet_note(self, db, envelope):
        summary = wet_signature.evidence_summary(db, envelope["env"])
        assert summary["execution_mode"] == "electronic"
        assert summary["attestations"] == []
        assert summary["note"] == ""

    def test_wet_signer_gets_no_certificate_binding(self, db, envelope):
        """A paper signatory has no key and no certificate. The sealer must skip them rather
        than sign on their behalf with somebody else's credential."""
        from app.tasks import _certificates_for_signers

        wet_signature.set_execution_mode(
            db, envelope["env"], wet_recipient_ids=[envelope["ministry"].id],
            actor=envelope["officer"],
        )
        db.commit()
        wet_signature.attest(
            db, envelope=envelope["env"], contract=envelope["contract"],
            file_obj=_scan(db, envelope), actor=envelope["officer"],
            recipient=envelope["ministry"],
        )
        db.commit()

        pairs = _certificates_for_signers(db, [envelope["ministry"]])
        assert pairs == [], "a wet signatory must not be paired with any certificate"


def test_security_import_is_available(db):
    assert security is not None
