"""Phase 2 — per-signatory PAdES signing, the authority matrix, and execution reliability.

The headline test is `TestPerSignatorySigning`: it signs one document with two different
signatories' certificates and verifies, against the actual PDF bytes, that two independent
signatures exist and that each names its own certificate serial. That is the claim the RFP
turns on — "one certificate per signatory, no shared or role-based certificates" — and it is
worth nothing if only asserted against our own database columns.

Requirements: SOW-21.
"""

from __future__ import annotations

import io
import uuid

import pytest

from app import authority_service, models, security
from app.authority_service import AuthorityError
from app.pki import ca as ca_mod
from app.pki import lifecycle, ra

pyhanko = pytest.importorskip(
    "pyhanko", reason="per-signatory PAdES needs pyHanko (requirements-sign.txt)"
)


# ---------------------------------------------------------------------------- helpers


def _pdf(text: str = "Master Services Agreement") -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture()
def workspace(db, make_user):
    officer, tenant = make_user(name="RA Officer")
    root, issuing = ca_mod.provision_hierarchy(db, tenant.id, actor_id=officer.id)
    db.commit()
    return {"tenant": tenant, "officer": officer, "root": root, "issuing": issuing}


def _user_with_cert(db, ws, name: str, role: str = "author"):
    user = models.User(
        tenant_id=ws["tenant"].id, email=f"{uuid.uuid4().hex[:8]}@example.com", name=name,
        password_hash=security.hash_password("Str0ng!Passw0rd1"), role=role,
    )
    db.add(user)
    db.commit()
    req = ra.enrol_internal_user(db, user, actor=ws["officer"])
    db.commit()
    ra.approve(db, req, officer=ws["officer"], note="verified")
    db.commit()
    cert = lifecycle.issue_from_request(db, req, actor=ws["officer"])
    db.commit()
    return user, cert


class _Recipient:
    """The two attributes `sign_for_recipients` reads. Avoids building a whole envelope for
    the tests that only care about the signing mechanics."""

    def __init__(self, rid: str, name: str) -> None:
        self.id = rid
        self.name = name
        self.signed_name = name


# ---------------------------------------------------------------------------- signing


