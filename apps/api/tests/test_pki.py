"""PKI — CA hierarchy, RA workflow, certificate lifecycle, CRL, OCSP, path validation.

These are the acceptance criteria from the Phase 1 brief, written as tests:

    issue → validate chain → revoke → OCSP says revoked and the serial appears in the CRL
    renewal preserves the subject binding and issues a new serial
    suspension blocks signing; resumption restores it
    shared-certificate issuance is rejected
    the keystore round-trips without ever exposing key material to callers
    path validation accepts a valid third-party chain and rejects an expired or revoked one

The cryptography is verified against the actual bytes — chains are verified with the issuer's
public key, the CRL is checked for the serial, OCSP responses are parsed back. A test that only
asserted on our own database columns would pass just as happily against a CA that emits
malformed certificates.

Requirements: PKI-01, PKI-02, PKI-03, PKI-04, PKI-05, PKI-08, PKI-09.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import ocsp as ocsp_mod
from cryptography.x509.oid import NameOID
from sqlalchemy import text as sa_text

from app import models, security
from app.pki import ca as ca_mod
from app.pki import crl as crl_mod
from app.pki import lifecycle, ocsp, ra, validate
from app.pki.keystore import KeySpec, SoftKeyStore
from app.pki.lifecycle import PkiError


# ---------------------------------------------------------------------------- fixtures


@pytest.fixture()
def workspace(db, make_user):
    """A tenant with an RA officer, an ordinary signatory, and a provisioned PKI."""
    officer, tenant = make_user(name="RA Officer")
    signatory = models.User(
        tenant_id=tenant.id, email=f"s{uuid.uuid4().hex[:8]}@example.com", name="Ali Raza",
        password_hash=security.hash_password("Str0ng!Passw0rd1"), role="author",
    )
    db.add(signatory)
    db.commit()
    root, issuing = ca_mod.provision_hierarchy(db, tenant.id, actor_id=officer.id)
    db.commit()
    return {"tenant": tenant, "officer": officer, "signatory": signatory,
            "root": root, "issuing": issuing}


def _issue(db, ws, user=None):
    """enrol → approve → issue, the only supported route to a certificate."""
    subject = user or ws["signatory"]
    req = ra.enrol_internal_user(db, subject, actor=ws["officer"])
    db.commit()
    ra.approve(db, req, officer=ws["officer"], note="verified")
    db.commit()
    cert = lifecycle.issue_from_request(db, req, actor=ws["officer"])
    db.commit()
    return cert


def _verify_signed_by(child_pem: str, issuer_pem: str) -> None:
    """Raises if the child was not actually signed by the issuer's key."""
    child = ca_mod.from_pem(child_pem)
    issuer = ca_mod.from_pem(issuer_pem)
    issuer.public_key().verify(
        child.signature, child.tbs_certificate_bytes, ec.ECDSA(child.signature_hash_algorithm)
    )


# ---------------------------------------------------------------------------- hierarchy


class TestHierarchy:
    def test_root_is_self_signed_and_issuing_chains_to_it(self, db, workspace):
        _verify_signed_by(workspace["root"].pem, workspace["root"].pem)
        _verify_signed_by(workspace["issuing"].pem, workspace["root"].pem)

    def test_issuing_ca_cannot_mint_further_cas(self, db, workspace):
        """path_length=0 — a compromised issuing CA cannot extend the hierarchy."""
        bc = ca_mod.from_pem(workspace["issuing"].pem).extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value
        assert bc.ca is True
        assert bc.path_length == 0

    def test_ocsp_responder_certificate_is_delegated_and_marked(self, db, workspace):
        responder = ca_mod.get_ocsp_responder(db, workspace["tenant"].id)
        assert responder is not None
        cert = ca_mod.from_pem(responder.pem)
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        assert x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING in eku
        # OCSPNoCheck stops relying parties recursing into the responder's own status.
        cert.extensions.get_extension_for_class(x509.OCSPNoCheck)
        # It must be signed by the issuing CA, not by the root.
        _verify_signed_by(responder.pem, workspace["issuing"].pem)

    def test_provisioning_is_idempotent(self, db, workspace):
        root2, issuing2 = ca_mod.provision_hierarchy(db, workspace["tenant"].id)
        db.commit()
        assert issuing2.id == workspace["issuing"].id

    def test_serial_numbers_are_unpredictable(self, db, workspace):
        """A guessable serial lets an attacker probe OCSP for unissued certificates."""
        serials = {ca_mod.new_serial() for _ in range(50)}
        assert len(serials) == 50
        assert all(s.bit_length() > 64 for s in serials)


