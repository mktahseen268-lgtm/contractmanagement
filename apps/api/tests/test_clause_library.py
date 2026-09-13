"""Clause library, alternatives, and the playbook policy engine.

Three claims under test, in order of how much they matter:

1. **A template composes clauses by reference**, so improving a clause improves every template
   that uses it — and a reference that cannot resolve stops the draft rather than quietly
   producing a contract with a paragraph missing.
2. **Alternatives carry the same approval gate as anything else.** A fallback position is
   wording that ends up in a signed agreement; treating it as a lesser object is how
   unapproved language reaches a counterparty.
3. **A deviation is detected and classified.** `missing`, `altered` and `prohibited` are
   different findings, and a blocking one changes the approval route rather than producing a
   report somebody can approve past.

Requirements: SOW-02, SOW-03, SOW-06, SOW-10.
"""

from __future__ import annotations

import uuid

import pytest

from app import clause_service, models, playbook_service, security, template_service
from app.clause_service import ClauseError

CONFIDENTIALITY = (
    "Each party shall hold the other's Confidential Information in strict confidence and "
    "shall not disclose it to any third party without prior written consent."
)

LIABILITY = (
    "The total aggregate liability of either party under this Agreement shall not exceed the "
    "total fees paid in the twelve (12) months preceding the claim."
)

LIABILITY_FALLBACK = (
    "The total aggregate liability of either party under this Agreement shall not exceed two "
    "times (2x) the total fees paid in the twelve (12) months preceding the claim."
)

UNLIMITED_LIABILITY = (
    "Each party accepts unlimited liability for any and all losses arising under this "
    "Agreement, without cap or exclusion of any kind."
)


@pytest.fixture()
def workspace(db, make_user):
    """One tenant, an author and an approver — separation of duties needs two people."""
    author, tenant = make_user(email=f"author-{uuid.uuid4().hex[:8]}@example.com",
                               name="Clause Author")
    approver = models.User(
        tenant_id=tenant.id, email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        name="Legal Reviewer", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="manager",
    )
    db.add(approver)
    db.commit()
    return {"tenant": tenant, "author": author, "approver": approver}


def _clause(db, ws, key, body, *, title="", category="General", parent=None,
            position="preferred", risk="low", rank=0) -> models.Clause:
    c = models.Clause(
        tenant_id=ws["tenant"].id, key=key, title=title or key.replace("_", " ").title(),
        category=category, body=body, position=position, risk_level=risk,
        parent_id=parent.id if parent else None, fallback_rank=rank,
        status="draft", created_by=ws["author"].id,
    )
    db.add(c)
    db.flush()
    return c


def _approved(db, ws, key, body, **kwargs) -> models.Clause:
    c = _clause(db, ws, key, body, **kwargs)
    clause_service.submit_for_approval(db, c, actor=ws["author"])
    clause_service.approve(db, c, actor=ws["approver"])
    return c


def _contract(db, ws, body, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Vendor Services Agreement", type=kwargs.pop("type", "vendor"),
        status="draft", owner_id=ws["author"].id, created_by=ws["author"].id,
        body=body, value=kwargs.pop("value", 100_000), currency="PKR",
        department=kwargs.pop("department", ""), risk_level=kwargs.pop("risk_level", "low"),
        **kwargs,
    )
    db.add(c)
    db.flush()
    return c


def _playbook(db, ws, rules, *, contract_type="vendor", applies_when=None,
              status="active") -> models.Playbook:
    p = models.Playbook(
        tenant_id=ws["tenant"].id, name="Vendor policy", contract_type=contract_type,
        applies_when=applies_when or {}, rules=rules, status=status,
        created_by=ws["author"].id,
    )
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------------------


def test_a_draft_clause_has_no_approved_wording(db, workspace):
    c = _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    assert clause_service.approved_body(db, c) == ""