class TestPerSignatorySigning:
    def test_each_signatory_signs_with_their_own_certificate(self, db, workspace):
        from app.pki import signer as pki_signer

        alice, cert_a = _user_with_cert(db, workspace, "Ali Raza")
        bilal, cert_b = _user_with_cert(db, workspace, "Bilal Khan")
        assert cert_a.serial_number != cert_b.serial_number
        assert cert_a.key_id != cert_b.key_id, "signatories must not share a key"

        doc = pki_signer.sign_pdf_as(db, _pdf(), cert_a, field_name="Sig_1", signer_name=alice.name)
        db.commit()
        doc = pki_signer.sign_pdf_as(db, doc, cert_b, field_name="Sig_2", signer_name=bilal.name)
        db.commit()

        results = pki_signer.verify(doc, trust_roots_pem=[workspace["root"].pem])
        assert len(results) == 2, "expected one signature per signatory"
        assert all(r["intact"] and r["valid"] for r in results)
        assert all(r["trusted"] for r in results), "chain did not build to our root"
        assert {r["signer_serial"] for r in results} == {cert_a.serial_number, cert_b.serial_number}

    def test_signature_detects_tampering(self, db, workspace):
        from app.pki import signer as pki_signer

        _, cert = _user_with_cert(db, workspace, "Ali Raza")
        doc = pki_signer.sign_pdf_as(db, _pdf(), cert, field_name="Sig_1", signer_name="Ali Raza")
        db.commit()

        # Flip a byte inside the signed revision. (Page content is zlib-compressed, so
        # searching for the visible text finds nothing and would edit the trailer instead —
        # a region the signature does not cover, which would make this test vacuous.)
        tampered = bytearray(doc)
        tampered[400] = (tampered[400] + 1) % 256

        results = pki_signer.verify(bytes(tampered), trust_roots_pem=[workspace["root"].pem])
        assert not all(r["intact"] for r in results), "tampering was not detected"

    def test_ltv_material_is_embedded(self, db, workspace):
        """A signature only verifiable while the certificate is live is worth little on a
        ten-year contract. The chain + revocation data must be inside the document."""
        from app.pki import signer as pki_signer

        _, cert = _user_with_cert(db, workspace, "Ali Raza")
        plain = pki_signer.sign_pdf_as(db, _pdf(), cert, field_name="S", signer_name="A",
                                       embed_ltv=False)
        db.commit()
        with_ltv = pki_signer.sign_pdf_as(db, _pdf(), cert, field_name="S", signer_name="A",
                                          embed_ltv=True)
        db.commit()
        assert len(with_ltv) > len(plain), "no LTV material was added"
        assert b"/DSS" in with_ltv, "no Document Security Store in the signed PDF"

    def test_provider_reports_per_signatory_capability(self, monkeypatch):
        from app.config import settings
        from app.signing_provider import get_signing_provider

        monkeypatch.setattr(settings, "signing_provider", "pki")
        provider = get_signing_provider()
        assert provider.name == "pki"
        assert provider.cryptographic and provider.per_signatory

        # The shared-PKCS#12 provider must NOT claim per-signatory capability — that flag is
        # what `seal_envelope` branches on, and mislabelling it would silently reintroduce
        # shared-certificate signing.
        monkeypatch.setattr(settings, "signing_provider", "pades")
        monkeypatch.setattr(settings, "signing_cert_path", "/nonexistent.p12")
        other = get_signing_provider()
        assert other.cryptographic and not other.per_signatory

    def test_one_failure_does_not_lose_the_other_signatures(self, db, workspace, monkeypatch):
        """A signatory whose signature fails must not discard the ones that worked."""
        from app.signing_provider import PkiSigningProvider

        alice, cert_a = _user_with_cert(db, workspace, "Ali Raza")
        _, cert_b = _user_with_cert(db, workspace, "Bilal Khan")
        # Break the second certificate's key binding.
        cert_b.key_id = "missing-key"
        db.flush()

        provider = PkiSigningProvider()
        doc, receipts = provider.sign_for_recipients(
            db, _pdf(),
            [(_Recipient("r1", "Ali Raza"), cert_a), (_Recipient("r2", "Bilal Khan"), cert_b)],
            contract_ref="CM-1",
        )
        db.commit()

        assert [r["ok"] for r in receipts] == [True, False]
        assert receipts[0]["certificate_serial"] == cert_a.serial_number
        assert receipts[1]["error"], "the failure must carry a reason"

        from app.pki import signer as pki_signer

        good = pki_signer.verify(doc, trust_roots_pem=[workspace["root"].pem])
        assert len(good) == 1 and good[0]["valid"], "the successful signature was lost"

    def test_receipts_name_the_certificate_serial(self, db, workspace):
        from app.signing_provider import PkiSigningProvider

        _, cert = _user_with_cert(db, workspace, "Ali Raza")
        _, receipts = PkiSigningProvider().sign_for_recipients(
            db, _pdf(), [(_Recipient("r1", "Ali Raza"), cert)], contract_ref="CM-1",
        )
        db.commit()
        assert receipts[0]["certificate_serial"] == cert.serial_number
        assert receipts[0]["subject_dn"] == cert.subject_dn


# ---------------------------------------------------------------------------- authority matrix


def _contract(db, ws, owner, *, value=100000.0, ctype="msa", dept="Finance", currency="PKR"):
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Vendor Agreement", type=ctype, status="approved", owner_id=owner.id,
        created_by=owner.id, value=value, currency=currency, department=dept,
    )
    db.add(c)
    db.commit()
    return c


