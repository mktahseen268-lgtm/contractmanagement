"""The renewal sweep and webhook dispatch (Phase 10 — coverage on two beat-driven services).

Both run unattended, which is what makes them worth testing hard: nobody is watching when they
misbehave. The two failure modes that matter are **a reminder that never fires** and **a
reminder that fires every time the beat runs** — the first is silent, the second trains people
to ignore the channel.

Requirements: SOW-26, SOW-27, INT-10.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest import mock

import pytest

from app import models, renewal_service
from app import webhook_service as wh


@pytest.fixture()
def workspace(db, make_user):
    user, tenant = make_user()
    return db, db.merge(user), tenant


def _contract(db, user, tenant, **kw):
    row = models.Contract(
        tenant_id=tenant.id, reference_no=kw.pop("reference_no", "C-1"),
        title=kw.pop("title", "Vendor agreement"), owner_id=user.id, created_by=user.id,
        status=kw.pop("status", "active"), **kw)
    db.add(row)
    db.flush()
    return row


def _notifications(db, tenant, contract=None):
    q = db.query(models.Notification).filter(models.Notification.tenant_id == tenant.id)
    if contract is not None:
        q = q.filter(models.Notification.object_id == contract.id)
    return q.all()


# ---------------------------------------------------------------------------------------
# The sweep — state transitions
# ---------------------------------------------------------------------------------------


def test_a_contract_inside_the_window_is_flagged_expiring(workspace):
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, end_date=today + dt.timedelta(days=20))

    counts = renewal_service.sweep(db, today=today)
    db.flush()

    assert contract.status == "expiring"
    # `>=`, not `==`: the sweep deliberately runs across every tenant, so the totals include
    # whatever other tests left behind. Asserting an exact global count would make this pass or
    # fail depending on which tests ran first, which is worse than not asserting it at all.
    assert counts["flagged_expiring"] >= 1
    assert counts["reminders_sent"] >= 1
    assert [n.type for n in _notifications(db, tenant, contract)] == ["contract.expiring"]


def test_a_contract_beyond_the_window_is_left_alone(workspace):
    """The window exists so the warning arrives when something can still be done about it. A
    reminder eighteen months out is noise that teaches people to filter the channel."""
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, end_date=today + dt.timedelta(days=400))

    renewal_service.sweep(db, today=today)
    assert contract.status == "active"


def test_a_contract_past_its_end_date_expires(workspace):
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, end_date=today - dt.timedelta(days=1))

    counts = renewal_service.sweep(db, today=today)
    db.flush()

    assert contract.status == "expired"
    assert counts["moved_to_expired"] >= 1          # cross-tenant sweep — see the note above
    assert [n.type for n in _notifications(db, tenant, contract)] == ["contract.expired"]


def test_a_contract_already_expiring_still_expires(workspace):
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, status="expiring",
                         end_date=today - dt.timedelta(days=3))

    renewal_service.sweep(db, today=today)
    assert contract.status == "expired"


def test_a_contract_with_no_end_date_is_untouched(workspace):
    """Nothing can be computed from a missing date. Guessing one would schedule a reminder for
    a deadline nobody agreed to."""
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, end_date=None)

    renewal_service.sweep(db, today=dt.date(2026, 6, 1))
    assert contract.status == "active"
    assert _notifications(db, tenant, contract) == []


def test_a_draft_is_not_swept(workspace):
    """The sweep is about agreements in force. A draft with a date in the past is somebody's
    unfinished work, not an expired obligation."""
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, status="draft",
                         end_date=dt.date(2020, 1, 1))

    renewal_service.sweep(db, today=dt.date(2026, 6, 1))
    assert contract.status == "draft"


# ---------------------------------------------------------------------------------------
# The sweep — reminder idempotency
# ---------------------------------------------------------------------------------------


def test_the_expired_notice_fires_once_not_on_every_beat(workspace):
    """The sweep runs hourly. Re-notifying each time would put twenty-four identical messages
    in somebody's inbox by tomorrow, and they would stop reading the twenty-fifth."""
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, end_date=today - dt.timedelta(days=1))

    renewal_service.sweep(db, today=today)
    db.flush()
    contract.status = "active"                     # as if it were re-activated and re-expired
    db.flush()
    renewal_service.sweep(db, today=today)
    db.flush()

    expired_notices = [n for n in _notifications(db, tenant, contract)
                       if n.type == "contract.expired"]
    assert len(expired_notices) == 1