def test_submit_then_approve_freezes_a_version(db, workspace):
    c = _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    clause_service.submit_for_approval(db, c, actor=workspace["author"])
    assert c.status == "pending_approval"

    snapshot = clause_service.approve(db, c, actor=workspace["approver"], note="Legal sign-off")
    assert c.status == "active"
    assert c.version_no == 1
    assert snapshot.body == CONFIDENTIALITY
    assert clause_service.approved_body(db, c) == CONFIDENTIALITY


def test_the_author_cannot_approve_their_own_clause(db, workspace):
    c = _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    clause_service.submit_for_approval(db, c, actor=workspace["author"])
    c.created_by = workspace["approver"].id
    with pytest.raises(ClauseError, match="someone other than its author"):
        clause_service.approve(db, c, actor=workspace["approver"])


def test_an_empty_clause_cannot_be_submitted(db, workspace):
    c = _clause(db, workspace, "empty", "   ")
    with pytest.raises(ClauseError, match="needs wording"):
        clause_service.submit_for_approval(db, c, actor=workspace["author"])


def test_approving_again_supersedes_the_previous_version(db, workspace):
    c = _approved(db, workspace, "liability", LIABILITY)
    first = clause_service.active_version(db, c)
    c.body = LIABILITY_FALLBACK
    c.status = "draft"
    clause_service.submit_for_approval(db, c, actor=workspace["author"])
    second = clause_service.approve(db, c, actor=workspace["approver"], note="2x cap")

    assert first.status == "superseded"
    assert second.version_no == 2
    assert clause_service.approved_body(db, c) == LIABILITY_FALLBACK


def test_editing_approved_wording_sends_it_back_to_draft(db, workspace):
    c = _approved(db, workspace, "liability", LIABILITY)
    c.body = LIABILITY + " Nothing in this clause limits liability for fraud."
    clause_service.edit_unapproves(c)
    assert c.status == "draft"
    # The approved snapshot is untouched, so anything generated now still gets v1 wording.
    assert clause_service.approved_body(db, c) == ""


def test_retiring_takes_the_clause_and_its_versions_out_of_use(db, workspace):
    c = _approved(db, workspace, "liability", LIABILITY)
    snapshot = clause_service.active_version(db, c)
    clause_service.retire(db, c, actor=workspace["approver"])
    assert c.status == "retired"
    assert snapshot.status == "retired"
    assert clause_service.approved_body(db, c) == ""


# ---------------------------------------------------------------------------------------
# Alternatives
# ---------------------------------------------------------------------------------------


def test_alternatives_are_ranked_fallbacks_of_their_parent(db, workspace):
    parent = _approved(db, workspace, "liability", LIABILITY)
    second = _approved(db, workspace, "liability_2x", LIABILITY_FALLBACK,
                       parent=parent, position="fallback", rank=2)
    first = _approved(db, workspace, "liability_15x", LIABILITY_FALLBACK,
                      parent=parent, position="acceptable", rank=1)

    ranked = clause_service.alternatives(db, parent)
    assert [c.id for c in ranked] == [first.id, second.id]


def test_an_alternative_needs_approval_like_anything_else(db, workspace):
    """The wording of a fallback ends up in a signed agreement too."""
    parent = _approved(db, workspace, "liability", LIABILITY)
    alt = _clause(db, workspace, "liability_2x", LIABILITY_FALLBACK,
                  parent=parent, position="fallback")
    assert alt.status == "draft"
    assert clause_service.approved_body(db, alt) == ""
    clause_service.submit_for_approval(db, alt, actor=workspace["author"])
    clause_service.approve(db, alt, actor=workspace["approver"])
    assert clause_service.approved_body(db, alt) == LIABILITY_FALLBACK


# ---------------------------------------------------------------------------------------
# Composition into templates
# ---------------------------------------------------------------------------------------


def test_references_are_found_in_order_without_duplicates():
    body = "[[clause:a]] then [[clause:b]] then [[clause:a]] again."
    assert clause_service.references_in(body) == ["a", "b"]