# ---------------------------------------------------------------------------- keystore


class TestKeyStore:
    def test_private_key_is_never_returned_by_the_interface(self):
        """There is deliberately no `export_private_key` — a caller cannot serialise a key out,
        which is what lets HSM and software stores share one code path."""
        assert not hasattr(SoftKeyStore, "export_private_key")

    def test_key_material_is_encrypted_at_rest(self, db, monkeypatch):
        """A database dump must not yield a signing key.

        The Fernet chain is configured explicitly here rather than relying on the ambient
        environment: without `MFA_ENCRYPTION_KEYS` the `EncryptedString` type passes values
        through by design (the dev default), so a test that just read whatever the current env
        produced would silently stop asserting anything in CI.
        """
        from cryptography.fernet import Fernet

        from app import secrets_box
        from app.config import settings

        monkeypatch.setattr(settings, "mfa_encryption_keys", Fernet.generate_key().decode())
        secrets_box.reset_for_tests()
        try:
            store = SoftKeyStore()
            key_id = f"test-{uuid.uuid4().hex}"
            store.generate_keypair(db, key_id, KeySpec("ec-p256"))
            db.flush()

            # Raw SQL, deliberately: selecting through the mapped column would run the
            # `EncryptedString` result processor and hand back the *decrypted* value, so the
            # test would pass even if nothing were ever encrypted.
            raw = db.execute(
                sa_text("SELECT material FROM pki_keys WHERE id = :id"), {"id": key_id}
            ).scalar_one()
            assert "BEGIN PRIVATE KEY" not in raw, "private key written to the database in the clear"
            assert "MII" not in raw, "base64 DER visible in the stored value"

            # …and it must still decrypt back to a usable key.
            sig = store.sign(db, key_id, b"payload")
            store.public_key(db, key_id).verify(sig, b"payload", ec.ECDSA(hashes.SHA256()))
        finally:
            secrets_box.reset_for_tests()

    def test_sign_round_trips_against_the_public_key(self, db):
        store = SoftKeyStore()
        key_id = f"test-{uuid.uuid4().hex}"
        store.generate_keypair(db, key_id, KeySpec("ec-p256"))
        db.flush()
        sig = store.sign(db, key_id, b"payload")
        store.public_key(db, key_id).verify(sig, b"payload", ec.ECDSA(hashes.SHA256()))

    def test_destroy_removes_the_key(self, db):
        store = SoftKeyStore()
        key_id = f"test-{uuid.uuid4().hex}"
        store.generate_keypair(db, key_id, KeySpec("ec-p256"))
        assert store.exists(db, key_id)
        store.destroy(db, key_id)
        assert not store.exists(db, key_id)


# ---------------------------------------------------------------------------- RA


