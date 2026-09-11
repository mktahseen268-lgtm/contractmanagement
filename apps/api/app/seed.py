"""Seeds the demo workspace if the DB is empty. Login: demo@mobilinkbank.com / demo1234"""

import datetime as dt
import random
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, security
from .audit import record
# NOTE: the seed deliberately does NOT set the RLS tenant context — on PostgreSQL the
# `tenant_isolation` policies are permissive when the `app.cm_tenant` GUC is unset, so
# inserting the demo data works without it, and we avoid the GUC leaking into request contexts.

DEMO_EMAIL = "demo@mobilinkbank.com"
DEMO_PASSWORD = "demo1234"

_PARTIES = ["Sadiq Traders (Pvt) Ltd", "Karachi Textile Mills Ltd", "Indus Logistics",
            "Ravi Engineering Works", "Chenab Foods (Pvt) Ltd", "Bolan Distributors",
            "Margalla Technologies", "Sindh Agri Supplies"]
_TYPES = ["msa", "nda", "lease", "vendor", "service", "employment"]
_TYPE_TITLES = {
    "msa": "Master Services Agreement",
    "nda": "Mutual Non-Disclosure Agreement",
    "lease": "Office Lease Agreement",
    "vendor": "Vendor Agreement",
    "service": "Service Agreement",
    "employment": "Employment Agreement",
}
_STATUSES = ["draft", "draft", "in_review", "in_review", "approved", "out_for_signature", "signed", "active", "active", "active", "expiring", "expired", "changes_requested"]
_DEPTS = ["Procurement", "Legal", "Human Resources", "Real Estate & Administration",
          "Operations", "Finance", "Information Technology", "Branchless Banking"]
#: One jurisdiction: the Bank, its counterparties and the configured default are all
#: Pakistani. Drawn once per agreement below so the field and the clause agree.
_LAW = "Islamic Republic of Pakistan"
_RISKS = ["low", "low", "low", "medium", "medium", "high", "critical"]
# (title, description, due-offset-in-days-from-today) — negative offsets become 'overdue'.
_OBLIGATION_TEMPLATES = [
    ("Send renewal notice", "Notify the counterparty of intent to renew before the deadline.", -5),
    ("Quarterly compliance review", "Confirm covenant and policy compliance for the quarter.", 4),
    ("Submit deliverables report", "Provide the agreed milestone deliverables.", 12),
    ("Pay current invoice", "Settle the current period invoice (Net-30).", 1),
    ("Insurance certificate renewal", "Refresh the certificate of insurance on file.", -2),
    ("Security review sign-off", "Complete the annual vendor security attestation.", 25),
    ("Onboarding checklist", "Complete counterparty onboarding steps.", -18),
    ("Data-processing audit", "Verify DPA controls and data-residency commitments.", 40),
]


#: The status hops an agreement makes on its way to each end state. Only the ones that reach
#: execution contribute a cycle time; the rest are still in flight and get a partial history so
#: the pipeline views have something real in them.
_JOURNEY_TO = {
    "draft": [],
    "in_review": ["in_review"],
    "changes_requested": ["in_review", "changes_requested"],
    "approved": ["in_review", "approved"],
    "out_for_signature": ["in_review", "approved", "out_for_signature"],
    "signed": ["in_review", "approved", "out_for_signature", "signed"],
    "active": ["in_review", "approved", "out_for_signature", "signed", "active"],
    "expiring": ["in_review", "approved", "out_for_signature", "signed", "active", "expiring"],
    "expired": ["in_review", "approved", "out_for_signature", "signed", "active", "expired"],
    "renewed": ["in_review", "approved", "out_for_signature", "signed", "active", "renewed"],
    "terminated": ["in_review", "approved", "out_for_signature", "signed", "active", "terminated"],
    "rejected": ["in_review", "rejected"],
    "voided": ["in_review", "approved", "voided"],
    "declined": ["in_review", "approved", "out_for_signature", "declined"],
}


