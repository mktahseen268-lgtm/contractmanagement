"""SIEM feed and sanctions screening.

**SIEM.** The feed is a projection of the audit log, not a second log, so the tests check that
an audit row becomes a well-formed CEF event with the right category and severity — and that a
collector outage is survivable rather than fatal. A monitoring outage must never become a
service outage.

**Sanctions.** The interesting property is not "does it match identical strings" but "does it
match the transliterations that actually occur" — Mohammed/Muhammad/Mohamad are one person —
"without burying the analyst in noise". Both directions are tested. A hit never auto-rejects;
it raises a review that a person decides, with a note, and that decision is audited.

Requirements: SEC-13, INT-06, INT-09.
"""

from __future__ import annotations

import datetime as dt
import re
import socket
import threading
import uuid

import pytest

from app import audit, models, repository_service, sanctions, siem
from app.sanctions import SanctionsError


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"int-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    return {"tenant": tenant, "owner": owner}


@pytest.fixture(autouse=True)
def clean_lists(db):
    """Sanctions entries are global, not tenant-scoped, so tests must not leak into each
    other the way tenant-scoped rows do not.

    Committed rather than flushed: on SQLite a held-open write transaction blocks the separate
    session `make_user` opens, and the whole file deadlocks on the writer lock.
    """
    db.query(models.SanctionsEntry).delete()
    db.commit()
    yield
    db.query(models.SanctionsEntry).delete()
    db.commit()


def _entry(db, name, *, source="OFAC", aliases=(), day=None, **kwargs):
    row = models.SanctionsEntry(
        source=source, list_name=f"{source} SDN", name=name,
        name_key=sanctions.search_key(name, aliases), aliases=list(aliases),
        snapshot_date=day or dt.date.today(), is_active=True, **kwargs)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------------------
# SIEM: classification
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("action,category", [
    ("auth.login", "authentication"),
    ("auth.login.failed", "security_incident"),
    ("auth.lockout", "security_incident"),
    ("user.role_changed", "access_control"),
    ("api_key.created", "access_control"),
    ("webhook.delivered", "network"),
    ("export.generated", "audit_trail"),
    ("pki.certificate_issued", "system_activity"),
    ("contract.created", "application_usage"),
])
def test_actions_land_in_the_right_siem_category(action, category):
    """The InfoSec table enumerates these categories; an event in the wrong one is an event
    the collector's rules will not fire on."""
    assert siem.classify(action)[0] == category


def test_a_failed_login_outranks_a_successful_one():
    assert siem.classify("auth.login.failed")[1] < siem.classify("auth.login")[1]


def test_a_broken_audit_chain_is_critical():
    """The one event that means somebody is tampering with the record itself."""
    assert siem.classify("audit.chain_broken")[1] == siem.CRITICAL


def test_an_unknown_action_is_still_reported():
    """An event nobody classified is still an event — dropping it loses exactly the novel
    activity worth seeing."""
    category, severity = siem.classify("something.entirely.new")
    assert category == "application_usage"
    assert severity == siem.INFORMATIONAL


# ---------------------------------------------------------------------------------------
# SIEM: formatting
# ---------------------------------------------------------------------------------------


def _audit_row(db, ws, action="auth.login.failed", **kwargs):
    entry = audit.record(db, tenant_id=ws["tenant"].id, action=action, actor=ws["owner"],
                         object_type="user", object_id=ws["owner"].id,
                         object_label=kwargs.pop("label", "ayesha@mmbl.test"),
                         ip=kwargs.pop("ip", "10.1.2.3"), meta=kwargs.pop("meta", {}))
    db.flush()
    return entry


def test_cef_has_the_required_header_fields(db, workspace):
    line = siem.to_cef(_audit_row(db, workspace))
    header = line.split("|")
    assert header[0] == "CEF:0"
    assert header[1] == "Thiqa"
    assert header[2] == "ContractManagement"
    assert header[4] == "auth.login.failed"