class TestRegistrationAuthority:
    def test_certificate_cannot_be_issued_without_an_approved_request(self, db, workspace):
        req = ra.enrol_internal_user(db, workspace["signatory"], actor=workspace["officer"])
        db.commit()
        assert req.status == "pending"
        with pytest.raises(PkiError, match="approved"):
            lifecycle.issue_from_request(db, req, actor=workspace["officer"])

    def test_rejected_request_cannot_be_issued(self, db, workspace):
        req = ra.enrol_internal_user(db, workspace["signatory"], actor=workspace["officer"])
        db.commit()
        ra.reject(db, req, officer=workspace["officer"], note="identity not verified")
        db.commit()
        with pytest.raises(PkiError):
            lifecycle.issue_from_request(db, req, actor=workspace["officer"])

    def test_officer_cannot_approve_their_own_request(self, db, workspace):
        """Separation of duties. Self-issuance defeats the point of having an RA."""
        req = ra.enrol_internal_user(db, workspace["officer"], actor=workspace["officer"])
        db.commit()
        with pytest.raises(PkiError, match="own certificate request"):
            ra.approve(db, req, officer=workspace["officer"])

    def test_non_admin_cannot_act_as_ra_officer(self, db, workspace):
        req = ra.enrol_internal_user(db, workspace["signatory"], actor=workspace["officer"])
        db.commit()
        with pytest.raises(PkiError, match="Registration Authority"):
            ra.approve(db, req, officer=workspace["signatory"])

    def test_duplicate_open_request_is_refused(self, db, workspace):
        ra.enrol_internal_user(db, workspace["signatory"], actor=workspace["officer"])
        db.commit()
        with pytest.raises(PkiError, match="open enrolment request"):
            ra.enrol_internal_user(db, workspace["signatory"], actor=workspace["officer"])

    def test_dual_control_requires_two_distinct_officers(self, db, workspace, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ra_dual_control", True)
        second = models.User(
            tenant_id=workspace["tenant"].id, email=f"o{uuid.uuid4().hex[:8]}@example.com",
            name="Second Officer", password_hash=security.hash_password("Str0ng!Passw0rd1"),
            role="admin",
        )
        db.add(second)
        db.commit()

        req = ra.enrol_internal_user(db, workspace["signatory"], actor=workspace["officer"])
        db.commit()

        ra.approve(db, req, officer=workspace["officer"], note="first")
        db.commit()
        assert req.status == "pending", "one approval must not be enough under dual control"

        with pytest.raises(PkiError, match="two different RA officers"):
            ra.approve(db, req, officer=workspace["officer"], note="again")

        ra.approve(db, req, officer=second, note="second")
        db.commit()
        assert req.status == "approved"
        assert req.reviewed_by != req.second_reviewed_by

    def test_identity_evidence_is_carried_into_the_certificate_audit_entry(self, db, workspace):
        cert = _issue(db, workspace)
        entry = db.query(models.AuditLog).filter(
            models.AuditLog.action == "pki.certificate.issued",
            models.AuditLog.object_id == cert.id,
        ).one()
        assert entry.meta["identity_evidence"]["email"] == workspace["signatory"].email


# ---------------------------------------------------------------------------- issuance


class TestIssuance:
    def test_issued_certificate_chains_to_the_issuing_ca(self, db, workspace):
        cert = _issue(db, workspace)
        _verify_signed_by(cert.pem, workspace["issuing"].pem)

    def test_certificate_is_bound_to_the_signatory(self, db, workspace):
        cert = _issue(db, workspace)
        parsed = ca_mod.from_pem(cert.pem)
        cn = parsed.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        assert cn == workspace["signatory"].name
        assert cert.subject_user_id == workspace["signatory"].id
        san = parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert workspace["signatory"].email in san.get_values_for_type(x509.RFC822Name)

    def test_certificate_carries_non_repudiation(self, db, workspace):
        """contentCommitment is what makes this a signature certificate rather than an
        authentication one — without it the signature means much less legally."""
        cert = _issue(db, workspace)
        ku = ca_mod.from_pem(cert.pem).extensions.get_extension_for_class(x509.KeyUsage).value
        assert ku.content_commitment is True
        assert ku.key_cert_sign is False, "a signatory certificate must not be able to sign certificates"

    def test_certificate_advertises_crl_and_ocsp(self, db, workspace):
        """Without CDP/AIA a relying party has no way to discover how to check revocation."""
        parsed = ca_mod.from_pem(_issue(db, workspace).pem)
        cdp = parsed.extensions.get_extension_for_class(x509.CRLDistributionPoints).value
        assert cdp[0].full_name[0].value.endswith(".crl")
        aia = parsed.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
        methods = {d.access_method for d in aia}
        assert x509.oid.AuthorityInformationAccessOID.OCSP in methods
        assert x509.oid.AuthorityInformationAccessOID.CA_ISSUERS in methods

    def test_shared_certificate_issuance_is_rejected(self, db, workspace):
        """The RFP forbids shared or role-based certificates."""
        _issue(db, workspace)
        req = models.CertificateRequest(
            tenant_id=workspace["tenant"].id, subject_dn="CN=Ali Raza",
            subject_user_id=workspace["signatory"].id,
            subject_email=workspace["signatory"].email, profile="internal", status="approved",
        )
        db.add(req)
        db.flush()
        with pytest.raises(PkiError, match="already holds active certificate"):
            lifecycle.issue_from_request(db, req, actor=workspace["officer"])

    def test_leaf_never_outlives_its_issuer(self, db, workspace):
        cert = _issue(db, workspace)
        assert cert.not_after <= workspace["issuing"].not_after


# ---------------------------------------------------------------------------- lifecycle


class TestLifecycle:
    def test_renewal_preserves_binding_and_changes_the_serial(self, db, workspace):
        original = _issue(db, workspace)
        original_serial, original_id = original.serial_number, original.id

        fresh = lifecycle.renew(db, original, actor=workspace["officer"])
        db.commit()

        assert fresh.serial_number != original_serial
        assert fresh.key_id != original.key_id, "a renewal must get a new key, not reuse the old one"
        assert fresh.subject_user_id == workspace["signatory"].id
        assert fresh.subject_dn == original.subject_dn
        assert fresh.renewed_from_id == original_id
        assert fresh.status == "active"
        # The superseded certificate must stop occupying the subject's one active slot.
        assert db.get(models.Certificate, original_id).status == "revoked"
        assert db.get(models.Certificate, original_id).revocation_reason == "superseded"
        _verify_signed_by(fresh.pem, workspace["issuing"].pem)

    def test_suspension_blocks_signing_and_resumption_restores_it(self, db, workspace):
        cert = _issue(db, workspace)
        lifecycle.assert_usable_for_signing(cert)  # baseline

        lifecycle.suspend(db, cert, actor=workspace["officer"], note="under investigation")
        db.commit()
        assert cert.status == "suspended"
        with pytest.raises(PkiError, match="suspended"):
            lifecycle.assert_usable_for_signing(cert)

        lifecycle.resume(db, cert, actor=workspace["officer"])
        db.commit()
        assert cert.status == "active"
        lifecycle.assert_usable_for_signing(cert)

    def test_revocation_is_terminal(self, db, workspace):
        cert = _issue(db, workspace)
        lifecycle.revoke(db, cert, reason="key_compromise", actor=workspace["officer"])
        db.commit()
        with pytest.raises(PkiError, match="revoked"):
            lifecycle.resume(db, cert, actor=workspace["officer"])
        with pytest.raises(PkiError, match="revoked"):
            lifecycle.suspend(db, cert, actor=workspace["officer"])
        with pytest.raises(PkiError, match="already revoked"):
            lifecycle.revoke(db, cert, reason="superseded", actor=workspace["officer"])

    def test_unknown_revocation_reason_is_rejected(self, db, workspace):
        cert = _issue(db, workspace)
        with pytest.raises(PkiError, match="Unknown revocation reason"):
            lifecycle.revoke(db, cert, reason="because_i_said_so", actor=workspace["officer"])

    def test_expired_certificate_cannot_sign(self, db, workspace):
        cert = _issue(db, workspace)
        cert.not_after = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=1)
        db.flush()
        with pytest.raises(PkiError, match="expired"):
            lifecycle.assert_usable_for_signing(cert)

    def test_expire_sweep_frees_the_subject_slot(self, db, workspace):
        cert = _issue(db, workspace)
        cert.not_after = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=1)
        db.flush()
        assert lifecycle.expire_sweep(db, workspace["tenant"].id) == 1
        db.commit()
        assert cert.status == "expired"
        # The subject may now be issued a fresh certificate.
        assert lifecycle.active_certificate_for(
            db, workspace["tenant"].id, user_id=workspace["signatory"].id
        ) is None