def _record_journey(db: Session, tenant_id: str, c, creator, users, rng) -> None:
    """Write the agreement's audit history at the dates it would really have happened.

    Every analytics figure — cycle time, the volume trend, stage performance — is derived from
    the audit trail rather than stored. Writing the whole history in one instant made "days
    from raised to executed" honestly computed and honestly zero, and put the entire volume
    trend in a single bar on today's date.

    **The clock is moved, the rows are not edited.** The timestamp is inside the audit HMAC, so
    rewriting `at` on a stored row would break the chain that exists to prove stored rows are
    never rewritten. `audit._utcnow` is the seam the chain-ordering tests already use.
    """
    from . import audit

    hops = _JOURNEY_TO.get(c.status, [])
    # Raised up to a year back, anchored so an agreement is never raised after it took effect.
    raised = dt.datetime.now() - dt.timedelta(days=rng.randint(20, 340), hours=rng.randint(0, 23))
    if c.effective_date:
        raised = min(raised, dt.datetime.combine(c.effective_date, dt.time(9, 30)))
    c.created_at = raised

    real_clock = audit._utcnow
    moment = raised
    try:
        audit._utcnow = lambda at=moment: at
        record(db, tenant_id=tenant_id, action="contract.created", actor=creator,
               object_type="contract", object_id=c.id, object_label=c.title,
               meta={"source": c.source})

        previous = "draft"
        for hop in hops:
            # A few working days per hop, so cycle times land in a believable band rather than
            # every agreement taking the same time.
            moment = moment + dt.timedelta(days=rng.randint(1, 11), hours=rng.randint(0, 23))
            if moment > dt.datetime.now():
                moment = dt.datetime.now() - dt.timedelta(hours=1)
            audit._utcnow = lambda at=moment: at
            action = "contract.submitted" if hop == "in_review" else "contract.status_changed"
            record(db, tenant_id=tenant_id, action=action, actor=rng.choice(users),
                   object_type="contract", object_id=c.id, object_label=c.title,
                   meta={"from": previous, "to": hop})
            previous = hop
        c.updated_at = moment
    finally:
        # Restore the real clock even if a row fails, or every audit entry written afterwards
        # would silently carry a seeded timestamp.
        audit._utcnow = real_clock


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(models.Tenant).limit(1)) is not None:
        return False
    rng = random.Random(42)

    tenant_id = uuid.uuid4().hex
    tenant = models.Tenant(id=tenant_id, name="Mobilink Microfinance Bank", slug="mmbl",
                           locale="en", currency="PKR", plan="business")
    db.add(tenant)
    db.flush()

    colors = ["#3E7BFA", "#8B7BF5", "#2BC0D4", "#F6B83C", "#F5736B", "#3FBF7F"]
    owner = models.User(tenant_id=tenant.id, email=DEMO_EMAIL, name="Demo Owner", password_hash=security.hash_password(DEMO_PASSWORD), role="owner", department="Legal", avatar_color=colors[0])
    manager = models.User(tenant_id=tenant.id, email="manager@mobilinkbank.com", name="Mariam Khan", password_hash=security.hash_password(DEMO_PASSWORD), role="manager", department="Procurement", avatar_color=colors[1])
    approver = models.User(tenant_id=tenant.id, email="approver@mobilinkbank.com", name="John Doe", password_hash=security.hash_password(DEMO_PASSWORD), role="approver", department="Finance", avatar_color=colors[2])
    author = models.User(tenant_id=tenant.id, email="author@mobilinkbank.com", name="Aisha Smith", password_hash=security.hash_password(DEMO_PASSWORD), role="author", department="Operations", avatar_color=colors[3])
    # A second Registration Authority officer. The RA refuses to let an officer approve their
    # own certificate request — separation of duties — so a workspace with one officer can
    # never issue that officer a certificate, including the demo login's.
    admin = models.User(tenant_id=tenant.id, email="admin@mobilinkbank.com", name="Bilal Farooq", password_hash=security.hash_password(DEMO_PASSWORD), role="admin", department="Information Technology", avatar_color=colors[4])
    db.add_all([owner, manager, approver, author, admin])
    db.flush()
    users = [owner, manager, approver, author, admin]

    # default approval workflows
    db.add_all([
        models.WorkflowDefinition(tenant_id=tenant.id, name="Standard approval", status="active",
                                  default_for_types=["msa", "vendor", "service", "nda"],
                                  steps=[{"name": "Manager review", "assignee_kind": "role", "assignee_value": "manager"}], created_by=owner.id),
        models.WorkflowDefinition(tenant_id=tenant.id, name="High-value approval", status="active",
                                  default_for_types=["lease", "employment"],
                                  steps=[{"name": "Manager review", "assignee_kind": "role", "assignee_value": "manager"},
                                         {"name": "Owner sign-off", "assignee_kind": "role", "assignee_value": "owner"}], created_by=owner.id),
        models.WorkflowDefinition(tenant_id=tenant.id, name="Procurement (draft)", status="draft", default_for_types=[],
                                  steps=[{"name": "Procurement review", "assignee_kind": "role", "assignee_value": "approver"},
                                         {"name": "Finance review", "assignee_kind": "role", "assignee_value": "manager"},
                                         {"name": "Owner sign-off", "assignee_kind": "role", "assignee_value": "owner"}], created_by=owner.id),
    ])

    record(db, tenant_id=tenant.id, action="tenant.created", actor=owner, object_type="tenant", object_id=tenant.id, object_label=tenant.name)

    today = dt.date.today()
    for i in range(28):
        ctype = rng.choice(_TYPES)
        party = rng.choice(_PARTIES)
        st = rng.choice(_STATUSES)
        start = today - dt.timedelta(days=rng.randint(0, 240))
        months = rng.choice([6, 12, 12, 24, 36])
        end = start + dt.timedelta(days=months * 30)
        # nudge a handful into "expiring soon" territory
        if st == "expiring":
            end = today + dt.timedelta(days=rng.randint(3, 28))
        if st == "expired":
            end = today - dt.timedelta(days=rng.randint(1, 60))
        creator = rng.choice(users)
        ownr = rng.choice(users)
        title = f"{_TYPE_TITLES[ctype]} — {party}"
        # PKR, so the bands line up with the approval matrix (5m Finance, 25m CFO).
        value = rng.choice([0, 850_000, 2_400_000, 4_800_000, 9_600_000,
                            18_000_000, 32_000_000]) if ctype != "nda" else 0
        c = models.Contract(
            tenant_id=tenant.id,
            reference_no=f"C-{start.year}-{i + 1:04d}",
            title=title,
            type=ctype,
            status=st,
            owner_id=ownr.id,
            counterparty=party,
            department=rng.choice(_DEPTS),
            value=value,
            currency="PKR",
            effective_date=start,
            end_date=end,
            renewal_type=rng.choice(["none", "none", "auto", "manual"]),
            governing_law=_LAW,
            risk_level=rng.choice(_RISKS),
            ai_summary=f"{months}-month {_TYPE_TITLES[ctype].lower()} with {party}. Standard commercial terms. (AI summary — verify before relying.)" if rng.random() < 0.7 else "",
            tags=rng.sample(["renewal", "priority", "gov", "regional", "annual", "key-account"], k=rng.randint(0, 2)),
            body=f"# {title}\n\nThis Agreement is made between Mobilink Microfinance Bank ('the Bank') and {party} ('the Counterparty').\n\n## 1. Services\n…\n\n## 2. Term\nThis Agreement runs for {months} months from {start.isoformat()}.\n\n## 3. Fees\n{('PKR ' + format(value, ',') ) if value else 'No fees (NDA).'}\n\n## 4. Confidentiality\n…\n\n## 5. Governing Law\nThis Agreement is governed by the laws of {_LAW}.\n",
            source=rng.choice(["manual", "manual", "template", "ocr"]),
            created_by=creator.id,
        )
        db.add(c)
        db.flush()
        db.add(models.ContractVersion(tenant_id=tenant.id, contract_id=c.id, version_no=1, body=c.body, change_summary="Created", created_by=creator.id))
        _record_journey(db, tenant.id, c, creator, users, rng)
        if rng.random() < 0.4:
            cm = models.Comment(tenant_id=tenant.id, contract_id=c.id, author_id=rng.choice(users).id, author_name=rng.choice(users).name, body=rng.choice(["Please double-check the liability cap.", "Counterparty asked for net-45 payment terms.", "Approved pending the data-residency clause.", "Can we shorten the auto-renew notice to 30 days?"]))
            db.add(cm)
            record(db, tenant_id=tenant.id, action="contract.commented", actor=rng.choice(users), object_type="contract", object_id=c.id, object_label=c.title)
        # obligations — a couple per non-draft contract, with a spread of due dates/statuses so the
        # Obligations tab + reminders surface real data (overdue / due-soon / upcoming / done).
        if st not in ("draft", "expired", "terminated", "voided"):
            for (otitle, odesc, ooff) in rng.sample(_OBLIGATION_TEMPLATES, k=rng.randint(2, 3)):
                due = today + dt.timedelta(days=ooff)
                ostatus = "overdue" if ooff < 0 else ("done" if rng.random() < 0.2 else "pending")
                ob = models.Obligation(
                    tenant_id=tenant.id, contract_id=c.id, title=otitle, description=odesc,
                    due_date=due, owner_id=ownr.id, status=ostatus, created_by=creator.id,
                )
                if ostatus == "done":
                    ob.completed_at = dt.datetime.now() - dt.timedelta(days=rng.randint(1, 20))
                    ob.completed_by_id = ownr.id
                    ob.completed_by_name = ownr.name
                db.add(ob)

    # a couple of notifications for the demo owner
    db.add(models.Notification(tenant_id=tenant.id, user_id=owner.id, type="contract.approval_requested", title="Mariam Khan asked for your approval", body="On \"Master Services Agreement — Indus Logistics\"", object_type="contract"))
    db.add(models.Notification(tenant_id=tenant.id, user_id=owner.id, type="contract.expiring", title="3 contracts expire within 30 days", body="Review renewals on the dashboard.", object_type="contract"))

    # --- clause library + policy -------------------------------------------------------
    # Seeded pre-approved so the library is usable on first run; a demo workspace where every
    # clause sits in `draft` would demonstrate the approval gate and nothing else. Templates
    # below reference these by key, so they have to exist first.
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for spec in _DEMO_CLAUSES:
        alternatives = spec.pop("alternatives", [])
        clause = models.Clause(
            tenant_id=tenant.id, created_by=owner.id, status="active", version_no=1,
            approved_by=owner.id, approved_at=now, **spec,
        )
        db.add(clause)
        db.flush()
        db.add(models.ClauseVersion(
            tenant_id=tenant.id, clause_id=clause.id, version_no=1, title=clause.title,
            body=clause.body, position=clause.position, risk_level=clause.risk_level,
            status="active", change_summary="Seeded", approved_by=owner.id, approved_at=now,
            created_by=owner.id,
        ))
        for rank, alt in enumerate(alternatives, start=1):
            fallback = models.Clause(
                tenant_id=tenant.id, created_by=owner.id, status="active", version_no=1,
                approved_by=owner.id, approved_at=now, parent_id=clause.id,
                fallback_rank=rank, category=clause.category, **alt,
            )
            db.add(fallback)
            db.flush()
            db.add(models.ClauseVersion(
                tenant_id=tenant.id, clause_id=fallback.id, version_no=1,
                title=fallback.title, body=fallback.body, position=fallback.position,
                risk_level=fallback.risk_level, status="active", change_summary="Seeded",
                approved_by=owner.id, approved_at=now, created_by=owner.id,
            ))

    for book in _DEMO_PLAYBOOKS:
        db.add(models.Playbook(tenant_id=tenant.id, created_by=owner.id, **book))

    # reusable contract templates (spawn a pre-filled draft in one click; {{merge}} vars resolve on use)
    # Seeded pre-approved at v1: a demo workspace where every template sits unusable in `draft`
    # would show the approval gate working and the product not.
    for tpl in _DEMO_TEMPLATES:
        t = models.ContractTemplate(
            tenant_id=tenant.id, created_by=owner.id, status="active", is_active=True,
            version_no=1, approved_by=owner.id, approved_at=now,
            effective_from=now.date(), **tpl,
        )
        db.add(t)
        db.flush()
        db.add(models.ContractTemplateVersion(
            tenant_id=tenant.id, template_id=t.id, version_no=1, name=t.name,
            body=t.body or "", fields=list(t.fields or []), status="active",
            change_summary="Seeded", approved_by=owner.id, approved_at=now,
            created_by=owner.id,
        ))

    # Adoption content: help copy, the knowledge base and the training courses (Phase 9).
    # Gap-fill, so this is also safe on an existing workspace — nothing edited is overwritten.
    from . import content_service

    content_service.seed_all(db, tenant.id, tenant.locale or "en")

    db.commit()

    # Everything configured *around* the contract spine — departments, folders, the approval
    # matrix, parties, holds, PKI, envelopes. Kept in its own module and run last because it
    # reads the records created above, and because it is gap-fill: safe to re-run on a
    # workspace somebody is already using.
    from . import demo_seed

    demo_seed.seed_extras(db, tenant.id)
    return True