def test_expand_inserts_the_approved_wording(db, workspace):
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    text, included, unresolved = clause_service.expand(
        db, workspace["tenant"].id, "## 5. Confidentiality\n\n[[clause:confidentiality]]\n")
    assert CONFIDENTIALITY in text
    assert unresolved == []
    assert included[0]["key"] == "confidentiality"
    assert included[0]["version_no"] == 1


def test_expand_uses_the_approved_snapshot_not_a_live_edit(db, workspace):
    """The heart of it: an in-progress edit must not reach a contract."""
    c = _approved(db, workspace, "liability", LIABILITY)
    c.body = "Liability is unlimited and uncapped."   # author still drafting
    db.flush()
    text, _included, _unresolved = clause_service.expand(
        db, workspace["tenant"].id, "[[clause:liability]]")
    assert text == LIABILITY
    assert "unlimited" not in text


def test_an_unresolvable_reference_is_reported_not_dropped(db, workspace):
    """A contract quietly missing its liability cap is the worst thing this can produce."""
    text, included, unresolved = clause_service.expand(
        db, workspace["tenant"].id, "Before [[clause:nonexistent]] after")
    assert unresolved == ["nonexistent"]
    assert included == []
    assert "[[clause:nonexistent]]" in text


def test_an_unapproved_clause_does_not_resolve(db, workspace):
    _clause(db, workspace, "confidentiality", CONFIDENTIALITY)
    _text, _included, unresolved = clause_service.expand(
        db, workspace["tenant"].id, "[[clause:confidentiality]]")
    assert unresolved == ["confidentiality"]


def test_validate_references_explains_both_failure_modes(db, workspace):
    _clause(db, workspace, "draft_clause", CONFIDENTIALITY)
    problems = clause_service.validate_references(
        db, workspace["tenant"].id, "[[clause:draft_clause]] [[clause:missing_clause]]")
    assert any("does not exist" in p for p in problems)
    assert any("draft" in p for p in problems)


@pytest.mark.parametrize("tag", [
    "[[Clause:Confidentiality]]",
    "[[ clause : confidentiality ]]",
    "[[CLAUSE:CONFIDENTIALITY]]",
    "\\[\\[clause:confidentiality\\]\\]",
])
def test_a_harmless_variation_of_the_tag_still_resolves(db, workspace, tag):
    """Case, spacing and the escaping a rich-text editor adds are the same intent. A strict
    match ignored every one of them silently: approval passed and the clause was missing."""
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    text, included, unresolved = clause_service.expand(
        db, workspace["tenant"].id, f"Before {tag} after")
    assert CONFIDENTIALITY in text
    assert unresolved == []
    assert included[0]["key"] == "confidentiality"


def test_spaces_hyphens_and_escapes_in_a_key_map_to_underscores():
    body = "[[clause:Data-Protection]] [[clause:data protection]] \\[\\[clause:data\\_protection\\]\\]"
    assert clause_service.references_in(body) == ["data_protection"]


def test_a_mistyped_key_blocks_template_approval_by_name(db, workspace):
    """The failure that used to be silent now stops approval and names the tag."""
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="Typo", contract_type="nda",
        body="## Confidentiality\n\n[[clause:confidentialty]]", fields=[], status="draft",
        is_active=False, created_by=workspace["author"].id,
    )
    db.add(template)
    db.flush()
    with pytest.raises(Exception, match="confidentialty.*does not exist"):
        template_service.submit_for_approval(db, template, actor=workspace["author"])


def test_a_tag_with_no_key_is_reported(db, workspace):
    problems = clause_service.validate_references(db, workspace["tenant"].id, "[[clause: ]]")
    assert any("no key" in p for p in problems)


def test_a_tag_typed_inside_a_sentence_becomes_its_own_section(db, workspace):
    """Glued onto the sentence before it, the clause read as part of that paragraph."""
    clause = _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    body = "## Terms\nYou agree to the terms.  [[clause:confidentiality]]"
    text, _included, _unresolved = clause_service.expand(db, workspace["tenant"].id, body)
    assert f"You agree to the terms.  \n\n## {clause.title}\n\n{CONFIDENTIALITY}" in text


