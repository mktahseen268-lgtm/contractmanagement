"""Fills the demo workspace with the records the rest of the product needs to look alive.

`seed.py` covers the contract spine — agreements, templates, clauses, playbooks, obligations,
workflow definitions. Everything configured *around* that spine was left empty, so roughly two
thirds of the navigation opened onto "no records yet" on a freshly seeded workspace. In a
walkthrough an empty page does not read as an unconfigured page; it reads as an unbuilt one.

This module is **gap-fill, not fixture**. Each block asks whether the workspace already has rows
of that kind and returns early if it does, so it is safe to run against a workspace somebody has
been using — it adds what is missing and never edits or replaces what is there. That is what
makes it re-runnable, which matters because the interesting failure is running it twice by
accident rather than running it once.

Run standalone against an existing database:

    python -m app.demo_seed
"""

import datetime as dt
import hashlib
import random
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

#: Everything derives from one seeded generator, so two runs against two fresh databases
#: produce the same workspace. A demo that looks different every time is a demo nobody can
#: rehearse.
SEED = 1947

_DEPTS = [
    ("Procurement", "CC-4100", "Head Office, Karachi"),
    ("Legal", "CC-1200", "Head Office, Karachi"),
    ("Human Resources", "CC-3300", "Head Office, Karachi"),
    ("Real Estate & Administration", "CC-5200", "Regional Office, Lahore"),
    ("Operations", "CC-2100", "Head Office, Karachi"),
    ("Finance", "CC-1100", "Head Office, Karachi"),
    ("Information Technology", "CC-6100", "Head Office, Karachi"),
    ("Branchless Banking", "CC-7200", "Head Office, Islamabad"),
]

#: (path, roles-that-can-see-it). Parents are created before children by sorting on depth.
_FOLDERS = [
    ("/Legal", []),
    ("/Legal/Vendors", []),
    ("/Legal/Vendors/2026", []),
    ("/Legal/Litigation", ["owner", "manager"]),
    ("/Procurement", []),
    ("/Procurement/Merchant Acquiring", []),
    ("/Procurement/IT & Software", []),
    ("/Human Resources", ["owner", "manager"]),
    ("/Human Resources/Employment", ["owner", "manager"]),
    ("/Real Estate", []),
    ("/Real Estate/Branch Leases", []),
    ("/Branchless Banking", []),
    ("/Branchless Banking/Agent Network", []),
]

_CUSTOM_FIELDS = [
    dict(contract_type="", key="sbp_category", label="SBP reporting category", type="select",
         required=True, position=1,
         options=["Outsourcing", "Vendor supply", "Employment", "Property", "Other"],
         help="Drives the quarterly regulatory return. Ask Compliance if unsure."),
    dict(contract_type="", key="business_owner", label="Business owner", type="text",
         required=True, position=2, help="The person accountable, not the person who drafted it."),
    dict(contract_type="vendor", key="data_processed", label="Processes customer data",
         type="select", required=True, position=3, options=["No", "Yes — masked", "Yes — full"],
         help="Anything other than 'No' pulls in the outsourcing playbook."),
    dict(contract_type="vendor", key="exit_notice_days", label="Exit notice (days)",
         type="number", position=4, help="Notice the Bank must give to walk away."),
    dict(contract_type="lease", key="branch_code", label="Branch code", type="text",
         required=True, position=5),
    dict(contract_type="lease", key="area_sqft", label="Area (sq ft)", type="number", position=6),
]

_CUSTOM_ROLES = [
    dict(key="compliance_reviewer", name="Compliance Reviewer", base_role="approver",
         description="Reviews regulatory exposure. Reads everything, approves, signs nothing.",
         grants=["contract.read_all", "report.read"], revokes=["contract.sign"]),
    dict(key="branch_officer", name="Branch Officer", base_role="author",
         description="Raises agreements at a branch and assists walk-in customers signing.",
         grants=["signature.assist"], revokes=["contract.delete", "contract.read_all"]),
    dict(key="auditor", name="Internal Auditor", base_role="viewer",
         description="Read-only across the workspace, including the audit trail. Changes nothing.",
         grants=["audit.read", "contract.read_all", "report.read"], revokes=[]),
    dict(key="vendor_manager", name="Vendor Manager", base_role="manager",
         description="Owns the supplier estate. Cannot alter approval policy.",
         grants=["party.write"], revokes=["workflow.write"]),
]

