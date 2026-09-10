"""Redline — word-level comparison, accept/reject, anchored threads.

The two properties everything else rests on:

- accepting **every** change reconstructs the compared text exactly;
- accepting **none** reconstructs the base text exactly.

If either fails, accept/reject silently corrupts documents — the changes a reviewer thought
they were rejecting come back, or wording nobody chose appears. Both are property-tested
against a corpus rather than a single happy path.

Requirements: SOW-07.
"""

from __future__ import annotations

import uuid

import pytest

from app import models, redline_service, security
from app.redline_service import RedlineError

BASE = (
    "1. The Supplier shall provide the Services with reasonable skill and care.\n\n"
    "2. The total aggregate liability of either party shall not exceed the total fees paid "
    "in the twelve (12) months preceding the claim.\n\n"
    "3. Either party may terminate on sixty (60) days' written notice.\n"
)

PROPOSED = (
    "1. The Supplier shall provide the Services with reasonable skill and care.\n\n"
    "2. The total aggregate liability of either party shall not exceed two times (2x) the "
    "total fees paid in the twelve (12) months preceding the claim.\n\n"
    "3. Either party may terminate on ninety (90) days' written notice.\n\n"
    "4. This Agreement is governed by the laws of England and Wales.\n"
)

#: Documents that break naive diffing: pure insert, pure delete, reordering, unicode,
#: whitespace-only change, and an empty side.
CORPUS = [
    ("", "Everything is new."),
    ("Everything is removed.", ""),
    ("one two three", "one two three"),
    ("one two three", "one three"),
    ("one three", "one two three"),
    ("alpha beta gamma", "gamma beta alpha"),
    ("Fee is PKR 250,000.00", "Fee is PKR 500,000.00"),
    ("Ünïcode wörds stay intact", "Ünïcode words stay intact"),
    ("trailing space kept ", "trailing space kept"),
    ("multi\n\nparagraph\n\ndocument", "multi\n\nrewritten paragraph\n\ndocument"),
    (BASE, PROPOSED),
    (BASE, BASE),
]


# ---------------------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("base,proposed", CORPUS)
def test_accepting_everything_reconstructs_the_proposal(base, proposed):
    result = redline_service.compare(base, proposed)
    every = [c.index for c in result.changes]
    assert redline_service.apply(base, proposed, every) == proposed


@pytest.mark.parametrize("base,proposed", CORPUS)
def test_accepting_nothing_reconstructs_the_base(base, proposed):
    redline_service.compare(base, proposed)
    assert redline_service.apply(base, proposed, []) == base


@pytest.mark.parametrize("base,proposed", CORPUS)
def test_the_diff_is_deterministic(base, proposed):
    """The change index is an identifier the client sends back, so it has to mean the same
    thing on the next request. That only holds if the diff is reproducible."""
    first = redline_service.compare(base, proposed).to_dict()
    second = redline_service.compare(base, proposed).to_dict()
    assert first == second


def test_identical_documents_produce_no_changes():
    result = redline_service.compare(BASE, BASE)
    assert result.identical
    assert result.changes == []
    assert result.removed == 0 and result.added == 0


def test_a_changed_cap_shows_the_words_that_moved():
    result = redline_service.compare(BASE, PROPOSED)
    text = " ".join(c.after for c in result.changes)
    assert "two times (2x)" in text
    assert "ninety (90)" in text
    assert any("England and Wales" in c.after for c in result.changes)


def test_each_change_carries_context_so_it_can_be_placed():
    result = redline_service.compare(BASE, PROPOSED)
    cap = next(c for c in result.changes if "two times" in c.after)
    assert "liability" in cap.before_context or "exceed" in cap.before_context


def test_accepting_one_change_leaves_the_others_alone():
    """The whole point of accept/reject: partial acceptance has to be exact."""
    result = redline_service.compare(BASE, PROPOSED)
    cap = next(c for c in result.changes if "two times" in c.after)
    merged = redline_service.apply(BASE, PROPOSED, [cap.index])

    assert "two times (2x)" in merged            # taken
    assert "sixty (60) days" in merged           # rejected, base wording kept
    assert "England and Wales" not in merged     # rejected


def test_anchors_point_at_the_proposed_wording():
    """A comment anchored to a change must land on the text it is about."""
    result = redline_service.compare(BASE, PROPOSED)
    for change in result.changes:
        assert PROPOSED[change.anchor_start:change.anchor_end] == change.after


def test_word_counts_report_how_much_moved():
    result = redline_service.compare("one two three four", "one two three four five six")
    assert result.added == 2
    assert result.removed == 0
    assert result.unchanged == 4


def test_a_stale_change_index_is_rejected():
    """A client with a drifted view must not get a document nobody chose."""
    result = redline_service.compare(BASE, PROPOSED)
    with pytest.raises(RedlineError, match="not in this comparison"):
        redline_service.validate_selection(result, [len(result.changes) + 7])


def test_a_valid_selection_is_normalised():
    result = redline_service.compare(BASE, PROPOSED)
    assert redline_service.validate_selection(result, [1, 0, 1]) == [0, 1]


def test_the_summary_reads_as_an_audit_line():
    result = redline_service.compare(BASE, PROPOSED)
    summary = redline_service.summarise(result, accepted=[0])
    assert summary.startswith("Redline: accepted 1 of ")
    assert "words" in summary