def test_cef_severity_runs_the_opposite_way_to_syslog(db, workspace):
    """CEF is 0..10 with 10 most severe; syslog is 0..7 with 0 most severe. Mapping them the
    wrong way round produces a dashboard where every critical event looks routine."""
    critical = siem.to_cef(_audit_row(db, workspace, action="audit.chain_broken"))
    routine = siem.to_cef(_audit_row(db, workspace, action="contract.created"))
    assert int(critical.split("|")[6]) > int(routine.split("|")[6])


def test_cef_carries_the_actor_ip_and_chain_position(db, workspace):
    line = siem.to_cef(_audit_row(db, workspace))
    assert "src=10.1.2.3" in line
    assert "suser=Owner" in line
    assert "cn1Label=auditSeq" in line


def test_cef_escapes_a_pipe_in_the_header(db, workspace):
    """An unescaped pipe would split the header and the collector would drop the event."""
    entry = _audit_row(db, workspace, action="contract.created")
    entry.action = "weird|action"
    assert "weird\\|action" in siem.to_cef(entry)


def test_cef_escapes_an_equals_sign_in_the_extension(db, workspace):
    entry = _audit_row(db, workspace, label="Agreement = the thing")
    assert "\\=" in siem.to_cef(entry)


def test_clf_is_a_parseable_web_log_line(db, workspace):
    line = siem.to_clf(_audit_row(db, workspace))
    assert re.match(r'^10\.1\.2\.3 - \S+ \[\d{2}/\w{3}/\d{4}:', line)
    assert '"auth.login.failed /user/' in line


def test_the_syslog_frame_is_octet_counted(db, workspace):
    """Newline-delimited framing would tear one event into several when the body contains a
    newline — which is how an incident becomes unreadable at the worst moment."""
    frame = siem.syslog_frame("hello world", siem.WARNING, hostname="cm-1")
    count, payload = frame.split(b" ", 1)
    assert int(count) == len(payload)
    assert payload.startswith(b"<") and b"cm-1" in payload


def test_the_syslog_priority_encodes_the_severity():
    frame = siem.syslog_frame("x", siem.CRITICAL, facility=13, hostname="h")
    priority = int(frame.split(b"<")[1].split(b">")[0])
    assert priority == 13 * 8 + siem.CRITICAL


# ---------------------------------------------------------------------------------------
# SIEM: delivery
# ---------------------------------------------------------------------------------------


def test_the_feed_is_off_until_configured():
    assert siem.is_enabled() is False


def test_emitting_while_disabled_is_a_no_op(db, workspace):
    assert siem.emit(_audit_row(db, workspace)) is False


def test_events_reach_a_listening_collector(db, workspace, monkeypatch):
    """End to end over a real socket — a mocked sender would not prove the framing works."""
    from app.config import settings

    received: list[bytes] = []
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _accept():
        conn, _ = server.accept()
        received.append(conn.recv(65535))
        conn.close()

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()

    monkeypatch.setattr(settings, "siem_enabled", True)
    monkeypatch.setattr(settings, "siem_host", "127.0.0.1")
    monkeypatch.setattr(settings, "siem_port", port)
    monkeypatch.setattr(settings, "siem_tls", False)
    siem.reset_sender()

    assert siem.emit(_audit_row(db, workspace)) is True
    thread.join(timeout=3)
    siem.reset_sender()
    server.close()

    assert received, "the collector received nothing"
    assert b"CEF:0|Thiqa|ContractManagement" in received[0]


def test_an_unreachable_collector_does_not_raise(db, workspace, monkeypatch):
    """A monitoring outage must never become a service outage."""
    from app.config import settings

    monkeypatch.setattr(settings, "siem_enabled", True)
    monkeypatch.setattr(settings, "siem_host", "127.0.0.1")
    monkeypatch.setattr(settings, "siem_port", 1)          # nothing listens here
    monkeypatch.setattr(settings, "siem_tls", False)
    monkeypatch.setattr(settings, "siem_timeout", 1)
    siem.reset_sender()

    # The audit row itself now emits, so the count is not exactly one. What matters is that
    # nothing raised and the failure was counted rather than swallowed silently.
    assert siem.emit(_audit_row(db, workspace)) is False
    assert siem.get_sender().failures >= 1
    siem.reset_sender()