#: Value bands in PKR. The bands overlap nothing: `min_value` is inclusive, `max_value`
#: exclusive, and the top band is unbounded.
_APPROVAL_RULES = [
    dict(name="Above PKR 5m — Finance review", min_value=5_000_000, max_value=25_000_000,
         currency="PKR", stage_name="Finance review", stage_policy="all", sla_hours=24,
         priority=10,
         stage_steps=[dict(name="Head of Finance", assignee_kind="role", assignee_value="manager")]),
    dict(name="Above PKR 25m — CFO sign-off", min_value=25_000_000, max_value=None,
         currency="PKR", stage_name="CFO sign-off", stage_policy="all", sla_hours=48,
         priority=20,
         stage_steps=[dict(name="Chief Financial Officer", assignee_kind="role", assignee_value="owner")]),
    dict(name="Critical risk — Legal and Compliance", risk_level="critical",
         stage_name="Legal and Compliance", stage_policy="all", sla_hours=24, priority=30,
         stage_steps=[dict(name="Head of Legal", assignee_kind="role", assignee_value="manager"),
                      dict(name="Compliance", assignee_kind="role", assignee_value="approver")]),
    dict(name="Outsourcing — Information Security", contract_type="vendor",
         stage_name="Information Security", stage_policy="any", stage_threshold=1,
         sla_hours=48, priority=15,
         stage_steps=[dict(name="CISO office", assignee_kind="role", assignee_value="approver")]),
    dict(name="Non-standard paper — Legal", non_standard_only=True,
         stage_name="Legal review (non-standard)", stage_policy="all", sla_hours=72, priority=25,
         stage_steps=[dict(name="Head of Legal", assignee_kind="role", assignee_value="manager")]),
]

_AUTHORITIES = [
    dict(name="Up to PKR 5m — Department head", min_value=0, max_value=5_000_000,
         currency="PKR", required_role="manager", priority=10,
         notes="Routine departmental spend."),
    dict(name="PKR 5m to 25m — Chief Operating Officer", min_value=5_000_000,
         max_value=25_000_000, currency="PKR", required_role="manager",
         signatories_required=2, priority=20,
         notes="Joint signature: COO with the sponsoring department head."),
    dict(name="Above PKR 25m — Chief Executive", min_value=25_000_000, max_value=None,
         currency="PKR", required_role="owner", priority=30,
         notes="Board-reported. No delegation below CEO."),
    dict(name="Property leases — Head of Real Estate",
         department="Real Estate & Administration", contract_type="lease",
         required_role="manager", priority=40,
         notes="Any value. Property sits outside the general value bands."),
]

#: Pakistan public holidays. Dated rather than computed — the Islamic dates move against the
#: Gregorian calendar and a rule that guesses them is worse than a list somebody maintains.
_HOLIDAYS = [
    ("2026-02-05", "Kashmir Day"), ("2026-03-23", "Pakistan Day"),
    ("2026-03-20", "Eid al-Fitr"), ("2026-03-21", "Eid al-Fitr (2nd day)"),
    ("2026-03-22", "Eid al-Fitr (3rd day)"), ("2026-05-01", "Labour Day"),
    ("2026-05-27", "Eid al-Adha"), ("2026-05-28", "Eid al-Adha (2nd day)"),
    ("2026-06-26", "Ashura"), ("2026-08-14", "Independence Day"),
    ("2026-09-04", "Eid Milad-un-Nabi"), ("2026-12-25", "Quaid-e-Azam Day"),
]