class TestAuthorityMatrix:
    def test_silent_matrix_permits_anything(self, db, workspace):
        """With no rules configured the matrix must not block execution — a bank rolling this
        out incrementally would otherwise be unable to sign anything on day one."""
        alice, _ = _user_with_cert(db, workspace, "Ali Raza")
        contract = _contract(db, workspace, alice)
        result = authority_service.check_selection(db, contract, [alice.id])
        assert result["compliant"] and result["matrix_silent"]

    def test_value_band_selects_the_rule(self, db, workspace):
        alice, _ = _user_with_cert(db, workspace, "Ali Raza")
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Under 1M", "min_value": 0, "max_value": 1_000_000,
            "required_role": "author", "signatories_required": 1,
        })
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Over 1M", "min_value": 1_000_001, "max_value": None,
            "required_role": "owner", "signatories_required": 1,
        })
        db.commit()

        small = _contract(db, workspace, alice, value=500_000)
        assert authority_service.resolve(db, small).name == "Under 1M"
        large = _contract(db, workspace, alice, value=5_000_000)
        assert authority_service.resolve(db, large).name == "Over 1M"

    def test_role_hierarchy_satisfies_a_lower_requirement(self, db, workspace):
        """A rule requiring `manager` must be satisfiable by an owner — otherwise every matrix
        needs a row per role and drifts out of date immediately."""
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Manager+", "required_role": "manager", "signatories_required": 1,
        })
        db.commit()
        contract = _contract(db, workspace, workspace["officer"])
        # The RA officer is an owner.
        result = authority_service.check_selection(db, contract, [workspace["officer"].id])
        assert result["compliant"], result["deviations"]

    def test_unauthorised_signatory_is_flagged(self, db, workspace):
        junior, _ = _user_with_cert(db, workspace, "Junior Staff", role="author")
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "High value", "min_value": 1_000_000, "required_role": "owner",
            "signatories_required": 1,
        })
        db.commit()
        contract = _contract(db, workspace, junior, value=5_000_000)
        result = authority_service.check_selection(db, contract, [junior.id])
        assert not result["compliant"]
        assert any("not authorised" in d for d in result["deviations"])

    def test_joint_signature_requirement(self, db, workspace):
        a, _ = _user_with_cert(db, workspace, "Owner A", role="owner")
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Two signatures", "required_role": "owner", "signatories_required": 2,
        })
        db.commit()
        contract = _contract(db, workspace, a, value=100)
        result = authority_service.check_selection(db, contract, [a.id])
        assert not result["compliant"]
        assert any("requires 2 authorised" in d for d in result["deviations"])

    def test_override_needs_a_reason_and_is_audited(self, db, workspace):
        junior, _ = _user_with_cert(db, workspace, "Junior Staff", role="author")
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Owner only", "required_role": "owner", "signatories_required": 1,
        })
        db.commit()
        contract = _contract(db, workspace, junior)

        with pytest.raises(AuthorityError, match="override reason"):
            authority_service.enforce(db, contract, [junior.id], actor=workspace["officer"])

        authority_service.enforce(
            db, contract, [junior.id],
            override_reason="Authorised signatory on leave; approved by CFO over email.",
            actor=workspace["officer"],
        )
        db.commit()

        entry = db.query(models.AuditLog).filter(
            models.AuditLog.action == "signature.authority_override",
            models.AuditLog.object_id == contract.id,
        ).one()
        assert "on leave" in entry.meta["reason"]
        assert entry.meta["rule_name"] == "Owner only"
        assert entry.meta["deviations"], "the override must record what was deviated from"

    def test_most_specific_rule_wins(self, db, workspace):
        alice, _ = _user_with_cert(db, workspace, "Ali Raza")
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Any contract", "required_role": "author",
        })
        authority_service.upsert(db, workspace["tenant"].id, {
            "name": "Finance MSAs", "department": "Finance", "contract_type": "msa",
            "currency": "PKR", "required_role": "owner",
        })
        db.commit()
        contract = _contract(db, workspace, alice, ctype="msa", dept="Finance", currency="PKR")
        assert authority_service.resolve(db, contract).name == "Finance MSAs"

    def test_rule_changes_are_audited(self, db, workspace):
        rule = authority_service.upsert(
            db, workspace["tenant"].id, {"name": "Initial", "required_role": "manager"},
            actor=workspace["officer"],
        )
        db.commit()
        authority_service.upsert(
            db, workspace["tenant"].id, {"name": "Initial", "required_role": "owner"},
            actor=workspace["officer"], rule_id=rule.id,
        )
        db.commit()
        actions = {
            row.action
            for row in db.query(models.AuditLog).filter(models.AuditLog.object_id == rule.id).all()
        }
        assert actions == {"authority.rule_created", "authority.rule_updated"}


