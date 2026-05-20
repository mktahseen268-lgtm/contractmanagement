"""Signing-portal access-token security — verifies that:
  - the raw URL token is never stored in the DB (only the SHA-256 hash and Fernet ciphertext)
  - lookups by hashed token work
  - expired tokens look like 'not found' (don't leak existence)
  - decrypt round-trips for reminders
  - void wipes hash + ciphertext + expiry
"""

import datetime as dt

import pytest
from sqlalchemy import text

from app import models, signing_service, security
from app.database import SessionLocal, set_request_tenant


@pytest.fixture()
def envelope_with_recipient(make_user):
    """A signed-in tenant + one contract + one envelope + one signer recipient."""
    user, tenant = make_user()
    with SessionLocal() as db:
        set_request_tenant(tenant.id)
        contract = models.Contract(
            tenant_id=tenant.id, reference_no="CT-001", title="Test Agreement",
            owner_id=user.id, status="approved", created_by=user.id,
        )
        db.add(contract); db.flush()
        env = models.SignatureEnvelope(
            tenant_id=tenant.id, contract_id=contract.id, status="draft",
            signing_order="sequential", message="", created_by=user.id,
        )
        db.add(env); db.flush()
        rec = models.SignatureRecipient(
            tenant_id=tenant.id, envelope_id=env.id, sequence=0,
            name="Bob Signer", email="bob@example.test", kind="signer", status="created",
        )
        db.add(rec); db.commit()
        return tenant.id, env.id, rec.id


class TestSigningTokenStorage:
    def test_raw_token_is_not_persisted(self, envelope_with_recipient):
        tenant_id, _env_id, rec_id = envelope_with_recipient
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            rec = db.get(models.SignatureRecipient, rec_id)
            raw = signing_service._mint_token_for(rec)
            db.commit()

            # The raw token MUST NOT appear in any persisted column. Read columns through
            # raw SQL so we bypass EncryptedString.process_result_value (which decrypts).
            row = db.execute(text(
                "SELECT access_token_hash, access_token_secret, access_token_expires_at "
                "FROM signature_recipients WHERE id = :id"
            ), {"id": rec_id}).first()
            stored_hash, stored_secret, _ = row
            assert raw not in (stored_hash or "")
            assert raw not in (stored_secret or "")
            assert stored_hash == security.hash_token(raw)

    def test_lookup_by_hash_finds_recipient(self, envelope_with_recipient):
        tenant_id, _env_id, rec_id = envelope_with_recipient
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            rec = db.get(models.SignatureRecipient, rec_id)
            raw = signing_service._mint_token_for(rec)
            db.commit()
        with SessionLocal() as db2:
            set_request_tenant(tenant_id)
            found = signing_service.recipient_by_token(db2, raw)
            assert found is not None
            assert found.id == rec_id

    def test_wrong_token_returns_none(self, envelope_with_recipient):
        tenant_id, _env_id, rec_id = envelope_with_recipient
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            rec = db.get(models.SignatureRecipient, rec_id)
            signing_service._mint_token_for(rec)
            db.commit()
        with SessionLocal() as db2:
            set_request_tenant(tenant_id)
            assert signing_service.recipient_by_token(db2, "wrong-token-value") is None

    def test_expired_token_returns_none(self, envelope_with_recipient):
        tenant_id, _env_id, rec_id = envelope_with_recipient
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            rec = db.get(models.SignatureRecipient, rec_id)
            raw = signing_service._mint_token_for(rec)
            # Force expiry into the past
            rec.access_token_expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
            db.commit()
        with SessionLocal() as db2:
            set_request_tenant(tenant_id)
            assert signing_service.recipient_by_token(db2, raw) is None

    def test_decrypt_for_reminder_round_trips(self, envelope_with_recipient):
        tenant_id, _env_id, rec_id = envelope_with_recipient
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            rec = db.get(models.SignatureRecipient, rec_id)
            raw = signing_service._mint_token_for(rec)
            db.commit()
        with SessionLocal() as db2:
            set_request_tenant(tenant_id)
            rec2 = db2.get(models.SignatureRecipient, rec_id)
            assert signing_service.decrypt_token_for(rec2) == raw

    def test_clear_token_wipes_all_three_columns(self, envelope_with_recipient):
        tenant_id, _env_id, rec_id = envelope_with_recipient
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            rec = db.get(models.SignatureRecipient, rec_id)
            signing_service._mint_token_for(rec)
            db.commit()
            db.refresh(rec)
            assert rec.access_token_hash and rec.access_token_secret and rec.access_token_expires_at

            signing_service._clear_token(rec)
            db.commit()
            db.refresh(rec)
            assert rec.access_token_hash is None
            assert rec.access_token_secret is None
            assert rec.access_token_expires_at is None