# ---------------------------------------------------------------------------- CRL


class TestCrl:
    def test_revoked_serial_appears_in_a_signed_crl(self, db, workspace):
        cert = _issue(db, workspace)
        lifecycle.revoke(db, cert, reason="key_compromise", actor=workspace["officer"])
        db.commit()

        der = crl_mod.publish(db, workspace["issuing"])
        db.commit()
        parsed = x509.load_der_x509_crl(der)

        assert parsed.is_signature_valid(ca_mod.from_pem(workspace["issuing"].pem).public_key())
        entry = parsed.get_revoked_certificate_by_serial_number(int(cert.serial_number, 16))
        assert entry is not None
        reason = entry.extensions.get_extension_for_class(x509.CRLReason).value
        assert reason.reason == x509.ReasonFlags.key_compromise

    def test_active_certificate_is_absent_from_the_crl(self, db, workspace):
        cert = _issue(db, workspace)
        der = crl_mod.publish(db, workspace["issuing"])
        db.commit()
        parsed = x509.load_der_x509_crl(der)
        assert parsed.get_revoked_certificate_by_serial_number(int(cert.serial_number, 16)) is None

    def test_crl_number_is_monotonic(self, db, workspace):
        first = x509.load_der_x509_crl(crl_mod.publish(db, workspace["issuing"]))
        db.commit()
        second = x509.load_der_x509_crl(crl_mod.publish(db, workspace["issuing"]))
        db.commit()
        n1 = first.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number
        n2 = second.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number
        assert n2 > n1

    def test_suspended_certificate_is_listed_as_certificate_hold(self, db, workspace):
        cert = _issue(db, workspace)
        lifecycle.suspend(db, cert, actor=workspace["officer"])
        db.commit()
        parsed = x509.load_der_x509_crl(crl_mod.publish(db, workspace["issuing"]))
        db.commit()
        entry = parsed.get_revoked_certificate_by_serial_number(int(cert.serial_number, 16))
        assert entry is not None
        assert entry.extensions.get_extension_for_class(
            x509.CRLReason
        ).value.reason == x509.ReasonFlags.certificate_hold

    def test_delta_crl_requires_a_base(self, db, workspace):
        with pytest.raises(ValueError, match="No base CRL"):
            crl_mod.generate_delta_crl(db, workspace["issuing"])

    def test_delta_crl_is_marked_as_a_delta(self, db, workspace):
        crl_mod.publish(db, workspace["issuing"])
        db.commit()
        cert = _issue(db, workspace)
        lifecycle.revoke(db, cert, reason="superseded", actor=workspace["officer"])
        db.commit()

        delta = x509.load_der_x509_crl(crl_mod.publish(db, workspace["issuing"], delta=True))
        db.commit()
        indicator = delta.extensions.get_extension_for_class(x509.DeltaCRLIndicator).value
        assert indicator.crl_number >= 1
        assert delta.get_revoked_certificate_by_serial_number(int(cert.serial_number, 16)) is not None


