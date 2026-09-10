"""AI assist — clause suggestion, data capture, and the confirmation gate.

The load-bearing claim is a negative one: **extraction never writes to a contract by itself**.
A confidence score is not a fact, and a plausible-but-wrong end date silently applied drives
renewal reminders for a term that does not exist. Everything else here is ranking.

Clause suggestion is deliberately deterministic — grounded in the library and the playbook, not
generated — so the same draft always produces the same list and every entry cites why.

Requirements: SOW-04.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import ai_service, clause_service, models, security
from app.ai_service import AiError

CONFIDENTIALITY = "Each party shall hold the other's Confidential Information in confidence."
LIABILITY = "Liability shall not exceed the fees paid in the preceding twelve (12) months."
DATA_PROTECTION = "The Supplier shall process personal data only on documented instructions."


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"ai-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    approver = models.User(
        tenant_id=tenant.id, email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        name="Legal", password_hash=security.hash_password("Str0ng!Passw0rd1"), role="manager",
    )
    db.add(approver)
    db.commit()
    return {"tenant": tenant, "owner": owner, "approver": approver}


def _clause(db, ws, key, body, *, risk="low") -> models.Clause:
    c = models.Clause(
        tenant_id=ws["tenant"].id, key=key, title=key.replace("_", " ").title(),
        category="General", body=body, risk_level=risk, status="draft",
        created_by=ws["owner"].id,
    )
    db.add(c)
    db.flush()
    clause_service.submit_for_approval(db, c, actor=ws["owner"])
    clause_service.approve(db, c, actor=ws["approver"])
    return c


def _contract(db, ws, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title=kwargs.pop("title", "Vendor Services Agreement"),
        type=kwargs.pop("type", "vendor"), status="draft",
        owner_id=ws["owner"].id, created_by=ws["owner"].id,
        body=kwargs.pop("body", ""), value=100_000, currency="PKR", **kwargs,
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------------------
# Clause suggestion
# ---------------------------------------------------------------------------------------


def test_a_policy_required_missing_clause_is_the_top_suggestion(db, workspace):
    _clause(db, workspace, "data_protection", DATA_PROTECTION, risk="high")
    db.add(models.Playbook(
        tenant_id=workspace["tenant"].id, name="Vendor policy", contract_type="vendor",
        applies_when={}, status="active", created_by=workspace["owner"].id,
        rules=[{"clause_key": "data_protection", "kind": "required", "severity": "blocker"}],
    ))
    db.flush()

    suggestions = ai_service.suggest_clauses(db, _contract(db, workspace))
    assert suggestions[0]["key"] == "data_protection"
    assert suggestions[0]["basis"] == "policy"
    assert suggestions[0]["severity"] == "blocker"
    assert "Required by" in suggestions[0]["reason"]


def test_it_suggests_what_comparable_agreements_actually_use(db, workspace):
    """Evidence, not a guess — and the reason says so in countable terms."""
    clause = _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    for _ in range(3):
        peer = _contract(db, workspace)
        peer.included_clauses = [{"clause_id": clause.id, "key": "confidentiality",
                                  "version_no": 1, "title": "Confidentiality"}]
    db.flush()

    suggestions = ai_service.suggest_clauses(db, _contract(db, workspace))
    match = next(s for s in suggestions if s["key"] == "confidentiality")
    assert match["basis"] == "peers"
    assert "3 of" in match["reason"]


def test_a_clause_already_in_the_draft_is_not_suggested(db, workspace):
    clause = _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    contract = _contract(db, workspace)
    contract.included_clauses = [{"clause_id": clause.id, "key": "confidentiality",
                                  "version_no": 1, "title": "Confidentiality"}]
    db.flush()
    assert all(s["key"] != "confidentiality"
               for s in ai_service.suggest_clauses(db, contract))


def test_a_clause_referenced_in_the_body_is_not_suggested(db, workspace):
    _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    contract = _contract(db, workspace, body="[[clause:confidentiality]]")
    assert all(s["key"] != "confidentiality"
               for s in ai_service.suggest_clauses(db, contract))


def test_high_risk_library_clauses_are_suggested_even_without_policy(db, workspace):
    _clause(db, workspace, "indemnity", "The Supplier shall indemnify the Bank.", risk="critical")
    suggestions = ai_service.suggest_clauses(db, _contract(db, workspace))
    match = next(s for s in suggestions if s["key"] == "indemnity")
    assert match["basis"] == "risk"
    assert "critical" in match["reason"]


def test_suggestions_are_deterministic(db, workspace):
    """Same draft, same list — an auditor can re-run it and get the same answer."""
    _clause(db, workspace, "indemnity", "Indemnity.", risk="high")
    _clause(db, workspace, "liability", LIABILITY, risk="high")
    contract = _contract(db, workspace)
    first = ai_service.suggest_clauses(db, contract)
    second = ai_service.suggest_clauses(db, contract)
    assert [s["key"] for s in first] == [s["key"] for s in second]


def test_an_unapproved_clause_is_never_suggested(db, workspace):
    c = models.Clause(
        tenant_id=workspace["tenant"].id, key="draft_clause", title="Draft",
        body="Unapproved.", risk_level="critical", status="draft",
        created_by=workspace["owner"].id,
    )
    db.add(c)
    db.flush()
    assert all(s["key"] != "draft_clause"
               for s in ai_service.suggest_clauses(db, _contract(db, workspace)))


# ---------------------------------------------------------------------------------------
# Data capture — the confirmation gate
# ---------------------------------------------------------------------------------------


def test_capture_writes_nothing_to_the_contract(db, workspace):
    """The whole point. Extraction proposes; a person decides."""
    contract = _contract(db, workspace, title="Original title")
    before = {"title": contract.title, "counterparty": contract.counterparty,
              "value": contract.value}

    review = ai_service.capture(db, contract, file_bytes=b"anything",
                                file_name="scan.pdf", actor=workspace["owner"])

    assert review.status == "pending"
    assert contract.title == before["title"]
    assert contract.counterparty == before["counterparty"]
    assert contract.value == before["value"]


def test_the_capture_records_which_provider_produced_it(db, workspace):
    """`stub` means the document was not read. Nobody should mistake it for extraction."""
    review = ai_service.capture(db, _contract(db, workspace), file_bytes=b"x",
                                file_name="scan.pdf", actor=workspace["owner"])
    assert review.provider == "stub"


def test_only_capturable_fields_are_stored(db, workspace):
    review = ai_service.capture(db, _contract(db, workspace), file_bytes=b"x",
                                file_name="scan.pdf", actor=workspace["owner"])
    assert set(review.fields).issubset(ai_service.CAPTURABLE)


def test_applying_writes_only_the_ticked_fields(db, workspace):
    contract = _contract(db, workspace, title="Original title")
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    original_counterparty = contract.counterparty

    applied = ai_service.apply_capture(db, review, contract, ["title"],
                                       actor=workspace["owner"])

    assert list(applied) == ["title"]
    assert contract.title != "Original title"
    assert contract.counterparty == original_counterparty, "an unticked field must not move"
    assert review.status == "applied"
    assert review.applied_fields == ["title"]


def test_a_field_that_was_never_offered_is_refused(db, workspace):
    """A stale client must not write a set of values nobody reviewed."""
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    with pytest.raises(AiError, match="not part of this extraction"):
        ai_service.apply_capture(db, review, contract, ["department"],
                                 actor=workspace["owner"])


def test_a_capture_cannot_be_applied_twice(db, workspace):
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    ai_service.apply_capture(db, review, contract, ["title"], actor=workspace["owner"])
    with pytest.raises(AiError, match="already been dealt with"):
        ai_service.apply_capture(db, review, contract, ["title"], actor=workspace["owner"])


def test_accepting_nothing_discards_the_capture(db, workspace):
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    assert ai_service.apply_capture(db, review, contract, [], actor=workspace["owner"]) == {}
    assert review.status == "discarded"


def test_discarding_leaves_the_contract_alone(db, workspace):
    contract = _contract(db, workspace, title="Untouched")
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    ai_service.discard(db, review, actor=workspace["owner"])
    assert review.status == "discarded"
    assert contract.title == "Untouched"


def test_a_date_that_cannot_be_parsed_is_refused_not_guessed(db, workspace):
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    review.fields = {**review.fields,
                     "end_date": {"value": "sometime next year", "confidence": 0.9}}
    db.flush()
    with pytest.raises(AiError, match="not a date"):
        ai_service.apply_capture(db, review, contract, ["end_date"], actor=workspace["owner"])


def test_a_captured_date_becomes_a_real_date(db, workspace):
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    review.fields = {**review.fields, "end_date": {"value": "2027-03-01", "confidence": 0.9}}
    db.flush()
    ai_service.apply_capture(db, review, contract, ["end_date"], actor=workspace["owner"])
    assert contract.end_date == dt.date(2027, 3, 1)


def test_a_low_confidence_value_is_shown_but_not_pre_ticked(db, workspace):
    """Confidence gates the default, never the write."""
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    review.fields = {"counterparty": {"value": "Acme Trading", "confidence": 0.42}}
    db.flush()

    rows = ai_service.presentable(db, review, contract)["fields"]
    row = next(r for r in rows if r["field"] == "counterparty")
    assert row["value"] == "Acme Trading"
    assert row["suggested"] is False


def test_a_high_confidence_value_that_changes_nothing_is_not_pre_ticked(db, workspace):
    """Otherwise confirming becomes a habit of clicking through no-ops."""
    contract = _contract(db, workspace, title="Vendor Services Agreement")
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    review.fields = {"title": {"value": "Vendor Services Agreement", "confidence": 0.99}}
    db.flush()

    row = ai_service.presentable(db, review, contract)["fields"][0]
    assert row["changes"] is False
    assert row["suggested"] is False


def test_a_high_confidence_change_is_pre_ticked(db, workspace):
    contract = _contract(db, workspace, title="Old")
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    review.fields = {"title": {"value": "New title", "confidence": 0.97}}
    db.flush()

    row = ai_service.presentable(db, review, contract)["fields"][0]
    assert row["changes"] is True
    assert row["suggested"] is True


def test_the_confirmation_is_audited_with_what_was_accepted(db, workspace):
    """"The model did not write these" has to be provable, not asserted."""
    contract = _contract(db, workspace)
    review = ai_service.capture(db, contract, file_bytes=b"x", file_name="scan.pdf",
                                actor=workspace["owner"])
    ai_service.apply_capture(db, review, contract, ["title"], actor=workspace["owner"])
    db.flush()

    entry = db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id, action="contract.ai_capture_confirmed"
    ).one()
    assert entry.actor_id == workspace["owner"].id
    assert "title" in entry.meta["applied"]


# ---------------------------------------------------------------------------------------
# The on-prem provider
# ---------------------------------------------------------------------------------------


def test_the_local_provider_is_selected_when_configured(monkeypatch):
    """The MMBL setting: a model inside the deployment, so no document leaves the network."""
    from app import ocr_provider
    from app.config import settings

    monkeypatch.setattr(settings, "ocr_provider", "local")
    monkeypatch.setattr(settings, "ocr_base_url", "http://llm.internal:8000/v1")
    provider = ocr_provider.get_ocr_provider()
    assert isinstance(provider, ocr_provider.LocalOcrProvider)
    assert provider.base_url == "http://llm.internal:8000/v1"


def test_local_falls_back_to_the_stub_without_an_endpoint(monkeypatch):
    from app import ocr_provider
    from app.config import settings

    monkeypatch.setattr(settings, "ocr_provider", "local")
    monkeypatch.setattr(settings, "ocr_base_url", "")
    assert isinstance(ocr_provider.get_ocr_provider(), ocr_provider.StubOcrProvider)


def test_an_unreadable_document_returns_nothing_rather_than_inventing_fields():
    """A fabricated low-confidence guess still reaches a human as a finding worth weighing."""
    from app import ocr_provider

    provider = ocr_provider.LocalOcrProvider("http://llm.internal:8000/v1", "model")
    result = provider.extract(file_bytes=b"", file_name="scan.png")
    assert result["fields"] == {}
    assert result["provider"] == "local"
    assert "error" in result


def test_a_transport_failure_degrades_instead_of_exploding():
    """An unreachable model must not take the upload down with it."""
    from app import ocr_provider

    provider = ocr_provider.LocalOcrProvider("http://127.0.0.1:1/v1", "model", timeout=1)
    result = provider.extract(file_bytes=b"Some contract text.", file_name="doc.txt")
    assert result["fields"] == {}
    assert "error" in result