# Demo templates seeded into a fresh workspace so the Templates page isn't empty on first run.
#
# The first one carries a real intake form so the merge-field journey is demonstrable the
# moment the stack comes up: pick the agreement type, fill the drop-downs, and the draft
# generates itself. The rest are body-only templates, which is still a valid shape.
_DEMO_TEMPLATES: list[dict] = [
    dict(
        name="Merchant Acquiring Agreement", contract_type="vendor",
        description="Onboarding a merchant onto the acquiring estate. Fill the form and the draft generates itself.",
        default_term_months=12, default_renewal_type="auto", default_risk_level="medium",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan",
        default_tags=["merchant", "acquiring", "standard"],
        fields=[
            dict(key="merchant_name", label="Merchant legal name", type="text", required=True,
                 group="Merchant", help="Exactly as registered."),
            dict(key="merchant_ntn", label="NTN", type="text", required=True, group="Merchant"),
            dict(key="region", label="Region", type="select", required=True, group="Merchant",
                 options=["Sindh", "Punjab", "Khyber Pakhtunkhwa", "Balochistan",
                          "Islamabad Capital Territory", "Gilgit-Baltistan", "Azad Jammu & Kashmir"]),
            dict(key="channels", label="Channels", type="multiselect", group="Commercials",
                 options=["POS", "QR", "E-commerce", "ATM"]),
            dict(key="mdr_percent", label="Merchant discount rate (%)", type="number",
                 required=True, group="Commercials", minimum=0, maximum=10),
            dict(key="settlement_days", label="Settlement cycle (days)", type="number",
                 required=True, default=2, group="Commercials", minimum=0, maximum=30),
            dict(key="security_deposit", label="Security deposit", type="money",
                 group="Commercials", minimum=0),
            dict(key="start_date", label="Go-live date", type="date", required=True,
                 group="Commercials"),
        ],
        # The wording that is *policy* comes from the clause library by reference, so improving
        # a clause improves this template and every other one that uses it. Only the wording
        # specific to this agreement type is written inline.
        body=(
            "# Merchant Acquiring Agreement\n\n"
            "This Agreement is made on {{today}} between **{{our_entity}}** (the \"Bank\") and "
            "**{{merchant_name}}**, NTN {{merchant_ntn}}, of {{region}} (the \"Merchant\").\n\n"
            "## 1. Services\n\n"
            "The Bank shall provide acquiring services over the following channels: {{channels}}.\n\n"
            "## 2. Commercials\n\n"
            "1. The Merchant shall pay a merchant discount rate of {{mdr_percent}}% of the value "
            "of each transaction.\n"
            "2. The Bank shall settle net proceeds within {{settlement_days}} working days of "
            "the transaction date.\n"
            "3. The Merchant shall maintain a security deposit of {{security_deposit}} for the "
            "duration of this Agreement.\n\n"
            "## 3. Term\n\n"
            "This Agreement takes effect on {{start_date}} and continues for the term stated "
            "overleaf unless terminated in accordance with clause 4.\n\n"
            "## 4. Termination\n\n"
            "[[clause:termination_for_convenience]]\n\n"
            "## 5. Confidentiality\n\n"
            "[[clause:confidentiality]]\n\n"
            "## 6. Data protection\n\n"
            "[[clause:data_protection]]\n\n"
            "## 7. Limitation of liability\n\n"
            "[[clause:limitation_of_liability]]\n\n"
            "## 8. Governing law\n\n"
            "[[clause:governing_law_pk]]"
        ),
    ),
    dict(
        name="Mutual Non-Disclosure Agreement", contract_type="nda",
        description="Standard mutual NDA for early-stage discussions. 2-year confidentiality term.",
        default_term_months=24, default_renewal_type="none", default_risk_level="low",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan", default_tags=["nda", "mutual", "standard"],
        body=(
            "# Mutual Non-Disclosure Agreement\n\n"
            "This Mutual Non-Disclosure Agreement (the \"Agreement\") is entered into between "
            "**{{counterparty}}** and the Company, effective **{{effective_date}}**.\n\n"
            "## 1. Confidential Information\nEach party may disclose confidential business, technical, and financial information to the other.\n\n"
            "## 2. Obligations\nThe receiving party shall hold all Confidential Information in strict confidence and use it solely to evaluate the potential relationship.\n\n"
            "## 3. Term\nThe confidentiality obligations survive for two (2) years from the date of disclosure.\n\n"
            "## 4. Governing Law\nThis Agreement is governed by the laws of the Islamic Republic of Pakistan."
        ),
    ),
    dict(
        name="Master Services Agreement", contract_type="msa",
        description="Enterprise MSA with SOW framework, 12-month term, auto-renewal.",
        default_term_months=12, default_renewal_type="auto", default_risk_level="medium",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan", default_tags=["msa", "enterprise", "services"],
        body=(
            "# Master Services Agreement\n\n"
            "This Master Services Agreement is made between **{{counterparty}}** (\"Customer\") and the Company "
            "(\"Provider\"), effective **{{effective_date}}**, with a total value of **{{value}}**.\n\n"
            "## 1. Scope of Services\nProvider will deliver the services described in each Statement of Work (\"SOW\") executed under this Agreement.\n\n"
            "## 2. Fees and Payment\nCustomer shall pay all undisputed invoices within thirty (30) days.\n\n"
            "## 3. Term and Termination\nThis Agreement begins on the Effective Date and continues until **{{end_date}}**, renewing automatically for successive terms unless either party gives 60 days notice.\n\n"
            "## 4. Limitation of Liability\nEach party's total aggregate liability shall not exceed the fees paid in the preceding twelve (12) months.\n\n"
            "## 5. Confidentiality\nEach party shall protect the other's Confidential Information."
        ),
    ),
    dict(
        name="Vendor / Supplier Agreement", contract_type="vendor",
        description="Procurement template for goods & services suppliers. Net-30 terms.",
        default_term_months=12, default_renewal_type="manual", default_risk_level="medium",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan", default_tags=["vendor", "procurement", "supplier"],
        body=(
            "# Vendor Agreement\n\n"
            "This Vendor Agreement is between **{{counterparty}}** (\"Vendor\") and the Company, effective **{{effective_date}}**.\n\n"
            "## 1. Supply of Goods/Services\nVendor shall supply the goods and/or services set out in the applicable purchase order.\n\n"
            "## 2. Pricing and Payment\nAll prices are firm for the term. Payment terms are Net-30 from invoice date.\n\n"
            "## 3. Quality and Warranties\nVendor warrants that all deliverables conform to specifications and are free from defects.\n\n"
            "## 4. Term\nThis Agreement remains in effect until **{{end_date}}**."
        ),
    ),
    dict(
        name="Employment Offer Letter", contract_type="employment",
        description="Standard full-time employment offer with at-will terms.",
        default_term_months=12, default_renewal_type="none", default_risk_level="low",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan", default_tags=["employment", "offer", "hr"],
        body=(
            "# Employment Offer Letter\n\n"
            "Dear **{{counterparty}}**,\n\nWe are pleased to offer you employment with the Company, starting **{{effective_date}}**.\n\n"
            "## Position\nYou will be employed in a full-time capacity reporting to your manager.\n\n"
            "## Compensation\nYour annual compensation will be **{{value}}**, paid in accordance with the Company's standard payroll schedule.\n\n"
            "## At-Will Employment\nYour employment is at-will and may be terminated by either party at any time.\n\n"
            "## Confidentiality\nYou agree to protect the Company's confidential and proprietary information."
        ),
    ),
    dict(
        name="SaaS Subscription Agreement", contract_type="service",
        description="Cloud software subscription with annual term and auto-renewal.",
        default_term_months=12, default_renewal_type="auto", default_risk_level="medium",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan", default_tags=["saas", "subscription", "service"],
        body=(
            "# SaaS Subscription Agreement\n\n"
            "This Subscription Agreement is between **{{counterparty}}** (\"Subscriber\") and the Company, effective **{{effective_date}}**.\n\n"
            "## 1. Subscription\nSubscriber receives access to the Company's software-as-a-service platform for the subscription term.\n\n"
            "## 2. Fees\nThe annual subscription fee is **{{value}}**, billed in advance.\n\n"
            "## 3. Data Protection\nThe Company processes Subscriber data in accordance with its Data Processing Addendum and applicable law.\n\n"
            "## 4. Term\nThe subscription runs until **{{end_date}}** and renews automatically for successive annual terms.\n\n"
            "## 5. Service Levels\nThe Company targets 99.9% monthly uptime."
        ),
    ),
    dict(
        name="Commercial Lease Agreement", contract_type="lease",
        description="Office space lease, 36-month term with manual renewal.",
        default_term_months=36, default_renewal_type="manual", default_risk_level="high",
        default_currency="PKR", default_governing_law="Islamic Republic of Pakistan", default_tags=["lease", "property", "office"],
        body=(
            "# Commercial Lease Agreement\n\n"
            "This Lease is between **{{counterparty}}** (\"Tenant\") and the Company (\"Landlord\"), effective **{{effective_date}}**.\n\n"
            "## 1. Premises\nLandlord leases the described commercial premises to Tenant.\n\n"
            "## 2. Rent\nTenant shall pay rent totaling **{{value}}** over the term, payable monthly in advance.\n\n"
            "## 3. Term\nThe lease term runs from the Effective Date through **{{end_date}}**.\n\n"
            "## 4. Maintenance\nTenant shall keep the premises in good repair, ordinary wear and tear excepted.\n\n"
            "## 5. Governing Law\nThis Lease is governed by the laws of the Islamic Republic of Pakistan."
        ),
    ),
]