def test_a_batch_reports_what_got_through(db, workspace, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "siem_enabled", True)
    monkeypatch.setattr(settings, "siem_host", "127.0.0.1")
    monkeypatch.setattr(settings, "siem_port", 1)
    monkeypatch.setattr(settings, "siem_tls", False)
    monkeypatch.setattr(settings, "siem_timeout", 1)
    siem.reset_sender()

    result = siem.emit_many([_audit_row(db, workspace) for _ in range(3)])
    assert result == {"sent": 0, "failed": 3}
    siem.reset_sender()


# ---------------------------------------------------------------------------------------
# Sanctions: name matching
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("Mohammed Al Fulan", "Muhammad Al Fulan"),
    ("Ünal Bayraktar", "Unal Bayraktar"),
    ("ACME TRADING LIMITED", "Acme Trading Ltd"),
    ("Hassan, Ali", "Ali Hassan"),
])
def test_transliterations_and_reorderings_still_match(a, b):
    """Exact matching finds almost nothing on a real sanctions list."""
    assert sanctions.score(a, b) >= sanctions.MATCH_THRESHOLD


@pytest.mark.parametrize("a,b", [
    ("Ali Hassan", "Omar Sheikh"),
    ("Acme Trading", "Zenith Logistics"),
    ("Muhammad Ali", "Muhammad Yusuf Khan Abbasi"),
])
def test_different_people_do_not_match(a, b):
    """Matching too loosely buries the analyst until they stop reading."""
    assert sanctions.score(a, b) < sanctions.MATCH_THRESHOLD


def test_a_single_shared_common_name_is_not_a_match():
    """"Muhammad" appears in a large fraction of the list; on its own it means nothing."""
    assert sanctions.score("Muhammad Iqbal", "Muhammad Yusuf") < sanctions.MATCH_THRESHOLD


def test_a_shorter_name_inside_a_longer_one_matches():
    assert sanctions.score("Ali Hassan", "Ali Hassan Al Mansouri") >= sanctions.MATCH_THRESHOLD


def test_normalisation_drops_entity_noise():
    assert sanctions.normalise("The Acme Trading Company Limited") == "acme"


# ---------------------------------------------------------------------------------------
# Sanctions: screening
# ---------------------------------------------------------------------------------------


def test_a_clean_screen_is_still_recorded(db, workspace):
    """"We checked and found nothing" is the fact an auditor asks for, and it cannot be
    reconstructed from an absence of records."""
    _entry(db, "Someone Entirely Different")
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Acme Trading"},
                                            actor=workspace["owner"])
    screening = sanctions.screen_party(db, party, actor=workspace["owner"])
    assert screening.status == "clear"
    assert screening.hit_count == 0


def test_a_match_raises_a_review_rather_than_rejecting(db, workspace):
    """Automatic rejection on a fuzzy name match strands legitimate counterparties with no
    recourse and no record of why."""
    _entry(db, "Zenith Logistics FZE", programme="SDGT", country="AE")
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Zenith Logistics"},
                                            actor=workspace["owner"])
    screening = sanctions.screen_party(db, party, actor=workspace["owner"])

    assert screening.status == "review"
    assert screening.hits[0]["source"] == "OFAC"
    assert screening.hits[0]["programme"] == "SDGT"
    assert party.is_active is True, "a hit must not deactivate the party on its own"


def test_an_alias_match_says_it_matched_on_an_alias(db, workspace):
    """A reviewer needs to see why without re-deriving it."""
    _entry(db, "Formal Registered Name", aliases=["Zenith Logistics"])
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Zenith Logistics"},
                                            actor=workspace["owner"])
    screening = sanctions.screen_party(db, party, actor=workspace["owner"])
    assert "alias" in screening.hits[0]["matched_on"]


