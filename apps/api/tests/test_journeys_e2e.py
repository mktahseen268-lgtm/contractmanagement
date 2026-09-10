"""End-to-end journey tests (Phase 10).

The RFI describes two journeys, and this walks both of them through the real HTTP surface:
authentication, template generation, approval routing, execution, and the customer's side of
the signature. Nothing is called directly — every step is a request a browser could make, so a
route that exists but is wired wrong fails here rather than in UAT.

**These double as the UAT evidence.** Each test carries the requirement IDs from the Scope &
Technical Specification (`SOW-04`, `BB-01`, …), so a passing run is traceable to the clause it
satisfies. The numbered test book is generated from these names.

They are deliberately *journeys*, not endpoint tests. The unit suites already cover each
service in isolation; what nothing else covers is whether the pieces line up — that a contract
generated from a template can actually be submitted, that the approval actually unblocks
sending, that the link in the email actually signs.
"""

from __future__ import annotations

import uuid

import pytest

from app import models, security

PASSWORD = "JourneyTest!9xQ2"


# ---------------------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------------------


class Actor:
    """One signed-in person, holding their own bearer token.

    A separate client per actor rather than swapping headers, because the interesting failures
    in an approval flow are the ones where the wrong person's identity leaks between steps.
    """

    def __init__(self, client, email, password=PASSWORD):
        self.client = client
        self.email = email
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, f"login failed for {email}: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, json=None, **kw):
        return self.client.post(path, json=json, headers=self.headers, **kw)

    def patch(self, path, json=None, **kw):
        return self.client.patch(path, json=json, headers=self.headers, **kw)


@pytest.fixture()
def workspace(db, client):
    """A tenant with the four roles a journey needs, all able to sign in over HTTP."""
    from app.database import SessionLocal, set_request_tenant

    tenant_id = uuid.uuid4().hex
    domain = f"j{tenant_id[:6]}.mmbl-demo.co"
    people = {}

    with SessionLocal() as s:
        set_request_tenant(tenant_id)
        s.add(models.Tenant(id=tenant_id, name="MMBL Journey",
                            slug=f"j-{tenant_id[:8]}", currency="PKR"))
        s.flush()
        for role in ("owner", "author", "approver", "manager"):
            user = models.User(
                tenant_id=tenant_id, email=f"{role}@{domain}", name=role.title(),
                password_hash=security.hash_password(PASSWORD), role=role)
            s.add(user)
            s.flush()
            people[role] = user.email

        # An approval workflow, because without one `submit-for-approval` falls through to a
        # plain status change and the journey never exercises routing at all. A single
        # approver step is the shape MMBL's standard flow takes.
        s.add(models.WorkflowDefinition(
            tenant_id=tenant_id, name="Standard approval", status="active",
            default_for_types=["vendor", "msa", "service", "nda", "other"],
            steps=[{"name": "Approver review", "assignee_kind": "role",
                    "assignee_value": "approver"}],
            created_by=list(people.values()) and next(iter(people.values())) or "",
        ))
        s.commit()

    set_request_tenant(tenant_id)
    return {"tenant_id": tenant_id, "people": people}


@pytest.fixture()
def author(client, workspace):
    return Actor(client, workspace["people"]["author"])


@pytest.fixture()
def approver(client, workspace):
    return Actor(client, workspace["people"]["approver"])


@pytest.fixture()
def owner(client, workspace):
    return Actor(client, workspace["people"]["owner"])


def _approved_template(owner, *, title="BBCORP Merchant Agreement"):
    """A template that has been through its approval gate — the only kind that can generate."""
    created = owner.post("/templates", json={
        "name": title,
        "contract_type": "vendor",
        "body": (
            "# {{agreement_title}}\n\n"
            "This agreement is between {{our_entity}} and {{counterparty}}.\n\n"
            "## Commercials\n"
            "Merchant discount rate: {{mdr}}%\n"
            "Settlement period: {{settlement_days}} days\n"
            "Term commences {{effective_date}} and ends {{end_date}}.\n"
        ),
        "fields": [
            {"key": "agreement_title", "label": "Agreement title", "type": "text", "required": True},
            {"key": "mdr", "label": "Merchant discount rate", "type": "number", "required": True},
            {"key": "settlement_days", "label": "Settlement period (days)", "type": "number", "required": True},
        ],
    })
    assert created.status_code == 201, created.text
    tid = created.json()["id"]

    assert owner.post(f"/templates/{tid}/submit", json={}).status_code == 200
    approved = owner.post(f"/templates/{tid}/approve", json={})
    assert approved.status_code == 200, approved.text
    return tid