# ---------------------------------------------------------------------------- OCSP


class TestOcsp:
    def _ask(self, db, workspace, cert, nonce: bytes | None = None):
        leaf = ca_mod.from_pem(cert.pem)
        issuer = ca_mod.from_pem(workspace["issuing"].pem)
        der = ocsp.build_request(leaf, issuer, nonce=nonce)
        return ocsp_mod.load_der_ocsp_response(ocsp.build_response(db, workspace["tenant"].id, der))

    def test_active_certificate_is_good(self, db, workspace):
        resp = self._ask(db, workspace, _issue(db, workspace))
        assert resp.response_status == ocsp_mod.OCSPResponseStatus.SUCCESSFUL
        assert resp.certificate_status == ocsp_mod.OCSPCertStatus.GOOD

    def test_revoked_certificate_is_revoked_with_the_reason(self, db, workspace):
        cert = _issue(db, workspace)
        lifecycle.revoke(db, cert, reason="key_compromise", actor=workspace["officer"])
        db.commit()
        resp = self._ask(db, workspace, cert)
        assert resp.certificate_status == ocsp_mod.OCSPCertStatus.REVOKED
        assert resp.revocation_reason == x509.ReasonFlags.key_compromise

    def test_suspended_certificate_is_revoked_on_hold(self, db, workspace):
        cert = _issue(db, workspace)
        lifecycle.suspend(db, cert, actor=workspace["officer"])
        db.commit()
        resp = self._ask(db, workspace, cert)
        assert resp.certificate_status == ocsp_mod.OCSPCertStatus.REVOKED
        assert resp.revocation_reason == x509.ReasonFlags.certificate_hold

    def test_nonce_is_echoed(self, db, workspace):
        """RFC 6960 §4.4.1. Without the nonce, a stale `good` response can be replayed for a
        certificate that has since been revoked."""
        resp = self._ask(db, workspace, _issue(db, workspace), nonce=b"unique-nonce-1234")
        echoed = resp.extensions.get_extension_for_class(x509.OCSPNonce).value
        assert echoed.nonce == b"unique-nonce-1234"

    def test_response_is_signed_by_the_delegated_responder(self, db, workspace):
        resp = self._ask(db, workspace, _issue(db, workspace))
        responder = ca_mod.get_ocsp_responder(db, workspace["tenant"].id)
        responder_cert = ca_mod.from_pem(responder.pem)
        responder_cert.public_key().verify(
            resp.signature, resp.tbs_response_bytes, ec.ECDSA(resp.signature_hash_algorithm)
        )

    def test_unissued_serial_is_unknown_not_good(self, db, workspace):
        """`unknown` must not be conflated with `good`, or an attacker can mint a certificate
        this CA never issued and have the responder vouch for it."""
        issuer = ca_mod.from_pem(workspace["issuing"].pem)
        key = ec.generate_private_key(ec.SECP256R1())
        forged = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Forged")]))
            .issuer_name(issuer.subject)
            .public_key(key.public_key())
            .serial_number(ca_mod.new_serial())
            .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
            .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        der = ocsp.build_request(forged, issuer)
        resp = ocsp_mod.load_der_ocsp_response(
            ocsp.build_response(db, workspace["tenant"].id, der)
        )
        assert resp.certificate_status == ocsp_mod.OCSPCertStatus.UNKNOWN

    def test_malformed_request_does_not_raise(self, db, workspace):
        """This is a public unauthenticated endpoint; a parse error must not become a 500."""
        resp = ocsp_mod.load_der_ocsp_response(
            ocsp.build_response(db, workspace["tenant"].id, b"not-a-valid-ocsp-request")
        )
        assert resp.response_status == ocsp_mod.OCSPResponseStatus.MALFORMED_REQUEST

    def test_responder_identifies_the_issuer_without_a_tenant_hint(self, db, workspace):
        """The AIA URL baked into a certificate has no tenant in it, so the public endpoint
        must resolve the CA from the request's own issuer hashes."""
        cert = _issue(db, workspace)
        der = ocsp.build_request(ca_mod.from_pem(cert.pem), ca_mod.from_pem(workspace["issuing"].pem))
        resp = ocsp_mod.load_der_ocsp_response(ocsp.build_response(db, None, der))
        assert resp.certificate_status == ocsp_mod.OCSPCertStatus.GOOD

    def test_unrelated_issuer_gets_unauthorized(self, db, workspace):
        """A request for a CA we do not operate must not be answered."""
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Someone Else CA")])
        foreign_ca = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(ca_mod.new_serial())
            .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
            .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        der = ocsp.build_request(foreign_ca, foreign_ca)
        resp = ocsp_mod.load_der_ocsp_response(ocsp.build_response(db, None, der))
        assert resp.response_status == ocsp_mod.OCSPResponseStatus.UNAUTHORIZED


