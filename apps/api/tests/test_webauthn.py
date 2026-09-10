"""FIDO2 / WebAuthn (Phase 8, item 1).

These tests drive a **real software authenticator** — a genuine ES256 key pair, a real CBOR
attestation object, a real signature over `authenticatorData || SHA256(clientDataJSON)`. The
library verifies it exactly as it would verify a YubiKey.

That matters more than usual here. A test that stubs out `verify_registration_response` proves
only that the code calls a function; the failure mode with WebAuthn is an authenticator that
appears to enrol and authenticates nothing, and a stub reproduces that failure perfectly while
staying green. So the authenticator below is ~70 lines of the real thing.

Requirements: SEC-03.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app import models, webauthn_service
from app.config import settings

RP_ID = "cm.test"
ORIGIN = "https://cm.test"


# ---------------------------------------------------------------------------------------
# A software authenticator
# ---------------------------------------------------------------------------------------


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class SoftAuthenticator:
    """The smallest thing that a real WebAuthn verifier accepts."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps({
            1: 2,        # kty: EC2
            3: -7,       # alg: ES256
            -1: 1,       # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        })

    def _authenticator_data(self, *, attested: bool, sign_count: int) -> bytes:
        # UP (0x01) | UV (0x04), plus AT (0x40) when the attested credential data is present.
        flags = 0x01 | 0x04 | (0x40 if attested else 0x00)
        data = hashlib.sha256(RP_ID.encode()).digest() + bytes([flags])
        data += sign_count.to_bytes(4, "big")
        if attested:
            data += b"\x00" * 16                                   # AAGUID
            data += len(self.credential_id).to_bytes(2, "big")
            data += self.credential_id
            data += self._cose_key()
        return data

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({
            "type": kind, "challenge": challenge, "origin": ORIGIN, "crossOrigin": False,
        }).encode()

    def register(self, options: dict) -> dict:
        client_data = self._client_data("webauthn.create", options["challenge"])
        auth_data = self._authenticator_data(attested=True, sign_count=self.sign_count)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": _b64(self.credential_id),
            "rawId": _b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64(client_data),
                "attestationObject": _b64(attestation),
            },
            "transports": ["usb"],
            "clientExtensionResults": {},
        }

    def assert_(self, options: dict, *, sign_count: int | None = None) -> dict:
        if sign_count is None:
            self.sign_count += 1
            sign_count = self.sign_count
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = self._authenticator_data(attested=False, sign_count=sign_count)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": _b64(self.credential_id),
            "rawId": _b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64(client_data),
                "authenticatorData": _b64(auth_data),
                "signature": _b64(signature),
                "userHandle": None,
            },
            "clientExtensionResults": {},
        }


@pytest.fixture()
def passkeys_on(monkeypatch):
    monkeypatch.setattr(settings, "webauthn_enabled", True)
    monkeypatch.setattr(settings, "webauthn_rp_id", RP_ID)
    monkeypatch.setattr(settings, "webauthn_rp_name", "CM Test")
    monkeypatch.setattr(settings, "webauthn_origin", ORIGIN)
    webauthn_service._challenges.clear()
    yield
    webauthn_service._challenges.clear()


@pytest.fixture()
def enrolled(db, make_user, passkeys_on):
    """A user with one registered passkey, plus the authenticator that holds its key."""
    user, _tenant = make_user()
    user = db.merge(user)
    auth = SoftAuthenticator()
    options = webauthn_service.begin_registration(db, user)
    webauthn_service.finish_registration(db, user, auth.register(options), label="Yubi 5")
    db.commit()
    return user, auth


# ---------------------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------------------


def test_registration_stores_only_a_public_key(db, enrolled):
    """A breach of this table must not yield anything an attacker can authenticate with."""
    user, auth = enrolled
    row = webauthn_service.credentials_for(db, user)[0]

    assert row.credential_id == _b64(auth.credential_id)
    assert row.label == "Yubi 5"
    # The stored key is a COSE *public* key. The private key never leaves the authenticator,
    # so there is nothing here to steal.
    assert _unb64(row.public_key) == auth._cose_key()
    private = auth.key.private_numbers().private_value.to_bytes(32, "big")
    assert private not in _unb64(row.public_key)