# ---------------------------------------------------------------------------------------
# Journey 1 — BBCORP: intake → draft → approval → execution
# ---------------------------------------------------------------------------------------


def test_journey_1_bbcorp_intake_to_execution(client, db, workspace, owner, author, approver):
    """SOW-01, SOW-04, SOW-11, SOW-17, SOW-21, BB-01, BB-02.

    The whole spine in one pass: an approved template, a structured intake, a generated draft,
    a routed approval, an envelope, and a counterparty signature from an unauthenticated link.
    """
    # ── 1. Legal publishes an approved template (SOW-01) ────────────────────────────────
    template_id = _approved_template(owner)

    listed = author.get("/templates").json()
    assert any(t["id"] == template_id and t["status"] == "active" for t in listed), listed

    # ── 2. The form is driven by the template, not hard-coded (SOW-04) ──────────────────
    form = author.get(f"/templates/{template_id}/form")
    assert form.status_code == 200, form.text
    keys = {f["key"] for f in form.json()["fields"]}
    assert {"agreement_title", "mdr", "settlement_days"} <= keys

    # ── 3. An incomplete intake is refused rather than producing a gapped document ───────
    incomplete = author.post(f"/templates/{template_id}/generate", json={
        "title": "QR Merchant — Acme Traders",
        "counterparty": "Acme Traders",
        "values": {"agreement_title": "QR Merchant Agreement"},     # mdr and settlement missing
    })
    assert incomplete.status_code == 400, incomplete.text
    assert "mdr" in incomplete.text or "Merchant discount" in incomplete.text

    # ── 4. A complete intake generates the draft (SOW-04) ───────────────────────────────
    generated = author.post(f"/templates/{template_id}/generate", json={
        "title": "QR Merchant — Acme Traders",
        "counterparty": "Acme Traders",
        "value": 500000,
        "effective_date": "2026-09-01",
        "end_date": "2027-08-31",
        "values": {
            "agreement_title": "QR Merchant Agreement",
            "mdr": 1.75,
            "settlement_days": 2,
        },
    })
    assert generated.status_code == 201, generated.text
    contract = generated.json()
    contract_id = contract["id"]

    assert contract["status"] == "draft"
    # The merged values are in the body — no placeholder survived into the document.
    body = author.get(f"/contracts/{contract_id}").json()["body"]
    assert "1.75" in body
    assert "Acme Traders" in body
    assert "{{" not in body

    # ── 5. Guidance says what to do next (SOW-33 support) ───────────────────────────────
    guidance = author.get(f"/contracts/{contract_id}/guidance")
    assert guidance.status_code == 200
    assert guidance.json()["progress"]["stage"] == "drafting"

    # ── 6. It cannot be sent for signature before approval ──────────────────────────────
    premature = author.post(f"/contracts/{contract_id}/prepare-signature", json={
        "recipients": [{"name": "Acme Signatory", "email": "signer@acme-traders.co",
                        "kind": "signer"}],
        "message": "", "signing_order": "sequential",
    })
    assert premature.status_code in (403, 409), premature.text

    # ── 7. Submit for approval (SOW-11) ─────────────────────────────────────────────────
    submitted = author.post(f"/contracts/{contract_id}/submit-for-approval", json={})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] in ("in_review", "draft")

    # While a run is active, the plain status action is blocked — decisions go through the
    # workflow so approvals cannot be stepped around.
    sidestep = author.post(f"/contracts/{contract_id}/transition",
                           json={"status": "approved"})
    assert sidestep.status_code in (403, 409), sidestep.text

    # ── 8. The author cannot approve their own work (SOW-16) ────────────────────────────
    self_approve = author.post(f"/contracts/{contract_id}/workflow/decide",
                               json={"decision": "approve", "comment": ""})
    assert self_approve.status_code in (403, 409), self_approve.text

    # ── 9. The approver decides (SOW-11) ────────────────────────────────────────────────
    decided = approver.post(f"/contracts/{contract_id}/workflow/decide",
                            json={"decision": "approve", "comment": "Rate is within policy."})
    assert decided.status_code == 200, decided.text

    state = author.get(f"/contracts/{contract_id}").json()
    assert state["status"] in ("approved", "in_review"), state["status"]

    if state["status"] != "approved":
        # A multi-stage workflow needs the remaining stages; drive them with the owner, who
        # holds an override role.
        for _ in range(4):
            more = owner.post(f"/contracts/{contract_id}/workflow/decide",
                              json={"decision": "approve", "comment": "ok"})
            if more.status_code != 200:
                break
            if author.get(f"/contracts/{contract_id}").json()["status"] == "approved":
                break
        state = author.get(f"/contracts/{contract_id}").json()

    assert state["status"] == "approved", state

    # ── 10. Prepare and send the envelope (SOW-17) ──────────────────────────────────────
    envelope = author.post(f"/contracts/{contract_id}/prepare-signature", json={
        "recipients": [{"name": "Acme Signatory", "email": "signer@acme-traders.co",
                        "kind": "signer"}],
        "message": "Please review and sign.",
        "signing_order": "sequential",
    })
    assert envelope.status_code == 201, envelope.text
    envelope_id = envelope.json()["id"]

    sent = author.post(f"/envelopes/{envelope_id}/send", json={})
    assert sent.status_code == 200, sent.text
    assert author.get(f"/contracts/{contract_id}").json()["status"] == "out_for_signature"

    # ── 11. The counterparty signs from an unauthenticated link (BB-01) ─────────────────
    from app import signing_service as ss

    recipient = ss.recipients(db, envelope_id)[0]
    raw_token = ss.decrypt_token_for(recipient)
    assert raw_token, "the signer was never given a working link"

    # No Authorization header anywhere in this block — that is the point.
    viewed = client.post(f"/sign/{raw_token}/view")
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["valid"] is True
    assert viewed.json()["can_sign"] is True

    signature = client.post(f"/sign/{raw_token}/sign", json={
        "full_name": "Imran Qureshi", "consent": True, "tab_fills": [],
        "signature_kind": "typed",
    })
    assert signature.status_code == 200, signature.text

    # ── 12. A retried signature does not double-sign (BB-02) ────────────────────────────
    retry = client.post(f"/sign/{raw_token}/sign", json={
        "full_name": "Imran Qureshi", "consent": True, "tab_fills": [],
        "signature_kind": "typed",
    })
    assert retry.status_code in (200, 409), retry.text

    events = db.query(models.SignatureEvent).filter(
        models.SignatureEvent.envelope_id == envelope_id,
        models.SignatureEvent.event == "signed").all()
    assert len(events) == 1, "a retry produced a second signature"

    # ── 13. Execution completes and the record is filed (SOW-21) ────────────────────────
    final = author.get(f"/contracts/{contract_id}").json()
    assert final["status"] in ("signed", "active"), final["status"]

    # ── 14. Every step of it is on the audit trail (SEC-12) ─────────────────────────────
    # The activity feed carries the contract's own lifecycle. Signature events live on the
    # envelope, which is where an auditor reconstructing an execution would look for them —
    # so both are checked rather than assuming one endpoint shows everything.
    activity = author.get(f"/contracts/{contract_id}/activity")
    assert activity.status_code == 200
    contract_actions = {a["action"] for a in activity.json()}
    assert "contract.created" in contract_actions, contract_actions
    assert any(a.startswith("contract.sent_for_signature") or "signature" in a
               for a in contract_actions), contract_actions

    signature_events = {e.event for e in db.query(models.SignatureEvent).filter(
        models.SignatureEvent.envelope_id == envelope_id).all()}
    assert {"created", "sent", "signed", "completed"} <= signature_events, signature_events

    # And the chain that makes all of it tamper-evident still verifies (SEC-12).
    from app import audit
    ok, problems = audit.verify_chain(db, workspace["tenant_id"])
    assert ok, problems


