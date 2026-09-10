"""Bulk send — one approved template dispatched to many signers.

The failure this feature can produce is not a stack trace, it is five hundred wrong documents
in five hundred inboxes, which cannot be recalled. So the tests here are weighted towards the
things that are unrecoverable once they happen: the wrong person's details merged into somebody
else's agreement, a second envelope to someone who already has one, and a batch that half-fails
without saying which half.

Requirements: SOW-17, BB-09.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import bulk_send_service, models, security, signing_service, template_service
from app.bulk_send_service import BulkSendError

BODY = ("This undertaking is made between {{org}} and {{name}} of {{company}}, "
        "whose agent code is {{agent_code}}.")


@pytest.fixture()
def workspace(db, make_user):
    """A tenant, an author and an approver — a template cannot approve itself."""
    author, tenant = make_user(email=f"author-{uuid.uuid4().hex[:8]}@example.com",
                               name="Batch Author")
    approver = models.User(
        tenant_id=tenant.id, email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        name="Legal Reviewer", password_hash=security.hash_password("Str0ng!Passw0rd1"),
        role="manager",
    )
    db.add(approver)
    db.commit()
    return {"tenant": tenant, "author": author, "approver": approver}


def _template(db, ws, *, body: str = BODY, fields: list | None = None, approve: bool = True):
    t = models.ContractTemplate(
        tenant_id=ws["tenant"].id, name="Branch Agent Undertaking", contract_type="other",
        body=body, default_currency="PKR", status="draft", is_active=False,
        # `name` is a declared field like any other — bulk send fills it from the row rather
        # than asking for it twice. Approval refuses a template whose placeholders have nothing
        # behind them, and that check is not relaxed for bulk send: a template that would
        # generate a literal `{{name}}` must not become usable just because a batch supplies it.
        fields=fields if fields is not None else [
            {"key": "name", "label": "Signer name", "type": "text", "required": True},
            {"key": "company", "label": "Company", "type": "text", "required": True},
            {"key": "agent_code", "label": "Agent code", "type": "text", "required": True},
        ],
        created_by=ws["author"].id,
    )
    db.add(t)
    db.flush()
    if approve:
        template_service.submit_for_approval(db, t, actor=ws["author"])
        template_service.approve(db, t, actor=ws["approver"])
    db.commit()
    return t


def _rows(n: int = 3) -> list[dict]:
    return [
        {"name": f"Signer {i}", "email": f"signer{i}-{uuid.uuid4().hex[:6]}@example.test",
         "values": {"company": f"Company {i}", "agent_code": f"BB-{1000 + i}"}}
        for i in range(n)
    ]


def _run(db, ws, rows, **kwargs) -> models.BulkSendBatch:
    batch = bulk_send_service.create_batch(
        db, template=kwargs.pop("template", None) or _template(db, ws),
        actor=ws["author"], rows=rows, **kwargs)
    db.commit()
    bulk_send_service.run_batch(db, batch.id)
    db.expire_all()
    return db.get(models.BulkSendBatch, batch.id)


def _items(db, batch) -> list[models.BulkSendItem]:
    return sorted(
        db.query(models.BulkSendItem).filter(models.BulkSendItem.batch_id == batch.id).all(),
        key=lambda i: i.sequence)


def _envelopes(db, ws) -> int:
    """This tenant's envelopes only.

    A global count would be a test that passes alone and fails in a suite: the sweeps run
    cross-tenant on purpose, and the test database carries every other test's rows.
    """
    return db.query(models.SignatureEnvelope).filter(
        models.SignatureEnvelope.tenant_id == ws["tenant"].id).count()


# ---------------------------------------------------------------------------------------
# Validation — everything that must be caught before a single email leaves
# ---------------------------------------------------------------------------------------


def test_every_bad_row_is_reported_not_just_the_first(db, workspace):
    """The whole point of a pre-flight check. Reporting only the first bad row turns a
    five-hundred-row sheet into five hundred round trips."""
    t = _template(db, workspace)
    rows = _rows(2) + [
        {"name": "", "email": "nope", "values": {}},
        {"name": "No Code", "email": "b@example.test", "values": {"company": "X"}},
    ]
    problems = bulk_send_service.validate_rows(t, rows, {})

    assert [p["row"] for p in problems] == [3, 4]
    assert any("Name is required" in e for e in problems[0]["errors"])
    assert any("not a valid email" in e for e in problems[0]["errors"])
    assert any("Agent code is required" in e for e in problems[1]["errors"])


def test_a_duplicate_address_is_refused(db, workspace):
    """Two envelopes for the same agreement to the same person is a paste error every time,
    and it cannot be undone once sent — you cannot unsend the second."""
    t = _template(db, workspace)
    rows = _rows(1)
    rows.append({**rows[0], "name": "Same Person Again"})

    problems = bulk_send_service.validate_rows(t, rows, {})
    assert len(problems) == 1
    assert "Duplicate of row 1" in problems[0]["errors"][0]


def test_a_duplicate_is_caught_regardless_of_case(db, workspace):
    t = _template(db, workspace)
    rows = _rows(1)
    rows.append({**rows[0], "email": rows[0]["email"].upper()})

    assert bulk_send_service.validate_rows(t, rows, {})


def test_nothing_is_sent_when_any_row_is_bad(db, workspace):
    """A partial send is the unrecoverable outcome: the good rows are gone and the operator is
    left reconciling inboxes against a spreadsheet."""
    t = _template(db, workspace)
    rows = _rows(4)
    rows[2]["values"].pop("agent_code")

    with pytest.raises(BulkSendError) as e:
        bulk_send_service.create_batch(db, template=t, actor=workspace["author"], rows=rows)

    assert e.value.problems and e.value.problems[0]["row"] == 3
    assert db.query(models.BulkSendBatch).filter(
        models.BulkSendBatch.tenant_id == workspace["tenant"].id).count() == 0
    assert _envelopes(db, workspace) == 0


def test_an_unapproved_template_cannot_be_sent_in_bulk(db, workspace):
    """Bulk send dispatches without a human reading each draft, so the template's approval is
    the only review that happens. Skipping it would mean unreviewed wording at scale."""
    t = _template(db, workspace, approve=False)
    with pytest.raises(BulkSendError, match="not been approved"):
        bulk_send_service.create_batch(db, template=t, actor=workspace["author"],
                                       rows=_rows(1))


def test_an_oversized_batch_is_refused(db, workspace):
    t = _template(db, workspace)
    rows = [{"name": f"S{i}", "email": f"s{i}@example.test",
             "values": {"company": "C", "agent_code": "A"}}
            for i in range(bulk_send_service.MAX_ROWS + 1)]
    with pytest.raises(BulkSendError, match="limited to"):
        bulk_send_service.validate_rows(t, rows, {})


def test_an_empty_batch_is_refused(db, workspace):
    with pytest.raises(BulkSendError, match="at least one"):
        bulk_send_service.validate_rows(_template(db, workspace), [], {})


# ---------------------------------------------------------------------------------------
# Merge values — the silent failure mode
# ---------------------------------------------------------------------------------------


def test_a_row_gets_its_own_details_not_its_neighbours(db, workspace):
    """The failure this guards against renders perfectly: every document valid, every one
    carrying the wrong person's name. Nothing errors, so nothing catches it but this."""
    batch = _run(db, workspace, _rows(3))
    items = _items(db, batch)

    for item in items:
        contract = db.get(models.Contract, item.contract_id)
        assert item.name in contract.body
        assert item.values["company"] in contract.body
        for other in items:
            if other is not item:
                assert other.values["agent_code"] not in contract.body


