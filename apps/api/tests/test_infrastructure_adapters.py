"""Storage, secrets, email and SMS (Phase 10 — coverage on the infrastructure adapters).

These are the modules that talk to the outside world, which is exactly why they are worth
testing without it. Each has a local or console implementation that is the real code path in
development and CI, and the production adapter behind the same interface.

The failures that matter here are quiet ones: a storage key that escapes its tenant prefix, a
secret that round-trips as plaintext because encryption was never configured, an outbox row
that says `sent` when nothing was delivered.

Requirements: INT-07, INT-08.
"""

from __future__ import annotations

import base64
from unittest import mock

import pytest

from app import email as email_mod
from app import models, secrets_box, sms, storage
from app.config import settings


# ---------------------------------------------------------------------------------------
# Storage — keys and the tenant prefix
# ---------------------------------------------------------------------------------------


def test_a_tenant_key_is_prefixed_with_its_tenant():
    """The prefix is the isolation. Everything in object storage is addressed by it, so a key
    built without one puts a bank's document where another deployment's sweep can find it."""
    assert storage.tenant_key("t123", "ocr", "abc-scan.pdf") == "tenants/t123/ocr/abc-scan.pdf"


def test_key_parts_cannot_escape_the_prefix_with_a_leading_slash():
    """A part beginning with `/` would otherwise produce `tenants/t1//etc/passwd`, and on some
    backends an absolute path."""
    assert storage.tenant_key("t1", "/etc", "passwd") == "tenants/t1/etc/passwd"


def test_windows_separators_are_normalised():
    """Keys are built on whatever host the app runs on and read by every other one. A backslash
    that survives into an S3 key is a different object from the one with a slash."""
    assert storage.tenant_key("t1", "docs\\2026", "a.pdf") == "tenants/t1/docs/2026/a.pdf"


def test_empty_parts_are_dropped():
    assert storage.tenant_key("t1", "", "a.pdf") == "tenants/t1/a.pdf"


@pytest.fixture()
def local(tmp_path):
    backend = storage.LocalFsBackend(str(tmp_path / "store"))
    backend.ensure_ready()
    return backend


def test_a_local_object_round_trips(local):
    local.put("tenants/t1/a.txt", b"hello", "text/plain")

    assert local.exists("tenants/t1/a.txt") is True
    with local.open_stream("tenants/t1/a.txt") as fh:
        assert fh.read() == b"hello"


def test_a_missing_object_does_not_exist(local):
    assert local.exists("tenants/t1/nope.txt") is False


def test_deleting_something_that_is_not_there_is_not_an_error(local):
    """Delete is called on cleanup paths where the object may already be gone. Raising would
    turn a successful purge into a failed one."""
    local.delete("tenants/t1/never-existed.txt")      # must not raise


def test_a_traversing_key_is_refused(local):
    """`../` in a key is the whole of path traversal. Without this check a crafted filename
    writes outside the storage root — and filenames arrive from uploads."""
    with pytest.raises(ValueError, match="invalid storage key"):
        local.put("../../escaped.txt", b"x")
    with pytest.raises(ValueError, match="invalid storage key"):
        local.exists("tenants/../../etc/passwd")


def test_move_relocates_and_removes_the_original(local):
    """The archive sweep depends on this: a move that copies without deleting doubles cold
    storage and leaves the hot copy live."""
    local.put("tenants/t1/hot/a.pdf", b"payload")
    local.move("tenants/t1/hot/a.pdf", "tenants/t1/cold/a.pdf")

    assert local.exists("tenants/t1/hot/a.pdf") is False
    with local.open_stream("tenants/t1/cold/a.pdf") as fh:
        assert fh.read() == b"payload"


def test_moving_onto_itself_is_a_no_op_not_a_deletion(local):
    """Without the early return this reads the file, writes it back over itself, then deletes
    it — losing the object entirely."""
    local.put("tenants/t1/a.pdf", b"payload")
    local.move("tenants/t1/a.pdf", "tenants/t1/a.pdf")

    assert local.exists("tenants/t1/a.pdf") is True
    with local.open_stream("tenants/t1/a.pdf") as fh:
        assert fh.read() == b"payload"


def test_nested_directories_are_created_on_write(local):
    local.put("tenants/t1/deep/deeper/deepest/a.txt", b"x")
    assert local.exists("tenants/t1/deep/deeper/deepest/a.txt") is True


def test_get_storage_returns_the_local_backend_when_s3_is_off(monkeypatch):
    monkeypatch.setattr(storage, "_backend", None)
    monkeypatch.setattr(settings, "s3_bucket", "")

    backend = storage.get_storage()
    assert backend.name == "local"
    monkeypatch.setattr(storage, "_backend", None)


# ---------------------------------------------------------------------------------------
# Secrets — encryption at rest
# ---------------------------------------------------------------------------------------


def _key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def test_a_configured_box_encrypts_and_round_trips():
    box = secrets_box.SecretsBox.from_settings(_key())

    assert box.enabled is True
    token = box.encrypt("s3cret-totp-seed")
    assert "s3cret-totp-seed" not in token          # the point of the exercise
    assert box.decrypt(token) == "s3cret-totp-seed"