# ---------------------------------------------------------------------------- §4.3


class TestReviewerMayAlsoSign:
    def test_same_user_can_review_and_sign(self, db, workspace):
        """RFP §4a(ii) 4.3 explicitly allows the reviewer and the signatory to be the same
        person. Asserted rather than left implicit, because a separation-of-duties rule added
        later (Phase 8) could plausibly break it by accident."""
        from app import signing_service

        approver, _ = _user_with_cert(db, workspace, "Dual Role", role="approver")
        contract = _contract(db, workspace, approver)

        class _In:
            def __init__(self, name, email, kind="signer"):
                self.name, self.email, self.kind = name, email, kind

        env = signing_service.create_envelope(
            db, contract=contract,
            recipients_in=[_In(approver.name, approver.email)],
            message="", signing_order="sequential", by_user=approver,
        )
        db.commit()

        recipients = signing_service.recipients(db, env.id)
        assert len(recipients) == 1
        assert recipients[0].signer_user_id == approver.id, (
            "the recipient must bind to the internal user so the sealer can find their certificate"
        )

    def test_external_counterparty_has_no_internal_binding(self, db, workspace):
        """An outside signatory must not accidentally match a workspace user."""
        from app import signing_service

        alice, _ = _user_with_cert(db, workspace, "Ali Raza")
        contract = _contract(db, workspace, alice)

        class _In:
            def __init__(self, name, email, kind="signer"):
                self.name, self.email, self.kind = name, email, kind

        env = signing_service.create_envelope(
            db, contract=contract,
            recipients_in=[_In("Outside Counsel", "counsel@othercompany.example")],
            message="", signing_order="sequential", by_user=alice,
        )
        db.commit()
        assert signing_service.recipients(db, env.id)[0].signer_user_id is None


# ---------------------------------------------------------------------------- reliability


class TestExecutionReliability:
    def test_concurrent_signing_is_rejected_not_silently_merged(self, db, workspace):
        """Two parallel signers reading the same envelope state must not both write it.
        Losing a signature here would be invisible until someone read the executed PDF."""
        from app import signing_service

        alice, _ = _user_with_cert(db, workspace, "Ali Raza")
        contract = _contract(db, workspace, alice)
        env = models.SignatureEnvelope(
            tenant_id=workspace["tenant"].id, contract_id=contract.id,
            status="sent", created_by=alice.id, lock_version=0,
        )
        db.add(env)
        db.commit()

        signing_service._claim_envelope(db, env)  # first writer wins
        assert env.lock_version == 1

        stale = db.get(models.SignatureEnvelope, env.id)
        stale.lock_version = 0  # simulate a second worker holding the pre-claim snapshot
        with pytest.raises(signing_service.ConcurrentSigningError):
            signing_service._claim_envelope(db, stale)

    def test_seal_status_defaults_to_pending(self, db, workspace):
        alice, _ = _user_with_cert(db, workspace, "Ali Raza")
        contract = _contract(db, workspace, alice)
        env = models.SignatureEnvelope(
            tenant_id=workspace["tenant"].id, contract_id=contract.id,
            status="sent", created_by=alice.id,
        )
        db.add(env)
        db.commit()
        assert env.seal_status == "pending"
        assert env.seal_attempts == 0
        assert env.execution_mode == "electronic"