def test_whitespace_only_reformatting_round_trips():
    """Reflowing a paragraph must not corrupt it in either direction."""
    base = "The Supplier shall\nprovide the Services."
    proposed = "The Supplier shall provide the Services."
    every = [c.index for c in redline_service.compare(base, proposed).changes]
    assert redline_service.apply(base, proposed, every) == proposed
    assert redline_service.apply(base, proposed, []) == base


# ---------------------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------------------

PASSWORD = "Str0ng!Passw0rd1"


@pytest.fixture()
def api(client, db, make_user):
    user, tenant = make_user(email=f"redline-{uuid.uuid4().hex[:8]}@example.com",
                            name="Redline Owner")
    row = db.get(models.User, user.id)
    row.password_hash = security.hash_password(PASSWORD)

    contract = models.Contract(
        tenant_id=tenant.id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Vendor Services Agreement", type="vendor", status="draft",
        owner_id=user.id, created_by=user.id, body=PROPOSED, value=100_000, currency="PKR",
    )
    db.add(contract)
    db.flush()
    db.add(models.ContractVersion(
        tenant_id=tenant.id, contract_id=contract.id, version_no=1, body=BASE,
        change_summary="Our paper", created_by=user.id,
    ))
    db.commit()

    r = client.post("/auth/login", json={"email": row.email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {
        "tenant": tenant, "user": user, "contract": contract,
        "h": {"Authorization": f"Bearer {r.json()['access_token']}"},
    }


def test_the_default_comparison_is_last_saved_against_the_live_draft(client, api):
    """The question actually being asked most of the time."""
    r = client.get(f"/contracts/{api['contract'].id}/redline", headers=api["h"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["base_version_no"] == 1
    assert body["compare_version_no"] is None
    assert body["compare_label"] == "Current draft"
    assert body["identical"] is False
    assert body["change_count"] == len(body["changes"])


def test_comparing_a_version_against_itself_shows_nothing(client, api):
    r = client.get(f"/contracts/{api['contract'].id}/redline?base=1&compare=1", headers=api["h"])
    assert r.status_code == 200
    assert r.json()["identical"] is True


def test_an_unknown_version_is_a_404(client, api):
    r = client.get(f"/contracts/{api['contract'].id}/redline?base=99", headers=api["h"])
    assert r.status_code == 404


def test_applying_a_partial_selection_saves_a_new_version(client, db, api):
    contract_id = api["contract"].id
    redline = client.get(f"/contracts/{contract_id}/redline", headers=api["h"]).json()
    cap = next(c for c in redline["changes"] if "two times" in c["after"])

    r = client.post(f"/contracts/{contract_id}/redline/apply", headers=api["h"], json={
        "base_version_no": 1, "compare_version_no": None, "accept": [cap["index"]],
    })
    assert r.status_code == 200, r.text
    assert "two times (2x)" in r.json()["body"]
    assert "sixty (60) days" in r.json()["body"], "a rejected change must keep the base wording"

    versions = client.get(f"/contracts/{contract_id}/versions", headers=api["h"]).json()
    assert any(v["change_summary"].startswith("Redline: accepted 1 of") for v in versions), \
        "the previous wording has to stay recoverable"


def test_applying_a_stale_index_is_refused(client, api):
    r = client.post(f"/contracts/{api['contract'].id}/redline/apply", headers=api["h"], json={
        "base_version_no": 1, "accept": [999],
    })
    assert r.status_code == 400
    assert "not in this comparison" in r.json()["detail"]


def test_a_signed_agreement_cannot_be_redlined(client, db, api):
    """Negotiation is over. Editing the text of a signed agreement is an amendment, not a
    redline, and must not look like one."""
    contract = db.get(models.Contract, api["contract"].id)
    contract.status = "signed"
    db.commit()
    r = client.post(f"/contracts/{api['contract'].id}/redline/apply", headers=api["h"],
                    json={"base_version_no": 1, "accept": []})
    assert r.status_code == 409


def test_a_comment_anchors_to_the_proposed_change(client, api):
    contract_id = api["contract"].id
    redline = client.get(f"/contracts/{contract_id}/redline", headers=api["h"]).json()
    cap = next(c for c in redline["changes"] if "two times" in c["after"])

    r = client.post(f"/contracts/{contract_id}/redline/comment", headers=api["h"], json={
        "body": "Doubling the cap needs the CFO.",
        "anchor_start": cap["anchor_start"], "anchor_end": cap["anchor_end"],
        "internal_only": True,
    })
    assert r.status_code == 201, r.text
    comment = r.json()
    assert comment["anchor_start"] == cap["anchor_start"]
    assert comment["internal_only"] is True


def test_an_inverted_anchor_is_refused(client, api):
    r = client.post(f"/contracts/{api['contract'].id}/redline/comment", headers=api["h"], json={
        "body": "nope", "anchor_start": 90, "anchor_end": 10,
    })
    assert r.status_code == 400


def test_another_tenant_cannot_see_the_redline(client, db, api, make_user):
    outsider, _tenant = make_user(email=f"other-{uuid.uuid4().hex[:8]}@example.com",
                                  name="Other Tenant")
    row = db.get(models.User, outsider.id)
    row.password_hash = security.hash_password(PASSWORD)
    db.commit()
    token = client.post("/auth/login",
                        json={"email": row.email, "password": PASSWORD}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/contracts/{api['contract'].id}/redline",
                      headers=headers).status_code == 404