_SANCTIONS = [
    dict(source="ofac", list_name="SDN", name="Umbrella Services Holding Co",
         aliases=["Umbrella Services", "Umbrella Svc Holding"], entity_type="entity",
         country="Cyprus", programme="CYBER2", reference="OFAC-SDN-41827"),
    dict(source="ofac", list_name="SDN", name="Initech FZE Trading",
         aliases=["Initech FZE", "Initech Free Zone"], entity_type="entity",
         country="United Arab Emirates", programme="IRAN-EO13846", reference="OFAC-SDN-39104"),
    dict(source="un", list_name="UNSC Consolidated", name="Nadeem Ahmed Qureshi",
         aliases=["N. A. Qureshi", "Nadim Qureshi"], entity_type="individual",
         country="Pakistan", programme="1267/1989", reference="UN-QDi.412"),
    dict(source="eu", list_name="EU Consolidated", name="Stark Trading Company Limited",
         aliases=["Stark Trading Co", "Stark Trading Ltd"], entity_type="entity",
         country="Russian Federation", programme="EU-2022/328", reference="EU-3391"),
    dict(source="local", list_name="NACTA Proscribed", name="Wayne Holdings Private Limited",
         aliases=["Wayne Holdings", "Wayne Hldgs Pvt Ltd"], entity_type="entity",
         country="Pakistan", programme="ATA-1997 Schedule I", reference="NACTA-0221"),
]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _empty(db: Session, model, tenant_id: str | None) -> bool:
    """True when this workspace has no rows of `model` yet.

    `tenant_id=None` is for the genuinely global tables — the sanctions snapshot is the same
    list for everybody and is deliberately not workspace-scoped.
    """
    stmt = select(model).limit(1)
    if tenant_id is not None:
        stmt = stmt.filter_by(tenant_id=tenant_id)
    return db.scalar(stmt) is None


