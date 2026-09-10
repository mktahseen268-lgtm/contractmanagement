"""Merge fields, template approval, and generation.

The RFI's intake mechanic (§2.3) in one sentence: pick the agreement type, fill a form of
drop-downs and lists-of-values, and the system generates the draft from the **pre-approved**
template. These tests hold the three properties that make that sentence true rather than
merely plausible:

- the form is validated **server-side**, so a bad value never reaches a contract;
- a placeholder nothing fills is an **error**, never a silent blank in an executed agreement;
- what generated the draft is the **approved snapshot**, not whatever the template says today.

Requirements: SOW-04.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import merge_engine, models, security, template_service
from app.merge_engine import FieldDef, MergeError

# ---------------------------------------------------------------------------------------
# The engine on its own
# ---------------------------------------------------------------------------------------


def _fields(*specs: dict) -> list[FieldDef]:
    return merge_engine.parse_fields(list(specs))


def test_placeholders_are_found_in_order_without_duplicates():
    body = "{{merchant_name}} agrees. {{fee}} payable. {{merchant_name}} confirms."
    assert merge_engine.placeholders_in(body) == ["merchant_name", "fee"]


def test_definition_rejects_a_select_with_no_options():
    problems = merge_engine.validate_definition(
        _fields({"key": "region", "type": "select", "options": []})
    )
    assert any("at least one option" in p for p in problems)


def test_definition_rejects_duplicate_and_malformed_keys():
    problems = merge_engine.validate_definition(
        _fields({"key": "fee"}, {"key": "fee"}, {"key": "Not A Key"})
    )
    assert any("duplicate key" in p for p in problems)
    assert any("not a valid key" in p for p in problems)


def test_definition_flags_a_placeholder_no_field_supplies():
    """A template referencing {{gap}} can never be filled. Catching it at authoring time costs
    a minute; catching it at generation time blocks whoever is raising the agreement."""
    problems = merge_engine.validate_definition(
        _fields({"key": "fee", "type": "money"}), body="Pay {{fee}} by {{gap}}."
    )
    assert len(problems) == 1
    assert "{{gap}}" in problems[0]


def test_definition_accepts_contract_derived_placeholders():
    """{{counterparty}} and friends come from the contract, not the form — not a defect."""
    assert merge_engine.validate_definition([], body="Between {{our_entity}} and {{counterparty}}.") == []


@pytest.mark.parametrize(
    "spec,value,expected",
    [
        ({"key": "n", "type": "number"}, "1,500", 1500.0),
        ({"key": "m", "type": "money"}, "250000", 250000.0),
        ({"key": "d", "type": "date"}, "2026-03-01", dt.date(2026, 3, 1)),
        ({"key": "b", "type": "boolean"}, "yes", True),
        ({"key": "b", "type": "boolean"}, "no", False),
        ({"key": "t", "type": "text"}, "  padded  ", "padded"),
    ],
)
def test_values_are_coerced_to_their_declared_type(spec, value, expected):
    cleaned, errors = merge_engine.validate_values(_fields(spec), {spec["key"]: value})
    assert errors == []
    assert cleaned[spec["key"]] == expected


def test_a_money_field_refuses_prose():
    """'about 5 lakh' produces a contract nobody can report on. Reject it at the boundary."""
    _cleaned, errors = merge_engine.validate_values(
        _fields({"key": "fee", "type": "money", "label": "Monthly fee"}), {"fee": "about 5 lakh"}
    )
    assert errors == ["Monthly fee must be a number."]


def test_a_select_refuses_a_value_outside_its_list():
    fields = _fields({"key": "region", "type": "select", "options": ["Sindh", "Punjab"]})
    _cleaned, errors = merge_engine.validate_values(fields, {"region": "Balochistan"})
    assert len(errors) == 1
    assert "not one of the permitted values" in errors[0]


def test_multiselect_reports_every_invalid_choice_at_once():
    fields = _fields({"key": "svc", "type": "multiselect", "options": ["a", "b"]})
    _cleaned, errors = merge_engine.validate_values(fields, {"svc": ["a", "x", "y"]})
    assert "x, y" in errors[0]


def test_numeric_bounds_are_enforced():
    fields = _fields({"key": "term", "type": "number", "minimum": 1, "maximum": 60})
    _cleaned, errors = merge_engine.validate_values(fields, {"term": 120})
    assert "at most" in errors[0]


def test_a_required_field_left_blank_is_an_error():
    fields = _fields({"key": "fee", "type": "money", "required": True, "label": "Fee"})
    _cleaned, errors = merge_engine.validate_values(fields, {"fee": "  "})
    assert errors == ["Fee is required."]


def test_an_optional_field_left_blank_is_not():
    fields = _fields({"key": "note", "type": "text"})
    cleaned, errors = merge_engine.validate_values(fields, {})
    assert errors == []
    assert cleaned["note"] == ""


def test_a_default_fills_in_for_an_absent_value():
    fields = _fields({"key": "region", "type": "select", "options": ["Sindh"], "default": "Sindh"})
    cleaned, errors = merge_engine.validate_values(fields, {})
    assert errors == []
    assert cleaned["region"] == "Sindh"


def test_unknown_submitted_keys_are_dropped_not_rejected():
    """A template edited between rendering the form and submitting it must not throw away
    everything the user typed."""
    cleaned, errors = merge_engine.validate_values(
        _fields({"key": "fee", "type": "money"}), {"fee": 10, "removed_field": "x"}
    )
    assert errors == []
    assert cleaned == {"fee": 10.0}


# --- rendering --------------------------------------------------------------------------


def test_render_substitutes_and_formats_deterministically():
    fields = _fields(
        {"key": "fee", "type": "money"},
        {"key": "start", "type": "date"},
        {"key": "seats", "type": "number"},
    )
    values = {"fee": 250000, "start": dt.date(2026, 3, 1), "seats": 12}
    result = merge_engine.render(
        "Fee {{fee}} from {{start}} for {{seats}} seats.", fields, values, currency="PKR"
    )
    assert result.text == "Fee PKR 250,000.00 from 01 March 2026 for 12 seats."
    assert result.ok


def test_render_is_stable_across_repeated_calls():
    """The DOCX a counterparty receives must say exactly what the record says."""
    fields = _fields({"key": "fee", "type": "money"})
    body = "Fee: {{fee}}"
    first = merge_engine.render(body, fields, {"fee": 1234.5}, currency="PKR").text
    second = merge_engine.render(body, fields, {"fee": 1234.5}, currency="PKR").text
    assert first == second == "Fee: PKR 1,234.50"


def test_an_unfilled_placeholder_stays_visible_and_is_reported():
    """A visible {{monthly_fee}} is an obvious defect. A silent gap is one that gets signed."""
    result = merge_engine.render("Pay {{monthly_fee}} monthly.", [], {})
    assert result.unresolved == ["monthly_fee"]
    assert "{{monthly_fee}}" in result.text
    assert not result.ok


def test_an_empty_value_counts_as_unresolved_rather_than_blanking_the_document():
    fields = _fields({"key": "fee", "type": "text"})
    result = merge_engine.render("Pay {{fee}}.", fields, {"fee": ""})
    assert result.unresolved == ["fee"]
    assert "{{fee}}" in result.text


def test_template_fields_win_over_contract_derived_values():
    """A template can capture the counterparty's full legal name and override the short one."""
    fields = _fields({"key": "counterparty", "type": "text"})
    result = merge_engine.render(
        "Between us and {{counterparty}}.", fields,
        {"counterparty": "Acme Trading (Private) Limited"},
        extra={"counterparty": "Acme"},
    )
    assert "Acme Trading (Private) Limited" in result.text