def test_the_follow_up_reminders_fire_at_their_thresholds(workspace):
    db, user, tenant = workspace
    end = dt.date(2026, 6, 30)
    contract = _contract(db, user, tenant, status="expiring", end_date=end)

    for days in renewal_service.REMINDER_DAYS:
        renewal_service.sweep(db, today=end - dt.timedelta(days=days))
        db.flush()

    markers = {f"expiring-{d}d" for d in renewal_service.REMINDER_DAYS}
    bodies = " ".join(n.body or "" for n in _notifications(db, tenant, contract))
    for marker in markers:
        assert marker in bodies


def test_the_same_threshold_does_not_re_fire(workspace):
    db, user, tenant = workspace
    end = dt.date(2026, 6, 30)
    contract = _contract(db, user, tenant, status="expiring", end_date=end)
    day = end - dt.timedelta(days=renewal_service.REMINDER_DAYS[0])

    renewal_service.sweep(db, today=day)
    db.flush()
    before = len(_notifications(db, tenant, contract))
    renewal_service.sweep(db, today=day)
    db.flush()

    assert len(_notifications(db, tenant, contract)) == before


def test_a_reminder_is_skipped_when_there_is_nobody_to_tell(workspace):
    """`owner_id` is NOT NULL on a contract, so this cannot arise through the ORM — but the
    guard is what stops a notification row being written against a null user if it ever does,
    and a notification nobody can open is worse than none."""
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, end_date=dt.date(2026, 6, 1))
    contract.owner_id = None

    assert renewal_service._notify(db, contract, kind="contract.expired",
                                   title="x", body="y") is False
    assert renewal_service._already_notified(db, contract, "contract.expired", "expired") is False


# ---------------------------------------------------------------------------------------
# The sweep — obligations
# ---------------------------------------------------------------------------------------


def test_a_pending_obligation_past_its_date_becomes_overdue(workspace):
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, end_date=today + dt.timedelta(days=200))
    obligation = models.Obligation(
        tenant_id=tenant.id, contract_id=contract.id, title="Quarterly report",
        owner_id=user.id, created_by=user.id, status="pending",
        due_date=today - dt.timedelta(days=2))
    db.add(obligation)
    db.flush()

    counts = renewal_service.sweep(db, today=today)
    assert obligation.status == "overdue"
    assert counts["obligations_overdue"] >= 1


def test_a_completed_obligation_is_not_reopened(workspace):
    """Marking a done obligation overdue because its date has passed would be actively wrong —
    the commitment was met."""
    db, user, tenant = workspace
    today = dt.date(2026, 6, 1)
    contract = _contract(db, user, tenant, end_date=today + dt.timedelta(days=200))
    obligation = models.Obligation(
        tenant_id=tenant.id, contract_id=contract.id, title="Filed already",
        owner_id=user.id, created_by=user.id, status="done",
        due_date=today - dt.timedelta(days=30))
    db.add(obligation)
    db.flush()

    renewal_service.sweep(db, today=today)
    assert obligation.status == "done"


# ---------------------------------------------------------------------------------------
# Renewal
# ---------------------------------------------------------------------------------------


def test_renewing_creates_a_draft_successor_and_closes_the_original(workspace):
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, status="active", value=250000, currency="PKR",
                         effective_date=dt.date(2025, 1, 1), end_date=dt.date(2025, 12, 31),
                         body="Original text", counterparty="Acme Ltd")

    successor = renewal_service.renew(db, contract=contract, by_user=user)
    db.flush()

    assert contract.status == "renewed"
    assert successor.status == "draft"
    assert successor.renewed_from_id == contract.id
    assert successor.value == 250000
    assert successor.counterparty == "Acme Ltd"
    assert successor.body == "Original text"
    assert successor.source == "renewal"


def test_the_successor_starts_the_day_after_the_original_ends(workspace):
    """A one-day gap would leave the counterparty unbound for a day, which is exactly the thing
    a renewal exists to avoid."""
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, effective_date=dt.date(2025, 1, 1),
                         end_date=dt.date(2025, 12, 31))

    successor = renewal_service.renew(db, contract=contract, by_user=user)
    assert successor.effective_date == dt.date(2026, 1, 1)


def test_the_successor_inherits_the_original_term_length(workspace):
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, effective_date=dt.date(2025, 1, 1),
                         end_date=dt.date(2025, 6, 30))          # 180 days

    successor = renewal_service.renew(db, contract=contract, by_user=user)
    assert (successor.end_date - successor.effective_date).days == 180