def test_a_strong_match_is_labelled_probable(db, workspace):
    _entry(db, "Zenith Logistics")
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Zenith Logistics"},
                                            actor=workspace["owner"])
    screening = sanctions.screen_party(db, party, actor=workspace["owner"])
    assert screening.hits[0]["confidence"] == "probable"


def test_the_screening_records_which_snapshot_it_used(db, workspace):
    """A screen is only as current as the list behind it."""
    _entry(db, "Zenith Logistics", day=dt.date(2026, 1, 15))
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Zenith Logistics"},
                                            actor=workspace["owner"])
    screening = sanctions.screen_party(db, party, actor=workspace["owner"])
    assert screening.list_snapshot_date == dt.date(2026, 1, 15)


def test_a_hit_is_audited_distinctly_from_a_clear_screen(db, workspace):
    _entry(db, "Zenith Logistics")
    party = repository_service.create_party(db, workspace["tenant"].id,
                                            {"name": "Zenith Logistics"},
                                            actor=workspace["owner"])
    sanctions.screen_party(db, party, actor=workspace["owner"])
    db.flush()
    actions = {e.action for e in db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id).all()}
    assert "party.sanctions_hit" in actions


# ---------------------------------------------------------------------------------------
# Sanctions: decisions
# ---------------------------------------------------------------------------------------


def _hit_screening(db, ws):
    _entry(db, "Zenith Logistics")
    party = repository_service.create_party(db, ws["tenant"].id, {"name": "Zenith Logistics"},
                                            actor=ws["owner"])
    return sanctions.screen_party(db, party, actor=ws["owner"]), party


def test_clearing_a_hit_requires_a_note(db, workspace):
    """"Cleared" with no reason is indistinguishable from somebody clicking through it."""
    screening, _party = _hit_screening(db, workspace)
    with pytest.raises(SanctionsError, match="needs a note"):
        sanctions.decide(db, screening, actor=workspace["owner"], cleared=True, note="  ")


def test_clearing_leaves_the_party_usable(db, workspace):
    screening, party = _hit_screening(db, workspace)
    sanctions.decide(db, screening, actor=workspace["owner"], cleared=True,
                     note="Different entity — registration number does not match.")
    assert screening.status == "cleared"
    assert party.is_active is True


def test_confirming_a_match_stops_the_party_being_used(db, workspace):
    """A confirmed match is not a note on a file."""
    screening, party = _hit_screening(db, workspace)
    sanctions.decide(db, screening, actor=workspace["owner"], cleared=False,
                     note="Confirmed against OFAC SDN entry.")
    assert screening.status == "confirmed"
    assert party.is_active is False
    assert party.kyc_status == "rejected"


def test_a_screening_cannot_be_decided_twice(db, workspace):
    screening, _party = _hit_screening(db, workspace)
    sanctions.decide(db, screening, actor=workspace["owner"], cleared=True, note="Cleared.")
    with pytest.raises(SanctionsError, match="already been decided"):
        sanctions.decide(db, screening, actor=workspace["owner"], cleared=False, note="No.")


def test_the_queue_is_oldest_first(db, workspace):
    """The longest-waiting hit is the one holding somebody's onboarding up."""
    for name in ("Zenith Logistics", "Zenith Holdings"):
        _entry(db, name)
    for name in ("Zenith Logistics", "Zenith Holdings"):
        party = repository_service.create_party(db, workspace["tenant"].id, {"name": name},
                                                actor=workspace["owner"])
        sanctions.screen_party(db, party, actor=workspace["owner"])
    db.flush()

    rows = sanctions.queue(db, workspace["tenant"].id)
    assert len(rows) == 2
    assert rows[0].created_at <= rows[1].created_at


# ---------------------------------------------------------------------------------------
# Sanctions: list snapshots
# ---------------------------------------------------------------------------------------