def test_an_unconfigured_box_tags_plaintext_rather_than_pretending():
    """Storing the value untagged would make it indistinguishable from ciphertext later, and a
    deployment that turns encryption on afterwards could not tell which rows were already
    protected."""
    box = secrets_box.SecretsBox.from_settings("")

    assert box.enabled is False
    stored = box.encrypt("plain")
    assert stored != "plain"                         # tagged
    assert box.decrypt(stored) == "plain"


def test_none_stays_none_in_both_directions():
    box = secrets_box.SecretsBox.from_settings(_key())
    assert box.encrypt(None) is None
    assert box.decrypt(None) is None


def test_a_key_chain_decrypts_what_an_older_key_encrypted():
    """This is what makes key rotation possible: the old key stays in the chain read-only while
    values are re-encrypted. Without it, rotating the key destroys every stored secret."""
    old, new = _key(), _key()
    before = secrets_box.SecretsBox.from_settings(old)
    token = before.encrypt("mfa-seed")

    after = secrets_box.SecretsBox.from_settings(f"{new}\n{old}")
    assert after.decrypt(token) == "mfa-seed"


def test_rotate_re_encrypts_under_the_current_key():
    old, new = _key(), _key()
    token = secrets_box.SecretsBox.from_settings(old).encrypt("mfa-seed")

    chained = secrets_box.SecretsBox.from_settings(f"{new}\n{old}")
    rotated = chained.rotate(token)

    # Now readable by the new key alone — which is what lets the old one be retired.
    assert secrets_box.SecretsBox.from_settings(new).decrypt(rotated) == "mfa-seed"


def test_decrypting_without_the_right_key_fails_loudly():
    """Returning the ciphertext, or None, would put an unusable value into a TOTP check and
    produce "your code is wrong" for every user instead of an operator-visible error."""
    token = secrets_box.SecretsBox.from_settings(_key()).encrypt("mfa-seed")
    stranger = secrets_box.SecretsBox.from_settings(_key())

    with pytest.raises(RuntimeError, match="key chain"):
        stranger.decrypt(token)


def test_ciphertext_found_with_no_keys_configured_is_an_error():
    """Silently returning the raw token would write a Fernet blob into a QR code."""
    token = secrets_box.SecretsBox.from_settings(_key()).encrypt("mfa-seed")

    with pytest.raises(RuntimeError, match="no MFA_ENCRYPTION_KEYS"):
        secrets_box.SecretsBox.from_settings("").decrypt(token)


def test_an_unprefixed_legacy_value_is_read_as_plaintext():
    """Rows written before the tagging existed. Treating them as ciphertext would break every
    one of them on upgrade."""
    box = secrets_box.SecretsBox.from_settings(_key())
    assert box.decrypt("legacy-plain-value") == "legacy-plain-value"


def test_a_raw_32_byte_key_is_accepted():
    """Operators generate keys with `openssl rand` as often as with Fernet. Rejecting the
    unpadded form would be a config error nobody could diagnose from the message."""
    import os

    raw = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    box = secrets_box.SecretsBox.from_settings(raw)

    assert box.enabled is True
    assert box.decrypt(box.encrypt("x")) == "x"


def test_a_nonsense_key_is_rejected_at_startup_not_at_use():
    """Failing on the first MFA enrolment instead of at boot would mean the deployment looks
    healthy and the first user to enrol finds the problem."""
    with pytest.raises(ValueError, match="Invalid MFA_ENCRYPTION_KEY"):
        secrets_box.SecretsBox.from_settings("this-is-not-a-key")


# ---------------------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("0300-1234567", "+923001234567"),
    ("+92 300 1234567", "+923001234567"),
    ("92 300 1234567", "+923001234567"),
    ("3001234567", "+923001234567"),
    ("00923001234567", "+923001234567"),
    ("(0300) 123 4567", "+923001234567"),
])
def test_every_spelling_of_a_number_normalises_to_one_value(raw, expected):
    """The number is an identity claim. Two spellings producing two values means two party
    records for one person — and eventually two certificates."""
    assert sms.normalise_msisdn(raw) == expected


def test_an_empty_number_normalises_to_empty_not_a_country_code():
    """`+92` on its own looks like a number and is not one. Sending to it fails silently at the
    gateway."""
    assert sms.normalise_msisdn("") == ""
    assert sms.normalise_msisdn("   ") == ""


def test_masking_shows_enough_to_reconcile_and_no_more():
    """It goes on the Certificate of Completion, which is disclosed. Four digits let a branch
    match it against their record; the rest is not theirs to publish."""
    assert sms.mask_msisdn("+923001234567") == "***4567"
    assert sms.mask_msisdn("12") == "***"
    assert sms.mask_msisdn("") == "***"


@pytest.mark.parametrize("address, expected", [
    ("ayesha.khan@bank.test", "ay***@bank.test"),
    ("a@bank.test", "a***@bank.test"),
    ("ab@bank.test", "a***@bank.test"),      # 2 chars is not > 2, so one is shown
    ("not-an-address", "***"),
    ("", "***"),
])
def test_email_masking(address, expected):
    assert sms.mask_email(address) == expected


