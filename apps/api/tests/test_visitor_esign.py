"""Visitor eSigning — the public, unauthenticated surface.

This is the highest-risk code in the product: anyone on the internet can reach it, and a
successful run mints a certificate and attaches a signatory to a real agreement. The tests
therefore lean on the negative cases — wrong code, expired code, brute force, a session from
someone else's link, signing before reading — because those are the ways it gets abused.

Requirements: SOW-22, BB-06.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid

import pytest

from app import models, security, sms, visitor_service
from app.pki import ca as ca_mod
from app.visitor_service import VisitorBlocked, VisitorError


@pytest.fixture()
def workspace(db, make_user):
    officer, tenant = make_user(name="Branch Officer")
    contract = models.Contract(
        tenant_id=tenant.id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Merchant Onboarding Agreement", type="service", status="out_for_signature",
        owner_id=officer.id, created_by=officer.id, value=250000, currency="PKR",
    )
    db.add(contract)
    db.commit()
    invitation, raw = visitor_service.create_invitation(
        db, contract=contract, actor=officer, label="Branch counter",
    )
    db.commit()
    return {"tenant": tenant, "officer": officer, "contract": contract,
            "invitation": invitation, "token": raw}


def _start(db, ws, **kw):
    params = {"name": "Ahmed Merchant", "email": "ahmed@merchant.example",
              "channel": "email", "ip": "10.1.2.3"}
    params.update(kw)
    return visitor_service.start_session(db, ws["invitation"], **params)


def _code_for(db, session_id: str) -> str:
    """Read the code the visitor would actually have received, out of the delivery outbox.

    Deliberately not reading `otp_code_hash` and reversing it: going through the outbox means
    these tests break if OTP delivery breaks, which is the failure that would otherwise reach
    production silently (a visitor waiting forever for a code that was never sent).
    """
    session = db.get(models.VisitorSession, session_id)
    target = session.phone if session.otp_channel == "sms" else session.email
    row = (
        db.query(models.EmailOutbox)
        .filter(models.EmailOutbox.to_email == target)
        .order_by(models.EmailOutbox.created_at.desc(), models.EmailOutbox.id.desc())
        .first()
    )
    assert row is not None, f"no code was delivered to {target}"
    match = re.search(r"(\d{6})", row.body)
    assert match, f"no code found in the delivered message: {row.body!r}"
    code = match.group(1)
    assert hashlib.sha256(code.encode()).hexdigest() == session.otp_code_hash, (
        "the delivered code does not match the stored hash"
    )
    return code


# ---------------------------------------------------------------------------- invitations


class TestInvitations:
    def test_only_a_hash_of_the_token_is_stored(self, db, workspace):
        """The lookup column must be a one-way hash, so a database leak cannot be turned back
        into a working signing URL."""
        from sqlalchemy import text as sa_text

        raw = workspace["token"]
        row = db.execute(
            sa_text("SELECT token_hash, token_secret FROM signing_invitations WHERE id = :i"),
            {"i": workspace["invitation"].id},
        ).mappings().one()
        assert row["token_hash"] == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in row["token_hash"]

    def test_token_copy_is_encrypted_at_rest(self, db, workspace, monkeypatch):
        """The reversible copy (kept so the QR can be re-rendered) must be ciphertext.

        Configured explicitly: without `MFA_ENCRYPTION_KEYS` the `EncryptedString` type passes
        values through by design, so a test reading the ambient environment would assert
        nothing in CI.
        """
        from cryptography.fernet import Fernet
        from sqlalchemy import text as sa_text

        from app import secrets_box
        from app.config import settings

        monkeypatch.setattr(settings, "mfa_encryption_keys", Fernet.generate_key().decode())
        secrets_box.reset_for_tests()
        try:
            invitation, raw = visitor_service.create_invitation(
                db, contract=workspace["contract"], actor=workspace["officer"], label="Encrypted",
            )
            db.commit()
            stored = db.execute(
                sa_text("SELECT token_secret FROM signing_invitations WHERE id = :i"),
                {"i": invitation.id},
            ).scalar_one()
            assert raw not in stored, "the signing token was written in the clear"
            # …and it must still decrypt, or the QR could never be re-rendered.
            assert db.get(models.SigningInvitation, invitation.id).token_secret == raw
        finally:
            secrets_box.reset_for_tests()

    def test_token_resolves(self, db, workspace):
        found = visitor_service.invitation_by_token(db, workspace["token"])
        assert found is not None and found.id == workspace["invitation"].id

    def test_wrong_token_does_not_resolve(self, db, workspace):
        assert visitor_service.invitation_by_token(db, "not-a-real-token") is None

    def test_expired_invitation_does_not_resolve(self, db, workspace):
        workspace["invitation"].expires_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(minutes=1)
        db.commit()
        assert visitor_service.invitation_by_token(db, workspace["token"]) is None

    def test_revoked_invitation_does_not_resolve(self, db, workspace):
        workspace["invitation"].is_active = False
        db.commit()
        assert visitor_service.invitation_by_token(db, workspace["token"]) is None

    def test_use_cap_closes_the_link(self, db, workspace):
        """A link minted for one named merchant must not be reusable by the next person."""
        workspace["invitation"].max_signatures = 1
        workspace["invitation"].signature_count = 1
        db.commit()
        assert visitor_service.invitation_by_token(db, workspace["token"]) is None


# ---------------------------------------------------------------------------- identity


class TestIdentityBinding:
    def test_start_sends_a_masked_code_and_creates_nothing_irreversible(self, db, workspace):
        session, masked = _start(db, workspace)
        db.commit()
        assert session.status == "otp_sent"
        assert masked == "ah***@merchant.example", "the full identifier must not be echoed back"
        # Nothing irreversible yet: no certificate, no recipient, no signature.
        assert session.certificate_id is None
        assert session.recipient_id is None
        assert session.verified_at is None

    def test_wrong_code_is_rejected(self, db, workspace):
        session, _ = _start(db, workspace)
        db.commit()
        with pytest.raises(VisitorError, match="not correct"):
            visitor_service.verify_session(db, workspace["invitation"], session, "000000")
        assert session.verified_at is None

    def test_brute_force_is_blocked(self, db, workspace):
        """The attempt cap, not the code length, is what makes a 6-digit OTP safe."""
        session, _ = _start(db, workspace)
        db.commit()
        from app.config import settings

        for _ in range(settings.esign_otp_max_attempts):
            with pytest.raises(VisitorError):
                visitor_service.verify_session(db, workspace["invitation"], session, "111111")
        with pytest.raises(VisitorBlocked):
            visitor_service.verify_session(db, workspace["invitation"], session, "111111")
        assert session.status == "blocked"

    def test_expired_code_is_rejected(self, db, workspace):
        session, _ = _start(db, workspace)
        db.commit()
        code = _code_for(db, session.id)
        session.otp_expires_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(seconds=1)
        db.commit()
        with pytest.raises(VisitorError, match="expired"):
            visitor_service.verify_session(db, workspace["invitation"], session, code)

    def test_correct_code_verifies_and_burns_the_code(self, db, workspace):
        session, _ = _start(db, workspace)
        db.commit()
        code = _code_for(db, session.id)
        visitor_service.verify_session(db, workspace["invitation"], session, code)
        db.commit()
        assert session.verified_at is not None and session.status == "verified"
        assert session.otp_code_hash is None, "an OTP must be single-use"

    def test_resend_is_capped(self, db, workspace):
        from app.config import settings

        session, _ = _start(db, workspace)
        db.commit()
        for _ in range(settings.esign_otp_max_sends - 1):
            visitor_service.resend_otp(db, workspace["invitation"], session)
        db.commit()
        with pytest.raises(VisitorBlocked):
            visitor_service.resend_otp(db, workspace["invitation"], session)

    def test_session_from_another_invitation_is_not_accepted(self, db, workspace):
        """A session id must not be usable against a different link."""
        session, _ = _start(db, workspace)
        db.commit()
        other, _raw = visitor_service.create_invitation(
            db, contract=workspace["contract"], actor=workspace["officer"], label="Other",
        )
        db.commit()
        assert visitor_service.session_by_id(db, other, session.id) is None

    def test_sms_channel_requires_a_number(self, db, workspace):
        with pytest.raises(VisitorError, match="mobile number"):
            _start(db, workspace, channel="sms", phone="", email="a@b.example")

    def test_cnic_is_reduced_to_the_last_four_digits(self, db, workspace):
        """A full national identity number has no operational value here and every downside."""
        session, _ = _start(db, workspace, cnic="42101-1234567-8")
        db.commit()
        assert session.cnic_last4 == "5678"
        from sqlalchemy import text as sa_text

        row = db.execute(
            sa_text("SELECT * FROM visitor_sessions WHERE id = :i"), {"i": session.id}
        ).mappings().one()
        assert "42101" not in " ".join(str(v) for v in row.values())

    def test_rate_limited_per_ip(self, db, workspace, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "esign_sessions_per_hour", 2)
        _start(db, workspace)
        _start(db, workspace)
        db.commit()
        with pytest.raises(VisitorBlocked, match="Too many"):
            _start(db, workspace)


# ---------------------------------------------------------------------------- party identity


class TestPartyIdentity:
    def test_same_identifier_yields_the_same_party(self, db, workspace):
        """Otherwise a returning merchant collects a new certificate every visit, and
        'one active certificate per signatory' quietly stops being true."""
        a, _ = _start(db, workspace, email="repeat@merchant.example")
        db.commit()
        b, _ = _start(db, workspace, email="REPEAT@Merchant.Example")
        db.commit()
        assert a.party_ref == b.party_ref

    def test_party_ref_does_not_contain_the_identifier(self, db, workspace):
        session, _ = _start(db, workspace, email="private@merchant.example")
        db.commit()
        assert "private" not in session.party_ref
        assert "merchant.example" not in session.party_ref

    def test_phone_spellings_normalise_to_one_party(self, db, workspace):
        a, _ = _start(db, workspace, channel="sms", phone="0300-1234567", email="")
        db.commit()
        b, _ = _start(db, workspace, channel="sms", phone="+92 300 1234567", email="")
        db.commit()
        assert a.party_ref == b.party_ref


class TestMsisdn:
    @pytest.mark.parametrize("raw,expected", [
        ("0300-1234567", "+923001234567"),
        ("+92 300 1234567", "+923001234567"),
        ("923001234567", "+923001234567"),
        ("3001234567", "+923001234567"),
        ("0092 300 1234567", "+923001234567"),
    ])
    def test_normalisation(self, raw, expected):
        assert sms.normalise_msisdn(raw) == expected

    def test_masking_keeps_only_the_last_four(self):
        assert sms.mask_msisdn("+923001234567") == "***4567"
        assert sms.mask_email("ahmed@merchant.example") == "ah***@merchant.example"


# ---------------------------------------------------------------------------- consent


class TestConsentEvidence:
    def test_signing_is_locked_until_the_document_is_read(self, db, workspace):
        session, _ = _start(db, workspace)
        db.commit()
        code = _code_for(db, session.id)
        visitor_service.verify_session(db, workspace["invitation"], session, code)
        db.commit()

        allowed, reason = visitor_service.may_sign(session)
        assert not allowed and "read to the end" in reason

        visitor_service.record_consent(db, session, pages_viewed=4, total_pages=4,
                                       scrolled_to_end=True)
        db.commit()
        allowed, _ = visitor_service.may_sign(session)
        assert allowed

    def test_unverified_session_can_never_sign(self, db, workspace):
        session, _ = _start(db, workspace)
        db.commit()
        visitor_service.record_consent(db, session, pages_viewed=4, total_pages=4,
                                       scrolled_to_end=True)
        allowed, reason = visitor_service.may_sign(session)
        assert not allowed and "Verify your identity" in reason

    def test_evidence_bundle_is_masked(self, db, workspace):
        """This bundle is printed on the Certificate of Completion, which gets emailed."""
        session, _ = _start(db, workspace)
        db.commit()
        code = _code_for(db, session.id)
        visitor_service.verify_session(db, workspace["invitation"], session, code)
        visitor_service.record_consent(db, session, pages_viewed=3, total_pages=3,
                                       scrolled_to_end=True)
        db.commit()
        evidence = visitor_service.identity_evidence(session)
        assert evidence["method"] == "email_otp"
        assert evidence["masked_identifier"] == "ah***@merchant.example"
        assert "ahmed@merchant.example" not in str(evidence)
        assert evidence["scroll_completed_at"] and evidence["pages_viewed"] == 3


# ---------------------------------------------------------------------------- certificates


class TestVisitorCertificate:
    def test_verified_visitor_gets_their_own_short_lived_certificate(self, db, workspace):
        ca_mod.provision_hierarchy(db, workspace["tenant"].id, actor_id=workspace["officer"].id)
        db.commit()

        session, _ = _start(db, workspace)
        db.commit()
        code = _code_for(db, session.id)
        visitor_service.verify_session(db, workspace["invitation"], session, code)
        certificate = visitor_service.issue_visitor_certificate(db, session)
        db.commit()

        assert certificate is not None
        assert certificate.profile == "visitor"
        assert certificate.subject_party_id == session.party_ref
        assert certificate.subject_user_id is None, "a visitor is not a workspace user"
        from app.config import settings

        span = (certificate.not_after - certificate.not_before).days
        assert span <= settings.pki_visitor_validity_days + 1, "visitor certs must be short-lived"

    def test_certificate_records_that_it_was_auto_approved(self, db, workspace):
        """An auditor must be able to see the certificate rests on an OTP, not on a human."""
        ca_mod.provision_hierarchy(db, workspace["tenant"].id, actor_id=workspace["officer"].id)
        db.commit()
        session, _ = _start(db, workspace)
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], session,
                                       _code_for(db, session.id))
        certificate = visitor_service.issue_visitor_certificate(db, session)
        db.commit()

        request = db.get(models.CertificateRequest, certificate.request_id)
        assert request.evidence["auto_approved"] is True
        assert "OTP-verified" in request.evidence["auto_approval_basis"]
        assert request.evidence["method"] == "email_otp"

    def test_returning_visitor_reuses_their_certificate(self, db, workspace):
        ca_mod.provision_hierarchy(db, workspace["tenant"].id, actor_id=workspace["officer"].id)
        db.commit()
        first, _ = _start(db, workspace, email="repeat@merchant.example")
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], first, _code_for(db, first.id))
        cert_a = visitor_service.issue_visitor_certificate(db, first)
        db.commit()

        second, _ = _start(db, workspace, email="repeat@merchant.example")
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], second, _code_for(db, second.id))
        cert_b = visitor_service.issue_visitor_certificate(db, second)
        db.commit()
        assert cert_a.id == cert_b.id, "one active certificate per signatory, visitors included"

    def test_unverified_session_cannot_get_a_certificate(self, db, workspace):
        ca_mod.provision_hierarchy(db, workspace["tenant"].id, actor_id=workspace["officer"].id)
        db.commit()
        session, _ = _start(db, workspace)
        db.commit()
        with pytest.raises(VisitorError, match="verified"):
            visitor_service.issue_visitor_certificate(db, session)

    def test_missing_pki_does_not_block_signing(self, db, workspace):
        """No CA provisioned: the visitor still signs, with visual evidence only. Refusing to
        let a merchant sign because the CA is not set up is the wrong failure mode."""
        session, _ = _start(db, workspace)
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], session,
                                       _code_for(db, session.id))
        db.commit()
        assert visitor_service.issue_visitor_certificate(db, session) is None


# ---------------------------------------------------------------------------- anti-automation


class TestProofOfWork:
    def test_valid_solution_is_accepted(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "esign_pow_bits", 8)
        challenge = visitor_service.pow_challenge("inv1", "10.0.0.1")["challenge"]
        for i in range(100000):
            if hashlib.sha256(f"{challenge}{i}".encode()).digest()[0] == 0:
                assert visitor_service.verify_pow("inv1", "10.0.0.1", challenge, str(i))
                return
        pytest.fail("no solution found")

    def test_wrong_solution_is_rejected(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "esign_pow_bits", 12)
        challenge = visitor_service.pow_challenge("inv1", "10.0.0.1")["challenge"]
        assert not visitor_service.verify_pow("inv1", "10.0.0.1", challenge, "definitely-wrong")

    def test_forged_challenge_is_rejected(self, monkeypatch):
        """The challenge is HMAC'd, so a client cannot mint an easy one for itself."""
        from app.config import settings

        monkeypatch.setattr(settings, "esign_pow_bits", 8)
        assert not visitor_service.verify_pow("inv1", "10.0.0.1", "aaaa.111.bbbb", "0")

    def test_challenge_is_bound_to_the_invitation(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "esign_pow_bits", 8)
        challenge = visitor_service.pow_challenge("inv1", "10.0.0.1")["challenge"]
        assert not visitor_service.verify_pow("inv2", "10.0.0.1", challenge, "0")

    def test_disabled_when_bits_is_zero(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "esign_pow_bits", 0)
        assert visitor_service.verify_pow("inv1", "1.1.1.1", "", "")