def test_importing_replaces_the_previous_snapshot(db, workspace):
    """Merging would silently keep delisted people on the list forever."""
    sanctions.import_entries(db, "OFAC", [{"name": "Delisted Person"}],
                             snapshot_date=dt.date(2026, 1, 1))
    result = sanctions.import_entries(db, "OFAC", [{"name": "Still Listed"}],
                                      snapshot_date=dt.date(2026, 6, 1))

    assert result["superseded"] == 1
    active = db.query(models.SanctionsEntry).filter_by(is_active=True).all()
    assert [e.name for e in active] == ["Still Listed"]


def test_a_superseded_entry_is_kept_not_deleted(db, workspace):
    """A past screening result has to remain explainable against the list that produced it."""
    sanctions.import_entries(db, "OFAC", [{"name": "Delisted Person"}])
    sanctions.import_entries(db, "OFAC", [{"name": "Still Listed"}])
    assert db.query(models.SanctionsEntry).filter_by(is_active=False).count() == 1


def test_importing_one_source_leaves_the_others_alone(db, workspace):
    sanctions.import_entries(db, "OFAC", [{"name": "A"}])
    sanctions.import_entries(db, "UN", [{"name": "B"}])
    active = {e.source for e in db.query(models.SanctionsEntry).filter_by(is_active=True).all()}
    assert active == {"OFAC", "UN"}


def test_an_unknown_source_is_refused(db, workspace):
    with pytest.raises(SanctionsError, match="Unknown sanctions source"):
        sanctions.import_entries(db, "MADE_UP", [{"name": "A"}])


def test_status_reports_the_oldest_list_not_the_newest(db, workspace):
    """The screen is only as good as its stalest list; reporting the freshest overstates it."""
    sanctions.import_entries(db, "OFAC", [{"name": "A"}], snapshot_date=dt.date(2026, 6, 1))
    sanctions.import_entries(db, "UN", [{"name": "B"}], snapshot_date=dt.date(2025, 1, 1))
    status = sanctions.snapshot_status(db, today=dt.date(2026, 6, 2))
    assert status["oldest"] == dt.date(2025, 1, 1)
    assert status["any_stale"] is True


def test_a_fresh_list_is_not_stale(db, workspace):
    sanctions.import_entries(db, "OFAC", [{"name": "A"}], snapshot_date=dt.date(2026, 6, 1))
    status = sanctions.snapshot_status(db, today=dt.date(2026, 6, 2))
    assert status["any_stale"] is False
    assert status["sources"][0]["age_days"] == 1


def test_status_says_when_nothing_is_loaded(db, workspace):
    """Screening against an empty list would otherwise look like a clean result."""
    assert sanctions.snapshot_status(db)["loaded"] is False


def test_every_audited_action_reaches_the_siem(db, workspace, monkeypatch):
    """The feed exists to carry events; wiring it and never calling it would be a feed that
    reports nothing while looking configured."""
    from app.config import settings

    sent: list[bytes] = []
    monkeypatch.setattr(settings, "siem_enabled", True)
    monkeypatch.setattr(settings, "siem_host", "127.0.0.1")
    monkeypatch.setattr(settings, "siem_tls", False)
    siem.reset_sender()
    monkeypatch.setattr(siem.get_sender(), "send", lambda frame: sent.append(frame) is None)

    audit.record(db, tenant_id=workspace["tenant"].id, action="contract.created",
                 actor=workspace["owner"], object_type="contract", object_label="X")
    db.flush()

    assert sent, "the audit path did not emit to the SIEM"
    assert b"contract.created" in sent[0]
    siem.reset_sender()