# The clause library a fresh workspace starts with. Deliberately small: enough to show
# composition, alternatives and a policy check, not a pretend legal department.
_DEMO_CLAUSES: list[dict] = [
    dict(
        key="confidentiality", title="Confidentiality", category="Confidentiality",
        position="preferred", risk_level="low",
        guidance="The standard mutual position. Use unless the counterparty is a regulator.",
        body=("Each party shall hold the other's Confidential Information in strict confidence "
              "and shall not disclose it to any third party without prior written consent. "
              "This obligation survives termination of this Agreement for a period of three "
              "(3) years."),
    ),
    dict(
        key="limitation_of_liability", title="Limitation of liability",
        category="Liability & Indemnity", position="preferred", risk_level="high",
        guidance="Our standard cap. Anything above 1x fees needs Legal and the CFO.",
        body=("The total aggregate liability of either party arising out of or in connection "
              "with this Agreement shall not exceed the total fees paid or payable in the "
              "twelve (12) months immediately preceding the event giving rise to the claim."),
        alternatives=[
            dict(key="limitation_of_liability_2x", title="Liability capped at 2x fees",
                 position="acceptable", risk_level="high",
                 guidance="Acceptable where the contract value is under PKR 5m and the "
                          "counterparty holds no customer data.",
                 body=("The total aggregate liability of either party arising out of or in "
                       "connection with this Agreement shall not exceed two times (2x) the "
                       "total fees paid or payable in the twelve (12) months immediately "
                       "preceding the event giving rise to the claim.")),
            dict(key="limitation_of_liability_carveout",
                 title="Liability cap with data-breach carve-out",
                 position="fallback", risk_level="critical",
                 guidance="Last resort. Requires CFO sign-off — the carve-out is uncapped.",
                 body=("The total aggregate liability of either party under this Agreement "
                       "shall not exceed the total fees paid in the preceding twelve (12) "
                       "months, save that no limitation shall apply to liability arising from "
                       "a breach of applicable data protection law.")),
        ],
    ),
    dict(
        key="data_protection", title="Data protection", category="Data Protection",
        position="preferred", risk_level="high",
        guidance="Mandatory wherever the counterparty processes customer data. Reflects SBP "
                 "expectations on outsourcing.",
        body=("The Supplier shall process personal data only on the documented instructions of "
              "the Bank, shall implement appropriate technical and organisational measures to "
              "protect it, and shall not transfer it outside the Islamic Republic of Pakistan "
              "without the Bank's prior written consent."),
    ),
    dict(
        key="termination_for_convenience", title="Termination for convenience",
        category="Termination", position="preferred", risk_level="medium",
        guidance="Keeps the Bank's exit open. Push hard to retain this.",
        body=("Either party may terminate this Agreement at any time by giving not less than "
              "sixty (60) days' prior written notice to the other party, without liability "
              "other than for amounts accrued up to the date of termination."),
    ),
    dict(
        key="governing_law_pk", title="Governing law — Pakistan", category="Governing Law",
        position="preferred", risk_level="low",
        guidance="Non-negotiable for regulated agreements.",
        body=("This Agreement shall be governed by and construed in accordance with the laws "
              "of the Islamic Republic of Pakistan, and the courts at Karachi shall have "
              "exclusive jurisdiction."),
    ),
    dict(
        key="unlimited_liability", title="Unlimited liability (prohibited)",
        category="Liability & Indemnity", position="fallback", risk_level="critical",
        guidance="Recorded so the playbook can detect it. Never agree to this wording.",
        body=("Each party accepts unlimited liability for any and all losses, damages and "
              "expenses arising under this Agreement, without cap, exclusion or limitation of "
              "any kind."),
    ),
]


