"""Post-execution changes: amendments, terminations, renewal notices, obligation sweeps.

Everything here happens after signature, which is what makes it different from drafting. Two
claims carry the weight:

- **An amendment does not silently rewrite the parent.** Until the amendment is executed the
  parent is still what is in force, and once it is, the *impact* is a recorded fact rather
  than something reconstructed later by comparing two documents.
- **Terminating is not a status change.** It needs a reason, sign-off from the functions with
  a stake, and it closes the obligations underneath — which would otherwise keep chasing
  people for work that no longer needs doing.

The obligation sweep is tested for idempotence, because a reminder system that repeats itself
gets filtered into a folder nobody opens.

Requirements: SOW-28.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import change_service, models, obligation_service, repository_service, security
from app.change_service import ChangeError


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"chg-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    manager = models.User(
        tenant_id=tenant.id, email=f"mgr-{uuid.uuid4().hex[:8]}@example.com",
        name="Manager", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="manager",
    )
    author = models.User(
        tenant_id=tenant.id, email=f"auth-{uuid.uuid4().hex[:8]}@example.com",
        name="Author", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="author",
    )
    db.add_all([manager, author])
    db.commit()
    return {"tenant": tenant, "owner": owner, "manager": manager, "author": author}


def _contract(db, ws, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title=kwargs.pop("title", "Vendor Services Agreement"),
        type=kwargs.pop("type", "vendor"), status=kwargs.pop("status", "active"),
        owner_id=ws["owner"].id, created_by=ws["owner"].id,
        value=kwargs.pop("value", 1_000_000), currency="PKR",
        body=kwargs.pop("body", "1. The Supplier shall provide the Services."),
        effective_date=kwargs.pop("effective_date", dt.date(2026, 1, 1)),
        end_date=kwargs.pop("end_date", dt.date(2026, 12, 31)),
        **kwargs,
    )
    db.add(c)
    db.flush()
    return c


def _obligation(db, ws, contract, **kwargs) -> models.Obligation:
    o = models.Obligation(
        tenant_id=ws["tenant"].id, contract_id=contract.id,
        title=kwargs.pop("title", "Quarterly service report"),
        due_date=kwargs.pop("due_date", dt.date(2026, 6, 30)),
        owner_id=kwargs.pop("owner_id", ws["author"].id),
        status=kwargs.pop("status", "pending"),
        created_by=ws["owner"].id, **kwargs,
    )
    db.add(o)
    db.flush()
    return o


# ---------------------------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------------------------


def test_a_draft_cannot_be_amended(db, workspace):
    """Amending a draft is just editing it."""
    with pytest.raises(ChangeError, match="Only a live agreement"):
        change_service.request_amendment(db, _contract(db, workspace, status="draft"),
                                         actor=workspace["owner"])


def test_an_agreement_under_legal_hold_cannot_be_amended(db, workspace):
    with pytest.raises(ChangeError, match="legal hold"):
        change_service.request_amendment(db, _contract(db, workspace, legal_hold=True),
                                         actor=workspace["owner"])


def test_an_amendment_is_a_separate_draft_leaving_the_parent_in_force(db, workspace):
    """The parent is still what governs until the amendment is executed."""
    parent = _contract(db, workspace, value=1_000_000)
    child = change_service.request_amendment(db, parent, actor=workspace["owner"],
                                             reason="Fee increase")

    assert child.id != parent.id
    assert child.status == "draft"
    assert parent.status == "active", "the parent must not move when an amendment opens"
    assert child.source == "amendment"


def test_the_amendment_inherits_the_parents_commercial_context(db, workspace):
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Acme Trading"}, actor=workspace["owner"])
    parent = _contract(db, workspace, governing_law="Pakistan")
    repository_service.link_contract_to_party(db, parent, party)
    db.flush()

    child = change_service.request_amendment(db, parent, actor=workspace["owner"])
    assert child.party_id == party.id
    assert child.governing_law == "Pakistan"
    assert child.currency == parent.currency


def test_the_amendment_is_linked_to_what_it_amends(db, workspace):
    parent = _contract(db, workspace)
    child = change_service.request_amendment(db, parent, actor=workspace["owner"])
    history = repository_service.history(db, child)
    assert [a["kind"] for a in history["ancestors"]] == ["amendment_of"]
    assert history["ancestors"][0]["contract_id"] == parent.id


def test_the_impact_reports_what_actually_moved(db, workspace):
    """What somebody approving the amendment needs to know, in their terms."""
    parent = _contract(db, workspace, value=1_000_000, end_date=dt.date(2026, 12, 31))
    child = change_service.request_amendment(db, parent, actor=workspace["owner"])
    child.value = 1_500_000
    child.end_date = dt.date(2027, 6, 30)
    child.body = parent.body + "\n2. A new obligation."
    db.flush()

    impact = change_service.amendment_impact(db, child, parent)

    assert impact["value_delta"] == 500_000
    assert impact["term_delta_days"] == 181
    assert impact["body_changed"] is True
    assert impact["fields"]["value"]["from"] == "1000000"
    assert impact["parent_reference"] == parent.reference_no


def test_the_impact_reports_clauses_added_and_removed(db, workspace):
    parent = _contract(db, workspace)
    parent.included_clauses = [{"key": "confidentiality"}, {"key": "liability"}]
    db.flush()
    child = change_service.request_amendment(db, parent, actor=workspace["owner"])
    child.included_clauses = [{"key": "confidentiality"}, {"key": "data_protection"}]
    db.flush()

    impact = change_service.amendment_impact(db, child, parent)
    assert impact["clauses"]["added"] == ["data_protection"]
    assert impact["clauses"]["removed"] == ["liability"]


def test_an_unsigned_amendment_cannot_take_effect(db, workspace):
    parent = _contract(db, workspace)
    child = change_service.request_amendment(db, parent, actor=workspace["owner"])
    with pytest.raises(ChangeError, match="has to be executed"):
        change_service.execute_amendment(db, child, actor=workspace["owner"])


def test_executing_an_amendment_records_the_impact_and_supersedes_the_parent(db, workspace):
    parent = _contract(db, workspace, value=1_000_000)
    child = change_service.request_amendment(db, parent, actor=workspace["owner"])
    child.value = 1_250_000
    child.status = "signed"
    db.flush()

    impact = change_service.execute_amendment(db, child, actor=workspace["owner"])

    assert child.amendment_impact["value_delta"] == 250_000
    assert impact["value_delta"] == 250_000
    history = repository_service.history(db, parent)
    assert any(d["kind"] == "supersedes" for d in history["descendants"])


def test_executing_something_that_is_not_an_amendment_is_refused(db, workspace):
    contract = _contract(db, workspace, status="signed")
    with pytest.raises(ChangeError, match="not an amendment"):
        change_service.execute_amendment(db, contract, actor=workspace["owner"])


# ---------------------------------------------------------------------------------------
# Terminations
# ---------------------------------------------------------------------------------------


def test_a_termination_needs_a_reason(db, workspace):
    with pytest.raises(ChangeError, match="needs a reason"):
        change_service.request_termination(db, _contract(db, workspace),
                                           actor=workspace["owner"], reason="  ")


def test_an_unknown_reason_code_is_refused(db, workspace):
    with pytest.raises(ChangeError, match="Unknown termination reason"):
        change_service.request_termination(db, _contract(db, workspace),
                                           actor=workspace["owner"], reason="x",
                                           reason_code="because")


def test_a_draft_cannot_be_terminated(db, workspace):
    """Terminating a draft is deleting it."""
    with pytest.raises(ChangeError, match="Only a live agreement"):
        change_service.request_termination(db, _contract(db, workspace, status="draft"),
                                           actor=workspace["owner"], reason="No longer needed")


def test_legal_hold_blocks_termination(db, workspace):
    with pytest.raises(ChangeError, match="legal hold"):
        change_service.request_termination(db, _contract(db, workspace, legal_hold=True),
                                           actor=workspace["owner"], reason="x")


def test_only_one_termination_request_can_be_open(db, workspace):
    contract = _contract(db, workspace)
    change_service.request_termination(db, contract, actor=workspace["owner"],
                                       reason="Switching supplier")
    with pytest.raises(ChangeError, match="already open"):
        change_service.request_termination(db, contract, actor=workspace["owner"],
                                           reason="Again")


def test_the_effective_date_defaults_to_the_notice_period(db, workspace):
    request = change_service.request_termination(
        db, _contract(db, workspace), actor=workspace["owner"],
        reason="Switching supplier", notice_days=60)
    assert request.effective_date == dt.date.today() + dt.timedelta(days=60)


def test_a_request_does_not_terminate_anything_by_itself(db, workspace):
    contract = _contract(db, workspace)
    change_service.request_termination(db, contract, actor=workspace["owner"],
                                       reason="Switching supplier")
    assert contract.status == "active"


def test_a_role_that_is_not_required_cannot_decide(db, workspace):
    contract = _contract(db, workspace)
    request = change_service.request_termination(
        db, contract, actor=workspace["owner"], reason="x",
        required_roles=["owner", "manager"])
    with pytest.raises(ChangeError, match="not one of the required sign-offs"):
        change_service.decide_termination(db, request, actor=workspace["author"], approve=True)


def test_nobody_decides_twice(db, workspace):
    request = change_service.request_termination(
        db, _contract(db, workspace), actor=workspace["owner"], reason="x",
        required_roles=["owner", "manager"])
    change_service.decide_termination(db, request, actor=workspace["owner"], approve=True)
    with pytest.raises(ChangeError, match="already decided"):
        change_service.decide_termination(db, request, actor=workspace["owner"], approve=True)


def test_it_stays_pending_until_every_required_role_has_approved(db, workspace):
    request = change_service.request_termination(
        db, _contract(db, workspace), actor=workspace["owner"], reason="x",
        required_roles=["owner", "manager"])
    change_service.decide_termination(db, request, actor=workspace["owner"], approve=True)
    assert request.status == "pending"
    change_service.decide_termination(db, request, actor=workspace["manager"], approve=True)
    assert request.status == "approved"


def test_one_rejection_ends_the_request(db, workspace):
    """Making the remaining functions decline something already refused wastes their time."""
    request = change_service.request_termination(
        db, _contract(db, workspace), actor=workspace["owner"], reason="x",
        required_roles=["owner", "manager"])
    change_service.decide_termination(db, request, actor=workspace["manager"], approve=False,
                                      comment="Exit fees are not budgeted.")
    assert request.status == "rejected"


def test_an_unapproved_termination_cannot_be_executed(db, workspace):
    contract = _contract(db, workspace)
    request = change_service.request_termination(db, contract, actor=workspace["owner"],
                                                 reason="x", required_roles=["owner"])
    request.status = "pending"
    with pytest.raises(ChangeError, match="not been approved"):
        change_service.execute_termination(db, request, contract, actor=workspace["owner"])


def test_executing_terminates_and_closes_open_obligations(db, workspace):
    """Obligations under a terminated agreement are moot, not overdue."""
    contract = _contract(db, workspace)
    pending = _obligation(db, workspace, contract)
    done = _obligation(db, workspace, contract, title="Already done", status="done")
    request = change_service.request_termination(
        db, contract, actor=workspace["owner"], reason="Switching supplier",
        required_roles=["owner"])
    change_service.decide_termination(db, request, actor=workspace["owner"], approve=True)

    change_service.execute_termination(db, request, contract, actor=workspace["owner"])

    assert contract.status == "terminated"
    assert request.status == "executed"
    assert pending.status == "skipped"
    assert done.status == "done", "a completed obligation is a record, not something to close"


def test_the_notice_is_generated_from_the_recorded_request(db, workspace):
    """A notice that disagrees with the record is a dispute."""
    contract = _contract(db, workspace, title="Merchant Acquiring Agreement")
    request = change_service.request_termination(
        db, contract, actor=workspace["owner"],
        reason="Merchant has ceased trading.", reason_code="cause", notice_days=30)

    notice = change_service.termination_notice(db, request, contract,
                                               "Mobilink Microfinance Bank")

    assert contract.reference_no in notice
    assert "Merchant Acquiring Agreement" in notice
    assert "for cause" in notice
    assert "Merchant has ceased trading." in notice
    assert request.effective_date.strftime("%d %B %Y") in notice
    assert "survive termination" in notice


# ---------------------------------------------------------------------------------------
# Renewal notice schedule
# ---------------------------------------------------------------------------------------


def test_the_default_schedule_is_ninety_sixty_thirty(db, workspace):
    assert change_service.notice_schedule(_contract(db, workspace)) == [90, 60, 30]


def test_a_per_agreement_schedule_overrides_the_default(db, workspace):
    contract = _contract(db, workspace)
    change_service.set_notice_schedule(db, contract, [180, 90], actor=workspace["owner"])
    assert change_service.notice_schedule(contract) == [180, 90]


def test_a_schedule_is_deduplicated_and_ordered(db, workspace):
    contract = _contract(db, workspace)
    change_service.set_notice_schedule(db, contract, [30, 90, 30, 60],
                                       actor=workspace["owner"])
    assert contract.renewal_notice_days == [90, 60, 30]


def test_an_empty_schedule_is_refused(db, workspace):
    with pytest.raises(ChangeError, match="at least one notice period"):
        change_service.set_notice_schedule(db, _contract(db, workspace), [0, -5],
                                           actor=workspace["owner"])


def test_an_absurd_notice_period_is_refused(db, workspace):
    with pytest.raises(ChangeError, match="almost certainly a mistake"):
        change_service.set_notice_schedule(db, _contract(db, workspace), [5000],
                                           actor=workspace["owner"])


def test_due_notices_reflect_how_close_expiry_is(db, workspace):
    contract = _contract(db, workspace, end_date=dt.date(2026, 12, 31))
    assert change_service.due_notices(contract, today=dt.date(2026, 1, 1)) == []
    assert change_service.due_notices(contract, today=dt.date(2026, 10, 15)) == [90]
    assert change_service.due_notices(contract, today=dt.date(2026, 12, 20)) == [90, 60, 30]


def test_an_agreement_with_no_end_date_raises_no_notices(db, workspace):
    assert change_service.due_notices(_contract(db, workspace, end_date=None)) == []


# ---------------------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------------------


def test_the_rollup_spans_every_agreement(db, workspace):
    a, b = _contract(db, workspace), _contract(db, workspace, title="Second")
    _obligation(db, workspace, a)
    _obligation(db, workspace, b, title="Annual audit")
    db.flush()

    result = obligation_service.rollup(db, workspace["tenant"].id)
    assert result["total"] == 2
    assert {i["contract_title"] for i in result["items"]} == {"Vendor Services Agreement",
                                                              "Second"}


def test_the_rollup_counts_what_an_operations_view_needs(db, workspace):
    contract = _contract(db, workspace)
    today = dt.date(2026, 6, 1)
    _obligation(db, workspace, contract, due_date=dt.date(2026, 5, 1))       # overdue
    _obligation(db, workspace, contract, due_date=dt.date(2026, 6, 4))       # this week
    _obligation(db, workspace, contract, due_date=dt.date(2026, 6, 20))      # this month
    _obligation(db, workspace, contract, due_date=None, owner_id=None)       # unassigned
    _obligation(db, workspace, contract, status="done")
    db.flush()

    summary = obligation_service.rollup(db, workspace["tenant"].id,
                                        today=today)["summary"]
    assert summary["overdue"] == 1
    # "Due this week" is what is coming, not what has already slipped — overdue has its own
    # count, and folding it in would hide the distinction an operations view exists to make.
    assert summary["due_this_week"] == 1
    assert summary["due_this_month"] == 2
    assert summary["unassigned"] == 1
    assert summary["done"] == 1


def test_the_rollup_can_be_filtered_to_one_owner(db, workspace):
    contract = _contract(db, workspace)
    _obligation(db, workspace, contract, owner_id=workspace["author"].id)
    _obligation(db, workspace, contract, owner_id=workspace["manager"].id)
    db.flush()
    result = obligation_service.rollup(db, workspace["tenant"].id,
                                       owner_id=workspace["author"].id)
    assert result["total"] == 1
    assert result["items"][0]["owner_name"] == "Author"


def test_another_tenants_obligations_never_appear(db, workspace, make_user):
    other_owner, other_tenant = make_user(email=f"x-{uuid.uuid4().hex[:8]}@example.com",
                                          name="Other")
    other = models.Contract(
        tenant_id=other_tenant.id, reference_no="X-1", title="Theirs", type="vendor",
        status="active", owner_id=other_owner.id, created_by=other_owner.id, currency="PKR",
    )
    db.add(other)
    db.flush()
    db.add(models.Obligation(tenant_id=other_tenant.id, contract_id=other.id,
                             title="Their obligation", created_by=other_owner.id))
    db.flush()
    assert obligation_service.rollup(db, workspace["tenant"].id)["total"] == 0


def test_the_sweep_marks_overdue_and_reminds(db, workspace):
    contract = _contract(db, workspace)
    _obligation(db, workspace, contract, due_date=dt.date(2026, 6, 5))
    db.flush()

    result = obligation_service.sweep(db, today=dt.date(2026, 6, 1),
                                      tenant_id=workspace["tenant"].id)
    assert result["reminded"] == 1


def test_the_sweep_does_not_repeat_a_reminder(db, workspace):
    """A reminder system that repeats itself gets filtered into a folder nobody opens."""
    contract = _contract(db, workspace)
    _obligation(db, workspace, contract, due_date=dt.date(2026, 6, 5))
    db.flush()

    first = obligation_service.sweep(db, today=dt.date(2026, 6, 1),
                                     tenant_id=workspace["tenant"].id)
    db.flush()
    second = obligation_service.sweep(db, today=dt.date(2026, 6, 1),
                                      tenant_id=workspace["tenant"].id)
    assert first["reminded"] == 1
    assert second["reminded"] == 0


def test_the_sweep_escalates_to_the_contract_owner_once(db, workspace):
    contract = _contract(db, workspace)
    _obligation(db, workspace, contract, due_date=dt.date(2026, 5, 1))
    db.flush()

    first = obligation_service.sweep(db, today=dt.date(2026, 6, 1),
                                     tenant_id=workspace["tenant"].id)
    db.flush()
    second = obligation_service.sweep(db, today=dt.date(2026, 6, 1),
                                      tenant_id=workspace["tenant"].id)

    assert first["marked_overdue"] == 1
    assert first["escalated"] == 1
    assert second["escalated"] == 0


def test_the_sweep_ignores_obligations_on_a_terminated_agreement(db, workspace):
    """Chasing people for work under an agreement that has ended is noise."""
    contract = _contract(db, workspace, status="terminated")
    _obligation(db, workspace, contract, due_date=dt.date(2026, 6, 5))
    db.flush()
    result = obligation_service.sweep(db, today=dt.date(2026, 6, 1),
                                      tenant_id=workspace["tenant"].id)
    assert result["reminded"] == 0
    assert result["escalated"] == 0
