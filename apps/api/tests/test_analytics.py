"""Analytics: KPIs, bottlenecks, workload, compliance posture and MIS trends.

Two properties are worth more than the rest:

**Every figure reports its sample.** A mean cycle time over four agreements and one over four
hundred are different claims, and a dashboard that hides the difference gets quoted in a board
pack as though they were the same. So the tests assert the sample, not just the number.

**Unfinished work is excluded, not counted as zero.** An average cycle time that treats
in-flight drafts as instant would improve every time somebody starts a new one — a metric that
rewards inactivity is worse than no metric.

Requirements: SOW-30.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import analytics_service, audit, clause_service, models, security


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"an-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    reviewer = models.User(
        tenant_id=tenant.id, email=f"rev-{uuid.uuid4().hex[:8]}@example.com",
        name="Reviewer", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="approver",
    )
    approver = models.User(
        tenant_id=tenant.id, email=f"mgr-{uuid.uuid4().hex[:8]}@example.com",
        name="Manager", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="manager",
    )
    db.add_all([reviewer, approver])
    db.commit()
    return {"tenant": tenant, "owner": owner, "reviewer": reviewer, "approver": approver}


def _contract(db, ws, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title=kwargs.pop("title", "Vendor Services Agreement"),
        type=kwargs.pop("type", "vendor"), status=kwargs.pop("status", "draft"),
        owner_id=ws["owner"].id, created_by=ws["owner"].id,
        value=kwargs.pop("value", 1_000_000), currency=kwargs.pop("currency", "PKR"),
        **kwargs,
    )
    db.add(c)
    db.flush()
    return c


def _status_change(db, ws, contract, frm, to, *, at=None):
    """Write the audit row a real status change would write, then pin its timestamp.

    `at` is overridden after the fact rather than mocked: the analytics read `AuditLog.at`,
    and pinning it is how a fixed-clock test stays readable.
    """
    entry = audit.record(db, tenant_id=ws["tenant"].id, action="contract.status_changed",
                         actor=ws["owner"], object_type="contract", object_id=contract.id,
                         object_label=contract.title, meta={"from": frm, "to": to})
    if at is not None:
        entry.at = at
    db.flush()
    return entry


def _run_with_step(db, ws, contract, **kwargs) -> models.WorkflowRunStep:
    definition = models.WorkflowDefinition(
        tenant_id=ws["tenant"].id, name="Standard", status="active", stages=[],
        created_by=ws["owner"].id)
    db.add(definition)
    db.flush()
    run = models.WorkflowRun(
        tenant_id=ws["tenant"].id, contract_id=contract.id, definition_id=definition.id,
        status="running", started_by=ws["owner"].id)
    db.add(run)
    db.flush()
    step = models.WorkflowRunStep(
        tenant_id=ws["tenant"].id, run_id=run.id, step_index=0,
        stage_index=kwargs.pop("stage_index", 0),
        name=kwargs.pop("name", "Legal review"),
        assignee_kind=kwargs.pop("assignee_kind", "user"),
        assignee_value=kwargs.pop("assignee_value", ws["reviewer"].id),
        status=kwargs.pop("status", "active"), **kwargs)
    db.add(step)
    db.flush()
    return step


# ---------------------------------------------------------------------------------------
# Cycle times
# ---------------------------------------------------------------------------------------


def test_cycle_time_is_measured_from_the_audit_log(db, workspace):
    contract = _contract(db, workspace, status="signed")
    _status_change(db, workspace, contract, "", "draft", at=dt.datetime(2026, 1, 1, 9, 0))
    _status_change(db, workspace, contract, "draft", "in_review",
                   at=dt.datetime(2026, 1, 5, 9, 0))
    _status_change(db, workspace, contract, "approved", "signed",
                   at=dt.datetime(2026, 1, 11, 9, 0))

    result = analytics_service.cycle_times(db, workspace["tenant"].id)
    assert result["overall"]["mean"] == 10.0
    assert result["overall"]["sample"] == 1


def test_an_unfinished_agreement_is_excluded_not_counted_as_zero(db, workspace):
    """A metric that improves every time somebody starts a draft is worse than no metric."""
    done = _contract(db, workspace, status="signed")
    _status_change(db, workspace, done, "", "draft", at=dt.datetime(2026, 1, 1))
    _status_change(db, workspace, done, "approved", "signed", at=dt.datetime(2026, 1, 11))

    unfinished = _contract(db, workspace, status="draft")
    _status_change(db, workspace, unfinished, "", "draft", at=dt.datetime(2026, 1, 1))

    result = analytics_service.cycle_times(db, workspace["tenant"].id)
    assert result["overall"]["mean"] == 10.0
    assert result["overall"]["sample"] == 1
    assert result["still_in_flight"] == 1


def test_cycle_times_are_broken_out_by_agreement_type(db, workspace):
    nda = _contract(db, workspace, type="nda", status="signed")
    _status_change(db, workspace, nda, "", "draft", at=dt.datetime(2026, 1, 1))
    _status_change(db, workspace, nda, "approved", "signed", at=dt.datetime(2026, 1, 3))

    msa = _contract(db, workspace, type="msa", status="signed")
    _status_change(db, workspace, msa, "", "draft", at=dt.datetime(2026, 1, 1))
    _status_change(db, workspace, msa, "approved", "signed", at=dt.datetime(2026, 1, 31))

    by_type = analytics_service.cycle_times(db, workspace["tenant"].id)["by_type"]
    assert by_type["nda"]["mean"] == 2.0
    assert by_type["msa"]["mean"] == 30.0


def test_the_median_survives_one_pathological_agreement(db, workspace):
    """Cycle-time data always has one. An average alone would report it as typical."""
    for days in (2, 3, 4, 400):
        contract = _contract(db, workspace, status="signed")
        _status_change(db, workspace, contract, "", "draft", at=dt.datetime(2026, 1, 1))
        _status_change(db, workspace, contract, "approved", "signed",
                       at=dt.datetime(2026, 1, 1) + dt.timedelta(days=days))

    overall = analytics_service.cycle_times(db, workspace["tenant"].id)["overall"]
    assert overall["mean"] > 100
    assert overall["median"] <= 4


def test_an_empty_repository_reports_none_rather_than_zero(db, workspace):
    """Zero would read as "instant"."""
    overall = analytics_service.cycle_times(db, workspace["tenant"].id)["overall"]
    assert overall["mean"] is None
    assert overall["sample"] == 0


# ---------------------------------------------------------------------------------------
# Stages and workload
# ---------------------------------------------------------------------------------------


def test_the_bottleneck_is_the_slowest_stage(db, workspace):
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, name="Legal review", status="approved",
                   activated_at=dt.datetime(2026, 1, 1, 9, 0),
                   decided_at=dt.datetime(2026, 1, 1, 11, 0))
    _run_with_step(db, workspace, contract, name="Finance review", status="approved",
                   activated_at=dt.datetime(2026, 1, 1, 9, 0),
                   decided_at=dt.datetime(2026, 1, 3, 9, 0))

    result = analytics_service.stage_performance(db, workspace["tenant"].id)
    assert result["bottleneck"] == "Finance review"
    assert result["stages"][0]["mean_hours"] == 48.0


def test_sla_adherence_is_reported_with_its_sample(db, workspace):
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, name="Legal review", status="approved",
                   activated_at=dt.datetime(2026, 1, 1, 9, 0),
                   decided_at=dt.datetime(2026, 1, 1, 10, 0),
                   due_at=dt.datetime(2026, 1, 2, 9, 0))
    _run_with_step(db, workspace, contract, name="Legal review", status="approved",
                   activated_at=dt.datetime(2026, 1, 1, 9, 0),
                   decided_at=dt.datetime(2026, 1, 5, 9, 0),
                   due_at=dt.datetime(2026, 1, 2, 9, 0))

    stage = analytics_service.stage_performance(db, workspace["tenant"].id)["stages"][0]
    assert stage["sla_adherence"] == 50.0
    assert stage["sla_sample"] == 2


def test_a_stage_with_no_sla_reports_none_not_a_hundred_percent(db, workspace):
    """Reporting 100% for something never measured is the worst kind of wrong."""
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, status="approved",
                   activated_at=dt.datetime(2026, 1, 1, 9, 0),
                   decided_at=dt.datetime(2026, 1, 1, 10, 0))
    stage = analytics_service.stage_performance(db, workspace["tenant"].id)["stages"][0]
    assert stage["sla_adherence"] is None


def test_workload_is_ordered_by_what_is_still_open(db, workspace):
    """The point is finding who is about to become a bottleneck, not ranking throughput."""
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, assignee_value=workspace["reviewer"].id,
                   status="active")
    _run_with_step(db, workspace, contract, assignee_value=workspace["reviewer"].id,
                   status="active")
    _run_with_step(db, workspace, contract, assignee_value=workspace["approver"].id,
                   status="approved", decided_by=workspace["approver"].id,
                   activated_at=dt.datetime(2026, 1, 1), decided_at=dt.datetime(2026, 1, 2))

    rows = analytics_service.reviewer_workload(db, workspace["tenant"].id)
    assert rows[0]["name"] == "Reviewer"
    assert rows[0]["open"] == 2


def test_overdue_reviews_are_counted_against_the_reviewer(db, workspace):
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, assignee_value=workspace["reviewer"].id,
                   status="active", due_at=dt.datetime(2020, 1, 1))
    rows = analytics_service.reviewer_workload(db, workspace["tenant"].id)
    assert rows[0]["overdue"] == 1


def test_escalations_are_trended_and_timed(db, workspace):
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, status="approved",
                   escalated_at=dt.datetime(2026, 3, 1, 9, 0),
                   decided_at=dt.datetime(2026, 3, 1, 15, 0))
    result = analytics_service.escalation_trend(db, workspace["tenant"].id, months=120)
    assert result["total"] == 1
    assert result["mean_resolution_hours"] == 6.0
    assert result["series"][0]["month"] == "2026-03"


# ---------------------------------------------------------------------------------------
# Renewals, negotiation, compliance
# ---------------------------------------------------------------------------------------


def test_the_renewal_pipeline_buckets_by_urgency(db, workspace):
    today = dt.date(2026, 6, 1)
    _contract(db, workspace, status="active", end_date=dt.date(2026, 5, 1))    # overdue
    _contract(db, workspace, status="active", end_date=dt.date(2026, 6, 20))   # 30
    _contract(db, workspace, status="active", end_date=dt.date(2026, 7, 20))   # 60
    _contract(db, workspace, status="active", end_date=dt.date(2027, 1, 1))    # later
    db.flush()

    result = analytics_service.renewal_pipeline(db, workspace["tenant"].id, today=today)
    assert result["counts"] == {"overdue": 1, "30": 1, "60": 1, "90": 0, "later": 1}
    assert result["value_at_risk"] == 3_000_000


def test_a_draft_is_not_in_the_renewal_pipeline(db, workspace):
    """Nothing renews that was never signed."""
    _contract(db, workspace, status="draft", end_date=dt.date(2026, 6, 10))
    db.flush()
    result = analytics_service.renewal_pipeline(db, workspace["tenant"].id,
                                                today=dt.date(2026, 6, 1))
    assert sum(result["counts"].values()) == 0


def test_negotiation_effort_counts_redline_rounds(db, workspace):
    contract = _contract(db, workspace)
    for i in range(3):
        db.add(models.ContractVersion(
            tenant_id=workspace["tenant"].id, contract_id=contract.id, version_no=i + 1,
            body="x", change_summary="Redline: accepted 2 of 5 changes (+10/-4 words)",
            created_by=workspace["owner"].id))
    db.add(models.ContractVersion(
        tenant_id=workspace["tenant"].id, contract_id=contract.id, version_no=4, body="x",
        change_summary="Before Word import from theirs.docx",
        created_by=workspace["owner"].id))
    db.flush()

    result = analytics_service.negotiation_effort(db, workspace["tenant"].id)
    assert result["max_redline_rounds"] == 3
    assert result["counterparty_returns"] == 1
    assert result["most_negotiated"][0]["redlines"] == 3


def test_clause_pressure_ranks_what_counterparties_push_back_on(db, workspace):
    liability = models.Clause(
        tenant_id=workspace["tenant"].id, key="liability", title="Liability",
        body="Liability shall not exceed the fees paid in the preceding twelve (12) months.",
        status="draft", created_by=workspace["owner"].id)
    db.add(liability)
    db.flush()
    clause_service.submit_for_approval(db, liability, actor=workspace["owner"])
    clause_service.approve(db, liability, actor=workspace["approver"])
    db.add(models.Playbook(
        tenant_id=workspace["tenant"].id, name="Policy", contract_type="vendor",
        applies_when={}, status="active", created_by=workspace["owner"].id,
        rules=[{"clause_key": "liability", "kind": "required", "severity": "blocker"}]))
    db.flush()

    _contract(db, workspace, status="active",
              body="Liability shall not exceed five times the fees paid in the preceding "
                   "twelve (12) months.")
    db.flush()

    rows = analytics_service.clause_pressure(db, workspace["tenant"].id)
    assert rows[0]["clause_key"] == "liability"
    assert rows[0]["pressure"] >= 1


def test_compliance_posture_is_computed_live(db, workspace):
    """A compliance number from a stale snapshot is the one number that must not be."""
    clause = models.Clause(
        tenant_id=workspace["tenant"].id, key="liability", title="Liability",
        body="Liability shall not exceed the fees paid in the preceding twelve (12) months.",
        status="draft", created_by=workspace["owner"].id)
    db.add(clause)
    db.flush()
    clause_service.submit_for_approval(db, clause, actor=workspace["owner"])
    clause_service.approve(db, clause, actor=workspace["approver"])
    db.add(models.Playbook(
        tenant_id=workspace["tenant"].id, name="Policy", contract_type="vendor",
        applies_when={}, status="active", created_by=workspace["owner"].id,
        rules=[{"clause_key": "liability", "kind": "required", "severity": "blocker"}]))
    db.flush()

    _contract(db, workspace, status="active", body="No liability clause at all.")
    db.flush()

    posture = analytics_service.compliance_posture(db, workspace["tenant"].id)
    assert posture["deviating"] == 1
    assert posture["missing_mandatory_clauses"] == 1
    assert posture["worst"][0]["blockers"] == 1


# ---------------------------------------------------------------------------------------
# MIS
# ---------------------------------------------------------------------------------------


def test_the_volume_trend_aligns_year_on_year_by_period(db, workspace):
    """Aligned by period key, not list offset — a missing month must not shift it by one."""
    old = _contract(db, workspace, status="signed")
    old.created_at = dt.datetime(2025, 3, 10)
    new = _contract(db, workspace, status="signed")
    new.created_at = dt.datetime(2026, 3, 10)
    db.flush()

    series = analytics_service.volume_trend(db, workspace["tenant"].id,
                                            months=120)["series"]
    march_2026 = next(p for p in series if p["period"] == "2026-03")
    assert march_2026["raised"] == 1
    assert march_2026["raised_year_ago"] == 1


def test_the_trend_can_be_bucketed_by_week(db, workspace):
    contract = _contract(db, workspace)
    contract.created_at = dt.datetime(2026, 3, 10)
    db.flush()
    series = analytics_service.volume_trend(db, workspace["tenant"].id,
                                            granularity="week")["series"]
    assert any("W" in p["period"] for p in series)


def test_an_unknown_granularity_is_refused(db, workspace):
    with pytest.raises(ValueError, match="Unknown granularity"):
        analytics_service.volume_trend(db, workspace["tenant"].id, granularity="fortnight")


def test_segmentation_uses_the_party_record_for_region(db, workspace):
    """A free-text counterparty cannot be segmented at all — this is the point of parties."""
    from app import repository_service

    party = repository_service.create_party(
        db, workspace["tenant"].id, {"name": "Acme Trading", "region": "Sindh"},
        actor=workspace["owner"])
    contract = _contract(db, workspace, value=500_000)
    repository_service.link_contract_to_party(db, contract, party)
    db.flush()

    by_region = analytics_service.segmentation(db, workspace["tenant"].id)["by_region"]
    assert by_region[0]["label"] == "Sindh"
    assert by_region[0]["value"] == 500_000


def test_unsegmented_rows_are_labelled_rather_than_dropped(db, workspace):
    """Dropping them would make the totals disagree with the repository count."""
    _contract(db, workspace)
    db.flush()
    by_region = analytics_service.segmentation(db, workspace["tenant"].id)["by_region"]
    assert by_region[0]["label"] == "Unassigned"


# ---------------------------------------------------------------------------------------
# Personal dashboard
# ---------------------------------------------------------------------------------------


def test_my_dashboard_shows_only_my_work(db, workspace):
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, assignee_value=workspace["reviewer"].id)
    _run_with_step(db, workspace, contract, assignee_value=workspace["approver"].id)

    result = analytics_service.my_dashboard(db, workspace["reviewer"])
    assert result["counts"]["reviews"] == 1
    assert result["reviews"][0]["reference_no"] == contract.reference_no


def test_a_role_assigned_step_reaches_everyone_in_that_role(db, workspace):
    contract = _contract(db, workspace)
    _run_with_step(db, workspace, contract, assignee_kind="role",
                   assignee_value="approver")
    assert analytics_service.my_dashboard(db, workspace["reviewer"])["counts"]["reviews"] == 1
    assert analytics_service.my_dashboard(db, workspace["approver"])["counts"]["reviews"] == 0


def test_my_dashboard_lists_my_overdue_obligations(db, workspace):
    contract = _contract(db, workspace)
    db.add(models.Obligation(
        tenant_id=workspace["tenant"].id, contract_id=contract.id, title="Report",
        due_date=dt.date(2026, 1, 1), owner_id=workspace["reviewer"].id,
        created_by=workspace["owner"].id))
    db.flush()

    result = analytics_service.my_dashboard(db, workspace["reviewer"],
                                            today=dt.date(2026, 6, 1))
    assert result["counts"]["overdue_obligations"] == 1
    assert result["obligations"][0]["overdue"] is True


def test_my_dashboard_lists_renewals_i_own(db, workspace):
    _contract(db, workspace, status="active", end_date=dt.date(2026, 7, 1))
    _contract(db, workspace, status="active", end_date=dt.date(2028, 1, 1))
    db.flush()
    result = analytics_service.my_dashboard(db, workspace["owner"],
                                            today=dt.date(2026, 6, 1))
    assert result["counts"]["renewals"] == 1