# Policy. The house rules apply to everything; the vendor rules bite on supplier paper.
_DEMO_PLAYBOOKS: list[dict] = [
    dict(
        name="House rules", description="Applies to every agreement, whatever the type.",
        contract_type="", applies_when={}, status="active",
        rules=[
            dict(clause_key="governing_law_pk", kind="required", severity="blocker",
                 guidance="Regulated agreements must be governed by Pakistani law."),
            dict(clause_key="unlimited_liability", kind="prohibited", severity="blocker",
                 guidance="Uncapped liability is never acceptable."),
        ],
    ),
    dict(
        name="Vendor and outsourcing policy",
        description="Supplier agreements, including anything touching customer data.",
        contract_type="vendor", applies_when={}, status="active",
        rules=[
            dict(clause_key="confidentiality", kind="required", severity="blocker"),
            dict(clause_key="limitation_of_liability", kind="required", severity="blocker",
                 guidance="A changed cap needs Legal and the CFO. Fallback wordings are in "
                          "the library."),
            dict(clause_key="data_protection", kind="required", severity="blocker",
                 guidance="SBP outsourcing expectations."),
            dict(clause_key="termination_for_convenience", kind="required",
                 severity="warning",
                 guidance="Preferred, not mandatory. Losing it is worth a conversation."),
        ],
    ),
]