def test_shared_values_never_overwrite_a_rows_identity(db, workspace):
    """A shared `name` would stamp one person's name onto all five hundred agreements, and
    every one of them would render without complaint."""
    merged = bulk_send_service._row_values(
        {"name": "Head Office", "company": "Default Ltd"},
        {"name": "Aisha Khan", "email": "aisha@example.test", "values": {}})

    assert merged["name"] == "Aisha Khan"
    assert merged["company"] == "Default Ltd"


def test_a_rows_own_values_beat_the_shared_ones(db, workspace):
    merged = bulk_send_service._row_values(
        {"company": "Default Ltd"},
        {"name": "A", "email": "a@example.test", "values": {"company": "Their Own Ltd"}})
    assert merged["company"] == "Their Own Ltd"


# ---------------------------------------------------------------------------------------
# Fan-out — one envelope each, never a shared one
# ---------------------------------------------------------------------------------------


def test_each_recipient_gets_their_own_contract_and_envelope(db, workspace):
    """One envelope with five hundred recipients would be one document all of them can see."""
    batch = _run(db, workspace, _rows(3))
    items = _items(db, batch)

    assert batch.status == "completed"
    assert batch.succeeded == 3 and batch.failed == 0
    assert len({i.contract_id for i in items}) == 3
    assert len({i.envelope_id for i in items}) == 3

    for item in items:
        rs = signing_service.recipients(db, item.envelope_id)
        assert len(rs) == 1, "a bulk envelope must never carry a second recipient"
        assert rs[0].email == item.email


def test_every_envelope_is_actually_sent_with_a_live_link(db, workspace):
    """A batch that creates draft envelopes and reports success would be indistinguishable from
    one that worked, right up until nobody signed anything."""
    batch = _run(db, workspace, _rows(2))

    for item in _items(db, batch):
        env = db.get(models.SignatureEnvelope, item.envelope_id)
        assert env.status == "sent"
        token = signing_service.decrypt_token_for(signing_service.recipients(db, env.id)[0])
        assert token and signing_service.recipient_by_token(db, token) is not None