def test_a_tag_on_its_own_line_is_left_where_the_author_put_it(db, workspace):
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    body = "## 5. Confidentiality\n\n[[clause:confidentiality]]\n"
    text, _included, _unresolved = clause_service.expand(db, workspace["tenant"].id, body)
    assert text == f"## 5. Confidentiality\n\n{CONFIDENTIALITY}\n"


def test_a_clause_may_itself_contain_merge_fields(db, workspace):
    """Clause expansion runs before field substitution, so this has to work end to end."""
    _approved(db, workspace, "fees",
              "The Merchant shall pay {{monthly_fee}} on the first day of each month.")
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="Fee template", contract_type="vendor",
        body="## 3. Fees\n\n[[clause:fees]]\n",
        fields=[{"key": "monthly_fee", "type": "money", "required": True}],
        default_currency="PKR", status="draft", is_active=False,
        created_by=workspace["author"].id,
    )
    db.add(template)
    db.flush()

    template_service.submit_for_approval(db, template, actor=workspace["author"])
    template_service.approve(db, template, actor=workspace["approver"])
    body, _values, _v, included = template_service.generate_body(
        db, template, {"monthly_fee": 250000}, currency="PKR")

    assert "PKR 250,000.00 on the first day" in body
    assert [entry["key"] for entry in included] == ["fees"]


def test_a_template_cannot_be_approved_with_a_broken_reference(db, workspace):
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="Broken", contract_type="vendor",
        body="[[clause:not_there]]", fields=[], status="draft", is_active=False,
        created_by=workspace["author"].id,
    )
    db.add(template)
    db.flush()
    with pytest.raises(Exception, match="not_there"):
        template_service.submit_for_approval(db, template, actor=workspace["author"])


def test_generation_refuses_when_a_clause_loses_its_approval(db, workspace):
    """Retiring a clause must stop the drafts that depend on it, loudly."""
    clause = _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="NDA", contract_type="nda",
        body="[[clause:confidentiality]]", fields=[], status="draft", is_active=False,
        created_by=workspace["author"].id,
    )
    db.add(template)
    db.flush()
    template_service.submit_for_approval(db, template, actor=workspace["author"])
    template_service.approve(db, template, actor=workspace["approver"])

    clause_service.retire(db, clause, actor=workspace["approver"])
    db.flush()
    with pytest.raises(Exception, match="no approved wording"):
        template_service.generate_body(db, template, {})


# ---------------------------------------------------------------------------------------
# Playbook: scope
# ---------------------------------------------------------------------------------------


def test_a_playbook_only_applies_to_its_contract_type(db, workspace):
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    _playbook(db, workspace, [{"clause_key": "confidentiality", "kind": "required"}],
              contract_type="nda")
    assert playbook_service.applicable(db, _contract(db, workspace, "", type="vendor")) == []
    assert len(playbook_service.applicable(db, _contract(db, workspace, "", type="nda"))) == 1


def test_a_house_wide_playbook_applies_to_everything(db, workspace):
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    _playbook(db, workspace, [{"clause_key": "confidentiality", "kind": "required"}],
              contract_type="")
    assert len(playbook_service.applicable(db, _contract(db, workspace, "", type="lease"))) == 1


def test_both_the_house_policy_and_the_type_policy_apply(db, workspace):
    """Taking only the most specific would silently drop the general rules."""
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "confidentiality", "kind": "required"}],
              contract_type="")
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}],
              contract_type="vendor")
    assert len(playbook_service.applicable(db, _contract(db, workspace, "", type="vendor"))) == 2


def test_a_value_threshold_narrows_the_policy(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}],
              applies_when={"min_value": 1_000_000})
    assert playbook_service.applicable(db, _contract(db, workspace, "", value=500_000)) == []
    assert len(playbook_service.applicable(db, _contract(db, workspace, "", value=5_000_000))) == 1