def test_multiselect_renders_as_a_readable_list():
    fields = _fields({"key": "svc", "type": "multiselect", "options": ["ATM", "POS", "QR"]})
    result = merge_engine.render("Services: {{svc}}.", fields, {"svc": ["ATM", "QR"]})
    assert result.text == "Services: ATM, QR."


def test_suggest_fields_scaffolds_from_a_pasted_body():
    suggested = merge_engine.suggest_fields(
        "{{merchant_name}} pays {{monthly_fee}} from {{start_date}} for {{seat_count}}.", []
    )
    assert [(f.key, f.type) for f in suggested] == [
        ("merchant_name", "text"),
        ("monthly_fee", "money"),
        ("start_date", "date"),
        ("seat_count", "number"),
    ]


def test_suggest_fields_skips_what_is_already_defined():
    existing = _fields({"key": "fee", "type": "money"})
    assert merge_engine.suggest_fields("{{fee}} and {{other}}", existing)[0].key == "other"


# ---------------------------------------------------------------------------------------
# Template lifecycle
# ---------------------------------------------------------------------------------------

MERCHANT_BODY = (
    "1. This agreement is between {{our_entity}} and {{merchant_name}}.\n"
    "2. The merchant operates in {{region}} and pays {{monthly_fee}} monthly.\n"
    "3. Services provided: {{services}}.\n"
    "4. The term begins {{start_date}}.\n"
)

