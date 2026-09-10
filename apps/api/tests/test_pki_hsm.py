"""PKCS#11 keystore, exercised against a real token.

The RFP requires HSM-protected keys at FIPS 140-2 Level 3. CI cannot have such a device, but
it *can* have SoftHSM2 — a software token that speaks the same PKCS#11 API. Running the real
`Pkcs11KeyStore` against it proves the code path works end to end (generate inside the token,
sign inside the token, never export), which is the part that would otherwise be untested
scaffolding until the day someone plugs in a Luna.

What SoftHSM2 does **not** prove: tamper resistance, FIPS validation, or key-ceremony
controls. Those are properties of the device, not of this code. See docs/PKI-ARCHITECTURE.md.

Skipped unless `HSM_LIBRARY_PATH` is set. CI sets it (see the `pki-hsm` job in ci.yml):

    sudo apt-get install -y softhsm2
    softhsm2-util --init-token --slot 0 --label cm-test --pin 1234 --so-pin 1234
    export HSM_LIBRARY_PATH=/usr/lib/softhsm/libsofthsm2.so HSM_TOKEN_LABEL=cm-test HSM_PIN=1234

Requirements: PKI-06, PKI-07.
"""

from __future__ import annotations

import os
import uuid

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app.pki.keystore import KeySpec

pytestmark = [
    pytest.mark.hsm,
    pytest.mark.skipif(
        not os.environ.get("HSM_LIBRARY_PATH"),
        reason="no PKCS#11 token configured (set HSM_LIBRARY_PATH)",
    ),
]


@pytest.fixture()
def hsm_store():
    pytest.importorskip("pkcs11", reason="python-pkcs11 not installed (requirements-pki.txt)")
    from app.config import settings
    from app.pki.keystore import Pkcs11KeyStore

    settings.hsm_library_path = os.environ["HSM_LIBRARY_PATH"]
    settings.hsm_token_label = os.environ.get("HSM_TOKEN_LABEL", "")
    settings.hsm_slot = int(os.environ.get("HSM_SLOT", "0"))
    settings.hsm_pin = os.environ.get("HSM_PIN", "")
    return Pkcs11KeyStore()


@pytest.fixture()
def key_id(hsm_store):
    kid = f"cm-test-{uuid.uuid4().hex[:12]}"
    yield kid
    try:
        hsm_store.destroy(None, kid)
    except Exception:  # noqa: BLE001
        pass


def test_key_is_generated_inside_the_token(hsm_store, key_id):
    hsm_store.generate_keypair(None, key_id, KeySpec("ec-p256"))
    assert hsm_store.exists(None, key_id)


def test_private_key_cannot_be_extracted(hsm_store, key_id):
    """The whole point of an HSM. CKA_SENSITIVE + CKA_EXTRACTABLE=false mean the token
    refuses to hand the value back — verified here against the token, not asserted from our
    own code."""
    import pkcs11
    from pkcs11 import Attribute, ObjectClass

    hsm_store.generate_keypair(None, key_id, KeySpec("ec-p256"))
    with hsm_store._open() as session:
        priv = next(iter(session.get_objects({
            Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.LABEL: key_id,
        })))
        assert priv[Attribute.SENSITIVE] is True
        assert priv[Attribute.EXTRACTABLE] is False
        with pytest.raises((pkcs11.exceptions.AttributeSensitive,
                            pkcs11.exceptions.AttributeTypeInvalid, Exception)):
            _ = priv[Attribute.VALUE]


def test_signature_verifies_against_the_token_public_key(hsm_store, key_id):
    """Signing happens inside the token; the DER re-encoding of the raw r||s output is the
    step most likely to be wrong, so verify with `cryptography` rather than trusting it."""
    hsm_store.generate_keypair(None, key_id, KeySpec("ec-p256"))
    payload = b"contract-digest"
    sig = hsm_store.sign(None, key_id, payload)
    hsm_store.public_key(None, key_id).verify(sig, payload, ec.ECDSA(hashes.SHA256()))


def test_signer_proxy_drives_a_real_certificate_build(hsm_store, key_id):
    """`ca.py` hands `KeyStore.signer_for()` straight to `x509.CertificateBuilder.sign()`.
    That only works if the proxy satisfies the duck-type `cryptography` expects — which is
    exactly what would break silently between the software and HSM paths."""
    import datetime as dt

    from cryptography import x509
    from cryptography.x509.oid import NameOID

    hsm_store.generate_keypair(None, key_id, KeySpec("ec-p256"))
    signer = hsm_store.signer_for(None, key_id)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "HSM Test CA")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(hsm_store.public_key(None, key_id))
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(signer, hashes.SHA256())
    )
    cert.public_key().verify(
        cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(cert.signature_hash_algorithm)
    )


def test_rsa_keys_work_too(hsm_store, key_id):
    """Some HSM estates are RSA-only; the mechanism mapping must cover both families."""
    from cryptography.hazmat.primitives.asymmetric import padding

    hsm_store.generate_keypair(None, key_id, KeySpec("rsa-2048"))
    sig = hsm_store.sign(None, key_id, b"payload")
    hsm_store.public_key(None, key_id).verify(
        sig, b"payload", padding.PKCS1v15(), hashes.SHA256()
    )


def test_destroy_removes_the_key_from_the_token(hsm_store, key_id):
    hsm_store.generate_keypair(None, key_id, KeySpec("ec-p256"))
    hsm_store.destroy(None, key_id)
    assert not hsm_store.exists(None, key_id)


def test_full_hierarchy_provisions_on_the_token(db, make_user, hsm_store, monkeypatch):
    """The acceptance case: a CA whose keys only ever exist inside the HSM."""
    from app.config import settings
    from app.pki import ca as ca_mod
    from app.pki import keystore as ks

    monkeypatch.setattr(settings, "keystore_provider", "pkcs11")
    ks.reset_keystore()
    try:
        _, tenant = make_user()
        root, issuing = ca_mod.provision_hierarchy(db, tenant.id)
        db.commit()
        assert ca_mod.from_pem(issuing.pem).subject.rfc4514_string() == issuing.subject_dn
        # Nothing landed in the software key table.
        from app import models

        assert db.get(models.PkiKey, issuing.key_id) is None
        assert db.get(models.PkiKey, root.key_id) is None
    finally:
        ks.reset_keystore()