def test_a_draft_playbook_does_not_apply(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}], status="draft")
    assert playbook_service.applicable(db, _contract(db, workspace, "")) == []


# ---------------------------------------------------------------------------------------
# Playbook: review
# ---------------------------------------------------------------------------------------


def test_an_unchanged_clause_is_present(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}])
    result = playbook_service.review(
        db, _contract(db, workspace, f"## 7. Liability\n\n{LIABILITY}\n"))
    assert result["ok"] is True
    assert result["findings"][0]["status"] == "present"


def test_formatting_alone_is_not_a_deviation(db, workspace):
    """Markdown emphasis, numbering and line wrapping all change between a template, a Word
    round-trip and a hand edit without changing the obligation. Flagging those would train
    reviewers to ignore the report."""
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}])
    reformatted = "7.1  **The total aggregate liability** of either party under this\n" \
                  "Agreement shall not exceed the total fees paid in the twelve (12)\n" \
                  "months preceding the claim."
    result = playbook_service.review(db, _contract(db, workspace, reformatted))
    assert result["findings"][0]["status"] == "present", result["findings"][0]["ratio"]


def test_a_missing_clause_is_reported_as_missing(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}])
    result = playbook_service.review(
        db, _contract(db, workspace, "## 1. Services\n\nThe supplier shall provide services."))
    assert result["ok"] is False
    assert result["findings"][0]["status"] == "missing"


def test_an_edited_cap_is_reported_as_altered_with_a_diff(db, workspace):
    """The interesting case, and the reason this feature exists: the clause is still there,
    so a reviewer skimming for headings sees nothing wrong — but the cap has doubled."""
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}])
    result = playbook_service.review(db, _contract(db, workspace, LIABILITY_FALLBACK))

    finding = result["findings"][0]
    assert finding["status"] == "altered"
    assert result["deviation_count"] == 1
    assert any("two times" in line for line in finding["diff"])


def test_prohibited_language_is_caught_when_present(db, workspace):
    _approved(db, workspace, "unlimited_liability", UNLIMITED_LIABILITY)
    _playbook(db, workspace, [{"clause_key": "unlimited_liability", "kind": "prohibited",
                               "severity": "blocker"}])
    result = playbook_service.review(db, _contract(db, workspace, UNLIMITED_LIABILITY))
    assert result["findings"][0]["status"] == "prohibited"


def test_prohibited_language_that_is_absent_produces_no_finding(db, workspace):
    _approved(db, workspace, "unlimited_liability", UNLIMITED_LIABILITY)
    _playbook(db, workspace, [{"clause_key": "unlimited_liability", "kind": "prohibited"}])
    result = playbook_service.review(
        db, _contract(db, workspace, "## 1. Services\n\nThe supplier shall provide services."))
    assert result["findings"] == []
    assert result["ok"] is True


def test_the_same_rule_in_two_playbooks_is_one_finding(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}], contract_type="")
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}],
              contract_type="vendor")
    result = playbook_service.review(db, _contract(db, workspace, ""))
    assert len(result["findings"]) == 1


def test_an_unapproved_clause_is_not_measured_against(db, workspace):
    """There is no authoritative wording to compare with, so a finding would be an invention."""
    _clause(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required"}])
    result = playbook_service.review(db, _contract(db, workspace, ""))
    assert result["checked"] == 0
    assert result["findings"] == []


def test_a_blocking_deviation_classifies_the_agreement_non_standard(db, workspace):
    """The classification is the point: a deviation that only produces a report is one
    somebody can approve without noticing."""
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required",
                               "severity": "blocker"}])
    contract = _contract(db, workspace, LIABILITY_FALLBACK)
    assert contract.is_non_standard is False

    result = playbook_service.review_and_classify(db, contract, actor=workspace["author"])
    assert result["classified_non_standard"] is True
    assert contract.is_non_standard is True
    assert "Liability" in contract.non_standard_reason


