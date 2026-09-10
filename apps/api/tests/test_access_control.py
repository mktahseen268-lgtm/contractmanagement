"""Permissions, separation of duties, step-up auth, need-to-know access, legal holds.

These are controls, so the tests are written as attacks. The questions worth answering are not
"does a manager have manager permissions" but:

- can somebody approve work they authored, and is the override recorded when they do;
- can a step-up challenge for one object be replayed against another;
- can a confidential agreement be read by somebody not on its list, and is the refusal logged;
- does releasing one legal hold expose an agreement a *second* matter still covers.

That last one is the bug the whole `legal_holds` table exists to prevent, and a boolean could
not have avoided it.

Requirements: SOW-16, SOW-29, SEC-01, SEC-07, SEC-08, SEC-09.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import access_control as ac
from app import audit, legal_hold_service, models, security
from app.access_control import AccessDenied, StepUpRequired
from app.legal_hold_service import LegalHoldError

PASSWORD = "Str0ng!Passw0rd1"

#: Hashed once for the whole module. The fixture builds five users per test and password
#: hashing is deliberately slow, so hashing per user cost this file about a minute of pure
#: KDF work for no additional coverage.
_HASH = security.hash_password(PASSWORD)


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"ac-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    # `make_user` sets a random password; step-up has to present a known one.
    db.get(models.User, owner.id).password_hash = _HASH
    people = {}
    for role in ("manager", "approver", "author", "viewer"):
        person = models.User(
            tenant_id=tenant.id, email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
            name=role.title(), password_hash=_HASH, role=role)
        db.add(person)
        people[role] = person
    db.commit()
    owner = db.get(models.User, owner.id)
    return {"tenant": tenant, "owner": owner, **people}


def _contract(db, ws, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title=kwargs.pop("title", "Vendor Services Agreement"), type="vendor",
        status=kwargs.pop("status", "draft"),
        owner_id=kwargs.pop("owner_id", ws["owner"].id), created_by=ws["owner"].id,
        currency="PKR", **kwargs)
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------------------


def test_the_builtin_roles_carry_what_they_should(db, workspace):
    assert ac.can(db, workspace["viewer"], "contract.read")
    assert not ac.can(db, workspace["viewer"], "contract.write")
    assert ac.can(db, workspace["author"], "contract.write")
    assert not ac.can(db, workspace["author"], "contract.approve")
    assert ac.can(db, workspace["manager"], "contract.approve")
    assert ac.can(db, workspace["owner"], "role.manage")


def test_an_unknown_role_degrades_to_viewer_not_to_nothing(db, workspace):
    """A typo in a role name should restrict somebody, not lock an administrator out of the
    system they administer."""
    workspace["author"].role = "typo-role"
    db.flush()
    permissions = ac.permissions_for(db, workspace["author"])
    assert permissions == set(ac.ROLE_PERMISSIONS["viewer"])


def test_a_custom_role_extends_its_base(db, workspace):
    db.add(models.CustomRole(
        tenant_id=workspace["tenant"].id, key="legal-reviewer", name="Legal Reviewer",
        base_role="approver", grants=["clause.approve", "template.approve"],
        revokes=[], created_by=workspace["owner"].id))
    db.flush()
    workspace["approver"].role = "legal-reviewer"

    permissions = ac.permissions_for(db, workspace["approver"])
    assert "contract.approve" in permissions      # from the base
    assert "clause.approve" in permissions        # granted


def test_a_revoke_always_wins(db, workspace):
    """"This role must never do X" is only worth writing down if nothing can grant it back."""
    db.add(models.CustomRole(
        tenant_id=workspace["tenant"].id, key="restricted", name="Restricted",
        base_role="manager", grants=["contract.approve"], revokes=["contract.approve"],
        created_by=workspace["owner"].id))
    db.flush()
    workspace["manager"].role = "restricted"
    assert not ac.can(db, workspace["manager"], "contract.approve")


def test_an_inactive_custom_role_falls_back(db, workspace):
    db.add(models.CustomRole(
        tenant_id=workspace["tenant"].id, key="dormant", name="Dormant",
        base_role="owner", grants=[], revokes=[], is_active=False,
        created_by=workspace["owner"].id))
    db.flush()
    workspace["viewer"].role = "dormant"
    assert not ac.can(db, workspace["viewer"], "role.manage")


def test_require_raises_rather_than_returning_false(db, workspace):
    with pytest.raises(AccessDenied, match="does not allow"):
        ac.require(db, workspace["viewer"], "contract.delete")


# ---------------------------------------------------------------------------------------
# Separation of duties
# ---------------------------------------------------------------------------------------


def test_the_author_of_an_agreement_cannot_approve_it(db, workspace):
    contract = _contract(db, workspace)
    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.authored",
                 actor=workspace["manager"], object_type="contract", object_id=contract.id)
    db.flush()

    with pytest.raises(AccessDenied, match="cannot be its final approver"):
        ac.enforce_segregation(db, user=workspace["manager"], action="contract.approved",
                               object_type="contract", object_id=contract.id)


def test_somebody_else_can_approve_it(db, workspace):
    contract = _contract(db, workspace)
    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.authored",
                 actor=workspace["author"], object_type="contract", object_id=contract.id)
    db.flush()
    ac.enforce_segregation(db, user=workspace["manager"], action="contract.approved",
                           object_type="contract", object_id=contract.id)


def test_the_rule_is_per_object_not_global(db, workspace):
    """Authoring one agreement must not stop you approving a different one."""
    authored = _contract(db, workspace)
    other = _contract(db, workspace, title="Something else")
    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.authored",
                 actor=workspace["manager"], object_type="contract", object_id=authored.id)
    db.flush()
    ac.enforce_segregation(db, user=workspace["manager"], action="contract.approved",
                           object_type="contract", object_id=other.id)


def test_a_block_is_recorded(db, workspace):
    """A control that fires silently cannot be evidenced."""
    contract = _contract(db, workspace)
    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.authored",
                 actor=workspace["manager"], object_type="contract", object_id=contract.id)
    db.flush()
    with pytest.raises(AccessDenied):
        ac.enforce_segregation(db, user=workspace["manager"], action="contract.approved",
                               object_type="contract", object_id=contract.id)
    db.flush()
    assert db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id, action="sod.blocked").count() == 1


def test_an_override_needs_a_reason_and_is_audited_loudly(db, workspace):
    """A small workspace may genuinely have nobody else — but "we knew and did it anyway"
    must be visible rather than indistinguishable from the control not firing."""
    contract = _contract(db, workspace)
    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.authored",
                 actor=workspace["manager"], object_type="contract", object_id=contract.id)
    db.flush()

    ac.enforce_segregation(db, user=workspace["manager"], action="contract.approved",
                           object_type="contract", object_id=contract.id,
                           override_reason="Sole legal reviewer on site this week.")
    db.flush()
    entry = db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id, action="sod.overridden").one()
    assert "Sole legal reviewer" in entry.meta["override_reason"]


def test_a_webhook_creator_cannot_reveal_its_own_secret(db, workspace):
    audit.record(db, tenant_id=workspace["tenant"].id, action="webhook.created",
                 actor=workspace["admin"] if "admin" in workspace else workspace["manager"],
                 object_type="webhook", object_id="hook-1")
    db.flush()
    with pytest.raises(AccessDenied, match="reveal its secret"):
        ac.enforce_segregation(db, user=workspace["manager"],
                               action="webhook.secret_revealed",
                               object_type="webhook", object_id="hook-1")


def test_an_unrelated_action_is_not_segregated(db, workspace):
    contract = _contract(db, workspace)
    ac.enforce_segregation(db, user=workspace["manager"], action="contract.read",
                           object_type="contract", object_id=contract.id)


# ---------------------------------------------------------------------------------------
# Step-up authentication
# ---------------------------------------------------------------------------------------


def test_only_sensitive_actions_need_step_up():
    assert ac.needs_step_up("user.role_changed")
    assert not ac.needs_step_up("contract.read")


def test_a_sensitive_action_without_a_challenge_demands_one(db, workspace):
    with pytest.raises(StepUpRequired) as caught:
        ac.consume(db, workspace["owner"], "user.role_changed", "",
                   object_type="user", object_id="u1")
    assert caught.value.challenge_id


def test_a_satisfied_challenge_lets_the_action_through(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "user.role_changed",
                                  object_type="user", object_id="u1")
    ac.satisfy(db, challenge, workspace["owner"], password=PASSWORD)
    ac.consume(db, workspace["owner"], "user.role_changed", challenge.id,
               object_type="user", object_id="u1")
    assert challenge.consumed_at is not None


def test_a_challenge_is_single_use(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "user.role_changed",
                                  object_type="user", object_id="u1")
    ac.satisfy(db, challenge, workspace["owner"], password=PASSWORD)
    ac.consume(db, workspace["owner"], "user.role_changed", challenge.id,
               object_type="user", object_id="u1")
    with pytest.raises(StepUpRequired):
        ac.consume(db, workspace["owner"], "user.role_changed", challenge.id,
                   object_type="user", object_id="u1")


def test_a_challenge_cannot_be_replayed_against_another_object(db, workspace):
    """The reason challenges are object-bound: a session-scoped "recently authenticated" flag
    would turn one re-authentication into a five-minute window over everything."""
    challenge = ac.open_challenge(db, workspace["owner"], "webhook.secret_revealed",
                                  object_type="webhook", object_id="hook-1")
    ac.satisfy(db, challenge, workspace["owner"], password=PASSWORD)
    with pytest.raises(StepUpRequired):
        ac.consume(db, workspace["owner"], "webhook.secret_revealed", challenge.id,
                   object_type="webhook", object_id="hook-2")


def test_a_challenge_cannot_be_reused_for_a_different_action(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "webhook.secret_revealed",
                                  object_type="webhook", object_id="hook-1")
    ac.satisfy(db, challenge, workspace["owner"], password=PASSWORD)
    with pytest.raises(StepUpRequired):
        ac.consume(db, workspace["owner"], "signature.voided", challenge.id,
                   object_type="webhook", object_id="hook-1")


def test_a_wrong_password_does_not_satisfy_a_challenge(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "user.role_changed")
    with pytest.raises(AccessDenied, match="did not match"):
        ac.satisfy(db, challenge, workspace["owner"], password="not-the-password")
    assert challenge.status == "pending"


def test_repeated_wrong_answers_burn_the_challenge(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "user.role_changed")
    for _ in range(ac.STEP_UP_MAX_ATTEMPTS):
        with pytest.raises(AccessDenied):
            ac.satisfy(db, challenge, workspace["owner"], password="wrong")
    with pytest.raises(AccessDenied, match="Too many attempts"):
        ac.satisfy(db, challenge, workspace["owner"], password=PASSWORD)
    assert challenge.status == "failed"


def test_an_expired_challenge_is_refused(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "user.role_changed")
    challenge.expires_at = dt.datetime(2020, 1, 1)
    db.flush()
    with pytest.raises(AccessDenied, match="expired"):
        ac.satisfy(db, challenge, workspace["owner"], password=PASSWORD)


def test_somebody_elses_challenge_cannot_be_answered(db, workspace):
    challenge = ac.open_challenge(db, workspace["owner"], "user.role_changed")
    with pytest.raises(AccessDenied, match="belongs to somebody else"):
        ac.satisfy(db, challenge, workspace["manager"], password=PASSWORD)


# ---------------------------------------------------------------------------------------
# Need-to-know access
# ---------------------------------------------------------------------------------------


def test_an_ordinary_agreement_is_visible_to_everyone(db, workspace):
    contract = _contract(db, workspace)
    assert ac.visible_to(db, workspace["viewer"], contract) is True


def test_a_confidential_agreement_is_not(db, workspace):
    contract = _contract(db, workspace, confidential=True)
    assert ac.visible_to(db, workspace["viewer"], contract) is False


def test_the_owner_can_always_see_their_own(db, workspace):
    """An access model where somebody can lock the account owner out produces an emergency,
    not security."""
    contract = _contract(db, workspace, confidential=True,
                         owner_id=workspace["manager"].id)
    assert ac.visible_to(db, workspace["manager"], contract) is True
    assert ac.visible_to(db, workspace["owner"], contract) is True


def test_an_explicit_grant_opens_it(db, workspace):
    contract = _contract(db, workspace, confidential=True)
    ac.grant(db, contract, actor=workspace["owner"], user_id=workspace["viewer"].id,
             reason="Assigned to the matter")
    assert ac.visible_to(db, workspace["viewer"], contract) is True


def test_a_role_grant_opens_it_for_that_role(db, workspace):
    contract = _contract(db, workspace, confidential=True)
    ac.grant(db, contract, actor=workspace["owner"], role="approver", reason="Review panel")
    assert ac.visible_to(db, workspace["approver"], contract) is True
    assert ac.visible_to(db, workspace["viewer"], contract) is False


def test_an_expired_grant_closes_again(db, workspace):
    contract = _contract(db, workspace, confidential=True)
    ac.grant(db, contract, actor=workspace["owner"], user_id=workspace["viewer"].id,
             reason="Temporary", expires_at=dt.datetime(2020, 1, 1))
    assert ac.visible_to(db, workspace["viewer"], contract) is False


def test_a_refused_read_is_logged(db, workspace):
    """The event an investigation starts from — invisible unless recorded."""
    contract = _contract(db, workspace, confidential=True)
    with pytest.raises(AccessDenied):
        ac.require_visible(db, workspace["viewer"], contract)
    db.flush()
    assert db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id, action="contract.access_denied").count() == 1


def test_break_glass_needs_a_reason(db, workspace):
    contract = _contract(db, workspace, confidential=True)
    with pytest.raises(AccessDenied, match="needs a reason"):
        ac.break_glass(db, contract, actor=workspace["manager"], reason="  ")


def test_break_glass_grants_access_and_shouts_about_it(db, workspace):
    contract = _contract(db, workspace, confidential=True)
    ac.break_glass(db, contract, actor=workspace["manager"],
                   reason="Regulator requested the file today.")
    db.flush()
    assert ac.visible_to(db, workspace["manager"], contract) is True
    assert db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id, action="access.break_glass").count() == 1


# ---------------------------------------------------------------------------------------
# Temporary external access
# ---------------------------------------------------------------------------------------


def test_a_link_resolves_to_its_record(db, workspace):
    contract = _contract(db, workspace)
    access, raw = ac.issue_temporary_access(
        db, contract, actor=workspace["owner"], email="counsel@firm.test", days=7)
    db.flush()
    assert ac.resolve_temporary(db, raw).id == access.id


def test_only_the_hash_is_stored(db, workspace):
    """A link that leaks from a mailbox must not be replayable out of the database."""
    contract = _contract(db, workspace)
    access, raw = ac.issue_temporary_access(
        db, contract, actor=workspace["owner"], email="counsel@firm.test")
    assert raw not in access.token_hash
    assert access.token_hash == ac.hash_token(raw)


def test_a_revoked_link_stops_resolving(db, workspace):
    contract = _contract(db, workspace)
    access, raw = ac.issue_temporary_access(
        db, contract, actor=workspace["owner"], email="counsel@firm.test")
    ac.revoke_temporary(db, access, actor=workspace["owner"])
    db.flush()
    assert ac.resolve_temporary(db, raw) is None


def test_an_expired_link_stops_resolving(db, workspace):
    """Returns nothing rather than an expired record, so a caller cannot serve content from
    one by mistake."""
    contract = _contract(db, workspace)
    access, raw = ac.issue_temporary_access(
        db, contract, actor=workspace["owner"], email="counsel@firm.test")
    access.expires_at = dt.datetime(2020, 1, 1)
    db.flush()
    assert ac.resolve_temporary(db, raw) is None


def test_a_wrong_token_resolves_to_nothing(db, workspace):
    assert ac.resolve_temporary(db, "not-a-real-token") is None


def test_an_absurd_duration_is_refused(db, workspace):
    contract = _contract(db, workspace)
    with pytest.raises(AccessDenied, match="between 1 and 90 days"):
        ac.issue_temporary_access(db, contract, actor=workspace["owner"],
                                   email="a@b.test", days=400)


def test_the_expiry_sweep_is_idempotent(db, workspace):
    contract = _contract(db, workspace)
    access, _raw = ac.issue_temporary_access(db, contract, actor=workspace["owner"],
                                              email="a@b.test")
    access.expires_at = dt.datetime(2020, 1, 1)
    db.flush()
    tenant_id = workspace["tenant"].id
    assert ac.expire_temporary(db, tenant_id=tenant_id) == 1
    assert ac.expire_temporary(db, tenant_id=tenant_id) == 0


# ---------------------------------------------------------------------------------------
# Legal holds
# ---------------------------------------------------------------------------------------


def test_placing_a_hold_sets_the_flag_every_retention_path_reads(db, workspace):
    contract = _contract(db, workspace)
    legal_hold_service.place(db, workspace["tenant"].id, matter="Regulator enquiry",
                             contract_ids=[contract.id], actor=workspace["owner"])
    assert contract.legal_hold is True


def test_a_hold_needs_a_matter_and_something_to_hold(db, workspace):
    with pytest.raises(LegalHoldError, match="matter name"):
        legal_hold_service.place(db, workspace["tenant"].id, matter="  ",
                                 contract_ids=["x"], actor=workspace["owner"])
    with pytest.raises(LegalHoldError, match="at least one agreement"):
        legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                 contract_ids=[], actor=workspace["owner"])


def test_a_hold_over_a_missing_agreement_is_refused(db, workspace):
    with pytest.raises(LegalHoldError, match="do not exist"):
        legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                 contract_ids=["nope"], actor=workspace["owner"])


def test_releasing_needs_a_reason(db, workspace):
    contract = _contract(db, workspace)
    hold = legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                    contract_ids=[contract.id], actor=workspace["owner"])
    with pytest.raises(LegalHoldError, match="needs a reason"):
        legal_hold_service.release(db, hold, actor=workspace["owner"], reason="  ")


def test_releasing_the_only_hold_clears_the_flag(db, workspace):
    contract = _contract(db, workspace)
    hold = legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                    contract_ids=[contract.id], actor=workspace["owner"])
    legal_hold_service.release(db, hold, actor=workspace["owner"], reason="Matter closed.")
    assert contract.legal_hold is False


def test_releasing_one_matter_does_not_expose_an_agreement_another_still_covers(db, workspace):
    """The bug the whole table exists to prevent. A boolean could not have avoided it, and
    the failure — evidence destroyed by a retention sweep — is not recoverable."""
    contract = _contract(db, workspace)
    first = legal_hold_service.place(db, workspace["tenant"].id, matter="Regulator enquiry",
                                     contract_ids=[contract.id], actor=workspace["owner"])
    legal_hold_service.place(db, workspace["tenant"].id, matter="Civil claim",
                             contract_ids=[contract.id], actor=workspace["owner"])

    legal_hold_service.release(db, first, actor=workspace["owner"], reason="Enquiry closed.")

    assert contract.legal_hold is True, "the civil claim still covers this agreement"
    assert legal_hold_service.blocks_deletion(db, contract) == "Civil claim"


def test_a_released_hold_cannot_be_released_twice(db, workspace):
    contract = _contract(db, workspace)
    hold = legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                    contract_ids=[contract.id], actor=workspace["owner"])
    legal_hold_service.release(db, hold, actor=workspace["owner"], reason="Done.")
    with pytest.raises(LegalHoldError, match="already been released"):
        legal_hold_service.release(db, hold, actor=workspace["owner"], reason="Again.")


def test_extending_a_hold_covers_the_new_agreements(db, workspace):
    first = _contract(db, workspace)
    second = _contract(db, workspace, title="Also relevant")
    hold = legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                    contract_ids=[first.id], actor=workspace["owner"])
    legal_hold_service.add_contracts(db, hold, [second.id], actor=workspace["owner"])
    assert second.legal_hold is True


def test_the_export_set_carries_audit_chain_positions(db, workspace):
    """The recipient has to be able to verify what they were given against the record."""
    contract = _contract(db, workspace)
    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.created",
                 actor=workspace["owner"], object_type="contract", object_id=contract.id)
    db.flush()
    hold = legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                                    contract_ids=[contract.id], actor=workspace["owner"])

    export = legal_hold_service.export_set(db, hold)
    assert export["contract_count"] == 1
    assert export["contracts"][0]["audit_seq_from"] is not None


def test_reconcile_repairs_a_drifted_flag(db, workspace):
    """Derived state that has drifted is discovered during a legal matter — the worst
    possible moment — so there is a repair path."""
    contract = _contract(db, workspace)
    legal_hold_service.place(db, workspace["tenant"].id, matter="M",
                             contract_ids=[contract.id], actor=workspace["owner"])
    contract.legal_hold = False        # simulate drift
    db.flush()

    assert legal_hold_service.reconcile(db, workspace["tenant"].id)["corrected"] == 1
    assert contract.legal_hold is True