def test_a_siem_failure_never_breaks_the_audited_action(db, workspace, monkeypatch):
    """Monitoring must never break the thing it monitors."""
    from app.config import settings

    monkeypatch.setattr(settings, "siem_enabled", True)
    monkeypatch.setattr(settings, "siem_host", "127.0.0.1")
    monkeypatch.setattr(settings, "siem_tls", False)
    siem.reset_sender()

    def _explode(_frame):
        raise RuntimeError("collector on fire")

    monkeypatch.setattr(siem.get_sender(), "send", _explode)

    entry = audit.record(db, tenant_id=workspace["tenant"].id, action="contract.created",
                         actor=workspace["owner"], object_type="contract", object_label="X")
    db.flush()
    assert entry.row_hash, "the audit row must still be written and chained"
    siem.reset_sender()


# ---------------------------------------------------------------------------------------
# Connectors: Teams, SharePoint, calendar
# ---------------------------------------------------------------------------------------


def test_teams_is_off_until_a_webhook_is_configured():
    from app import connectors

    assert connectors.teams_enabled() is False


def test_an_adaptive_card_puts_the_numbers_in_facts():
    """A paragraph gets skimmed and the number in it gets missed."""
    from app import connectors

    card = connectors.adaptive_card(
        title="Approved: Merchant Agreement", subtitle="C-2026-0007",
        facts={"Counterparty": "Acme Trading", "Value": "PKR 1,000,000", "Empty": ""},
        url="https://cm.mmbl.test/contracts/x")
    content = card["attachments"][0]["content"]
    facts = next(b for b in content["body"] if b["type"] == "FactSet")["facts"]

    assert [f["title"] for f in facts] == ["Counterparty", "Value"]
    assert content["actions"][0]["url"].endswith("/contracts/x")


def test_only_events_worth_interrupting_for_are_notifiable():
    """A channel that pings on every draft save gets muted within a week, taking the alerts
    that mattered with it."""
    from app import connectors

    assert "contract.signed" in connectors.NOTIFIABLE
    assert "contract.updated" not in connectors.NOTIFIABLE


def test_sharepoint_files_by_year_and_type(db, workspace):
    """A document library with forty thousand files in one folder is one SharePoint refuses
    to page through."""
    from app import connectors
    from app.config import settings

    contract = models.Contract(
        tenant_id=workspace["tenant"].id, reference_no="C-1", title="T", type="vendor",
        status="active", owner_id=workspace["owner"].id, created_by=workspace["owner"].id,
        currency="PKR", effective_date=dt.date(2026, 3, 1))
    target = connectors.sharepoint_target(contract, "C-1.pdf")
    assert target.endswith("/2026/vendor/C-1.pdf")
    assert settings.sharepoint_library.strip("/") in target


def test_an_ics_invite_is_well_formed():
    from app import connectors

    ics = connectors.calendar_invite(summary="Renewal due", starts=dt.date(2026, 12, 31),
                                     all_day=True, attendees=["a@b.test"])
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "DTSTART;VALUE=DATE:20261231" in ics
    assert "ATTENDEE;RSVP=TRUE" in ics
    assert ics.endswith("END:VCALENDAR\r\n")


def test_ics_lines_are_folded_to_the_spec_limit():
    """Clients that reject an over-long line do it silently, so a long agreement title would
    produce an invite that simply never appears in the calendar."""
    from app import connectors

    ics = connectors.calendar_invite(
        summary="Renewal due: " + "a very long agreement title " * 6,
        starts=dt.date(2026, 12, 31), all_day=True)
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_ics_escapes_a_comma():
    """An unescaped comma silently truncates the field in most clients."""
    from app import connectors

    ics = connectors.calendar_invite(summary="Acme Trading, Lahore",
                                     starts=dt.date(2026, 1, 1), all_day=True)
    assert "Acme Trading\\, Lahore" in ics