def test_a_warning_deviation_does_not_change_the_approval_route(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required",
                               "severity": "warning"}])
    contract = _contract(db, workspace, LIABILITY_FALLBACK)
    result = playbook_service.review_and_classify(db, contract, actor=workspace["author"])
    assert result["deviation_count"] == 1
    assert result["classified_non_standard"] is False
    assert contract.is_non_standard is False


def test_a_compliant_draft_passes_cleanly(db, workspace):
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [
        {"clause_key": "confidentiality", "kind": "required", "severity": "blocker"},
        {"clause_key": "liability", "kind": "required", "severity": "blocker"},
    ])
    body = f"## 5. Confidentiality\n\n{CONFIDENTIALITY}\n\n## 7. Liability\n\n{LIABILITY}\n"
    result = playbook_service.review_and_classify(db, _contract(db, workspace, body))
    assert result["ok"] is True
    assert result["checked"] == 2
    assert result["classified_non_standard"] is False


def test_a_generated_draft_is_compliant_with_the_policy_that_shaped_it(db, workspace):
    """End to end: the template composes the clauses, the playbook requires them, and the
    generated draft passes. If this fails the two halves have drifted apart."""
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    _approved(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [
        {"clause_key": "confidentiality", "kind": "required", "severity": "blocker"},
        {"clause_key": "liability", "kind": "required", "severity": "blocker"},
    ])
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="Vendor agreement", contract_type="vendor",
        body=("## 1. Services\n\nThe Supplier shall provide the services.\n\n"
              "## 5. Confidentiality\n\n[[clause:confidentiality]]\n\n"
              "## 7. Liability\n\n[[clause:liability]]\n"),
        fields=[], status="draft", is_active=False, created_by=workspace["author"].id,
    )
    db.add(template)
    db.flush()
    template_service.submit_for_approval(db, template, actor=workspace["author"])
    template_service.approve(db, template, actor=workspace["approver"])

    body, _values, _v, included = template_service.generate_body(db, template, {})
    assert len(included) == 2

    result = playbook_service.review(db, _contract(db, workspace, body))
    assert result["ok"] is True, result["findings"]


# ---------------------------------------------------------------------------------------
# Rule validation
# ---------------------------------------------------------------------------------------


def test_a_rule_naming_an_unknown_clause_is_rejected(db, workspace):
    problems = playbook_service.validate_rules(
        db, workspace["tenant"].id, [{"clause_key": "nope", "kind": "required"}])
    assert any("no such clause" in p for p in problems)