MERCHANT_FIELDS = [
    {"key": "merchant_name", "label": "Merchant legal name", "type": "text", "required": True},
    {"key": "region", "type": "select", "options": ["Sindh", "Punjab", "KPK"], "required": True},
    {"key": "monthly_fee", "type": "money", "required": True, "minimum": 0},
    {"key": "services", "type": "multiselect", "options": ["ATM", "POS", "QR"]},
    {"key": "start_date", "type": "date", "required": True},
]


@pytest.fixture()
def workspace(db, make_user):
    """One tenant, an author who writes templates and a manager who approves them.

    Two people on purpose: separation of duties is the control under test, and it cannot be
    exercised with a single user.
    """
    author, tenant = make_user(name="Template Author")
    approver = models.User(
        tenant_id=tenant.id, email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        name="Legal Reviewer", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="manager",
    )
    db.add(approver)
    db.commit()
    return {"tenant": tenant, "user": author, "approver": approver}


@pytest.fixture()
def user(workspace) -> models.User:
    return workspace["user"]


@pytest.fixture()
def approver(workspace) -> models.User:
    return workspace["approver"]


@pytest.fixture()
def db_session(db):
    return db


@pytest.fixture()
def template(db, workspace) -> models.ContractTemplate:
    t = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="Merchant Acquiring Agreement",
        contract_type="vendor", body=MERCHANT_BODY, fields=MERCHANT_FIELDS,
        default_currency="PKR", status="draft", is_active=False,
        created_by=workspace["user"].id,
    )
    db.add(t)
    db.commit()
    return t


def test_a_draft_template_cannot_generate(db_session, template):
    with pytest.raises(MergeError, match="not been approved"):
        template_service.generate_body(db_session, template, {})


def test_submit_then_approve_freezes_a_version(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    assert template.status == "pending_approval"
    assert template.is_active is False

    snapshot = template_service.approve(db_session, template, actor=approver, note="Legal sign-off")
    assert template.status == "active"
    assert template.is_active is True
    assert template.version_no == 1
    assert snapshot.version_no == 1
    assert snapshot.body == MERCHANT_BODY
    assert snapshot.approved_by == approver.id


def test_the_author_cannot_approve_their_own_template(db_session, template, user, approver):
    """Separation of duties: the control this whole feature exists to add."""
    template_service.submit_for_approval(db_session, template, actor=user)
    template.created_by = approver.id          # the reviewer is now also the author
    with pytest.raises(MergeError, match="someone other than its author"):
        template_service.approve(db_session, template, actor=approver)


def test_an_author_role_cannot_approve_at_all(db_session, template, user):
    """`author` can write templates. Writing one must not be the same as blessing it."""
    template_service.submit_for_approval(db_session, template, actor=user)
    junior = models.User(
        tenant_id=template.tenant_id, email=f"junior-{uuid.uuid4().hex[:8]}@example.com",
        name="Junior", password_hash=security.hash_password("Str0ng!Passw0rd1"), role="author",
    )
    db_session.add(junior)
    db_session.flush()
    with pytest.raises(MergeError, match="do not have permission"):
        template_service.approve(db_session, template, actor=junior)


def test_an_owner_may_approve_their_own_template_in_a_small_workspace(db_session, template, user):
    """The exemption is deliberate: a two-person workspace would otherwise be unable to
    approve anything at all, and a control nobody can satisfy gets switched off."""
    assert user.role == "owner"
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=user)
    assert template.status == "active"