# ---------------------------------------------------------------------------------------
# Journey 2 — other departments: review loop, changes requested, resubmission
# ---------------------------------------------------------------------------------------


def test_journey_2_review_loop_until_acceptance(client, db, workspace, owner, author, approver):
    """SOW-07, SOW-08, SOW-11, SOW-15.

    The RFI's second journey is the one with a loop in it: a reviewer sends it back, the author
    changes it, and it goes round again until somebody accepts. The loop is the requirement —
    a workflow that can only go forwards does not model how agreements actually get agreed.
    """
    template_id = _approved_template(owner, title="Service Agreement")

    created = author.post(f"/templates/{template_id}/generate", json={
        "title": "Service Agreement — Northern Logistics",
        "counterparty": "Northern Logistics",
        "value": 1200000,
        "effective_date": "2026-09-01", "end_date": "2027-08-31",
        "values": {"agreement_title": "Service Agreement", "mdr": 0, "settlement_days": 30},
    })
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]

    # ── Round one: sent back ────────────────────────────────────────────────────────────
    assert author.post(f"/contracts/{contract_id}/submit-for-approval",
                       json={}).status_code == 200

    sent_back = approver.post(f"/contracts/{contract_id}/workflow/decide", json={
        "decision": "changes_requested",
        "comment": "Settlement period must be 15 days for this counterparty.",
    })
    assert sent_back.status_code == 200, sent_back.text
    assert author.get(f"/contracts/{contract_id}").json()["status"] == "changes_requested"

    # The reviewer's reason is on the record, not in somebody's inbox (SOW-08). It is stored
    # against the step that was decided, which is where "why did this come back" is answered.
    decided_step = db.query(models.WorkflowRunStep).filter(
        models.WorkflowRunStep.tenant_id == workspace["tenant_id"],
        models.WorkflowRunStep.decision == "changes_requested").first()
    assert decided_step is not None, "no decided step was recorded"
    assert "15 days" in (decided_step.comment or ""), decided_step.comment
    assert decided_step.decided_by_name, "the decision does not say who made it"

    # ── The author revises ──────────────────────────────────────────────────────────────
    revised = author.patch(f"/contracts/{contract_id}", json={
        "body": "# Service Agreement\n\nSettlement period: 15 days\n",
    })
    assert revised.status_code == 200, revised.text

    versions = author.get(f"/contracts/{contract_id}/versions").json()
    assert len(versions) >= 2, "the revision did not create a new version"

    # ── Round two: accepted ─────────────────────────────────────────────────────────────
    resubmitted = author.post(f"/contracts/{contract_id}/submit-for-approval", json={})
    assert resubmitted.status_code == 200, resubmitted.text

    accepted = approver.post(f"/contracts/{contract_id}/workflow/decide",
                             json={"decision": "approve", "comment": "Agreed."})
    assert accepted.status_code == 200, accepted.text

    # ── Both rounds survive on the record ───────────────────────────────────────────────
    # Two runs, two decisions, both retained. An approval history that only kept the outcome
    # would answer "was it approved" and not "what did it take" — which is the question an
    # auditor reviewing a contested agreement is actually asking.
    runs = author.get(f"/contracts/{contract_id}/workflow")
    assert runs.status_code == 200, runs.text

    decisions = [s.decision for s in db.query(models.WorkflowRunStep).filter(
        models.WorkflowRunStep.tenant_id == workspace["tenant_id"],
        models.WorkflowRunStep.decision.is_not(None)).all()]
    assert "changes_requested" in decisions, decisions
    assert "approve" in decisions, decisions

    final = author.get(f"/contracts/{contract_id}").json()
    assert final["status"] == "approved", final["status"]


