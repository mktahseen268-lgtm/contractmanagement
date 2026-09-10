"""Workflow engine — parallel stages, completion policies, SLA, escalation, delegation.

The claim under test is the RFI's core mechanic: **reviewers work concurrently and mark their
own review complete independently**. The v1 engine could not do that, and sequential review is
the main thing producing the cycle times the RFI exists to fix — so the first test class is
the one that matters.

The SLA tests drive an explicit clock rather than sleeping, and the business-calendar tests
pin the behaviour that makes an SLA credible: a review raised on a Friday afternoon is not
overdue on Saturday morning.

Requirements: SOW-11, SOW-12, SOW-13, SOW-14, SOW-15.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import approval_matrix, business_calendar, models, security, workflow_service as wf
from app.workflow_service import WorkflowError


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(name="Workflow Owner")
    contract = models.Contract(
        tenant_id=tenant.id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Vendor Services Agreement", type="msa", status="draft",
        owner_id=owner.id, created_by=owner.id, value=500_000, currency="PKR",
        department="Procurement", risk_level="medium",
    )
    db.add(contract)
    db.commit()
    return {"tenant": tenant, "owner": owner, "contract": contract}


def _user(db, ws, name, role="approver", department="", client_facing=False):
    u = models.User(
        tenant_id=ws["tenant"].id, email=f"{uuid.uuid4().hex[:8]}@example.com", name=name,
        password_hash=security.hash_password("Str0ng!Passw0rd1"), role=role,
        department=department, is_client_facing=client_facing,
    )
    db.add(u)
    db.commit()
    return u


def _definition(db, ws, stages, *, name="WF", non_standard_stages=None):
    d = models.WorkflowDefinition(
        tenant_id=ws["tenant"].id, name=name, status="active",
        stages=stages, non_standard_stages=non_standard_stages or [],
        created_by=ws["owner"].id,
    )
    db.add(d)
    db.commit()
    return d


def _step_named(db, run, name):
    return next(s for s in wf.run_steps(db, run.id) if s.name == name)


# ---------------------------------------------------------------------------- parallel


class TestParallelStages:
    def test_every_step_in_a_stage_activates_together(self, db, workspace):
        """The whole point: Legal, Finance and Compliance review at the same time."""
        legal = _user(db, workspace, "Legal", department="Legal")
        finance = _user(db, workspace, "Finance", department="Finance")
        compliance = _user(db, workspace, "Compliance", department="Compliance")
        definition = _definition(db, workspace, [{
            "name": "Concurrent review", "policy": "all",
            "steps": [
                {"name": "Legal", "assignee_kind": "user", "assignee_value": legal.id},
                {"name": "Finance", "assignee_kind": "user", "assignee_value": finance.id},
                {"name": "Compliance", "assignee_kind": "user", "assignee_value": compliance.id},
            ],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()

        active = wf.active_steps(db, run)
        assert len(active) == 3, "all three reviewers must be able to start at once"
        assert {s.name for s in active} == {"Legal", "Finance", "Compliance"}

    def test_reviewers_complete_independently_and_out_of_order(self, db, workspace):
        legal = _user(db, workspace, "Legal")
        finance = _user(db, workspace, "Finance")
        definition = _definition(db, workspace, [{
            "name": "Review", "policy": "all",
            "steps": [
                {"name": "Legal", "assignee_kind": "user", "assignee_value": legal.id},
                {"name": "Finance", "assignee_kind": "user", "assignee_value": finance.id},
            ],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()

        # Finance goes first — order must not matter.
        wf.decide(db, run=run, step=_step_named(db, run, "Finance"),
                  contract=workspace["contract"], user=finance, decision="approve")
        db.commit()
        assert run.status == "running", "the stage is not done until Legal responds too"
        assert _step_named(db, run, "Legal").status == "active"

        wf.decide(db, run=run, step=_step_named(db, run, "Legal"),
                  contract=workspace["contract"], user=legal, decision="approve")
        db.commit()
        assert run.status == "approved"
        assert workspace["contract"].status == "approved"

    def test_next_stage_activates_only_after_the_current_one_completes(self, db, workspace):
        legal = _user(db, workspace, "Legal")
        finance = _user(db, workspace, "Finance")
        cfo = _user(db, workspace, "CFO", role="manager")
        definition = _definition(db, workspace, [
            {"name": "Functional review", "policy": "all", "steps": [
                {"name": "Legal", "assignee_kind": "user", "assignee_value": legal.id},
                {"name": "Finance", "assignee_kind": "user", "assignee_value": finance.id},
            ]},
            {"name": "Sign-off", "policy": "all", "steps": [
                {"name": "CFO", "assignee_kind": "user", "assignee_value": cfo.id},
            ]},
        ])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        assert _step_named(db, run, "CFO").status == "pending"

        for reviewer, step_name in ((legal, "Legal"), (finance, "Finance")):
            wf.decide(db, run=run, step=_step_named(db, run, step_name),
                      contract=workspace["contract"], user=reviewer, decision="approve")
            db.commit()

        assert _step_named(db, run, "CFO").status == "active"
        assert run.current_stage == 1

    def test_rejection_ends_the_run_immediately(self, db, workspace):
        """Waiting for the other reviewers to also say no would waste their time and delay
        the author's rework."""
        legal = _user(db, workspace, "Legal")
        finance = _user(db, workspace, "Finance")
        definition = _definition(db, workspace, [{
            "name": "Review", "policy": "all",
            "steps": [
                {"name": "Legal", "assignee_kind": "user", "assignee_value": legal.id},
                {"name": "Finance", "assignee_kind": "user", "assignee_value": finance.id},
            ],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()

        wf.decide(db, run=run, step=_step_named(db, run, "Legal"),
                  contract=workspace["contract"], user=legal, decision="reject",
                  comment="Indemnity cap unacceptable")
        db.commit()
        assert run.status == "rejected"
        assert workspace["contract"].status == "rejected"
        assert _step_named(db, run, "Finance").status == "skipped"

    def test_legacy_flat_definition_still_runs_sequentially(self, db, workspace):
        """Existing definitions must keep working — one step per stage IS the old behaviour."""
        a = _user(db, workspace, "First")
        b = _user(db, workspace, "Second")
        definition = models.WorkflowDefinition(
            tenant_id=workspace["tenant"].id, name="Legacy", status="active",
            steps=[
                {"name": "First", "assignee_kind": "user", "assignee_value": a.id},
                {"name": "Second", "assignee_kind": "user", "assignee_value": b.id},
            ],
            created_by=workspace["owner"].id,
        )
        db.add(definition)
        db.commit()

        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        active = wf.active_steps(db, run)
        assert len(active) == 1 and active[0].name == "First"


# ---------------------------------------------------------------------------- policies


class TestCompletionPolicies:
    def _run_with(self, db, ws, policy, threshold=0, count=3):
        users = [_user(db, ws, f"R{i}") for i in range(count)]
        definition = _definition(db, ws, [{
            "name": "Panel", "policy": policy, "threshold": threshold,
            "steps": [
                {"name": f"R{i}", "assignee_kind": "user", "assignee_value": u.id}
                for i, u in enumerate(users)
            ],
        }], name=f"WF-{policy}-{uuid.uuid4().hex[:4]}")
        run = wf.start_run(db, contract=ws["contract"], definition=definition, user=ws["owner"])
        db.commit()
        return run, users

    def test_any_completes_on_the_first_approval(self, db, workspace):
        run, users = self._run_with(db, workspace, "any")
        wf.decide(db, run=run, step=_step_named(db, run, "R1"),
                  contract=workspace["contract"], user=users[1], decision="approve")
        db.commit()
        assert run.status == "approved"
        assert _step_named(db, run, "R0").status == "skipped", (
            "colleagues who had not responded are no longer required"
        )

    def test_quorum_needs_the_configured_count(self, db, workspace):
        run, users = self._run_with(db, workspace, "quorum", threshold=2)
        wf.decide(db, run=run, step=_step_named(db, run, "R0"),
                  contract=workspace["contract"], user=users[0], decision="approve")
        db.commit()
        assert run.status == "running"
        wf.decide(db, run=run, step=_step_named(db, run, "R2"),
                  contract=workspace["contract"], user=users[2], decision="approve")
        db.commit()
        assert run.status == "approved"

    def test_percentage_rounds_to_a_whole_reviewer(self, db, workspace):
        """67% of three reviewers is two — you cannot have two-thirds of an approval."""
        run, users = self._run_with(db, workspace, "percentage", threshold=67)
        wf.decide(db, run=run, step=_step_named(db, run, "R0"),
                  contract=workspace["contract"], user=users[0], decision="approve")
        db.commit()
        assert run.status == "running"
        wf.decide(db, run=run, step=_step_named(db, run, "R1"),
                  contract=workspace["contract"], user=users[1], decision="approve")
        db.commit()
        assert run.status == "approved"

    def test_unknown_policy_falls_back_to_all(self, db, workspace):
        """An unrecognised policy must be the STRICTEST reading, never the loosest — a typo
        in a workflow definition must not silently reduce the approvals required."""
        definition = _definition(db, workspace, [{
            "name": "Typo", "policy": "majorityy",
            "steps": [{"name": "A", "assignee_kind": "role", "assignee_value": "approver"}],
        }])
        assert definition.as_stages()[0]["policy"] == "majorityy"
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        assert (run.stages or [])[0]["policy"] == "all"


# ---------------------------------------------------------------------------- matrix


class TestApprovalMatrix:
    def test_rule_adds_a_stage_when_the_value_crosses_a_threshold(self, db, workspace):
        cfo = _user(db, workspace, "CFO", role="manager")
        db.add(models.ApprovalRule(
            tenant_id=workspace["tenant"].id, name="Over 1M needs CFO",
            min_value=1_000_000, stage_name="CFO sign-off",
            stage_steps=[{"name": "CFO", "assignee_kind": "user", "assignee_value": cfo.id}],
        ))
        db.commit()

        definition = _definition(db, workspace, [{
            "name": "Base", "policy": "all",
            "steps": [{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"}],
        }])

        workspace["contract"].value = 500_000
        db.commit()
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        assert len(run.stages) == 1, "a 500k contract should not pull in the CFO"

        workspace["contract"].value = 5_000_000
        workspace["contract"].status = "draft"
        db.commit()
        run2 = wf.start_run(db, contract=workspace["contract"], definition=definition,
                            user=workspace["owner"])
        db.commit()
        assert [s["name"] for s in run2.stages] == ["Base", "CFO sign-off"]

    def test_rule_matching_nobody_is_skipped_not_inserted(self, db, workspace):
        """An empty stage could never complete — it would stall the review silently."""
        db.add(models.ApprovalRule(
            tenant_id=workspace["tenant"].id, name="Broken rule",
            min_value=0, stage_name="Nobody", stage_steps=[],
        ))
        db.commit()
        stages, applied, _ = approval_matrix.apply(db, workspace["contract"], [
            {"name": "Base", "policy": "all", "steps": [{"assignee_kind": "role",
                                                         "assignee_value": "approver"}]}
        ])
        assert [s["name"] for s in stages] == ["Base"]
        assert applied == []

    def test_non_standard_only_rule_waits_for_the_flag(self, db, workspace):
        db.add(models.ApprovalRule(
            tenant_id=workspace["tenant"].id, name="Non-standard needs Legal",
            non_standard_only=True, stage_name="Legal (non-standard)",
            stage_steps=[{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"}],
        ))
        db.commit()

        stages, applied, _ = approval_matrix.apply(db, workspace["contract"], [])
        assert applied == []

        wf.mark_non_standard(db, workspace["contract"], reason="Counterparty edited clause 7")
        db.commit()
        stages, applied, _ = approval_matrix.apply(db, workspace["contract"], [])
        assert [r.name for r in applied] == ["Non-standard needs Legal"]

    def test_material_change_triggers_a_reroute(self, db, workspace):
        cfo = _user(db, workspace, "CFO", role="manager")
        db.add(models.ApprovalRule(
            tenant_id=workspace["tenant"].id, name="Over 1M needs CFO", min_value=1_000_000,
            stage_name="CFO", stage_steps=[{"assignee_kind": "user", "assignee_value": cfo.id}],
        ))
        db.commit()
        definition = _definition(db, workspace, [{
            "name": "Base", "policy": "all",
            "steps": [{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"}],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()

        needed, reasons = approval_matrix.needs_rerouting(db, run, workspace["contract"])
        assert not needed

        # The exact hole this closes: quietly editing 500k up to 9M after routing.
        workspace["contract"].value = 9_000_000
        db.commit()
        needed, reasons = approval_matrix.needs_rerouting(db, run, workspace["contract"])
        assert needed
        assert any("value" in r for r in reasons)

    def test_immaterial_change_does_not_disturb_a_running_review(self, db, workspace):
        definition = _definition(db, workspace, [{
            "name": "Base", "policy": "all",
            "steps": [{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"}],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        workspace["contract"].value = 500_001  # crosses no threshold
        db.commit()
        needed, _ = approval_matrix.needs_rerouting(db, run, workspace["contract"])
        assert not needed


# ---------------------------------------------------------------------------- delegation


class TestDelegation:
    def test_assignment_routes_to_the_proxy(self, db, workspace):
        principal = _user(db, workspace, "On Leave")
        proxy = _user(db, workspace, "Covering")
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        db.add(models.Delegation(
            tenant_id=workspace["tenant"].id, from_user_id=principal.id, to_user_id=proxy.id,
            starts_at=now - dt.timedelta(days=1), ends_at=now + dt.timedelta(days=5),
            reason="Annual leave",
        ))
        db.commit()

        definition = _definition(db, workspace, [{
            "name": "Review", "policy": "all",
            "steps": [{"name": "Approver", "assignee_kind": "user",
                       "assignee_value": principal.id}],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()

        step = _step_named(db, run, "Approver")
        assert step.assignee_value == proxy.id
        assert step.delegated_from == principal.id, (
            "the principal must stay visible — an approval under delegation is not the "
            "principal personally approving"
        )
        assert wf.can_decide(proxy, step)
        assert wf.can_decide(principal, step), "the principal can still act if they return"

    def test_expired_delegation_does_not_route(self, db, workspace):
        principal = _user(db, workspace, "Back Now")
        proxy = _user(db, workspace, "Was Covering")
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        db.add(models.Delegation(
            tenant_id=workspace["tenant"].id, from_user_id=principal.id, to_user_id=proxy.id,
            starts_at=now - dt.timedelta(days=10), ends_at=now - dt.timedelta(days=1),
        ))
        db.commit()
        assert wf.resolve_delegate(db, workspace["tenant"].id, principal.id) is None

    def test_scoped_delegation_only_covers_its_contract_type(self, db, workspace):
        principal = _user(db, workspace, "Principal")
        proxy = _user(db, workspace, "Proxy")
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        db.add(models.Delegation(
            tenant_id=workspace["tenant"].id, from_user_id=principal.id, to_user_id=proxy.id,
            scope="nda", starts_at=now - dt.timedelta(days=1),
            ends_at=now + dt.timedelta(days=5),
        ))
        db.commit()
        assert wf.resolve_delegate(db, workspace["tenant"].id, principal.id,
                                   contract_type="nda") == proxy.id
        assert wf.resolve_delegate(db, workspace["tenant"].id, principal.id,
                                   contract_type="msa") is None

    def test_both_parties_appear_in_the_decision_audit(self, db, workspace):
        principal = _user(db, workspace, "Principal")
        proxy = _user(db, workspace, "Proxy")
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        db.add(models.Delegation(
            tenant_id=workspace["tenant"].id, from_user_id=principal.id, to_user_id=proxy.id,
            starts_at=now - dt.timedelta(days=1), ends_at=now + dt.timedelta(days=5),
        ))
        db.commit()
        definition = _definition(db, workspace, [{
            "name": "Review", "policy": "all",
            "steps": [{"name": "Approver", "assignee_kind": "user",
                       "assignee_value": principal.id}],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        wf.decide(db, run=run, step=_step_named(db, run, "Approver"),
                  contract=workspace["contract"], user=proxy, decision="approve")
        db.commit()

        entry = db.query(models.AuditLog).filter(
            models.AuditLog.tenant_id == workspace["tenant"].id,
            models.AuditLog.action == "contract.workflow_decision",
        ).one()
        assert entry.meta["delegated_from"] == principal.id
        assert entry.meta["delegated_from_name"] == principal.name


# ---------------------------------------------------------------------------- mid-flight


class TestMidFlightChanges:
    def _running(self, db, ws):
        definition = _definition(db, ws, [{
            "name": "Review", "policy": "all",
            "steps": [{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"}],
        }])
        run = wf.start_run(db, contract=ws["contract"], definition=definition, user=ws["owner"])
        db.commit()
        return run

    def test_reviewer_can_be_added_to_a_running_stage(self, db, workspace):
        run = self._running(db, workspace)
        extra = _user(db, workspace, "Risk")
        step = wf.add_reviewer(
            db, run=run, contract=workspace["contract"], stage_index=0, name="Risk",
            assignee_kind="user", assignee_value=extra.id, actor=workspace["owner"],
        )
        db.commit()
        assert step.status == "active", "a reviewer added to the current stage starts at once"
        assert step.added_mid_flight and step.added_by == workspace["owner"].id
        assert len(wf.active_steps(db, run)) == 2

    def test_adding_a_reviewer_is_audited(self, db, workspace):
        run = self._running(db, workspace)
        extra = _user(db, workspace, "Risk")
        wf.add_reviewer(db, run=run, contract=workspace["contract"], stage_index=0,
                        name="Risk", assignee_kind="user", assignee_value=extra.id,
                        actor=workspace["owner"])
        db.commit()
        assert db.query(models.AuditLog).filter(
            models.AuditLog.tenant_id == workspace["tenant"].id,
            models.AuditLog.action == "contract.reviewer_added",
        ).count() == 1

    def test_a_decided_reviewer_cannot_be_removed(self, db, workspace):
        """Removing them would erase a decision from the record."""
        approver = _user(db, workspace, "Decided")
        definition = _definition(db, workspace, [{
            "name": "Review", "policy": "all",
            "steps": [
                {"name": "A", "assignee_kind": "user", "assignee_value": approver.id},
                {"name": "B", "assignee_kind": "role", "assignee_value": "approver"},
            ],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        step = _step_named(db, run, "A")
        wf.decide(db, run=run, step=step, contract=workspace["contract"], user=approver,
                  decision="approve")
        db.commit()
        with pytest.raises(WorkflowError, match="already responded"):
            wf.remove_reviewer(db, run=run, contract=workspace["contract"], step=step,
                               actor=workspace["owner"])

    def test_a_stage_must_keep_at_least_one_reviewer(self, db, workspace):
        run = self._running(db, workspace)
        step = wf.active_steps(db, run)[0]
        with pytest.raises(WorkflowError, match="at least one reviewer"):
            wf.remove_reviewer(db, run=run, contract=workspace["contract"], step=step,
                               actor=workspace["owner"])

    def test_removing_the_last_outstanding_reviewer_completes_the_stage(self, db, workspace):
        a = _user(db, workspace, "A")
        b = _user(db, workspace, "B")
        definition = _definition(db, workspace, [{
            "name": "Review", "policy": "all",
            "steps": [
                {"name": "A", "assignee_kind": "user", "assignee_value": a.id},
                {"name": "B", "assignee_kind": "user", "assignee_value": b.id},
            ],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        wf.decide(db, run=run, step=_step_named(db, run, "A"),
                  contract=workspace["contract"], user=a, decision="approve")
        db.commit()
        wf.remove_reviewer(db, run=run, contract=workspace["contract"],
                           step=_step_named(db, run, "B"), actor=workspace["owner"],
                           reason="Not required after all")
        db.commit()
        assert run.status == "approved"

    def test_only_the_submitter_or_an_admin_can_change_the_set(self, db, workspace):
        run = self._running(db, workspace)
        outsider = _user(db, workspace, "Someone Else", role="author")
        with pytest.raises(WorkflowError, match="submitter or an admin"):
            wf.add_reviewer(db, run=run, contract=workspace["contract"], stage_index=0,
                            name="X", assignee_kind="role", assignee_value="approver",
                            actor=outsider)


# ---------------------------------------------------------------------------- SLA


class TestSlaAndEscalation:
    def _with_sla(self, db, ws, hours=8, escalate_to=None):
        approver = _user(db, ws, "Slow Approver")
        definition = _definition(db, ws, [{
            "name": "Timed", "policy": "all", "sla_hours": hours,
            "escalate_to_user_id": escalate_to,
            "steps": [{"name": "Approver", "assignee_kind": "user",
                       "assignee_value": approver.id}],
        }])
        run = wf.start_run(db, contract=ws["contract"], definition=definition, user=ws["owner"])
        db.commit()
        return run, approver

    def test_due_date_is_set_on_the_business_calendar(self, db, workspace):
        run, _ = self._with_sla(db, workspace, hours=8)
        step = wf.active_steps(db, run)[0]
        assert step.due_at is not None
        assert step.sla_hours == 8
        # 8 working hours can never be less than 8 wall-clock hours away.
        assert step.due_at >= step.activated_at + dt.timedelta(hours=8) - dt.timedelta(minutes=1)

    def test_reminder_fires_before_the_deadline_and_only_once(self, db, workspace):
        """Both ends of the clock are pinned to a working Wednesday.

        Elapsed time is measured in *working* hours, so a test that shifted `activated_at` by
        a wall-clock delta and swept at "now" would pass or fail depending on what time of day
        CI happened to run — which is exactly the kind of flake that gets a real assertion
        deleted six months later.
        """
        run, _ = self._with_sla(db, workspace, hours=8)
        step = wf.active_steps(db, run)[0]

        now = dt.datetime(2026, 8, 26, 15, 0)          # Wednesday, mid-afternoon
        step.activated_at = dt.datetime(2026, 8, 26, 9, 0)   # 6 working hours earlier
        step.due_at = dt.datetime(2026, 8, 27, 15, 0)        # comfortably ahead
        db.commit()

        first = wf.sla_sweep(db, now=now, tenant_id=workspace["tenant"].id)
        db.commit()
        assert first["reminded"] == 1, "6 of 8 working hours elapsed should trigger the reminder"
        assert step.reminded_at is not None

        second = wf.sla_sweep(db, now=now, tenant_id=workspace["tenant"].id)
        db.commit()
        assert second["reminded"] == 0, "a sweep must not re-notify the same step"

    def test_breach_escalates_once(self, db, workspace):
        boss = _user(db, workspace, "Head of Legal", role="manager")
        run, _ = self._with_sla(db, workspace, hours=4, escalate_to=boss.id)
        step = wf.active_steps(db, run)[0]
        step.due_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=1)
        db.commit()

        # Scoped to this tenant. An unscoped sweep counts every overdue step in the shared
        # test database, so the assertion would depend on what other tests left lying around
        # — which is exactly how this started failing once the suite grew.
        result = wf.sla_sweep(db, tenant_id=workspace["tenant"].id)
        db.commit()
        assert result["escalated"] == 1
        assert step.escalated_at is not None
        assert step.escalated_to == boss.id
        assert step.assignee_value == boss.id, "auto-escalation reassigns the step"
        assert step.delegated_from is not None, "whose deadline was missed stays visible"

        again = wf.sla_sweep(db, tenant_id=workspace["tenant"].id)
        db.commit()
        assert again["escalated"] == 0

    def test_escalation_without_a_target_notifies_rather_than_reassigns(self, db, workspace):
        run, approver = self._with_sla(db, workspace, hours=4, escalate_to=None)
        step = wf.active_steps(db, run)[0]
        step.due_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=1)
        db.commit()
        wf.sla_sweep(db, tenant_id=workspace["tenant"].id)
        db.commit()
        assert step.escalated_at is not None
        assert step.assignee_value == approver.id, "authority must not move without a target"

    def test_escalations_feed_is_queryable(self, db, workspace):
        run, _ = self._with_sla(db, workspace, hours=4)
        step = wf.active_steps(db, run)[0]
        step.due_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=1)
        db.commit()
        wf.sla_sweep(db, tenant_id=workspace["tenant"].id)
        db.commit()
        feed = wf.escalations(db, workspace["tenant"].id)
        assert len(feed) == 1 and feed[0].id == step.id

    def test_decision_records_whether_it_was_on_time(self, db, workspace):
        """SLA adherence is a KPI; it has to be derivable from the record."""
        run, approver = self._with_sla(db, workspace, hours=8)
        step = wf.active_steps(db, run)[0]
        step.due_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=1)
        db.commit()
        wf.decide(db, run=run, step=step, contract=workspace["contract"], user=approver,
                  decision="approve")
        db.commit()
        entry = db.query(models.AuditLog).filter(
            models.AuditLog.tenant_id == workspace["tenant"].id,
            models.AuditLog.action == "contract.workflow_decision",
        ).one()
        assert entry.meta["on_time"] is False

    def test_steps_without_an_sla_are_untouched(self, db, workspace):
        definition = _definition(db, workspace, [{
            "name": "No SLA", "policy": "all",
            "steps": [{"name": "A", "assignee_kind": "role", "assignee_value": "approver"}],
        }])
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        assert wf.active_steps(db, run)[0].due_at is None
        # Scoped to this tenant: the suite shares a database and other tests
        # deliberately leave overdue steps behind.
        assert wf.sla_sweep(db, tenant_id=workspace["tenant"].id) == {
            "reminded": 0, "escalated": 0, "breached": 0,
        }


# ---------------------------------------------------------------------------- calendar


class TestBusinessCalendar:
    def test_weekend_is_skipped(self, db):
        """A review raised Friday afternoon is not overdue on Saturday morning. Getting this
        wrong destroys trust in the escalation feed, after which everyone ignores it."""
        friday_4pm = dt.datetime(2026, 8, 21, 16, 0)   # a Friday
        assert friday_4pm.weekday() == 4
        due = business_calendar.add_business_hours(db, "t", friday_4pm, 4)
        assert due.weekday() == 0, "4 working hours from Friday 16:00 lands on Monday"

    def test_hours_outside_the_working_day_do_not_count(self, db):
        monday_5pm = dt.datetime(2026, 8, 24, 17, 0)
        due = business_calendar.add_business_hours(db, "t", monday_5pm, 4)
        assert due.date() > monday_5pm.date()

    def test_elapsed_excludes_the_weekend(self, db):
        friday_4pm = dt.datetime(2026, 8, 21, 16, 0)
        monday_10am = dt.datetime(2026, 8, 24, 10, 0)
        elapsed = business_calendar.business_hours_between(db, "t", friday_4pm, monday_10am)
        assert 2.9 < elapsed < 3.1, f"expected ~3 working hours, got {elapsed}"

    def test_holiday_is_not_a_working_day(self, db, make_user):
        _, tenant = make_user()
        db.add(models.Holiday(tenant_id=tenant.id, day=dt.date(2026, 8, 25), name="Test Holiday"))
        db.commit()
        monday_4pm = dt.datetime(2026, 8, 24, 16, 0)
        due = business_calendar.add_business_hours(db, tenant.id, monday_4pm, 4)
        assert due.date() == dt.date(2026, 8, 26), "Tuesday is a holiday; roll to Wednesday"

    def test_zero_hours_is_a_no_op(self, db):
        at = dt.datetime(2026, 8, 24, 10, 0)
        assert business_calendar.add_business_hours(db, "t", at, 0) == at


# ---------------------------------------------------------------------------- classification


class TestNonStandardClassification:
    def test_marking_is_idempotent_and_audited(self, db, workspace):
        wf.mark_non_standard(db, workspace["contract"], reason="Counterparty edited clause 7",
                             actor=workspace["owner"])
        db.commit()
        first_at = workspace["contract"].non_standard_at
        wf.mark_non_standard(db, workspace["contract"], reason="Something else",
                             actor=workspace["owner"])
        db.commit()
        assert workspace["contract"].non_standard_at == first_at
        assert workspace["contract"].non_standard_reason == "Counterparty edited clause 7"
        assert db.query(models.AuditLog).filter(
            models.AuditLog.tenant_id == workspace["tenant"].id,
            models.AuditLog.action == "contract.classified_non_standard",
        ).count() == 1

    def test_non_standard_definition_selects_the_other_route(self, db, workspace):
        definition = _definition(
            db, workspace,
            [{"name": "Standard", "policy": "all",
              "steps": [{"name": "Owner", "assignee_kind": "role", "assignee_value": "approver"}]}],
            non_standard_stages=[{
                "name": "Legal review (non-standard)", "policy": "all",
                "steps": [{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"}],
            }],
        )
        assert definition.as_stages()[0]["name"] == "Standard"
        assert definition.as_stages(non_standard=True)[0]["name"] == "Legal review (non-standard)"

        wf.mark_non_standard(db, workspace["contract"], reason="Client edit")
        db.commit()
        run = wf.start_run(db, contract=workspace["contract"], definition=definition,
                           user=workspace["owner"])
        db.commit()
        assert run.stages[0]["name"] == "Legal review (non-standard)"


def test_security_import(db):
    assert security is not None
