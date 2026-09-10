"""Masking, watermarking, antivirus and anti-automation.

Written as attacks again. The questions:

- does masking happen where the API responds, or only where a template renders (the second
  leaves the real value available to anyone calling the API directly);
- does a watermark actually name the viewer, or just say CONFIDENTIAL to nobody;
- does the antivirus **fail closed** when it cannot reach the daemon;
- is the proof-of-work actually verified, or is any nonce accepted.

The antivirus one matters most. Every other integration in this codebase fails open on
purpose, so a scanner that did the same would look consistent and be useless.

Requirements: SEC-14, SEC-15, SEC-16, SEC-17.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from app import data_protection as dp
from app.data_protection import VirusFound


# ---------------------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------------------


def test_a_cnic_keeps_only_its_last_four():
    """The last four is what somebody is asked to confirm; masking it to nothing makes the
    field useless for the purpose it exists for."""
    masked = dp.mask_value("42101-1234567-8")
    assert masked.endswith("67-8")
    assert "42101" not in masked


def test_an_email_keeps_its_domain():
    masked = dp.mask_value("ayesha.khan@mmbl.test", "email")
    assert masked.endswith("@mmbl.test")
    assert "ayesha" not in masked


def test_a_phone_keeps_its_last_four():
    assert dp.mask_value("+923001234567", "phone").endswith("4567")


def test_money_is_masked_entirely():
    """A partially-masked amount is guessable from its length."""
    assert dp.mask_value(1_250_000, "money") == "•••"


def test_a_short_value_reveals_nothing():
    assert dp.mask_value("abc") == "•••"


def test_an_empty_value_stays_empty():
    assert dp.mask_value(None) == ""
    assert dp.mask_value("") == ""


def test_identifiers_are_masked_inside_free_text():
    """A CNIC pasted into a comment is as exposed as one in its own column."""
    masked = dp.mask_text("Please verify 42101-1234567-8 before release.")
    assert "42101-1234567-8" not in masked
    assert "Please verify" in masked


def test_ordinary_numbers_survive_masking():
    """Masking every digit would make clause text unreadable."""
    assert "12" in dp.mask_text("See clause 12 and section 3.")


def test_roles_that_may_see_a_field_see_it(db=None):
    assert dp.may_see("value", "manager") is True
    assert dp.may_see("value", "viewer") is False
    assert dp.may_see("title", "viewer") is True, "unlisted fields are not masked"


def test_masking_is_applied_to_the_response_payload():
    """In the response, not the template — a template-level mask leaves the API returning the
    real value to anyone who calls it directly, which is the version that gets used."""
    payload = {"title": "Merchant Agreement", "value": 1_000_000,
               "contact_email": "a@b.test"}
    masked = dp.apply_masking(payload, "viewer")

    assert masked["title"] == "Merchant Agreement"
    assert masked["value"] == "•••"
    assert masked["value_masked"] is True
    assert masked["contact_email"].endswith("@b.test")


def test_a_permitted_role_gets_the_real_values():
    payload = {"value": 1_000_000}
    assert dp.apply_masking(payload, "manager")["value"] == 1_000_000
    assert "value_masked" not in dp.apply_masking(payload, "manager")


def test_masking_does_not_mutate_the_original():
    payload = {"value": 1_000_000}
    dp.apply_masking(payload, "viewer")
    assert payload["value"] == 1_000_000


# ---------------------------------------------------------------------------------------
# Watermarking
# ---------------------------------------------------------------------------------------


def test_the_watermark_names_the_viewer_and_the_moment():
    """It does not prevent a screenshot — it makes one attributable, which is the deterrent.
    A static CONFIDENTIAL stamp identifies nobody."""
    text = dp.watermark_text(name="Ayesha Khan", email="ayesha@mmbl.test",
                             when=dt.datetime(2026, 8, 28, 14, 30),
                             reference="C-2026-0007")
    assert "Ayesha Khan" in text
    assert "ayesha@mmbl.test" in text
    assert "2026-08-28" in text
    assert "C-2026-0007" in text


def test_stamping_produces_a_readable_pdf():
    from app import pdf as pdf_render

    class _Contract:
        id = "c1"
        title = "Merchant Acquiring Agreement"
        reference_no = "C-2026-0007"
        type = "vendor"
        status = "active"
        counterparty = "Acme Trading"
        value = 1_000_000
        currency = "PKR"
        effective_date = dt.date(2026, 1, 1)
        end_date = dt.date(2026, 12, 31)
        governing_law = "Pakistan"
        renewal_type = "none"
        department = "Procurement"
        body = "1. The Supplier shall provide the Services."
        ai_summary = ""

    original = pdf_render.render_contract_pdf_bytes(
        contract=_Contract(), org_name="MMBL", draft=False)
    stamped = dp.stamp_watermark(original, dp.watermark_text(name="Ayesha Khan"))

    assert stamped.startswith(b"%PDF")
    assert len(stamped) > len(original), "the overlay should add content"


def test_a_document_that_cannot_be_watermarked_is_still_served():
    """Refusing to show a document because a cosmetic layer failed sends the viewer to ask
    somebody to email it instead — strictly worse for confidentiality."""
    assert dp.stamp_watermark(b"not a pdf at all", "watermark") == b"not a pdf at all"


def test_view_only_headers_do_not_offer_a_download():
    headers = dp.download_headers(allow_download=False, filename="a.pdf")
    assert headers["Content-Disposition"].startswith("inline")
    assert "no-store" in headers["Cache-Control"]


def test_download_headers_attach_when_allowed():
    headers = dp.download_headers(allow_download=True, filename="a.pdf")
    assert headers["Content-Disposition"].startswith("attachment")


# ---------------------------------------------------------------------------------------
# Antivirus
# ---------------------------------------------------------------------------------------


def test_the_eicar_test_file_is_always_rejected():
    """Recognised without a daemon, so the rejection path can be exercised in CI. A scanner
    nobody has ever seen reject anything is a scanner nobody trusts."""
    clean, detail = dp.scan(dp.EICAR)
    assert clean is False
    assert "Eicar" in detail


def test_scan_or_raise_refuses_an_infected_upload():
    with pytest.raises(VirusFound, match="rejected"):
        dp.scan_or_raise(dp.EICAR, filename="invoice.pdf")


def test_an_unconfigured_scanner_says_so_rather_than_claiming_clean():
    """"Not scanned" and "scanned and clean" are different facts and must not be conflated."""
    clean, detail = dp.scan(b"an ordinary file")
    assert clean is True
    assert "not configured" in detail


def test_the_scanner_fails_closed_when_it_cannot_be_reached(monkeypatch):
    """The one integration here that does. An antivirus that waves files through when the
    daemon is unreachable provides no protection at exactly the moment an attacker would
    choose."""
    from app.config import settings

    monkeypatch.setattr(settings, "clamav_enabled", True)
    monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(settings, "clamav_port", 1)     # nothing listens here
    monkeypatch.setattr(settings, "clamav_timeout", 1)

    with pytest.raises(VirusFound, match="could not be scanned"):
        dp.scan(b"an ordinary file", filename="x.pdf")


def test_the_status_states_plainly_whether_uploads_are_protected():
    note = dp.status()["antivirus"]["note"].lower()
    assert "not configured" in note


# ---------------------------------------------------------------------------------------
# Anti-automation
# ---------------------------------------------------------------------------------------


def test_a_challenge_is_only_demanded_after_repeated_failures():
    """Somebody who mistypes their password once should not have to do arithmetic."""
    identifier = "someone@example.test"
    dp.clear_failures(identifier)
    assert dp.challenge_required(identifier) is False
    for _ in range(dp.POW_AFTER_FAILURES):
        dp.record_failure(identifier)
    assert dp.challenge_required(identifier) is True
    dp.clear_failures(identifier)


def test_a_successful_sign_in_clears_the_backoff():
    identifier = "someone-else@example.test"
    for _ in range(dp.POW_AFTER_FAILURES):
        dp.record_failure(identifier)
    dp.clear_failures(identifier)
    assert dp.challenge_required(identifier) is False


def test_a_correct_proof_of_work_verifies():
    challenge = dp.new_challenge()["challenge"]
    # Solved here the same way a browser would, at a low difficulty so the test is quick.
    bits = 8
    nonce = 0
    while True:
        digest = hashlib.sha256(f"{challenge}{nonce}".encode()).digest()
        if digest[0] == 0:
            break
        nonce += 1
    assert dp.verify_proof(challenge, str(nonce), bits=bits) is True


def test_a_wrong_nonce_does_not_verify():
    """The check has to actually run — accepting any nonce would make this theatre."""
    challenge = dp.new_challenge()["challenge"]
    assert dp.verify_proof(challenge, "0") is False


def test_an_empty_proof_does_not_verify():
    assert dp.verify_proof("abc", "") is False
    assert dp.verify_proof("", "123") is False


def test_the_challenge_explains_itself():
    """A client has to be able to solve it without reading our source."""
    challenge = dp.new_challenge()
    assert challenge["algorithm"] == "sha256"
    assert challenge["difficulty"] == dp.POW_DIFFICULTY_BITS
    assert "zero bits" in challenge["instructions"]