def test_a_rejected_agreement_does_not_become_signable(client, db, workspace, owner, author, approver):
    """SOW-11. Rejection is not "changes requested" — it ends the attempt, and an agreement
    that was rejected must not be sendable by any route."""
    template_id = _approved_template(owner, title="MoU")
    made = author.post(f"/templates/{template_id}/generate", json={
        "title": "MoU — Southern Bank", "counterparty": "Southern Bank",
        # The template references {{end_date}}, and the engine refuses to generate with an
        # unresolved placeholder rather than leaving a blank. Supplying it is the point.
        "effective_date": "2026-09-01", "end_date": "2027-08-31",
        "values": {"agreement_title": "MoU", "mdr": 0, "settlement_days": 0},
    })
    assert made.status_code == 201, made.text
    contract_id = made.json()["id"]

    author.post(f"/contracts/{contract_id}/submit-for-approval", json={})
    rejected = approver.post(f"/contracts/{contract_id}/workflow/decide", json={
        "decision": "reject", "comment": "Not proceeding."})
    assert rejected.status_code == 200, rejected.text

    status_now = author.get(f"/contracts/{contract_id}").json()["status"]
    assert status_now in ("rejected", "draft"), status_now

    blocked = author.post(f"/contracts/{contract_id}/prepare-signature", json={
        "recipients": [{"name": "X", "email": "x@southern-bank.co", "kind": "signer"}],
        "message": "", "signing_order": "sequential"})
    assert blocked.status_code in (403, 409), blocked.text