def test_the_chase_schedule_lands_on_the_envelope(db, workspace):
    batch = _run(db, workspace, _rows(1), reminder_interval_days=3, max_reminders=2,
                 expiry_days=14)
    env = db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id)

    assert env.reminder_interval_days == 3
    assert env.max_reminders == 2
    assert env.expires_at is not None
    assert (env.expires_at - bulk_send_service._now()).days in (13, 14)


def test_zero_expiry_days_means_no_envelope_deadline(db, workspace):
    """Not every batch has a deadline, and defaulting one on would silently kill links the
    operator expected to stay open."""
    batch = _run(db, workspace, _rows(1), expiry_days=0)
    assert db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id).expires_at is None


# ---------------------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------------------


def test_one_failing_row_does_not_stop_the_others(db, workspace, monkeypatch):
    """The whole reason each row commits separately."""
    t = _template(db, workspace)
    rows = _rows(4)
    calls = {"n": 0}
    real = signing_service.send_envelope

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("the mail relay refused this one")
        return real(*args, **kwargs)

    monkeypatch.setattr(signing_service, "send_envelope", flaky)
    batch = _run(db, workspace, rows, template=t)
    items = _items(db, batch)

    assert batch.status == "completed_with_errors"
    assert batch.succeeded == 3 and batch.failed == 1
    assert items[1].status == "failed"
    assert "mail relay refused" in items[1].error
    assert [i.status for i in items] == ["sent", "failed", "sent", "sent"]


def test_a_failed_row_records_why_on_itself(db, workspace, monkeypatch):
    """The rollback that follows a failure discards everything the attempt wrote — including
    the record of the failure, if it were written before the rollback rather than after."""
    monkeypatch.setattr(signing_service, "send_envelope",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("storage is down")))
    batch = _run(db, workspace, _rows(2))

    assert batch.failed == 2
    for item in _items(db, batch):
        assert item.status == "failed"
        assert "storage is down" in item.error
        assert item.contract_id is None, "a row that did not send must not claim a contract"


def test_a_failed_row_leaves_no_half_made_contract(db, workspace, monkeypatch):
    """A contract created and then abandoned would sit in the repository as a real agreement
    nobody raised."""
    monkeypatch.setattr(signing_service, "send_envelope",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))
    before = db.query(models.Contract).filter(
        models.Contract.tenant_id == workspace["tenant"].id).count()
    _run(db, workspace, _rows(3))
    db.expire_all()

    assert db.query(models.Contract).filter(
        models.Contract.tenant_id == workspace["tenant"].id).count() == before


# ---------------------------------------------------------------------------------------
# Operator control
# ---------------------------------------------------------------------------------------


def test_cancelling_stops_the_rest_and_leaves_no_row_pending(db, workspace):
    """A row still marked `pending` on a finished batch reads as "still going" forever."""
    t = _template(db, workspace)
    batch = bulk_send_service.create_batch(db, template=t, actor=workspace["author"],
                                           rows=_rows(3))
    db.commit()
    bulk_send_service.cancel(db, batch, actor=workspace["author"])
    db.commit()
    bulk_send_service.run_batch(db, batch.id)
    db.expire_all()

    assert db.get(models.BulkSendBatch, batch.id).status == "cancelled"
    assert {i.status for i in _items(db, batch)} == {"cancelled"}
    assert _envelopes(db, workspace) == 0


def test_cancelling_a_finished_batch_is_refused(db, workspace):
    batch = _run(db, workspace, _rows(1))
    with pytest.raises(BulkSendError, match="already finished"):
        bulk_send_service.cancel(db, batch, actor=workspace["author"])


def test_retry_re_sends_only_the_failures(db, workspace, monkeypatch):
    """Re-sending a row that already went out means a second envelope to somebody who has
    one — the same unrecoverable mistake the duplicate check exists to prevent."""
    calls = {"n": 0}
    real = signing_service.send_envelope

    def once_flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real(*args, **kwargs)

    monkeypatch.setattr(signing_service, "send_envelope", once_flaky)
    batch = _run(db, workspace, _rows(3))
    assert batch.failed == 1

    bulk_send_service.retry_failed(db, batch, actor=workspace["author"])
    db.commit()
    bulk_send_service.run_batch(db, batch.id)
    db.expire_all()

    batch = db.get(models.BulkSendBatch, batch.id)
    assert batch.status == "completed"
    assert batch.succeeded == 3 and batch.failed == 0
    assert _envelopes(db, workspace) == 3, "no row was sent twice"