def test_unknown_rule_kinds_and_severities_are_rejected(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    problems = playbook_service.validate_rules(db, workspace["tenant"].id, [
        {"clause_key": "liability", "kind": "mandatory", "severity": "critical"},
    ])
    assert any("unknown rule kind" in p for p in problems)
    assert any("unknown severity" in p for p in problems)


def test_a_duplicated_rule_is_rejected(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    problems = playbook_service.validate_rules(db, workspace["tenant"].id, [
        {"clause_key": "liability", "kind": "required"},
        {"clause_key": "liability", "kind": "required"},
    ])
    assert any("twice" in p for p in problems)


# ---------------------------------------------------------------------------------------
# The seeded demo workspace
# ---------------------------------------------------------------------------------------


def test_the_seeded_demo_workspace_is_coherent_end_to_end(db):
    """The demo path is what a live bid demo runs on, so CI has to own it.

    Seed → the merchant template composes five library clauses → generating a draft resolves
    every one of them → the vendor playbook that requires those clauses passes. If any link in
    that chain breaks, the demo breaks in front of the customer rather than here.
    """
    from app import seed
    from app.database import set_request_tenant

    # `seed_if_empty` is a no-op once any tenant exists, and the suite has created plenty.
    # Drive the same data through a tenant of our own instead of special-casing the seeder.
    tenant = models.Tenant(id=uuid.uuid4().hex, name="Seed Check", slug=f"s-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    db.flush()
    set_request_tenant(tenant.id)
    owner = models.User(
        tenant_id=tenant.id, email=f"owner-{uuid.uuid4().hex[:8]}@example.com", name="Owner",
        password_hash=security.hash_password("Str0ng!Passw0rd1"), role="owner",
    )
    db.add(owner)
    db.flush()

    ws = {"tenant": tenant, "author": owner, "approver": owner}

    for spec in seed._DEMO_CLAUSES:
        spec = dict(spec)
        alternatives = spec.pop("alternatives", [])
        parent = _approved(db, ws, spec.pop("key"), spec.pop("body"),
                           title=spec.get("title", ""), category=spec.get("category", ""),
                           position=spec.get("position", "preferred"),
                           risk=spec.get("risk_level", "low"))
        for rank, alt in enumerate(alternatives, start=1):
            _approved(db, ws, alt["key"], alt["body"], title=alt.get("title", ""),
                      parent=parent, position=alt.get("position", "fallback"),
                      risk=alt.get("risk_level", "low"), rank=rank)

    for book in seed._DEMO_PLAYBOOKS:
        db.add(models.Playbook(tenant_id=tenant.id, created_by=owner.id, **book))
    db.flush()

    merchant = next(t for t in seed._DEMO_TEMPLATES
                    if t["name"] == "Merchant Acquiring Agreement")
    template = models.ContractTemplate(
        tenant_id=tenant.id, created_by=owner.id, status="draft", is_active=False,
        **{k: v for k, v in merchant.items()},
    )
    db.add(template)
    db.flush()

    template_service.submit_for_approval(db, template, actor=owner)
    template_service.approve(db, template, actor=owner)

    body, _values, _v, included = template_service.generate_body(
        db, template,
        {"merchant_name": "Acme Trading (Private) Limited", "merchant_ntn": "1234567-8",
         "region": "Sindh", "channels": ["POS", "QR"], "mdr_percent": 1.75,
         "settlement_days": 2, "security_deposit": 250000, "start_date": "2026-09-01"},
        contract_vars={"our_entity": "Mobilink Microfinance Bank",
                       "today": "2026-08-26",
                       "governing_law": "Islamic Republic of Pakistan"},
        currency="PKR",
    )

    assert "[[clause:" not in body, "a clause reference did not resolve"
    assert "{{" not in body, "a merge field did not resolve"
    assert {entry["key"] for entry in included} == {
        "termination_for_convenience", "confidentiality", "data_protection",
        "limitation_of_liability", "governing_law_pk",
    }

    result = playbook_service.review(db, _contract(db, ws, body, type="vendor"))
    assert result["ok"] is True, result["findings"]
    assert result["checked"] == 6          # 4 vendor rules + 2 house rules


# ---------------------------------------------------------------------------------------
# Guided drafting: clause selection (Phase 3, item 5)
# ---------------------------------------------------------------------------------------


def _template_with(db, ws, body, *, fields=None) -> models.ContractTemplate:
    t = models.ContractTemplate(
        tenant_id=ws["tenant"].id, name="Vendor agreement", contract_type="vendor",
        body=body, fields=fields or [], status="draft", is_active=False,
        created_by=ws["author"].id,
    )
    db.add(t)
    db.flush()
    template_service.submit_for_approval(db, t, actor=ws["author"])
    template_service.approve(db, t, actor=ws["approver"])
    return t


def test_a_drafter_can_choose_a_pre_approved_fallback(db, workspace):
    """The wizard's clause-selection step. Choosing a fallback stays inside policy."""
    parent = _approved(db, workspace, "liability", LIABILITY)
    _approved(db, workspace, "liability_2x", LIABILITY_FALLBACK, parent=parent,
              position="acceptable", rank=1)
    template = _template_with(db, workspace, "## 7. Liability\n\n[[clause:liability]]\n")

    body, _v, _n, included = template_service.generate_body(
        db, template, {}, choices={"liability": "liability_2x"})

    assert "two times (2x)" in body
    assert included[0]["key"] == "liability_2x"
    assert included[0]["substituted_for"] == "liability"


def test_no_choice_means_the_preferred_wording(db, workspace):
    parent = _approved(db, workspace, "liability", LIABILITY)
    _approved(db, workspace, "liability_2x", LIABILITY_FALLBACK, parent=parent, rank=1)
    template = _template_with(db, workspace, "[[clause:liability]]")

    body, _v, _n, included = template_service.generate_body(db, template, {})
    assert body.strip() == LIABILITY
    assert included[0]["substituted_for"] is None


def test_an_arbitrary_clause_cannot_be_swapped_in(db, workspace):
    """Not a fallback position — that is editing the contract through a drop-down, without
    the approval that editing the template would have required."""
    _approved(db, workspace, "liability", LIABILITY)
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    template = _template_with(db, workspace, "[[clause:liability]]")

    with pytest.raises(ClauseError, match="not an approved alternative"):
        template_service.generate_body(
            db, template, {}, choices={"liability": "confidentiality"})


def test_an_unapproved_alternative_cannot_be_chosen(db, workspace):
    parent = _approved(db, workspace, "liability", LIABILITY)
    _clause(db, workspace, "liability_draft", LIABILITY_FALLBACK, parent=parent)
    template = _template_with(db, workspace, "[[clause:liability]]")

    with pytest.raises(ClauseError, match="not been approved"):
        template_service.generate_body(
            db, template, {}, choices={"liability": "liability_draft"})


def test_an_optional_clause_can_be_appended(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    template = _template_with(db, workspace, "[[clause:liability]]")

    body, _v, _n, included = template_service.generate_body(
        db, template, {}, extras=["confidentiality"])

    assert LIABILITY in body and CONFIDENTIALITY in body
    assert {e["key"] for e in included} == {"liability", "confidentiality"}


def test_the_wizard_is_told_the_options_and_their_risk(db, workspace):
    """Presenting fallbacks without saying which is riskier would be worse than no choice."""
    parent = _approved(db, workspace, "liability", LIABILITY, risk="high")
    _approved(db, workspace, "liability_2x", LIABILITY_FALLBACK, parent=parent,
              position="acceptable", risk="critical", rank=1)
    template = _template_with(db, workspace, "[[clause:liability]]")

    choices = template_service.clause_choices(db, template)
    assert len(choices) == 1
    options = choices[0]["options"]
    assert [o["key"] for o in options] == ["liability", "liability_2x"]
    assert options[0]["is_default"] is True
    assert options[1]["risk_level"] == "critical"
    assert options[1]["position"] == "acceptable"


def test_optional_clauses_exclude_what_the_template_already_uses(db, workspace):
    _approved(db, workspace, "liability", LIABILITY)
    _approved(db, workspace, "confidentiality", CONFIDENTIALITY)
    template = _template_with(db, workspace, "[[clause:liability]]")

    offered = {c["key"] for c in template_service.optional_clauses(db, template)}
    assert "confidentiality" in offered
    assert "liability" not in offered


def test_a_chosen_fallback_still_satisfies_a_playbook_that_allows_it(db, workspace):
    """A fallback is pre-approved wording, so choosing one is not a deviation of the
    alternative's own rule — the policy has to name which one it requires."""
    parent = _approved(db, workspace, "liability", LIABILITY)
    _approved(db, workspace, "liability_2x", LIABILITY_FALLBACK, parent=parent, rank=1)
    _playbook(db, workspace, [{"clause_key": "liability_2x", "kind": "required",
                               "severity": "blocker"}])
    template = _template_with(db, workspace, "[[clause:liability]]")

    body, _v, _n, _inc = template_service.generate_body(
        db, template, {}, choices={"liability": "liability_2x"})
    result = playbook_service.review(db, _contract(db, workspace, body))
    assert result["ok"] is True, result["findings"]