def test_a_renewal_invite_has_a_stable_uid(db, workspace):
    """Re-issuing after a date change must update the entry, not add a second one."""
    from app import connectors

    contract = models.Contract(
        tenant_id=workspace["tenant"].id, reference_no="C-1", title="T", type="vendor",
        status="active", owner_id=workspace["owner"].id, created_by=workspace["owner"].id,
        currency="PKR", end_date=dt.date(2026, 12, 31))
    db.add(contract)
    db.flush()

    first = connectors.renewal_invite(contract)
    contract.end_date = dt.date(2027, 6, 30)
    second = connectors.renewal_invite(contract)

    uid = f"UID:renewal-{contract.id}@contract-management"
    assert uid in first and uid in second
    assert "20270630" in second


def test_no_end_date_means_no_renewal_invite(db, workspace):
    from app import connectors

    contract = models.Contract(
        tenant_id=workspace["tenant"].id, reference_no="C-1", title="T", type="vendor",
        status="active", owner_id=workspace["owner"].id, created_by=workspace["owner"].id,
        currency="PKR", end_date=None)
    assert connectors.renewal_invite(contract) is None


def test_a_cancelled_invite_says_so():
    from app import connectors

    ics = connectors.calendar_invite(summary="x", starts=dt.date(2026, 1, 1), all_day=True,
                                     cancelled=True, sequence=2)
    assert "METHOD:CANCEL" in ics
    assert "STATUS:CANCELLED" in ics
    assert "SEQUENCE:2" in ics
    assert "BEGIN:VALARM" not in ics, "a cancelled event must not still alarm"


# ---------------------------------------------------------------------------------------
# SOAP facade
# ---------------------------------------------------------------------------------------


def _soap_request(operation: str, params: dict, api_key: str = "") -> str:
    body = "".join(f"<tns:{k}>{v}</tns:{k}>" for k, v in params.items())
    security = (
        '<soap:Header><wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-secext-1.0.xsd"><wsse:UsernameToken>'
        f'<wsse:Username>api</wsse:Username><wsse:Password>{api_key}</wsse:Password>'
        '</wsse:UsernameToken></wsse:Security></soap:Header>' if api_key else ""
    )
    return (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:tns="http://thiqa.example/contract-management">'
        f'{security}<soap:Body><tns:{operation}>{body}</tns:{operation}></soap:Body>'
        '</soap:Envelope>'
    )


def _api_key(db, ws) -> str:
    import hashlib
    import secrets

    raw = "cm_" + secrets.token_urlsafe(24)
    db.add(models.ApiKey(
        tenant_id=ws["tenant"].id, user_id=ws["owner"].id, name="SOAP",
        prefix=raw[:8], token_hash=hashlib.sha256(raw.encode()).hexdigest()))
    db.commit()
    return raw


def test_soap_is_off_by_default():
    """An unused SOAP endpoint is attack surface with no user."""
    from app import soap

    assert soap.is_enabled() is False


def test_a_request_without_credentials_gets_a_fault(db):
    from app import soap

    body, ok = soap.handle(db, _soap_request("GetContract", {"ReferenceNo": "C-1"}))
    assert ok is False
    assert "<faultcode>soap:Client</faultcode>" in body
    assert "No credentials" in body


def test_a_bad_api_key_gets_a_fault(db):
    from app import soap

    body, ok = soap.handle(db, _soap_request("GetContract", {"ReferenceNo": "C-1"},
                                             api_key="cm_nonsense"))
    assert ok is False
    assert "not accepted" in body


def test_malformed_xml_gets_a_fault_not_a_stack_trace(db):
    from app import soap

    body, ok = soap.handle(db, "<this is not xml")
    assert ok is False
    assert "well-formed" in body


def test_an_unknown_operation_lists_what_is_supported(db, workspace):
    from app import soap

    key = _api_key(db, workspace)
    body, ok = soap.handle(db, _soap_request("DeleteEverything", {}, api_key=key))
    assert ok is False
    assert "GetContract" in body