# ---------------------------------------------------------------------------------------
# Cross-cutting: the properties an evaluator will probe
# ---------------------------------------------------------------------------------------


def test_a_signing_link_is_useless_once_the_envelope_is_voided(client, db, workspace, owner, author, approver):
    """BB-01. A voided envelope whose link still works is voided in name only."""
    template_id = _approved_template(owner, title="Voidable")
    made = author.post(f"/templates/{template_id}/generate", json={
        "title": "Voidable agreement", "counterparty": "Someone",
        "effective_date": "2026-09-01", "end_date": "2027-08-31",
        "values": {"agreement_title": "Voidable", "mdr": 1, "settlement_days": 1},
    })
    assert made.status_code == 201, made.text
    contract_id = made.json()["id"]

    author.post(f"/contracts/{contract_id}/submit-for-approval", json={})
    approver.post(f"/contracts/{contract_id}/workflow/decide", json={"decision": "approve"})
    for _ in range(3):
        if author.get(f"/contracts/{contract_id}").json()["status"] == "approved":
            break
        owner.post(f"/contracts/{contract_id}/workflow/decide", json={"decision": "approve"})

    envelope_id = author.post(f"/contracts/{contract_id}/prepare-signature", json={
        "recipients": [{"name": "Signer", "email": "s@someone.co", "kind": "signer"}],
        "message": "", "signing_order": "sequential"}).json()["id"]
    author.post(f"/envelopes/{envelope_id}/send", json={})

    from app import signing_service as ss
    token = ss.decrypt_token_for(ss.recipients(db, envelope_id)[0])
    assert client.post(f"/sign/{token}/view").json()["valid"] is True

    voided = author.post(f"/envelopes/{envelope_id}/void", json={})
    assert voided.status_code == 200, voided.text

    dead = client.post(f"/sign/{token}/view")
    assert dead.status_code in (200, 404)
    if dead.status_code == 200:
        assert dead.json()["valid"] is False


def test_one_workspace_cannot_read_anothers_agreements(client, db, workspace, author, make_user):
    """The isolation property. Everything else in the submission rests on it, so it is proven
    over HTTP rather than assumed from the row filter."""
    template_id = None
    mine = author.post("/contracts", json={
        "title": "Confidential — internal", "counterparty": "Acme", "type": "vendor"})
    assert mine.status_code == 201, mine.text
    contract_id = mine.json()["id"]
    assert template_id is None

    # A user in a different tenant, signing in over HTTP like anybody else.
    other_email = f"outsider{uuid.uuid4().hex[:8]}@other-bank.co"
    from app.database import SessionLocal, set_request_tenant

    other_tenant = uuid.uuid4().hex
    with SessionLocal() as s:
        set_request_tenant(other_tenant)
        s.add(models.Tenant(id=other_tenant, name="Other Bank", slug=f"o-{other_tenant[:8]}"))
        s.flush()
        s.add(models.User(tenant_id=other_tenant, email=other_email, name="Outsider",
                          password_hash=security.hash_password(PASSWORD), role="owner"))
        s.commit()

    outsider = Actor(client, other_email)

    assert outsider.get(f"/contracts/{contract_id}").status_code == 404
    listing = outsider.get("/contracts").json()
    assert all(item["id"] != contract_id for item in listing["items"])

    set_request_tenant(workspace["tenant_id"])