def test_a_failed_sms_is_recorded_as_failed(db, make_user):
    """The caller decides what a failure means — for an OTP it has to be surfaced, or the
    visitor sits waiting for a code that is never coming. That only works if this returns
    False rather than swallowing it."""
    user, tenant = make_user()

    class _Broken(sms.SmsBackend):
        name = "broken"

        def send(self, to, body):
            raise sms.SmsError("gateway refused")

    with mock.patch.object(sms, "get_backend", return_value=_Broken()):
        ok = sms.send_sms(db, tenant.id, "0300-1234567", "Your code is 123456")
    db.flush()

    assert ok is False
    row = db.query(models.EmailOutbox).filter(
        models.EmailOutbox.tenant_id == tenant.id).one()
    assert row.status == "failed"
    assert "gateway refused" in row.last_error
    assert row.channel == "sms"


def test_a_successful_sms_is_recorded_with_its_provider_reference(db, make_user):
    user, tenant = make_user()

    class _Fine(sms.SmsBackend):
        name = "fine"

        def send(self, to, body):
            return "provider-ref-9"

    with mock.patch.object(sms, "get_backend", return_value=_Fine()):
        assert sms.send_sms(db, tenant.id, "0300-1234567", "code") is True
    db.flush()

    row = db.query(models.EmailOutbox).filter(
        models.EmailOutbox.tenant_id == tenant.id).one()
    assert row.status == "sent"
    assert row.provider_ref == "provider-ref-9"
    assert row.to_email == "+923001234567"           # normalised, not as typed


def test_sms_lands_in_the_same_outbox_as_email(db, make_user):
    """One delivery audit for both channels. Two tables would mean two places to look when
    somebody says they never got their code."""
    user, tenant = make_user()

    class _Fine(sms.SmsBackend):
        name = "fine"

        def send(self, to, body):
            return "ref"

    with mock.patch.object(sms, "get_backend", return_value=_Fine()):
        sms.send_sms(db, tenant.id, "03001234567", "hello")
    db.flush()

    assert db.query(models.EmailOutbox).filter(
        models.EmailOutbox.tenant_id == tenant.id,
        models.EmailOutbox.channel == "sms").count() == 1


# ---------------------------------------------------------------------------------------
# Email outbox
# ---------------------------------------------------------------------------------------


def test_an_email_is_queued_and_marked_sent(db, make_user):
    user, tenant = make_user()

    rid = email_mod.send_email("someone@bank.test", "Subject", "Body",
                               tenant_id=tenant.id, db=db)
    db.flush()

    row = db.get(models.EmailOutbox, rid)
    assert row.status == "sent"                      # console backend delivers immediately
    assert row.attempts == 1
    assert row.sent_at is not None


def test_a_delivery_failure_is_recorded_rather_than_raised(db, make_user):
    """`send_email` is called at the end of state-changing requests. Raising would roll back an
    approval because a mail server was down."""
    user, tenant = make_user()

    with mock.patch.object(email_mod, "_deliver", side_effect=OSError("smtp down")):
        rid = email_mod.send_email("someone@bank.test", "S", "B",
                                   tenant_id=tenant.id, db=db)
    db.flush()

    row = db.get(models.EmailOutbox, rid)
    assert row.status == "failed"
    assert "smtp down" in row.last_error


def test_the_flusher_retries_a_failed_row(db, make_user):
    user, tenant = make_user()
    with mock.patch.object(email_mod, "_deliver", side_effect=OSError("smtp down")):
        rid = email_mod.send_email("someone@bank.test", "S", "B",
                                   tenant_id=tenant.id, db=db)
    db.flush()

    counts = email_mod.flush_outbox(db)
    db.flush()

    assert counts["sent"] >= 1
    assert db.get(models.EmailOutbox, rid).status == "sent"


def test_the_flusher_gives_up_after_the_attempt_cap(db, make_user):
    """Otherwise a permanently bad address is retried every minute forever, and the outbox
    becomes a queue that never drains."""
    user, tenant = make_user()
    with mock.patch.object(email_mod, "_deliver", side_effect=OSError("nope")):
        rid = email_mod.send_email("bad@bank.test", "S", "B", tenant_id=tenant.id, db=db)
        db.flush()
        row = db.get(models.EmailOutbox, rid)
        row.attempts = 5
        db.flush()

        counts = email_mod.flush_outbox(db, max_attempts=5)

    assert counts["sent"] == 0
    assert counts["failed"] == 0                     # not even attempted
    assert db.get(models.EmailOutbox, rid).attempts == 5


def test_the_flusher_never_hands_a_phone_number_to_smtp(db, make_user):
    """SMS shares the outbox for audit. Retrying those here would post a phone number to a mail
    server — a data leak dressed up as a retry."""
    user, tenant = make_user()
    db.add(models.EmailOutbox(
        tenant_id=tenant.id, to_email="+923001234567", subject="SMS", body="code",
        status="failed", attempts=1, channel="sms"))
    db.flush()

    with mock.patch.object(email_mod, "_deliver") as deliver:
        email_mod.flush_outbox(db)

    assert deliver.call_count == 0