# ---------------------------------------------------------------------------- validation


def _external_chain(*, leaf_days: int = 365):
    """A self-contained third-party root + leaf, standing in for DigiCert et al."""
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "External Root CA")])
    now = dt.datetime.now(dt.timezone.utc)
    root = (
        x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
        .public_key(root_key.public_key()).serial_number(ca_mod.new_serial())
        .not_valid_before(now - dt.timedelta(days=10))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ), critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Overseas Signatory")])
    leaf = (
        x509.CertificateBuilder().subject_name(leaf_name).issuer_name(root_name)
        .public_key(leaf_key.public_key()).serial_number(ca_mod.new_serial())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=leaf_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ), critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )
    pem = lambda c: c.public_bytes(serialization.Encoding.PEM).decode("ascii")  # noqa: E731
    return pem(root), pem(leaf)


class TestThirdPartyValidation:
    def test_rejects_everything_when_no_trust_anchors_are_configured(self, db, workspace):
        _, leaf = _external_chain()
        result = validate.validate(db, workspace["tenant"].id, leaf, check_revocation=False)
        assert not result.ok
        assert "trust anchors" in result.reason.lower()

    def test_accepts_a_valid_third_party_chain(self, db, workspace):
        root, leaf = _external_chain()
        validate.add_trust_anchor(db, workspace["tenant"].id, root, name="External Root")
        db.commit()
        result = validate.validate(db, workspace["tenant"].id, leaf, check_revocation=False)
        assert result.ok, result.reason
        assert "Overseas Signatory" in result.chain[0]

    def test_rejects_an_expired_certificate(self, db, workspace):
        root, leaf = _external_chain()
        validate.add_trust_anchor(db, workspace["tenant"].id, root, name="External Root")
        db.commit()
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=400)
        result = validate.validate(
            db, workspace["tenant"].id, leaf, now=future, check_revocation=False
        )
        assert not result.ok
        assert "expired" in result.reason.lower()

    def test_rejects_a_certificate_from_an_untrusted_root(self, db, workspace):
        root_a, _ = _external_chain()
        _, leaf_b = _external_chain()
        validate.add_trust_anchor(db, workspace["tenant"].id, root_a, name="Root A")
        db.commit()
        result = validate.validate(db, workspace["tenant"].id, leaf_b, check_revocation=False)
        assert not result.ok
        assert "no trusted path" in result.reason.lower()

    def test_our_own_certificates_validate_against_our_own_root(self, db, workspace):
        validate.add_trust_anchor(
            db, workspace["tenant"].id, workspace["root"].pem, name="Internal Root", source="internal"
        )
        db.commit()
        cert = _issue(db, workspace)
        result = validate.validate(
            db, workspace["tenant"].id, cert.pem,
            intermediate_pems=[workspace["issuing"].pem], check_revocation=False,
        )
        assert result.ok, result.reason
        assert len(result.chain) == 3  # leaf -> issuing -> root

    def test_adding_the_same_anchor_twice_does_not_duplicate(self, db, workspace):
        root, _ = _external_chain()
        a = validate.add_trust_anchor(db, workspace["tenant"].id, root, name="R")
        db.commit()
        b = validate.add_trust_anchor(db, workspace["tenant"].id, root, name="R")
        db.commit()
        assert a.id == b.id


