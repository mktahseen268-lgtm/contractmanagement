"""Sign-off readiness pack.

The document a signatory reads before committing. The claim under test is narrow but load
bearing: **`ready` is false whenever anything should stop execution**, and the reason is
stated. An agreement that is not safe to sign but reports ready is the one failure that
matters here — everything else is presentation.

Requirements: SOW-11.
"""

from __future__ import annotations

import uuid

import pytest

from app import clause_service, models, pdf, readiness, security


LIABILITY = (
    "The total aggregate liability of either party under this Agreement shall not exceed the "
    "total fees paid in the twelve (12) months preceding the claim."
)
LIABILITY_CHANGED = LIABILITY.replace("shall not exceed the", "shall not exceed five times the")


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"ready-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    approver = models.User(
        tenant_id=tenant.id, email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        name="Legal Reviewer", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="manager",
    )
    db.add(approver)
    db.commit()
    return {"tenant": tenant, "owner": owner, "approver": approver}


def _contract(db, ws, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Vendor Services Agreement", type="vendor", status="approved",
        owner_id=ws["owner"].id, created_by=ws["owner"].id,
        body=kwargs.pop("body", LIABILITY), value=100_000, currency="PKR", **kwargs,
    )
    db.add(c)
    db.flush()
    return c


def _approved_run(db, ws, contract, *, status="approved") -> models.WorkflowRun:
    definition = models.WorkflowDefinition(
        tenant_id=ws["tenant"].id, name="Standard", status="active",
        stages=[{"name": "Legal", "steps": [{"name": "Legal review", "assignee_kind": "role",
                                             "assignee_value": "manager"}]}],
        created_by=ws["owner"].id,
    )
    db.add(definition)
    db.flush()
    run = models.WorkflowRun(
        tenant_id=ws["tenant"].id, contract_id=contract.id, definition_id=definition.id,
        status=status, started_by=ws["owner"].id, started_by_name=ws["owner"].name,
    )
    db.add(run)
    db.flush()
    db.add(models.WorkflowRunStep(
        tenant_id=ws["tenant"].id, run_id=run.id, step_index=0, stage_index=0,
        name="Legal review", assignee_kind="role", assignee_value="manager",
        status="approved" if status == "approved" else "active",
        decision="approved" if status == "approved" else None,
        decided_by=ws["approver"].id,
        decided_by_name=ws["approver"].name if status == "approved" else "",
        decided_at=None if status != "approved" else __import__("datetime").datetime(2026, 8, 26, 10, 0),
    ))
    db.flush()
    return run


def _playbook(db, ws, rules, *, contract_type="vendor"):
    p = models.Playbook(
        tenant_id=ws["tenant"].id, name="Vendor policy", contract_type=contract_type,
        applies_when={}, rules=rules, status="active", created_by=ws["owner"].id,
    )
    db.add(p)
    db.flush()
    return p


def _approved_clause(db, ws, key, body):
    c = models.Clause(
        tenant_id=ws["tenant"].id, key=key, title=key.replace("_", " ").title(),
        category="General", body=body, status="draft", created_by=ws["owner"].id,
    )
    db.add(c)
    db.flush()
    clause_service.submit_for_approval(db, c, actor=ws["owner"])
    clause_service.approve(db, c, actor=ws["approver"])
    return c


# ---------------------------------------------------------------------------------------


def test_an_agreement_with_no_approval_run_is_not_ready(db, workspace):
    pack = readiness.build(db, _contract(db, workspace))
    assert pack["ready"] is False
    assert any("No approval workflow" in b for b in pack["blockers"])


def test_a_running_workflow_blocks_and_names_who_it_is_waiting_on(db, workspace):
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract, status="running")
    pack = readiness.build(db, contract)
    assert pack["ready"] is False
    assert any("still running" in b and "Legal review" in b for b in pack["blockers"])


def test_a_completed_approval_makes_it_ready(db, workspace):
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract)
    pack = readiness.build(db, contract)
    assert pack["ready"] is True, pack["blockers"]
    assert pack["blockers"] == []


def test_the_approval_record_names_who_decided_what(db, workspace):
    """The accountability record a regulator asks for."""
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract)
    pack = readiness.build(db, contract)
    decision = pack["decisions"][0]
    assert decision["name"] == "Legal review"
    assert decision["who"] == workspace["approver"].name
    assert decision["decision"] == "approved"


def test_a_rejected_workflow_blocks(db, workspace):
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract, status="rejected")
    pack = readiness.build(db, contract)
    assert pack["ready"] is False
    assert any("rejected" in b for b in pack["blockers"])


def test_a_blocking_policy_deviation_blocks_signature(db, workspace):
    """The case this document exists for: the clause is present but the cap has changed, and
    nobody looking at the approval history alone would see it."""
    _approved_clause(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required",
                               "severity": "blocker"}])
    contract = _contract(db, workspace, body=LIABILITY_CHANGED)
    _approved_run(db, workspace, contract)

    pack = readiness.build(db, contract)
    assert pack["ready"] is False
    assert any("altered" in b for b in pack["blockers"])
    assert pack["policy"]["deviation_count"] == 1