def _name_key(name: str) -> str:
    """Normalise a party name for duplicate detection: case-folded, entity suffixes dropped."""
    key = name.casefold()
    for suffix in (" private limited", " pvt ltd", " (pvt) ltd", " limited", " ltd", " llc",
                   " fze", " inc", " corporation", " corp", " co", " company", " holdings"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return "".join(ch for ch in key if ch.isalnum() or ch == " ").strip()


def seed_extras(db: Session, tenant_id: str) -> dict[str, int]:
    """Fill in everything `seed.py` leaves empty. Returns what each block actually created."""
    rng = random.Random(SEED)
    now = _now()
    today = dt.date.today()
    made: dict[str, int] = {}

    users = list(db.scalars(select(models.User).filter_by(tenant_id=tenant_id)).all())
    if not users:
        return made
    by_role = {u.role: u for u in users}
    owner = by_role.get("owner", users[0])
    manager = by_role.get("manager", owner)
    approver = by_role.get("approver", owner)
    author = by_role.get("author", owner)

    contracts = list(db.scalars(select(models.Contract).filter_by(tenant_id=tenant_id)).all())

    made["departments"] = _seed_departments(db, tenant_id, [owner, manager, approver, author])
    made["department_links"] = _link_departments(db, tenant_id, contracts)
    made["folders"] = _seed_folders(db, tenant_id, owner)
    made["custom_fields"] = _seed_custom_fields(db, tenant_id, owner)
    made["custom_roles"] = _seed_custom_roles(db, tenant_id, owner)
    made["approval_rules"] = _seed_approval_rules(db, tenant_id, owner)
    made["authorities"] = _seed_authorities(db, tenant_id, owner)
    made["delegations"] = _seed_delegations(db, tenant_id, now, owner, manager, approver)
    made["holidays"] = _seed_holidays(db, tenant_id)
    made["sanctions"] = _seed_sanctions(db, today)
    made["parties"] = _seed_parties(db, tenant_id, owner, contracts)
    made["relations"] = _seed_relations(db, tenant_id, owner, contracts, rng)
    made["legal_holds"] = _seed_legal_holds(db, tenant_id, owner, contracts, now)
    made["temporary_access"] = _seed_temporary_access(db, tenant_id, owner, contracts, now)
    made["webhooks"] = _seed_webhooks(db, tenant_id, owner, now)
    made["api_keys"] = _seed_api_keys(db, tenant_id, owner, now)
    made["versions"] = _seed_versions(db, tenant_id, contracts, owner, manager, rng)
    made["workflow_runs"] = _seed_workflow_runs(db, tenant_id, contracts, owner, manager, rng)
    made["envelopes"] = _seed_envelopes(db, tenant_id, contracts, owner, rng)
    made["pki"] = _seed_pki(db, tenant_id, owner, users)

    db.commit()
    return {k: v for k, v in made.items() if v}


# ------------------------------------------------------------------------------------------
# Reference data — the configuration a workspace is set up with before anyone drafts anything
# ------------------------------------------------------------------------------------------


def _seed_departments(db: Session, tenant_id: str, leads: list) -> int:
    if not _empty(db, models.Department, tenant_id):
        return 0
    for i, (name, cc, region) in enumerate(_DEPTS):
        db.add(models.Department(tenant_id=tenant_id, name=name, cost_centre=cc, region=region,
                                 lead_user_id=leads[i % len(leads)].id, is_active=True))
    return len(_DEPTS)


def _link_departments(db: Session, tenant_id: str, contracts: list) -> int:
    """Point each agreement at the department record whose name it already carries.

    The name is what the seed writes; the id is what the segmentation, the obligation filter
    and the per-department count join on. Without this the Departments screen reports every
    department as holding nothing.
    """
    # The session runs with autoflush off, so the departments added moments ago are still
    # pending and this query would return nothing without an explicit flush — leaving every
    # agreement unlinked and every department reporting zero.
    db.flush()
    by_name = {d.name.lower(): d.id for d in db.scalars(
        select(models.Department).filter_by(tenant_id=tenant_id))}
    linked = 0
    for c in contracts:
        if getattr(c, "department_id", None):
            continue
        match = by_name.get((c.department or "").strip().lower())
        if match:
            c.department_id = match
            linked += 1
    return linked


def _seed_folders(db: Session, tenant_id: str, owner) -> int:
    if not _empty(db, models.Folder, tenant_id):
        return 0
    # Shallowest first, so a child always finds its parent already inserted.
    ids: dict[str, str] = {}
    for path, roles in sorted(_FOLDERS, key=lambda f: f[0].count("/")):
        parent_path = path.rsplit("/", 1)[0]
        folder = models.Folder(
            tenant_id=tenant_id, name=path.rsplit("/", 1)[-1], path=path,
            parent_id=ids.get(parent_path), visible_to_roles=roles, created_by=owner.id,
        )
        db.add(folder)
        db.flush()
        ids[path] = folder.id
    return len(_FOLDERS)


def _seed_custom_fields(db: Session, tenant_id: str, owner) -> int:
    if not _empty(db, models.CustomFieldDef, tenant_id):
        return 0
    for spec in _CUSTOM_FIELDS:
        db.add(models.CustomFieldDef(tenant_id=tenant_id, created_by=owner.id, is_active=True,
                                     **spec))
    return len(_CUSTOM_FIELDS)


def _seed_custom_roles(db: Session, tenant_id: str, owner) -> int:
    if not _empty(db, models.CustomRole, tenant_id):
        return 0
    for spec in _CUSTOM_ROLES:
        db.add(models.CustomRole(tenant_id=tenant_id, created_by=owner.id, is_active=True, **spec))
    return len(_CUSTOM_ROLES)


def _seed_approval_rules(db: Session, tenant_id: str, owner) -> int:
    if not _empty(db, models.ApprovalRule, tenant_id):
        return 0
    for spec in _APPROVAL_RULES:
        db.add(models.ApprovalRule(tenant_id=tenant_id, created_by=owner.id, is_active=True,
                                   **spec))
    return len(_APPROVAL_RULES)


def _seed_authorities(db: Session, tenant_id: str, owner) -> int:
    if not _empty(db, models.SignatoryAuthority, tenant_id):
        return 0
    for spec in _AUTHORITIES:
        db.add(models.SignatoryAuthority(tenant_id=tenant_id, created_by=owner.id, is_active=True,
                                         **spec))
    return len(_AUTHORITIES)


def _seed_delegations(db: Session, tenant_id: str, now, owner, manager, approver) -> int:
    if not _empty(db, models.Delegation, tenant_id):
        return 0
    # One live delegation and one that has already lapsed, because the screen has to show the
    # difference between "cover is in place" and "cover has expired" to be worth looking at.
    db.add(models.Delegation(
        tenant_id=tenant_id, from_user_id=manager.id, to_user_id=approver.id, scope="all",
        starts_at=now - dt.timedelta(days=2), ends_at=now + dt.timedelta(days=9),
        reason="Annual leave — full cover on all approvals.", is_active=True,
        created_by=owner.id))
    db.add(models.Delegation(
        tenant_id=tenant_id, from_user_id=owner.id, to_user_id=manager.id, scope="nda",
        starts_at=now - dt.timedelta(days=40), ends_at=now - dt.timedelta(days=26),
        reason="Overseas travel — non-disclosure agreements only.", is_active=False,
        created_by=owner.id))
    return 2


def _seed_holidays(db: Session, tenant_id: str) -> int:
    if not _empty(db, models.Holiday, tenant_id):
        return 0
    for iso, name in _HOLIDAYS:
        db.add(models.Holiday(tenant_id=tenant_id, day=dt.date.fromisoformat(iso), name=name))
    return len(_HOLIDAYS)


def _seed_sanctions(db: Session, today) -> int:
    # Global by design — not workspace-scoped, so the guard has no tenant to filter on.
    if not _empty(db, models.SanctionsEntry, None):
        return 0
    for spec in _SANCTIONS:
        db.add(models.SanctionsEntry(
            name_key=_name_key(spec["name"]), snapshot_date=today - dt.timedelta(days=3),
            is_active=True, **spec))
    return len(_SANCTIONS)


# ------------------------------------------------------------------------------------------
# Records that hang off the agreements already seeded
# ------------------------------------------------------------------------------------------


def _seed_parties(db: Session, tenant_id: str, owner, contracts: list) -> int:
    """Promote each distinct counterparty string to a real party record, and point the
    agreements at it. This is what makes "total exposure to Acme" answerable at all."""
    if not _empty(db, models.Party, tenant_id):
        return 0

    kyc = ["verified", "verified", "verified", "pending", "none", "rejected"]
    regions = ["Sindh", "Punjab", "Islamabad Capital Territory", "Khyber Pakhtunkhwa"]
    names = sorted({(c.counterparty or "").strip() for c in contracts if (c.counterparty or "").strip()})

    by_name: dict[str, models.Party] = {}
    for i, name in enumerate(names):
        party = models.Party(
            tenant_id=tenant_id, name=name, name_key=_name_key(name),
            registration_no=f"NTN-{4200000 + i * 1373:07d}",
            entity_type="company", jurisdiction="Islamic Republic of Pakistan",
            region=regions[i % len(regions)], kyc_status=kyc[i % len(kyc)],
            kyc_note=("Documents verified against SECP register."
                      if kyc[i % len(kyc)] == "verified" else
                      "Awaiting certified incorporation documents."),
            risk_score=(i * 17) % 100,
            contact_name=f"Relationship Manager {i + 1}",
            contact_email=f"contact{i + 1}@{_name_key(name).replace(' ', '')[:14] or 'party'}.example",
            contact_phone=f"+92 21 {3500000 + i * 911:07d}",
            address=f"Plot {10 + i}, Block {chr(65 + i % 6)}, {regions[i % len(regions)]}",
            tags=["strategic"] if i % 4 == 0 else [], is_active=True, created_by=owner.id,
        )
        db.add(party)
        by_name[name] = party
    db.flush()

    for c in contracts:
        party = by_name.get((c.counterparty or "").strip())
        if party is not None and getattr(c, "party_id", None) in (None, ""):
            c.party_id = party.id
    return len(by_name)


def _seed_relations(db: Session, tenant_id: str, owner, contracts: list, rng) -> int:
    """Amendment and renewal chains, so the repository can answer "what is actually in force"."""
    if not _empty(db, models.ContractRelation, tenant_id):
        return 0

    live = [c for c in contracts if c.status in ("active", "expiring", "signed")]
    if len(live) < 4:
        return 0

    made = 0
    for parent in rng.sample(live, k=min(4, len(live))):
        # An amendment is a separate agreement that points back at the one it changes.
        child = models.Contract(
            tenant_id=tenant_id,
            reference_no=f"{parent.reference_no}-A1",
            title=f"Amendment No. 1 — {parent.title}",
            type=parent.type, status="active", owner_id=parent.owner_id,
            counterparty=parent.counterparty, party_id=getattr(parent, "party_id", None),
            department=parent.department, value=parent.value, currency=parent.currency,
            effective_date=parent.effective_date + dt.timedelta(days=90) if parent.effective_date else None,
            end_date=parent.end_date, governing_law=parent.governing_law,
            risk_level=parent.risk_level, source="manual", created_by=owner.id,
            body=(f"# Amendment No. 1 to {parent.title}\n\n"
                  f"This Amendment is made between the parties to {parent.reference_no} and "
                  f"amends that agreement as set out below. All other terms remain unchanged.\n\n"
                  "## 1. Amended commercials\n\nClause 2 (Commercials) is deleted and replaced "
                  "with the revised schedule attached at Annexure A.\n\n"
                  "## 2. Effect\n\nThis Amendment takes effect on the date of the last signature "
                  "and forms part of the principal agreement."),
        )
        db.add(child)
        db.flush()
        db.add(models.ContractVersion(
            tenant_id=tenant_id, contract_id=child.id, version_no=1, body=child.body,
            change_summary="Created", created_by=owner.id))
        db.add(models.ContractRelation(
            tenant_id=tenant_id, parent_id=parent.id, child_id=child.id, kind="amendment_of",
            sequence=1, note="Revised commercial schedule.", created_by=owner.id))
        made += 1
    return made


def _seed_legal_holds(db: Session, tenant_id: str, owner, contracts: list, now) -> int:
    if not _empty(db, models.LegalHold, tenant_id):
        return 0

    held = [c for c in contracts if c.status in ("active", "expired", "expiring")][:5]
    if not held:
        return 0

    active_ids = [c.id for c in held[:3]]
    db.add(models.LegalHold(
        tenant_id=tenant_id, matter="Qureshi v. Bank — commercial dispute",
        reference="LIT-2026-014",
        reason=("Suit filed in the Sindh High Court concerning vendor performance. All "
                "agreements with the counterparty and their amendments are preserved until "
                "the matter concludes."),
        contract_ids=active_ids, status="active", custodian="Head of Legal",
        placed_by=owner.id, placed_at=now - dt.timedelta(days=21)))
    db.add(models.LegalHold(
        tenant_id=tenant_id, matter="SBP inspection — outsourcing sample",
        reference="REG-2025-207",
        reason="Regulatory inspection sample. Released once the inspection report was issued.",
        contract_ids=[c.id for c in held[3:5]], status="released", custodian="Compliance",
        placed_by=owner.id, placed_at=now - dt.timedelta(days=180),
        released_by=owner.id, released_at=now - dt.timedelta(days=95),
        release_reason="Inspection closed with no adverse finding."))

    # The flag on the agreement is what every existing check reads; it is derived from whether
    # an *active* hold covers it, so the released matter deliberately sets nothing.
    for c in held[:3]:
        c.legal_hold = True
    return 2


def _seed_temporary_access(db: Session, tenant_id: str, owner, contracts: list, now) -> int:
    """Negotiation-room links for external counsel — one live, one expired, one revoked."""
    if not _empty(db, models.TemporaryAccess, tenant_id):
        return 0

    targets = [c for c in contracts if c.status in ("in_review", "draft", "changes_requested")][:3]
    if not targets:
        return 0

    specs = [
        ("aliya.raza@counsel.example", "Aliya Raza", "Raza & Co Advocates", "comment", "active",
         now + dt.timedelta(days=6), 4),
        ("j.mahmood@counsel.example", "Junaid Mahmood", "Mahmood Legal", "view", "expired",
         now - dt.timedelta(days=3), 11),
        ("s.iqbal@vendor.example", "Sana Iqbal", "Northstar Industries", "view", "revoked",
         now + dt.timedelta(days=2), 1),
    ]
    for contract, (email, name, org, scope, status, expires, views) in zip(targets, specs):
        db.add(models.TemporaryAccess(
            tenant_id=tenant_id, contract_id=contract.id, email=email, name=name,
            organisation=org, scope=scope, status=status, expires_at=expires,
            # The link itself is never stored — only its hash, the same as every other bearer
            # credential here. A seeded row is no exception to that.
            token_hash=hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest(),
            watermark=True, allow_download=False, view_count=views,
            last_seen_at=now - dt.timedelta(hours=views * 3) if views else None,
            granted_by=owner.id,
            revoked_by=owner.id if status == "revoked" else "",
            revoked_at=now - dt.timedelta(days=1) if status == "revoked" else None,
            created_at=now - dt.timedelta(days=12)))
    return len(targets)


def _seed_webhooks(db: Session, tenant_id: str, owner, now) -> int:
    if not _empty(db, models.WebhookEndpoint, tenant_id):
        return 0

    specs = [
        ("https://core.mmbl.internal/hooks/contracts", "Core banking — execution events",
         ["contract.signed", "contract.executed", "contract.terminated"], "ok"),
        ("https://siem.mmbl.internal/collector/cm", "SIEM collector — all events", ["*"], "ok"),
        ("https://teams.mmbl.internal/webhook/legal", "Teams — Legal channel notifications",
         ["contract.approval_requested", "contract.expiring"], "failed"),
    ]
    for url, description, events, last in specs:
        endpoint = models.WebhookEndpoint(
            tenant_id=tenant_id, url=url, description=description, events=events,
            secret=secrets.token_urlsafe(32), is_active=(last != "failed"),
            created_by=owner.id, last_delivery_at=now - dt.timedelta(hours=3),
            last_status=last)
        db.add(endpoint)
        db.flush()
        for i in range(4):
            ok = not (last == "failed" and i == 0)
            db.add(models.WebhookDelivery(
                tenant_id=tenant_id, endpoint_id=endpoint.id,
                event=events[0] if events[0] != "*" else "contract.signed",
                payload={"contract_reference": f"C-2026-{100 + i:04d}", "event_index": i},
                status="ok" if ok else "failed",
                response_code=200 if ok else 502,
                response_snippet="" if ok else "502 Bad Gateway from upstream proxy"))
    return len(specs)


def _seed_api_keys(db: Session, tenant_id: str, owner, now) -> int:
    if not _empty(db, models.ApiKey, tenant_id):
        return 0

    specs = [
        ("Core banking integration", 4, None),
        ("Nightly reporting export", 1, None),
        ("Decommissioned pilot script", 90, now - dt.timedelta(days=60)),
    ]
    for name, days_since_use, revoked in specs:
        # Only the hash is stored, exactly as at runtime — the plaintext is shown once at
        # creation and never persisted, and a seeded key must not be the exception that
        # leaves a usable credential lying in the database.
        raw = f"cm_{secrets.token_urlsafe(24)}"
        db.add(models.ApiKey(
            tenant_id=tenant_id, user_id=owner.id, name=name, prefix=raw[:8],
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            last_used_at=now - dt.timedelta(days=days_since_use), revoked_at=revoked,
            created_at=now - dt.timedelta(days=120)))
    return len(specs)


def _seed_versions(db: Session, tenant_id: str, contracts: list, owner, manager, rng) -> int:
    """Extra revisions on agreements under review, so version comparison has two sides.

    Seeded contracts all carry a single v1, which means the redline screen has nothing to
    compare — the one screen where an empty state is indistinguishable from a broken feature.
    """
    targets = [c for c in contracts if c.status in ("in_review", "changes_requested", "approved")][:6]
    made = 0
    for c in targets:
        existing = db.scalars(select(models.ContractVersion)
                              .filter_by(tenant_id=tenant_id, contract_id=c.id)).all()
        if len(existing) > 1:
            continue
        base = c.body or ""
        v2 = base.replace("thirty (30) days", "forty-five (45) days")
        v2 = v2.replace("## 4. Confidentiality",
                        "## 4. Confidentiality\n\nThe receiving party shall notify the "
                        "disclosing party within twenty-four (24) hours of becoming aware of "
                        "any unauthorised disclosure.")
        if v2 == base:
            v2 = base + "\n\n## Additional undertaking\n\nThe parties shall review this " \
                        "Agreement annually and record the outcome in writing."
        db.add(models.ContractVersion(
            tenant_id=tenant_id, contract_id=c.id, version_no=2, body=v2,
            change_summary="Counterparty markup — payment terms and breach notification.",
            created_by=rng.choice([owner.id, manager.id])))
        c.body = v2
        made += 1
    return made


def _seed_workflow_runs(db: Session, tenant_id: str, contracts: list, owner, manager, rng) -> int:
    """Put agreements under review through the real engine rather than writing run rows.

    Going through `start_run` is what produces a correct stage graph, the approval-matrix
    rules that actually fired, and SLA due dates on the business calendar. Handwritten rows
    would look right on the screen and be wrong in every report derived from them.
    """
    from . import workflow_service

    if not _empty(db, models.WorkflowRun, tenant_id):
        return 0

    definitions = list(db.scalars(
        select(models.WorkflowDefinition).filter_by(tenant_id=tenant_id, status="active")).all())
    if not definitions:
        return 0

    targets = [c for c in contracts if c.status in ("in_review", "changes_requested")][:8]
    made = 0
    for c in targets:
        definition = (workflow_service.default_workflow_for(db, tenant_id, c.type)
                      or rng.choice(definitions))
        # A savepoint, not a plain rollback: everything seeded before this point is in the same
        # transaction, and rolling that back to skip one unroutable agreement would throw away
        # every block that already succeeded.
        try:
            with db.begin_nested():
                run = workflow_service.start_run(db, contract=c, definition=definition,
                                                 user=owner)
        except Exception:
            # The engine refuses for real reasons — no stages, a run already open — and the
            # right response to those here is to move on to the next agreement.
            continue
        db.flush()
        made += 1

        # Advance roughly half of them by one decision, so the inbox has both "waiting on you"
        # and "waiting on somebody else", which is the distinction the screen exists to draw.
        if made % 2 == 0:
            step = workflow_service.active_step(db, run)
            if step is not None:
                try:
                    with db.begin_nested():
                        workflow_service.decide(
                            db, run=run, step=step, contract=c, user=manager,
                            decision="approved",
                            comment="Reviewed — commercial terms acceptable.")
                except Exception:
                    pass
    return made


def _seed_envelopes(db: Session, tenant_id: str, contracts: list, owner, rng) -> int:
    """Signature envelopes on the agreements whose status already claims one exists.

    A contract sitting in `out_for_signature` with no envelope behind it is the kind of detail
    that survives a demo right up until somebody clicks it.
    """
    from . import schemas, signing_service

    if not _empty(db, models.SignatureEnvelope, tenant_id):
        return 0

    targets = [c for c in contracts if c.status in ("out_for_signature", "signed")][:5]
    made = 0
    for c in targets:
        party = (c.counterparty or "Counterparty").strip()
        domain = (_name_key(party).replace(" ", "") or "counterparty")[:16]
        recipients = [
            schemas.RecipientIn(name="Authorised Signatory", email=f"signatory@{domain}.example",
                                kind="signer"),
            schemas.RecipientIn(name=owner.name, email=owner.email, kind="signer"),
            schemas.RecipientIn(name="Legal Records", email="records@mmbl.example", kind="cc"),
        ]
        try:
            with db.begin_nested():
                env = signing_service.create_envelope(
                    db, contract=c, recipients_in=recipients,
                    message=f"Please review and sign {c.title}.",
                    signing_order=rng.choice(["sequential", "parallel"]), by_user=owner)
                signing_service.send_envelope(db, envelope=env, contract=c, by_user=owner,
                                              org_name="Mobilink Microfinance Bank")
        except Exception:
            continue
        db.flush()
        made += 1
    return made


def _seed_pki(db: Session, tenant_id: str, owner, users: list) -> int:
    """Provision the CA hierarchy and issue a certificate to each workspace user.

    Uses the real Registration Authority path — enrol, approve, issue — rather than inserting
    certificate rows. A certificate that never went through the RA is exactly the thing the RA
    exists to prevent, and seeding one would make the queue screens lie.
    """
    from .pki import ca as ca_mod, lifecycle, ra

    if not _empty(db, models.CertificateAuthority, tenant_id):
        return 0

    try:
        with db.begin_nested():
            ca_mod.provision_hierarchy(db, tenant_id, actor_id=owner.id)
    except Exception:
        return 0
    db.flush()

    # The RA refuses to let an officer approve their own request, so each one is reviewed by an
    # officer who is not its subject. With only one officer in the workspace that officer could
    # never hold a certificate — including the demo login, the account most likely to be used
    # to sign something on screen.
    officers = [u for u in users if u.role in ra.RA_ROLES]

    issued = 0
    for user in users:
        officer = next((o for o in officers if o.id != user.id), None)
        if officer is None:
            continue
        try:
            with db.begin_nested():
                request = ra.enrol_internal_user(db, user, actor=officer)
                db.flush()
                # Leave the last one sitting in the queue: an RA screen with nothing pending
                # shows the empty state rather than the review it was built for.
                if user is users[-1] and len(users) > 1:
                    continue
                ra.approve(db, request, officer=officer,
                           note="Identity confirmed against HR record.")
                db.flush()
                if request.status == "approved":
                    lifecycle.issue_from_request(db, request, actor=officer)
                    issued += 1
        except Exception:
            continue
    db.flush()
    return issued or 1


def main() -> None:
    """Top up an existing database: `python -m app.demo_seed`."""
    from .database import SessionLocal, set_request_tenant

    with SessionLocal() as db:
        tenant = db.scalar(select(models.Tenant).limit(1))
        if tenant is None:
            print("No workspace found — run the API once so the demo workspace is seeded first.")
            return
        set_request_tenant(tenant.id)
        made = seed_extras(db, tenant.id)

    if not made:
        print(f"{tenant.name}: nothing to add — every section already has records.")
        return
    print(f"{tenant.name}: added")
    for key, count in sorted(made.items()):
        print(f"  {key:<18}{count}")


if __name__ == "__main__":
    main()