def test_a_template_with_an_unfillable_placeholder_cannot_be_submitted(db_session, template, user):
    template.body = MERCHANT_BODY + "5. Settlement to {{bank_account}}.\n"
    with pytest.raises(MergeError, match="bank_account"):
        template_service.submit_for_approval(db_session, template, actor=user)


def test_an_empty_template_cannot_be_submitted(db_session, template, user):
    template.body = "   "
    with pytest.raises(MergeError, match="needs a body"):
        template_service.submit_for_approval(db_session, template, actor=user)


def test_rejection_returns_it_to_draft_with_the_reason(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.reject(db_session, template, actor=approver, reason="Clause 3 is wrong.")
    assert template.status == "draft"
    assert template.is_active is False
    assert "Clause 3" in template.approval_note


def test_editing_the_form_of_an_approved_template_un_approves_it(db_session, template, user, approver):
    """Widening a list-of-values is a real change to what the approved template permits, so it
    goes back through approval rather than taking effect silently."""
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)

    widened = [dict(f) for f in MERCHANT_FIELDS]
    widened[1] = {**widened[1], "options": ["Sindh", "Punjab", "KPK", "Balochistan"]}
    template_service.set_fields(db_session, template, widened)

    assert template.status == "draft"
    assert template.is_active is False


def test_removing_a_field_the_body_still_uses_is_refused(db_session, template):
    """The template would generate a contract with a hole in it. Refuse at authoring time."""
    with pytest.raises(MergeError, match="monthly_fee"):
        template_service.set_fields(db_session, template, MERCHANT_FIELDS[:2])


def test_set_fields_refuses_a_definition_that_cannot_work(db_session, template):
    with pytest.raises(MergeError, match="at least one option"):
        template_service.set_fields(db_session, template,
                                    [{"key": "region", "type": "select", "options": []}])


def test_approving_again_supersedes_the_previous_version(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    first = template_service.approve(db_session, template, actor=approver)
    template.body = MERCHANT_BODY.replace("The term begins", "The term commences")
    template.status = "draft"
    template_service.submit_for_approval(db_session, template, actor=user)
    second = template_service.approve(db_session, template, actor=approver, note="Fee cadence")

    assert first.status == "superseded"
    assert second.status == "active"
    assert second.version_no == 2
    assert template.version_no == 2


def test_generation_uses_the_approved_snapshot_not_the_live_edit(db_session, template, user, approver):
    """The heart of "generated from the pre-approved template". An in-progress edit must not
    leak into a contract before anyone has approved it."""
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)

    template.body = MERCHANT_BODY + "5. Unapproved clause the author is still drafting.\n"
    db_session.flush()

    body, _values, version_no, _clauses = template_service.generate_body(
        db_session, template,
        {"merchant_name": "Acme", "region": "Sindh", "monthly_fee": 50000,
         "start_date": "2026-03-01", "services": ["POS"]},
        contract_vars={"our_entity": "Mobilink Microfinance Bank"},
    )
    assert "Unapproved clause" not in body
    assert version_no == 1


def test_generation_refuses_when_a_required_field_is_missing(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)
    with pytest.raises(MergeError, match="required"):
        template_service.generate_body(db_session, template, {"merchant_name": "Acme"})


def test_generation_refuses_rather_than_leaving_a_gap(db_session, template, user, approver):
    """`our_entity` comes from the tenant; if the caller supplies no contract variables at all
    the document would have a hole in it. Refusing is the correct behaviour."""
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)
    with pytest.raises(MergeError, match="our_entity"):
        template_service.generate_body(
            db_session, template,
            {"merchant_name": "Acme", "region": "Sindh", "monthly_fee": 1,
             "start_date": "2026-01-01"},
        )


def test_allow_unresolved_is_an_explicit_opt_in(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)
    body, _values, _v, _clauses = template_service.generate_body(
        db_session, template,
        {"merchant_name": "Acme", "region": "Sindh", "monthly_fee": 1,
         "start_date": "2026-01-01"},
        allow_unresolved=True,
    )
    assert "{{our_entity}}" in body