def test_a_warning_deviation_is_a_note_not_a_blocker(db, workspace):
    _approved_clause(db, workspace, "liability", LIABILITY)
    _playbook(db, workspace, [{"clause_key": "liability", "kind": "required",
                               "severity": "warning"}])
    contract = _contract(db, workspace, body=LIABILITY_CHANGED)
    _approved_run(db, workspace, contract)

    pack = readiness.build(db, contract)
    assert pack["ready"] is True
    assert any("altered" in n for n in pack["notes"])


def test_an_open_amendment_thread_blocks(db, workspace):
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract)
    db.add(models.Comment(
        tenant_id=workspace["tenant"].id, contract_id=contract.id,
        author_id=workspace["owner"].id, author_name="Owner",
        body="The cap still needs the CFO.", kind="amendment", resolved=False,
    ))
    db.flush()
    pack = readiness.build(db, contract)
    assert pack["ready"] is False
    assert any("amendment thread" in b for b in pack["blockers"])


def test_a_resolved_amendment_thread_does_not_block(db, workspace):
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract)
    db.add(models.Comment(
        tenant_id=workspace["tenant"].id, contract_id=contract.id,
        author_id=workspace["owner"].id, author_name="Owner",
        body="Settled.", kind="amendment", resolved=True,
    ))
    db.flush()
    assert readiness.build(db, contract)["ready"] is True


def test_provenance_records_the_template_revision(db, workspace):
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="Vendor template", contract_type="vendor",
        body=LIABILITY, status="active", is_active=True, version_no=3,
        created_by=workspace["owner"].id,
    )
    db.add(template)
    db.flush()
    contract = _contract(db, workspace, source="template", template_id=template.id,
                         template_version_no=3)
    _approved_run(db, workspace, contract)

    prov = readiness.build(db, contract)["provenance"]
    assert prov["template"] == "Vendor template"
    assert prov["template_version"] == "v3"


def test_a_clause_revised_since_generation_is_surfaced(db, workspace):
    """The signatory is looking at wording that is no longer the approved wording."""
    clause = _approved_clause(db, workspace, "liability", LIABILITY)
    clause.body = LIABILITY + " Fraud is excluded."
    clause.status = "draft"
    clause_service.submit_for_approval(db, clause, actor=workspace["owner"])
    clause_service.approve(db, clause, actor=workspace["approver"])

    contract = _contract(db, workspace)
    contract.included_clauses = [{"clause_id": clause.id, "key": "liability",
                                  "version_no": 1, "title": "Liability"}]
    db.flush()
    _approved_run(db, workspace, contract)

    pack = readiness.build(db, contract)
    assert any("revised since" in n for n in pack["notes"])
    assert pack["provenance"]["clauses"][0]["stale"] is True


def test_it_notices_the_body_was_edited_after_generation(db, workspace):
    template = models.ContractTemplate(
        tenant_id=workspace["tenant"].id, name="T", contract_type="vendor", body=LIABILITY,
        status="active", is_active=True, created_by=workspace["owner"].id,
    )
    db.add(template)
    db.flush()
    contract = _contract(db, workspace, source="template", template_id=template.id,
                         template_version_no=1, body=LIABILITY_CHANGED)
    db.add(models.ContractVersion(
        tenant_id=workspace["tenant"].id, contract_id=contract.id, version_no=1,
        body=LIABILITY, change_summary="Generated", created_by=workspace["owner"].id,
    ))
    db.flush()
    _approved_run(db, workspace, contract)

    assert readiness.build(db, contract)["provenance"]["edited_since_generation"] is True


def test_legal_hold_is_flagged(db, workspace):
    contract = _contract(db, workspace, legal_hold=True)
    _approved_run(db, workspace, contract)
    assert any("legal hold" in n for n in readiness.build(db, contract)["notes"])


def test_the_pdf_renders_and_says_whether_it_is_ready(db, workspace):
    contract = _contract(db, workspace)
    _approved_run(db, workspace, contract)
    pack = readiness.build(db, contract)
    payload = pdf.render_readiness_pack_bytes(
        contract=contract, org_name="Mobilink Microfinance Bank", pack=pack)
    assert payload.startswith(b"%PDF")
    assert len(payload) > 1200


def test_the_pdf_renders_for_a_blocked_agreement_too(db, workspace):
    """The not-ready path is the one that matters, so it must not be the one that crashes."""
    contract = _contract(db, workspace)
    pack = readiness.build(db, contract)
    assert pack["ready"] is False
    assert pdf.render_readiness_pack_bytes(
        contract=contract, org_name="MMBL", pack=pack).startswith(b"%PDF")