def test_registration_is_audited(db, enrolled):
    user, _auth = enrolled
    actions = [a.action for a in db.query(models.AuditLog)
               .filter(models.AuditLog.tenant_id == user.tenant_id).all()]
    assert "webauthn.registered" in actions


def test_a_tampered_attestation_is_refused(db, make_user, passkeys_on):
    """The signature covers the client data. Change the origin and it must not verify."""
    user, _tenant = make_user()
    user = db.merge(user)
    auth = SoftAuthenticator()
    options = webauthn_service.begin_registration(db, user)
    credential = auth.register(options)
    forged = json.loads(_unb64(credential["response"]["clientDataJSON"]))
    forged["origin"] = "https://cm.test.evil"
    credential["response"]["clientDataJSON"] = _b64(json.dumps(forged).encode())

    with pytest.raises(webauthn_service.WebAuthnError):
        webauthn_service.finish_registration(db, user, credential)
    assert webauthn_service.credentials_for(db, user) == []


def test_the_same_key_cannot_enrol_twice(db, enrolled):
    user, auth = enrolled
    options = webauthn_service.begin_registration(db, user)
    with pytest.raises(webauthn_service.WebAuthnError, match="already registered"):
        webauthn_service.finish_registration(db, user, auth.register(options))


def test_a_challenge_is_single_use(db, make_user, passkeys_on):
    """Consumed on use — otherwise a captured response could be replayed inside the TTL."""
    user, _tenant = make_user()
    user = db.merge(user)
    auth = SoftAuthenticator()
    options = webauthn_service.begin_registration(db, user)
    credential = auth.register(options)
    webauthn_service.finish_registration(db, user, credential)

    with pytest.raises(webauthn_service.WebAuthnError, match="No pending challenge"):
        webauthn_service.finish_registration(db, user, credential)


def test_an_expired_challenge_is_refused(db, make_user, passkeys_on, monkeypatch):
    import datetime as dt

    user, _tenant = make_user()
    user = db.merge(user)
    auth = SoftAuthenticator()
    options = webauthn_service.begin_registration(db, user)

    later = webauthn_service._now() + webauthn_service.CHALLENGE_TTL + dt.timedelta(seconds=1)
    monkeypatch.setattr(webauthn_service, "_now", lambda: later)
    with pytest.raises(webauthn_service.WebAuthnError, match="expired"):
        webauthn_service.finish_registration(db, user, auth.register(options))


def test_disabled_when_not_configured(db, make_user, monkeypatch):
    monkeypatch.setattr(settings, "webauthn_enabled", False)
    user, _tenant = make_user()
    user = db.merge(user)
    with pytest.raises(webauthn_service.WebAuthnError, match="not configured"):
        webauthn_service.begin_registration(db, user)


# ---------------------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------------------


def test_a_real_assertion_verifies(db, enrolled):
    user, auth = enrolled
    options = webauthn_service.begin_authentication(db, user)
    row = webauthn_service.finish_authentication(db, user, auth.assert_(options))

    assert row.last_used_at is not None
    assert row.sign_count == auth.sign_count


def test_a_forged_signature_does_not_verify(db, enrolled):
    """A different key over the same challenge must fail — that is the whole guarantee."""
    user, auth = enrolled
    impostor = SoftAuthenticator()
    impostor.credential_id = auth.credential_id      # claims to be the enrolled key
    options = webauthn_service.begin_authentication(db, user)

    with pytest.raises(webauthn_service.WebAuthnError, match="did not verify"):
        webauthn_service.finish_authentication(db, user, impostor.assert_(options))