def test_generated_body_reads_correctly_end_to_end(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)
    body, values, _v, _clauses = template_service.generate_body(
        db_session, template,
        {"merchant_name": "Acme Trading (Private) Limited", "region": "Punjab",
         "monthly_fee": 250000, "start_date": "2026-03-01", "services": ["ATM", "QR"]},
        contract_vars={"our_entity": "Mobilink Microfinance Bank"},
        currency="PKR",
    )
    assert "between Mobilink Microfinance Bank and Acme Trading (Private) Limited" in body
    assert "operates in Punjab and pays PKR 250,000.00 monthly" in body
    assert "Services provided: ATM, QR." in body
    assert "The term begins 01 March 2026." in body
    assert "{{" not in body
    assert values["monthly_fee"] == 250000.0


def test_retiring_takes_the_template_and_its_versions_out_of_use(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    snapshot = template_service.approve(db_session, template, actor=approver)
    template_service.retire(db_session, template, actor=approver)
    assert template.status == "retired"
    assert template.is_active is False
    assert snapshot.status == "retired"
    with pytest.raises(MergeError, match="not been approved"):
        template_service.generate_body(db_session, template, {})


def test_form_schema_reports_whether_the_template_is_usable(db_session, template, user, approver):
    schema = template_service.form_schema(db_session, template)
    assert schema["usable"] is False
    assert [f["key"] for f in schema["fields"]][:2] == ["merchant_name", "region"]
    assert schema["defaults"]["currency"] == "PKR"

    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)
    assert template_service.form_schema(db_session, template)["usable"] is True


def test_preview_reports_errors_without_persisting_anything(db_session, template, user, approver):
    template_service.submit_for_approval(db_session, template, actor=user)
    template_service.approve(db_session, template, actor=approver)
    result = template_service.preview(db_session, template, {"monthly_fee": "not a number"})
    assert result["ok"] is False
    assert any("must be a number" in e for e in result["errors"])
    # Scoped to this tenant: the suite shares a database, so a global count would be counting
    # every other test's contracts.
    assert db_session.query(models.Contract).filter_by(tenant_id=template.tenant_id).count() == 0


# ---------------------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------------------


