"""Seeds a demo workspace if the DB is empty. Login: demo@acme.io / demo1234"""

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

DEMO_EMAIL = "demo@acme.io"
DEMO_PASSWORD = "demo1234"

_PARTIES = ["Acme Corporation", "Globex LLC", "Northstar Industries", "Initech FZE", "Stark Trading Co.", "Wayne Holdings", "Umbrella Services", "Hooli Ltd"]
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
_DEPTS = ["Procurement", "Legal", "HR", "Real Estate", "Operations", "Finance"]
_LAWS = ["Oman", "UAE", "Saudi Arabia", "England & Wales", "Bahrain"]
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


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(models.Tenant).limit(1)) is not None:
        return False
    rng = random.Random(42)

    tenant_id = uuid.uuid4().hex
    tenant = models.Tenant(id=tenant_id, name="Acme Holdings", slug="acme", locale="en", currency="USD", plan="business")
    db.add(tenant)
    db.flush()

    colors = ["#3E7BFA", "#8B7BF5", "#2BC0D4", "#F6B83C", "#F5736B", "#3FBF7F"]
    owner = models.User(tenant_id=tenant.id, email=DEMO_EMAIL, name="Demo Owner", password_hash=security.hash_password(DEMO_PASSWORD), role="owner", avatar_color=colors[0])
    manager = models.User(tenant_id=tenant.id, email="manager@acme.io", name="Mariam Khan", password_hash=security.hash_password(DEMO_PASSWORD), role="manager", avatar_color=colors[1])
    approver = models.User(tenant_id=tenant.id, email="approver@acme.io", name="John Doe", password_hash=security.hash_password(DEMO_PASSWORD), role="approver", avatar_color=colors[2])
    author = models.User(tenant_id=tenant.id, email="author@acme.io", name="Aisha Smith", password_hash=security.hash_password(DEMO_PASSWORD), role="author", avatar_color=colors[3])
    db.add_all([owner, manager, approver, author])
    db.flush()
    users = [owner, manager, approver, author]

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
        value = rng.choice([0, 24000, 48000, 96000, 120000, 250000, 480000]) if ctype != "nda" else 0
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
            currency="USD",
            effective_date=start,
            end_date=end,
            renewal_type=rng.choice(["none", "none", "auto", "manual"]),
            governing_law=rng.choice(_LAWS),
            risk_level=rng.choice(_RISKS),
            ai_summary=f"{months}-month {_TYPE_TITLES[ctype].lower()} with {party}. Standard commercial terms. (AI summary — verify before relying.)" if rng.random() < 0.7 else "",
            tags=rng.sample(["renewal", "priority", "gov", "regional", "annual", "key-account"], k=rng.randint(0, 2)),
            body=f"# {title}\n\nThis Agreement is made between Acme Holdings ('Provider') and {party} ('Client').\n\n## 1. Services\n…\n\n## 2. Term\nThis Agreement runs for {months} months from {start.isoformat()}.\n\n## 3. Fees\n{('USD ' + format(value, ',') ) if value else 'No fees (NDA).'}\n\n## 4. Confidentiality\n…\n\n## 5. Governing Law\nThis Agreement is governed by the laws of {rng.choice(_LAWS)}.\n",
            source=rng.choice(["manual", "manual", "template", "ocr"]),
            created_by=creator.id,
        )
        db.add(c)
        db.flush()
        db.add(models.ContractVersion(tenant_id=tenant.id, contract_id=c.id, version_no=1, body=c.body, change_summary="Created", created_by=creator.id))
        record(db, tenant_id=tenant.id, action="contract.created", actor=creator, object_type="contract", object_id=c.id, object_label=c.title, meta={"source": c.source})
        if st not in ("draft",):
            record(db, tenant_id=tenant.id, action="contract.status_changed", actor=rng.choice(users), object_type="contract", object_id=c.id, object_label=c.title, meta={"from": "draft", "to": st})
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
    db.add(models.Notification(tenant_id=tenant.id, user_id=owner.id, type="contract.approval_requested", title="Mariam Khan asked for your approval", body="On \"Master Services Agreement — Globex LLC\"", object_type="contract"))
    db.add(models.Notification(tenant_id=tenant.id, user_id=owner.id, type="contract.expiring", title="3 contracts expire within 30 days", body="Review renewals on the dashboard.", object_type="contract"))

    # reusable contract templates (spawn a pre-filled draft in one click; {{merge}} vars resolve on use)
    for tpl in _DEMO_TEMPLATES:
        db.add(models.ContractTemplate(tenant_id=tenant.id, created_by=owner.id, **tpl))

    db.commit()
    return True


# Demo templates seeded into a fresh workspace so the Templates page isn't empty on first run.
_DEMO_TEMPLATES: list[dict] = [
    dict(
        name="Mutual Non-Disclosure Agreement", contract_type="nda",
        description="Standard mutual NDA for early-stage discussions. 2-year confidentiality term.",
        default_term_months=24, default_renewal_type="none", default_risk_level="low",
        default_currency="USD", default_governing_law="DIFC", default_tags=["nda", "mutual", "standard"],
        body=(
            "# Mutual Non-Disclosure Agreement\n\n"
            "This Mutual Non-Disclosure Agreement (the \"Agreement\") is entered into between "
            "**{{counterparty}}** and the Company, effective **{{effective_date}}**.\n\n"
            "## 1. Confidential Information\nEach party may disclose confidential business, technical, and financial information to the other.\n\n"
            "## 2. Obligations\nThe receiving party shall hold all Confidential Information in strict confidence and use it solely to evaluate the potential relationship.\n\n"
            "## 3. Term\nThe confidentiality obligations survive for two (2) years from the date of disclosure.\n\n"
            "## 4. Governing Law\nThis Agreement is governed by the laws of the DIFC."
        ),
    ),
    dict(
        name="Master Services Agreement", contract_type="msa",
        description="Enterprise MSA with SOW framework, 12-month term, auto-renewal.",
        default_term_months=12, default_renewal_type="auto", default_risk_level="medium",
        default_currency="USD", default_governing_law="State of Delaware", default_tags=["msa", "enterprise", "services"],
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
        default_currency="USD", default_governing_law="State of New York", default_tags=["vendor", "procurement", "supplier"],
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
        default_currency="USD", default_governing_law="State of California", default_tags=["employment", "offer", "hr"],
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
        default_currency="USD", default_governing_law="DIFC", default_tags=["saas", "subscription", "service"],
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
        default_currency="USD", default_governing_law="State of Texas", default_tags=["lease", "property", "office"],
        body=(
            "# Commercial Lease Agreement\n\n"
            "This Lease is between **{{counterparty}}** (\"Tenant\") and the Company (\"Landlord\"), effective **{{effective_date}}**.\n\n"
            "## 1. Premises\nLandlord leases the described commercial premises to Tenant.\n\n"
            "## 2. Rent\nTenant shall pay rent totaling **{{value}}** over the term, payable monthly in advance.\n\n"
            "## 3. Term\nThe lease term runs from the Effective Date through **{{end_date}}**.\n\n"
            "## 4. Maintenance\nTenant shall keep the premises in good repair, ordinary wear and tear excepted.\n\n"
            "## 5. Governing Law\nThis Lease is governed by the laws of the State of Texas."
        ),
    ),
]