def test_getting_a_contract_over_soap(db, workspace):
    from app import soap

    key = _api_key(db, workspace)
    db.add(models.Contract(
        tenant_id=workspace["tenant"].id, reference_no="C-2026-0007",
        title="Merchant Acquiring Agreement", type="vendor", status="active",
        owner_id=workspace["owner"].id, created_by=workspace["owner"].id,
        counterparty="Acme Trading", value=1_000_000, currency="PKR"))
    db.commit()

    body, ok = soap.handle(db, _soap_request("GetContract",
                                             {"ReferenceNo": "C-2026-0007"}, api_key=key))
    assert ok is True
    assert "<tns:Title>Merchant Acquiring Agreement</tns:Title>" in body
    assert "<tns:Counterparty>Acme Trading</tns:Counterparty>" in body


def test_a_missing_contract_gets_a_fault(db, workspace):
    from app import soap

    key = _api_key(db, workspace)
    body, ok = soap.handle(db, _soap_request("GetContract", {"ReferenceNo": "C-NOPE"},
                                             api_key=key))
    assert ok is False
    assert "No agreement found" in body


def test_creating_a_contract_over_soap_still_starts_as_a_draft(db, workspace):
    """The integration is a way in, not a way around the lifecycle."""
    from app import soap

    key = _api_key(db, workspace)
    body, ok = soap.handle(db, _soap_request(
        "CreateContract",
        {"Title": "Core banking registration", "Counterparty": "Acme", "Value": "500000"},
        api_key=key))
    assert ok is True
    assert "<tns:Status>draft</tns:Status>" in body

    created = db.query(models.Contract).filter_by(
        tenant_id=workspace["tenant"].id, title="Core banking registration").one()
    assert created.source == "soap"
    assert created.value == 500000


def test_creating_without_a_title_gets_a_fault(db, workspace):
    from app import soap

    key = _api_key(db, workspace)
    body, ok = soap.handle(db, _soap_request("CreateContract", {"Value": "1"}, api_key=key))
    assert ok is False
    assert "needs a Title" in body


def test_a_bad_date_gets_a_fault_rather_than_being_guessed(db, workspace):
    from app import soap

    key = _api_key(db, workspace)
    body, ok = soap.handle(db, _soap_request(
        "CreateContract", {"Title": "X", "EndDate": "31/12/2026"}, api_key=key))
    assert ok is False
    assert "YYYY-MM-DD" in body


def test_listing_is_capped(db, workspace):
    """A legacy client asking for everything would otherwise pull a decade of agreements
    through a SOAP envelope."""
    from app import soap

    key = _api_key(db, workspace)
    for i in range(3):
        db.add(models.Contract(
            tenant_id=workspace["tenant"].id, reference_no=f"C-{i}", title=f"T{i}",
            type="vendor", status="active", owner_id=workspace["owner"].id,
            created_by=workspace["owner"].id, currency="PKR"))
    db.commit()

    body, ok = soap.handle(db, _soap_request("ListContracts", {"Limit": "2"}, api_key=key))
    assert ok is True
    assert "<tns:Count>2</tns:Count>" in body


def test_another_tenants_agreement_is_not_reachable_over_soap(db, workspace, make_user):
    from app import soap

    key = _api_key(db, workspace)
    other_owner, other_tenant = make_user(email=f"s-{uuid.uuid4().hex[:8]}@example.com",
                                          name="Other")
    db.add(models.Contract(
        tenant_id=other_tenant.id, reference_no="C-SECRET", title="Theirs", type="vendor",
        status="active", owner_id=other_owner.id, created_by=other_owner.id, currency="PKR"))
    db.commit()

    body, ok = soap.handle(db, _soap_request("GetContract", {"ReferenceNo": "C-SECRET"},
                                             api_key=key))
    assert ok is False
    assert "No agreement found" in body


def test_the_wsdl_describes_the_operations_it_actually_has():
    from defusedxml.ElementTree import fromstring

    from app import soap

    document = soap.wsdl("https://cm.mmbl.test")
    for operation in ("GetContract", "ListContracts", "CreateContract"):
        assert f'name="{operation}"' in document
    assert "https://cm.mmbl.test/soap" in document
    fromstring(document)      # must be well-formed