def test_retry_with_nothing_to_retry_is_refused(db, workspace):
    batch = _run(db, workspace, _rows(1))
    with pytest.raises(BulkSendError, match="no failed rows"):
        bulk_send_service.retry_failed(db, batch, actor=workspace["author"])


def test_rerunning_a_finished_batch_sends_nothing(db, workspace):
    """A duplicated task delivery, a retried worker — the second run must be a no-op."""
    batch = _run(db, workspace, _rows(2))
    out = bulk_send_service.run_batch(db, batch.id)
    db.expire_all()

    assert out == {"bulk_already_finished": 1}
    assert _envelopes(db, workspace) == 2


# ---------------------------------------------------------------------------------------
# Audit and isolation
# ---------------------------------------------------------------------------------------


def test_the_batch_is_audited(db, workspace):
    batch = _run(db, workspace, _rows(1))
    actions = {a.action for a in db.query(models.AuditLog).filter(
        models.AuditLog.object_id == batch.id).all()}
    assert "bulk_send.created" in actions


def test_a_batch_does_not_leak_across_tenants(db, make_user, workspace):
    other, other_tenant = make_user(email=f"other-{uuid.uuid4().hex[:8]}@example.com")
    batch = _run(db, workspace, _rows(1))

    visible = db.query(models.BulkSendBatch).filter(
        models.BulkSendBatch.tenant_id == other_tenant.id).all()
    assert batch.tenant_id != other_tenant.id
    assert visible == []


# ---------------------------------------------------------------------------------------
# Chasing and expiry — the unattended half
# ---------------------------------------------------------------------------------------


def test_an_envelope_past_its_deadline_expires_and_its_links_stop_working(db, workspace):
    """Marking it expired while the URL still resolves would make the deadline a label on a
    screen rather than a control."""
    batch = _run(db, workspace, _rows(1), expiry_days=14)
    env = db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id)
    token = signing_service.decrypt_token_for(signing_service.recipients(db, env.id)[0])
    assert signing_service.recipient_by_token(db, token) is not None

    signing_service.chase_and_expire(db, now=env.expires_at + dt.timedelta(minutes=1))
    db.flush()

    assert db.get(models.SignatureEnvelope, env.id).status == "expired"
    assert signing_service.recipient_by_token(db, token) is None


def test_an_envelope_with_no_deadline_is_never_expired(db, workspace):
    batch = _run(db, workspace, _rows(1), expiry_days=0)
    env_id = _items(db, batch)[0].envelope_id

    signing_service.chase_and_expire(db, now=bulk_send_service._now() + dt.timedelta(days=3650))
    assert db.get(models.SignatureEnvelope, env_id).status == "sent"


def test_a_reminder_is_sent_once_the_interval_has_passed(db, workspace):
    batch = _run(db, workspace, _rows(1), reminder_interval_days=3, max_reminders=2)
    env = db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id)

    signing_service.chase_and_expire(db, now=env.sent_at + dt.timedelta(days=2))
    db.flush()
    assert db.get(models.SignatureEnvelope, env.id).reminders_sent == 0

    signing_service.chase_and_expire(db, now=env.sent_at + dt.timedelta(days=3, minutes=1))
    db.flush()
    assert db.get(models.SignatureEnvelope, env.id).reminders_sent == 1


def test_reminders_stop_at_the_configured_maximum(db, workspace):
    """An unbounded chase is a mail-bomb with the bank's name on it."""
    batch = _run(db, workspace, _rows(1), reminder_interval_days=1, max_reminders=2)
    env = db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id)

    for day in range(1, 8):
        signing_service.chase_and_expire(db, now=env.sent_at + dt.timedelta(days=day,
                                                                           minutes=1))
        db.flush()

    assert db.get(models.SignatureEnvelope, env.id).reminders_sent == 2


def test_an_envelope_with_chasing_off_is_never_chased(db, workspace):
    batch = _run(db, workspace, _rows(1), reminder_interval_days=0, max_reminders=5)
    env = db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id)

    signing_service.chase_and_expire(db, now=env.sent_at + dt.timedelta(days=90))
    db.flush()
    assert db.get(models.SignatureEnvelope, env.id).reminders_sent == 0


def test_expiry_wins_over_a_reminder_due_in_the_same_sweep(db, workspace):
    """Chasing somebody towards a link that has just been revoked sends them to a dead page."""
    batch = _run(db, workspace, _rows(1), reminder_interval_days=1, max_reminders=5,
                 expiry_days=2)
    env = db.get(models.SignatureEnvelope, _items(db, batch)[0].envelope_id)

    signing_service.chase_and_expire(db, now=env.expires_at + dt.timedelta(hours=1))
    db.flush()

    fresh = db.get(models.SignatureEnvelope, env.id)
    assert fresh.status == "expired"
    assert fresh.reminders_sent == 0, "chased towards a link the same sweep had revoked"