def test_a_contract_with_no_dates_renews_for_twelve_months(workspace):
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, effective_date=None, end_date=None)

    successor = renewal_service.renew(db, contract=contract, by_user=user)
    assert successor.effective_date == dt.date.today()
    assert successor.end_date.year == dt.date.today().year + 1


def test_explicit_dates_win_over_the_defaults(workspace):
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, effective_date=dt.date(2025, 1, 1),
                         end_date=dt.date(2025, 12, 31))

    successor = renewal_service.renew(
        db, contract=contract, by_user=user,
        effective_date=dt.date(2026, 3, 1), end_date=dt.date(2027, 2, 28))

    assert successor.effective_date == dt.date(2026, 3, 1)
    assert successor.end_date == dt.date(2027, 2, 28)


def test_a_draft_cannot_be_renewed(workspace):
    """Renewal is a transition out of a live agreement. Renewing a draft would produce a
    successor to something that never took effect."""
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, status="draft")

    with pytest.raises(ValueError, match="can't be renewed"):
        renewal_service.renew(db, contract=contract, by_user=user)


def test_the_successor_gets_its_own_reference_and_first_version(workspace):
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, body="Version one")

    successor = renewal_service.renew(db, contract=contract, by_user=user)
    db.flush()

    assert successor.reference_no != contract.reference_no
    versions = db.query(models.ContractVersion).filter(
        models.ContractVersion.contract_id == successor.id).all()
    assert len(versions) == 1
    assert versions[0].version_no == 1
    assert versions[0].body == "Version one"


def test_the_chain_links_both_ways(workspace):
    db, user, tenant = workspace
    contract = _contract(db, user, tenant)
    successor = renewal_service.renew(db, contract=contract, by_user=user)
    db.flush()

    pred, succ = renewal_service.chain_links(db, successor)
    assert pred.id == contract.id
    assert succ is None                                    # nothing after the successor yet

    pred, succ = renewal_service.chain_links(db, contract)
    assert pred is None
    assert succ.id == successor.id


def test_a_leap_day_renewal_lands_on_a_real_date(workspace):
    """29 February plus a year is not a date. Left unhandled this raises, on one day in four
    years, inside a background sweep — the worst possible place to find it."""
    db, user, tenant = workspace
    contract = _contract(db, user, tenant, effective_date=None, end_date=None)

    successor = renewal_service.renew(
        db, contract=contract, by_user=user, effective_date=dt.date(2028, 2, 29))
    assert successor.end_date == dt.date(2029, 3, 1)


# ---------------------------------------------------------------------------------------
# Webhooks — signing
# ---------------------------------------------------------------------------------------


def test_the_signature_binds_the_timestamp_to_the_body(workspace):
    """`t=<unix>,v1=<hex>` over `timestamp.payload`. Signing the body alone would let an
    attacker replay a valid old delivery forever."""
    payload = b'{"event":"contract.signed"}'
    sig_a = wh.sign("shh", payload, timestamp=1_700_000_000)
    sig_b = wh.sign("shh", payload, timestamp=1_700_000_001)

    assert sig_a.startswith("t=1700000000,v1=")
    assert sig_a != sig_b


def test_a_different_secret_produces_a_different_signature(workspace):
    payload = b"{}"
    assert wh.sign("one", payload, timestamp=1) != wh.sign("two", payload, timestamp=1)


def test_the_signature_is_verifiable_by_a_receiver(workspace):
    """Reproduced the way a subscriber's own code would, so the header is provably usable and
    not just self-consistent."""
    import hashlib
    import hmac

    secret, payload, ts = "topsecret", b'{"a":1}', 1_700_000_000
    header = wh.sign(secret, payload, timestamp=ts)
    _t, v1 = header.split(",")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()

    assert v1 == f"v1={expected}"


def test_a_new_secret_is_long_enough_to_be_a_secret(workspace):
    a, b = wh.new_secret(), wh.new_secret()
    assert len(a) >= 32
    assert a != b


# ---------------------------------------------------------------------------------------
# Webhooks — subscription matching
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("events, event, expected", [
    ([], "contract.signed", True),                       # no filter means everything
    (["*"], "contract.signed", True),
    (["contract.signed"], "contract.signed", True),
    (["contract.*"], "contract.signed", True),
    (["contract.*"], "user.created", False),
    (["contract.signed"], "contract.voided", False),
    (["user.*", "contract.*"], "contract.voided", True),
])
def test_subscription_matching(events, event, expected):
    assert wh._matches(events, event) is expected


# ---------------------------------------------------------------------------------------
# Webhooks — dispatch
# ---------------------------------------------------------------------------------------