# ---------------------------------------------------------------------------- ECAC


class TestEcacReadiness:
    def test_cross_certification_preserves_existing_certificates(self, db, workspace):
        """The RFP asks that the issuing CA can be re-chained to an ECAC-accredited root
        without re-architecture and **without reissuing existing certificates**.

        The proof: issue a certificate, cross-certify the issuing CA under a new root, and
        show the original certificate still verifies — because the issuing CA kept its key.
        """
        cert = _issue(db, workspace)
        original_pem = cert.pem

        # Stand in for the accredited root.
        from app.pki.keystore import get_keystore

        store = get_keystore()
        ecac_key_id = f"ecac-{uuid.uuid4().hex[:8]}"
        store.generate_keypair(db, ecac_key_id, KeySpec("ec-p384"))
        ecac_name = ca_mod.build_name("ECAC Accredited Root", org_unit="ECAC")
        now = dt.datetime.now(dt.timezone.utc)
        ecac_cert = ca_mod.build_ca_certificate(
            subject=ecac_name, subject_public_key=store.public_key(db, ecac_key_id),
            issuer_name=ecac_name, issuer_signer=store.signer_for(db, ecac_key_id),
            issuer_spec=KeySpec("ec-p384"), not_before=now,
            not_after=now + dt.timedelta(days=3650), serial=ca_mod.new_serial(), path_length=1,
        )

        cross = ca_mod.cross_certify(
            db, workspace["issuing"], parent_pem=ca_mod.to_pem(ecac_cert),
            parent_key_id=ecac_key_id, parent_algorithm="ec-p384",
        )
        db.commit()

        # Same CA identity, new chain.
        assert cross.subject_dn == workspace["issuing"].subject_dn
        assert cross.key_id == workspace["issuing"].key_id
        assert cross.serial_number != workspace["issuing"].serial_number

        # The untouched certificate now validates under the ECAC root.
        validate.add_trust_anchor(
            db, workspace["tenant"].id, ca_mod.to_pem(ecac_cert), name="ECAC Root"
        )
        db.commit()
        result = validate.validate(
            db, workspace["tenant"].id, original_pem,
            intermediate_pems=[cross.pem], check_revocation=False,
        )
        assert result.ok, result.reason
        assert db.get(models.Certificate, cert.id).pem == original_pem, "nothing was reissued"

    def test_trust_anchors_live_in_the_database_not_a_file(self, db, workspace):
        """Runtime-extensible trust is what makes ECAC chaining a config change rather than a
        redeploy."""
        root, _ = _external_chain()
        validate.add_trust_anchor(db, workspace["tenant"].id, root, name="Late Addition")
        db.commit()
        assert any(
            a.subject.rfc4514_string().endswith("External Root CA")
            for a in validate.load_trust_anchors(db, workspace["tenant"].id)
        )


# ---------------------------------------------------------------------------- isolation


class TestTenantIsolation:
    def test_certificates_do_not_leak_between_tenants(self, db, workspace, make_user):
        cert = _issue(db, workspace)
        other_officer, other_tenant = make_user(name="Other Officer")
        ca_mod.provision_hierarchy(db, other_tenant.id, actor_id=other_officer.id)
        db.commit()
        assert lifecycle.active_certificate_for(
            db, other_tenant.id, user_id=workspace["signatory"].id
        ) is None
        assert cert.tenant_id == workspace["tenant"].id