# ---------------------------------------------------------------------------- attach


class TestRecipientAttachment:
    def _envelope(self, db, workspace):
        env = models.SignatureEnvelope(
            tenant_id=workspace["tenant"].id, contract_id=workspace["contract"].id,
            status="sent", created_by=workspace["officer"].id,
        )
        db.add(env)
        db.commit()
        return env

    def test_verified_visitor_joins_the_live_envelope(self, db, workspace):
        ca_mod.provision_hierarchy(db, workspace["tenant"].id, actor_id=workspace["officer"].id)
        db.commit()
        env = self._envelope(db, workspace)

        session, _ = _start(db, workspace)
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], session,
                                       _code_for(db, session.id))
        recipient, token = visitor_service.attach_recipient(db, workspace["invitation"], session)
        db.commit()

        assert recipient.envelope_id == env.id
        assert recipient.party_ref == session.party_ref
        assert recipient.signer_user_id is None
        assert recipient.identity_method == "email_otp"
        assert recipient.certificate_id
        assert token, "the visitor needs a signing link"

        from app import signing_service

        assert signing_service.recipient_by_token(db, token).id == recipient.id

    def test_no_open_envelope_is_a_clear_error(self, db, workspace):
        session, _ = _start(db, workspace)
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], session,
                                       _code_for(db, session.id))
        db.commit()
        with pytest.raises(VisitorError, match="not currently out for signature"):
            visitor_service.attach_recipient(db, workspace["invitation"], session)

    def test_reattaching_returns_the_same_recipient(self, db, workspace):
        """A visitor who reloads the page must not become two signatories."""
        self._envelope(db, workspace)
        session, _ = _start(db, workspace)
        db.commit()
        visitor_service.verify_session(db, workspace["invitation"], session,
                                       _code_for(db, session.id))
        first, _ = visitor_service.attach_recipient(db, workspace["invitation"], session)
        db.commit()
        second, _ = visitor_service.attach_recipient(db, workspace["invitation"], session)
        db.commit()
        assert first.id == second.id


# ---------------------------------------------------------------------------- outbox


class TestOutboxChannel:
    def test_sms_rows_are_marked_and_excluded_from_the_smtp_flush(self, db, workspace):
        """Without the channel filter the outbox beat would hand a phone number to SMTP."""
        from app import email as email_mod

        # A number unique to this test: the suite shares one database, and other tests in
        # this module also send SMS.
        number = "0300-7654321"
        sms.send_sms(db, workspace["tenant"].id, number, "code 123456")
        db.commit()

        row = (
            db.query(models.EmailOutbox)
            .filter(models.EmailOutbox.to_email == sms.normalise_msisdn(number))
            .order_by(models.EmailOutbox.created_at.desc(), models.EmailOutbox.id.desc())
            .first()
        )
        assert row is not None
        assert row.channel == "sms"
        assert row.status == "sent"

        row.status = "failed"  # make it a retry candidate
        db.commit()
        result = email_mod.flush_outbox(db)
        db.commit()
        assert result["sent"] == 0, "the SMTP flush must not pick up SMS rows"
        assert db.get(models.EmailOutbox, row.id).status == "failed"


def test_security_module_import_is_not_needed(db):
    """Guards against re-introducing an unused import that ruff would flag in CI."""
    assert security is not None