def _login(client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


PASSWORD = "Str0ng!Passw0rd1"


def _signed_in(client, db, user_id: str) -> dict:
    """Give an existing user a password we know, then log in as them.

    `make_user` hands back a detached instance from its own session, so the hash has to be set
    through *this* session or the update never reaches the database.
    """
    from app import models, security

    row = db.get(models.User, user_id)
    row.password_hash = security.hash_password(PASSWORD)
    db.commit()
    token = _login(client, row.email, PASSWORD)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def api(client, db, make_user):
    """A signed-in author and a signed-in manager in one workspace, with auth headers."""
    from app import security

    # An explicit address: the factory default uses the .test TLD, which email-validator
    # rejects as reserved, and /auth/login validates the address.
    author, tenant = make_user(email=f"author-{uuid.uuid4().hex[:8]}@example.com",
                               name="Intake Author")
    approver = models.User(
        tenant_id=tenant.id, email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        name="Legal Reviewer", password_hash=security.hash_password(PASSWORD), role="manager",
    )
    db.add(approver)
    db.commit()

    return {
        "tenant": tenant, "author": author, "approver": approver,
        "author_h": _signed_in(client, db, author.id),
        "approver_h": {"Authorization": f"Bearer {_login(client, approver.email, PASSWORD)}"},
    }


def _create_template(client, api) -> str:
    r = client.post("/templates", headers=api["author_h"], json={
        "name": "Merchant Acquiring Agreement", "contract_type": "vendor",
        "body": MERCHANT_BODY, "fields": MERCHANT_FIELDS, "default_currency": "PKR",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _approve(client, api, tid: str) -> None:
    assert client.post(f"/templates/{tid}/submit", headers=api["author_h"]).status_code == 200
    r = client.post(f"/templates/{tid}/approve", headers=api["approver_h"],
                    json={"note": "Legal sign-off"})
    assert r.status_code == 200, r.text


def test_a_new_template_is_not_usable_until_approved(client, api):
    tid = _create_template(client, api)
    body = client.get(f"/templates/{tid}", headers=api["author_h"]).json()
    assert body["status"] == "draft"
    assert body["is_active"] is False

    r = client.post(f"/templates/{tid}/generate", headers=api["author_h"],
                    json={"title": "Acme", "values": {}})
    assert r.status_code == 400
    assert "not been approved" in r.json()["detail"]


def test_creating_a_template_with_a_broken_form_is_rejected(client, api):
    r = client.post("/templates", headers=api["author_h"], json={
        "name": "Broken", "body": "Pay {{fee}}.",
        "fields": [{"key": "fee", "type": "select", "options": []}],
    })
    assert r.status_code == 400
    assert "at least one option" in r.json()["detail"]


def test_the_form_endpoint_describes_the_intake_screen(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    form = client.get(f"/templates/{tid}/form", headers=api["author_h"]).json()
    assert form["usable"] is True
    assert form["problems"] == []
    region = next(f for f in form["fields"] if f["key"] == "region")
    assert region["type"] == "select"
    assert region["options"] == ["Sindh", "Punjab", "KPK"]
    assert form["defaults"]["currency"] == "PKR"


def test_preview_renders_without_creating_a_contract(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    before = client.get("/contracts", headers=api["author_h"]).json()["total"]

    r = client.post(f"/templates/{tid}/preview", headers=api["author_h"], json={
        "counterparty": "Acme Trading", "title": "Acme Acquiring",
        "values": {"merchant_name": "Acme Trading (Private) Limited", "region": "Sindh",
                   "monthly_fee": 250000, "start_date": "2026-03-01", "services": ["POS"]},
    })
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["ok"] is True
    assert "PKR 250,000.00" in result["body"]
    assert client.get("/contracts", headers=api["author_h"]).json()["total"] == before


def test_generate_creates_the_draft_and_records_the_template_revision(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    r = client.post(f"/templates/{tid}/generate", headers=api["author_h"], json={
        "title": "Acme Acquiring Agreement", "counterparty": "Acme Trading",
        "value": 250000, "effective_date": "2026-03-01",
        "values": {"merchant_name": "Acme Trading (Private) Limited", "region": "Punjab",
                   "monthly_fee": 250000, "start_date": "2026-03-01",
                   "services": ["ATM", "QR"]},
    })
    assert r.status_code == 201, r.text
    contract = r.json()
    assert contract["status"] == "draft"
    assert "Acme Trading (Private) Limited" in contract["body"]
    assert "PKR 250,000.00" in contract["body"]
    assert "{{" not in contract["body"]


def test_generate_rejects_a_value_outside_the_permitted_list(client, api):
    """Server-side, because the browser is not the system of record."""
    tid = _create_template(client, api)
    _approve(client, api, tid)
    r = client.post(f"/templates/{tid}/generate", headers=api["author_h"], json={
        "title": "Bad", "values": {"merchant_name": "Acme", "region": "Atlantis",
                                   "monthly_fee": 1, "start_date": "2026-03-01"},
    })
    assert r.status_code == 400
    assert "not one of the permitted values" in r.json()["detail"]


def test_generate_reports_every_missing_required_field_at_once(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    r = client.post(f"/templates/{tid}/generate", headers=api["author_h"],
                    json={"title": "Bad", "values": {}})
    assert r.status_code == 400
    detail = r.json()["detail"]
    for label in ("Merchant legal name", "Region", "Monthly Fee", "Start Date"):
        assert label in detail


def test_the_author_cannot_approve_their_own_template_over_the_api(client, db, api):
    tid = _create_template(client, api)
    assert client.post(f"/templates/{tid}/submit", headers=api["author_h"]).status_code == 200
    # The author is an owner, who is deliberately exempt so a two-person workspace can still
    # approve anything. Demote them and the separation-of-duties rule applies.
    db.get(models.User, api["author"].id).role = "manager"
    db.commit()
    r = client.post(f"/templates/{tid}/approve", headers=api["author_h"], json={})
    assert r.status_code == 400
    assert "other than its author" in r.json()["detail"]


def test_rejection_sends_it_back_with_the_reason(client, api):
    tid = _create_template(client, api)
    assert client.post(f"/templates/{tid}/submit", headers=api["author_h"]).status_code == 200
    r = client.post(f"/templates/{tid}/reject", headers=api["approver_h"],
                    json={"reason": "Clause 3 needs the settlement window."})
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    assert "settlement window" in r.json()["approval_note"]


def test_versions_list_the_approved_revisions_newest_first(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    client.patch(f"/templates/{tid}", headers=api["author_h"],
                 json={"body": MERCHANT_BODY + "5. Notices in writing.\n"})
    _approve(client, api, tid)

    versions = client.get(f"/templates/{tid}/versions", headers=api["author_h"]).json()
    assert [v["version_no"] for v in versions] == [2, 1]
    assert versions[0]["status"] == "active"
    assert versions[1]["status"] == "superseded"


def test_editing_approved_wording_takes_it_out_of_use(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    r = client.patch(f"/templates/{tid}", headers=api["author_h"],
                     json={"body": MERCHANT_BODY + "5. A clause nobody approved.\n"})
    assert r.status_code == 200
    assert r.json()["status"] == "draft"

    blocked = client.post(f"/templates/{tid}/generate", headers=api["author_h"],
                          json={"title": "x", "values": {}})
    assert blocked.status_code == 400


def test_suggest_fields_scaffolds_the_form_from_a_pasted_body(client, api):
    r = client.post("/templates/suggest-fields", headers=api["author_h"],
                    json={"body": "{{merchant_name}} pays {{monthly_fee}} from {{start_date}}."})
    assert r.status_code == 200
    assert [(f["key"], f["type"]) for f in r.json()["fields"]] == [
        ("merchant_name", "text"), ("monthly_fee", "money"), ("start_date", "date"),
    ]


def test_a_retired_template_cannot_generate_over_the_api(client, api):
    tid = _create_template(client, api)
    _approve(client, api, tid)
    assert client.post(f"/templates/{tid}/retire", headers=api["approver_h"]).status_code == 200
    r = client.post(f"/templates/{tid}/generate", headers=api["author_h"],
                    json={"title": "x", "values": {}})
    assert r.status_code == 400


def test_a_template_from_another_tenant_is_invisible(client, api, make_user, db):
    """Belt and braces on top of row security."""
    tid = _create_template(client, api)
    _approve(client, api, tid)

    outsider, _tenant = make_user(email=f"other-{uuid.uuid4().hex[:8]}@example.com",
                                  name="Other Tenant")
    headers = _signed_in(client, db, outsider.id)

    assert client.get(f"/templates/{tid}/form", headers=headers).status_code == 404
    assert client.post(f"/templates/{tid}/generate", headers=headers,
                       json={"title": "x", "values": {}}).status_code == 404


def test_the_contract_records_which_template_revision_generated_it(client, db, api):
    """Two years later somebody has to answer "was this raised from the approved template,
    and with what values?". The contract itself has to carry the answer."""
    tid = _create_template(client, api)
    _approve(client, api, tid)
    r = client.post(f"/templates/{tid}/generate", headers=api["author_h"], json={
        "title": "Acme Acquiring Agreement", "counterparty": "Acme Trading",
        "values": {"merchant_name": "Acme Trading (Private) Limited", "region": "Sindh",
                   "monthly_fee": 250000, "start_date": "2026-03-01", "services": ["QR"]},
    })
    assert r.status_code == 201, r.text

    contract = db.get(models.Contract, r.json()["id"])
    db.refresh(contract)
    assert contract.template_id == tid
    assert contract.template_version_no == 1
    # Stored JSON-native, so the row survives a round-trip through the database.
    assert contract.merge_values["start_date"] == "2026-03-01"
    assert contract.merge_values["monthly_fee"] == 250000.0
    assert contract.merge_values["services"] == ["QR"]


def test_stored_values_render_identically_to_the_originals(db, template, user, approver):
    """`jsonable` must not change what the document says — otherwise regenerating from the
    stored answers would silently produce different wording."""
    template_service.submit_for_approval(db, template, actor=user)
    template_service.approve(db, template, actor=approver)
    submitted = {"merchant_name": "Acme", "region": "Sindh", "monthly_fee": 250000,
                 "start_date": "2026-03-01", "services": ["ATM"]}
    contract_vars = {"our_entity": "MMBL"}

    body, values, _v, _clauses = template_service.generate_body(
        db, template, submitted, contract_vars=contract_vars, currency="PKR")
    round_tripped, _values, _v2, _c2 = template_service.generate_body(
        db, template, merge_engine.jsonable(values), contract_vars=contract_vars,
        currency="PKR")
    assert body == round_tripped