def _endpoint(db, tenant, url="https://hooks.example.invalid/cm", events=None, active=True,
              created_by="system"):
    row = models.WebhookEndpoint(
        tenant_id=tenant.id, url=url, secret=wh.new_secret(), created_by=created_by,
        events=events if events is not None else ["*"], is_active=active)
    db.add(row)
    db.flush()
    return row


class _Resp:
    def __init__(self, status=200, body=b"ok"):
        self.status = status
        self._body = body

    def read(self, n=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_successful_delivery_is_recorded(workspace):
    db, user, tenant = workspace
    endpoint = _endpoint(db, tenant)

    with mock.patch("urllib.request.urlopen", return_value=_Resp(200, b"thanks")):
        sent = wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={"id": "c1"})
    db.flush()

    assert sent == 1
    delivery = db.query(models.WebhookDelivery).filter(
        models.WebhookDelivery.endpoint_id == endpoint.id).one()
    assert delivery.status == "ok"
    assert delivery.response_code == 200
    assert delivery.attempts == 1
    assert endpoint.last_status == "ok"


def test_a_non_2xx_response_is_a_failure(workspace):
    """A 500 from the subscriber is not a delivery. Recording it as one would make the retry
    logic never fire for the case it exists for."""
    db, user, tenant = workspace
    endpoint = _endpoint(db, tenant)

    with mock.patch("urllib.request.urlopen", return_value=_Resp(500, b"boom")):
        wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={})
    db.flush()

    delivery = db.query(models.WebhookDelivery).filter(
        models.WebhookDelivery.endpoint_id == endpoint.id).one()
    assert delivery.status == "failed"
    assert delivery.response_code == 500


def test_an_unreachable_endpoint_does_not_take_down_the_caller(workspace):
    """Dispatch happens inside a request that has already done its real work. A subscriber's
    outage must not roll back somebody's signature."""
    db, user, tenant = workspace
    endpoint = _endpoint(db, tenant)

    with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        sent = wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={})
    db.flush()

    assert sent == 1
    delivery = db.query(models.WebhookDelivery).filter(
        models.WebhookDelivery.endpoint_id == endpoint.id).one()
    assert delivery.status == "failed"
    assert "connection refused" in delivery.response_snippet
    assert endpoint.last_status == "failed"


def test_an_inactive_endpoint_receives_nothing(workspace):
    db, user, tenant = workspace
    _endpoint(db, tenant, active=False)

    with mock.patch("urllib.request.urlopen", return_value=_Resp()) as sender:
        assert wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={}) == 0
    assert sender.call_count == 0


def test_an_endpoint_that_did_not_subscribe_receives_nothing(workspace):
    db, user, tenant = workspace
    _endpoint(db, tenant, events=["user.*"])

    with mock.patch("urllib.request.urlopen", return_value=_Resp()) as sender:
        assert wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={}) == 0
    assert sender.call_count == 0


def test_another_tenants_endpoint_is_never_called(workspace, make_user):
    """The one that would be a breach rather than a bug: a webhook is an outbound channel to a
    third party, so a cross-tenant dispatch posts one bank's contract data to another's URL."""
    db, user, tenant = workspace
    db.commit()
    other_user, other_tenant = make_user()
    _endpoint(db, other_tenant, url="https://someone-else.example.invalid/hook")

    with mock.patch("urllib.request.urlopen", return_value=_Resp()) as sender:
        assert wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={}) == 0
    assert sender.call_count == 0


def test_the_delivery_carries_the_signature_and_event_headers(workspace):
    db, user, tenant = workspace
    endpoint = _endpoint(db, tenant)
    captured = {}

    def _capture(req, timeout=None):
        captured["headers"] = dict(req.headers)
        captured["body"] = req.data
        return _Resp()

    with mock.patch("urllib.request.urlopen", side_effect=_capture):
        wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={"id": "c1"})

    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["x-cm-event"] == "contract.signed"
    assert headers["x-cm-signature"].startswith("t=")
    assert headers["x-cm-delivery-id"]
    assert json.loads(captured["body"])["data"] == {"id": "c1"}
    assert json.loads(captured["body"])["tenant_id"] == tenant.id
    assert endpoint.secret not in captured["body"].decode()      # never in the payload


def test_dispatch_with_no_endpoints_is_a_cheap_no_op(workspace):
    db, user, tenant = workspace
    with mock.patch("urllib.request.urlopen") as sender:
        assert wh.dispatch(db, tenant_id=tenant.id, event="contract.signed", data={}) == 0
    assert sender.call_count == 0