def test_a_counter_that_does_not_advance_is_refused(db, enrolled):
    """The clone signal. An authenticator that reports a counter it has already used has
    either been copied or is replaying; both are reasons to stop."""
    user, auth = enrolled
    options = webauthn_service.begin_authentication(db, user)
    webauthn_service.finish_authentication(db, user, auth.assert_(options))
    stored = webauthn_service.credentials_for(db, user)[0].sign_count
    assert stored > 0

    options = webauthn_service.begin_authentication(db, user)
    with pytest.raises(webauthn_service.WebAuthnError, match="cloned"):
        webauthn_service.finish_authentication(db, user, auth.assert_(options, sign_count=stored))

    actions = [a.action for a in db.query(models.AuditLog)
               .filter(models.AuditLog.tenant_id == user.tenant_id).all()]
    assert "webauthn.counter_regression" in actions
    # The stored counter must not have moved backwards to match the replay.
    assert webauthn_service.credentials_for(db, user)[0].sign_count == stored


def test_a_failed_assertion_is_audited(db, enrolled):
    user, auth = enrolled
    impostor = SoftAuthenticator()
    impostor.credential_id = auth.credential_id
    options = webauthn_service.begin_authentication(db, user)
    with pytest.raises(webauthn_service.WebAuthnError):
        webauthn_service.finish_authentication(db, user, impostor.assert_(options))

    actions = [a.action for a in db.query(models.AuditLog)
               .filter(models.AuditLog.tenant_id == user.tenant_id).all()]
    assert "webauthn.failed" in actions


def test_another_users_passkey_is_not_accepted(db, make_user, enrolled):
    """Registered to somebody else, in another tenant. Refused before any crypto runs."""
    user, auth = enrolled
    other, _tenant = make_user()
    other = db.merge(other)

    other_auth = SoftAuthenticator()
    options = webauthn_service.begin_registration(db, other)
    webauthn_service.finish_registration(db, other, other_auth.register(options))
    db.flush()

    options = webauthn_service.begin_authentication(db, user)
    with pytest.raises(webauthn_service.WebAuthnError, match="not registered to you"):
        webauthn_service.finish_authentication(db, user, other_auth.assert_(options))


def test_authentication_without_a_passkey_says_so(db, make_user, passkeys_on):
    user, _tenant = make_user()
    user = db.merge(user)
    with pytest.raises(webauthn_service.WebAuthnError, match="no passkeys"):
        webauthn_service.begin_authentication(db, user)


# ---------------------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------------------


def test_removing_a_passkey_is_audited(db, enrolled):
    user, _auth = enrolled
    row = webauthn_service.credentials_for(db, user)[0]
    webauthn_service.remove(db, user, row.id)
    db.flush()

    assert webauthn_service.credentials_for(db, user) == []
    actions = [a.action for a in db.query(models.AuditLog)
               .filter(models.AuditLog.tenant_id == user.tenant_id).all()]
    assert "webauthn.removed" in actions


def test_the_last_factor_cannot_be_removed(db, enrolled):
    """An account with no password and one passkey must not be able to lock itself out."""
    user, _auth = enrolled
    user.password_hash = ""
    user.mfa_secret = None
    db.flush()

    row = webauthn_service.credentials_for(db, user)[0]
    with pytest.raises(webauthn_service.WebAuthnError, match="only way to sign in"):
        webauthn_service.remove(db, user, row.id)
    assert len(webauthn_service.credentials_for(db, user)) == 1


def test_another_users_passkey_cannot_be_removed(db, make_user, enrolled):
    _user, _auth = enrolled
    other, _tenant = make_user()
    other = db.merge(other)
    row = webauthn_service.credentials_for(db, _user)[0]

    with pytest.raises(webauthn_service.WebAuthnError, match="not registered to you"):
        webauthn_service.remove(db, other, row.id)
    with pytest.raises(webauthn_service.WebAuthnError, match="not registered to you"):
        webauthn_service.rename(db, other, row.id, "mine now")


def test_status_reports_the_fallback_honestly(db, enrolled):
    user, _auth = enrolled
    state = webauthn_service.status(db, user)

    assert state["enabled"] is True
    assert state["count"] == 1
    assert state["credentials"][0]["transports"] == ["usb"]
    assert state["has_fallback"] is True       # the fixture user has a password

    user.password_hash = ""
    user.mfa_secret = None
    db.flush()
    assert webauthn_service.status(db, user)["has_fallback"] is False
