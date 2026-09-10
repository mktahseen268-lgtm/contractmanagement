"""The repository: parties, relationships, departments, folders and custom fields.

Four small domains in one module because they are one idea — turning the free-text columns a
contract carries into records you can report on, assign to, and reason about. Splitting them
into four services would produce four files of thirty lines each that only ever get imported
together.

The load-bearing piece is **duplicate party detection**. A vendor master that lets "Acme
Trading (Pvt) Ltd" and "ACME TRADING PRIVATE LIMITED" both exist is worse than no vendor
master: it looks authoritative while giving the wrong answer to "what is our total exposure to
Acme?". So onboarding blocks on a likely duplicate and requires an explicit override with a
reason, which is recorded — "we knew and did it anyway" is a different fact from "nobody
noticed".
"""

from __future__ import annotations

import difflib
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import merge_engine, models
from .audit import record

# Entity suffixes that carry no identity. Stripped before comparison so a company is not
# treated as distinct from itself because somebody typed "Ltd" instead of "Limited".
_SUFFIXES = (
    "private limited", "pvt limited", "pvt ltd", "private ltd", "limited", "ltd", "llc",
    "l.l.c", "inc", "incorporated", "corporation", "corp", "company", "co", "plc", "gmbh",
    "sa", "nv", "bv", "ag", "fze", "fzc", "llp", "lp", "partnership", "trust", "foundation",
    "pjsc", "jsc", "psc", "sdn bhd", "bhd", "pte",
)

#: At or above this, two names are treated as the same party. Tuned so "Acme Trading" and
#: "Acme Trading Co" match while "Acme Trading" and "Acme Logistics" do not.
# ponytail: single global threshold; per-jurisdiction tuning if real vendor data shows one
# naming convention producing systematic false positives.
DUPLICATE_RATIO = 0.88

ENTITY_TYPES = ("company", "individual", "government", "ngo", "partnership", "other")
KYC_STATUSES = ("none", "pending", "verified", "rejected")
RELATION_KINDS = ("addendum_of", "amendment_of", "renewal_of", "supersedes", "related_to")


class RepositoryError(ValueError):
    """Refused repository operation. Routers map to 400/409."""


# ---------------------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------------------


def name_key(name: str) -> str:
    """A comparable form of a party name.

    Case-folded, punctuation removed, entity suffixes stripped. Stored on the row so the
    duplicate check is an index lookup rather than a scan of every party on every onboarding.
    """
    text = (name or "").lower()
    # Dots close up rather than splitting: "L.L.C" is "llc", not "l l c". Dotted abbreviations
    # are ordinary in company names and would otherwise defeat every suffix rule below.
    text = re.sub(r"[.’']", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    changed = True
    while changed and text:
        changed = False
        for suffix in _SUFFIXES:
            if text.endswith(" " + suffix):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
    return text


def find_duplicates(db: Session, tenant_id: str, name: str, registration_no: str = "",
                    *, exclude_id: str = "") -> list[dict]:
    """Parties that are probably the same as the one being onboarded.

    Two signals, reported separately because they mean different things: an exact registration
    number is proof, a similar name is a suspicion. A caller that conflates them either blocks
    on coincidence or lets a genuine duplicate through.
    """
    key = name_key(name)
    hits: dict[str, dict] = {}

    if registration_no.strip():
        for party in db.scalars(
            select(models.Party).where(
                models.Party.tenant_id == tenant_id,
                models.Party.registration_no == registration_no.strip(),
            )
        ).all():
            if party.id == exclude_id:
                continue
            hits[party.id] = {
                "id": party.id, "name": party.name,
                "registration_no": party.registration_no,
                "reason": "Same registration number.", "certainty": "exact", "ratio": 1.0,
            }

    if key:
        candidates = db.scalars(
            select(models.Party).where(
                models.Party.tenant_id == tenant_id,
                or_(models.Party.name_key == key,
                    models.Party.name_key.like(f"{key[:6]}%") if len(key) >= 6 else
                    models.Party.name_key == key),
            )
        ).all()
        for party in candidates:
            if party.id == exclude_id or party.id in hits:
                continue
            ratio = difflib.SequenceMatcher(None, key, party.name_key or "",
                                            autojunk=False).ratio()
            if party.name_key == key or ratio >= DUPLICATE_RATIO:
                hits[party.id] = {
                    "id": party.id, "name": party.name,
                    "registration_no": party.registration_no,
                    "reason": f"Name matches an existing party ({int(ratio * 100)}%).",
                    "certainty": "likely", "ratio": round(ratio, 3),
                }

    return sorted(hits.values(), key=lambda h: (-h["ratio"], h["name"]))


def create_party(db: Session, tenant_id: str, data: dict, *, actor: models.User,
                 override_reason: str = "", ip: str = "") -> models.Party:
    """Onboard a party, blocking on a likely duplicate unless overridden with a reason."""
    name = (data.get("name") or "").strip()
    if not name:
        raise RepositoryError("A party needs a name.")
    entity_type = data.get("entity_type") or "company"
    if entity_type not in ENTITY_TYPES:
        raise RepositoryError(f"Unknown entity type '{entity_type}'.")

    duplicates = find_duplicates(db, tenant_id, name, data.get("registration_no") or "")
    if duplicates and not override_reason.strip():
        raise RepositoryError(
            "This looks like an existing party: "
            + "; ".join(f"{d['name']} — {d['reason']}" for d in duplicates)
            + ". Supply a reason to onboard it anyway."
        )

    party = models.Party(
        tenant_id=tenant_id, name=name[:300], name_key=name_key(name)[:300],
        registration_no=(data.get("registration_no") or "").strip()[:100],
        entity_type=entity_type,
        jurisdiction=(data.get("jurisdiction") or "").strip()[:100],
        region=(data.get("region") or "").strip()[:100],
        kyc_status=data.get("kyc_status") or "none",
        risk_score=int(data.get("risk_score") or 0),
        contact_name=(data.get("contact_name") or "").strip()[:200],
        contact_email=(data.get("contact_email") or "").strip()[:320],
        contact_phone=(data.get("contact_phone") or "").strip()[:64],
        address=data.get("address") or "",
        tags=list(data.get("tags") or []),
        duplicate_override_of=duplicates[0]["id"] if duplicates else None,
        duplicate_override_reason=override_reason.strip()[:500],
        created_by=actor.id,
    )
    if party.kyc_status not in KYC_STATUSES:
        raise RepositoryError(f"Unknown KYC status '{party.kyc_status}'.")
    db.add(party)
    db.flush()

    record(db, tenant_id=tenant_id, action="party.created", actor=actor,
           object_type="party", object_id=party.id, object_label=party.name, ip=ip,
           meta={"registration_no": party.registration_no,
                 "duplicate_override": bool(duplicates),
                 "override_reason": override_reason[:200],
                 "matched": [d["id"] for d in duplicates]})
    return party


def link_contract_to_party(db: Session, contract: models.Contract,
                           party: models.Party) -> None:
    """Point a contract at a party, keeping the free-text field in step.

    Both are written on purpose: `party_id` is authoritative, and `counterparty` stays
    populated because every existing report, export and rendered PDF reads it.
    """
    contract.party_id = party.id
    contract.counterparty = party.name[:200]


# ---------------------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------------------


def relate(db: Session, parent: models.Contract, child: models.Contract, kind: str, *,
           actor: models.User, note: str = "", ip: str = "") -> models.ContractRelation:
    """Link two agreements. Addenda get a sequential number per parent."""
    if kind not in RELATION_KINDS:
        raise RepositoryError(f"Unknown relationship '{kind}'.")
    if parent.id == child.id:
        raise RepositoryError("An agreement cannot be related to itself.")
    if parent.tenant_id != child.tenant_id:
        raise RepositoryError("Both agreements must be in the same workspace.")

    existing = db.scalar(
        select(models.ContractRelation).where(
            models.ContractRelation.parent_id == parent.id,
            models.ContractRelation.child_id == child.id,
            models.ContractRelation.kind == kind,
        )
    )
    if existing is not None:
        return existing

    sequence = 0
    if kind == "addendum_of":
        siblings = db.scalars(
            select(models.ContractRelation).where(
                models.ContractRelation.parent_id == parent.id,
                models.ContractRelation.kind == "addendum_of",
            )
        ).all()
        sequence = max((s.sequence for s in siblings), default=0) + 1

    relation = models.ContractRelation(
        tenant_id=parent.tenant_id, parent_id=parent.id, child_id=child.id, kind=kind,
        sequence=sequence, note=note[:500], created_by=actor.id,
    )
    db.add(relation)
    db.flush()

    record(db, tenant_id=parent.tenant_id, action="contract.related", actor=actor,
           object_type="contract", object_id=child.id, object_label=child.title, ip=ip,
           meta={"kind": kind, "parent_id": parent.id, "sequence": sequence})
    return relation


def inherit_from_parent(child: models.Contract, parent: models.Contract) -> None:
    """Copy the parent's commercial context onto an addendum.

    An addendum that does not know its parent's counterparty, department or governing law
    forces the drafter to retype them, which is where they diverge.
    """
    for field in ("party_id", "counterparty", "department_id", "department",
                  "governing_law", "currency", "folder_id", "type"):
        if not getattr(child, field, None):
            setattr(child, field, getattr(parent, field, None))


def history(db: Session, contract: models.Contract) -> dict:
    """The agreement family: what this descends from, and what descends from it."""
    parents = db.scalars(
        select(models.ContractRelation).where(
            models.ContractRelation.tenant_id == contract.tenant_id,
            models.ContractRelation.child_id == contract.id,
        )
    ).all()
    children = db.scalars(
        select(models.ContractRelation).where(
            models.ContractRelation.tenant_id == contract.tenant_id,
            models.ContractRelation.parent_id == contract.id,
        ).order_by(models.ContractRelation.kind.asc(),
                   models.ContractRelation.sequence.asc())
    ).all()

    def _describe(relation: models.ContractRelation, other_id: str, direction: str) -> dict:
        other = db.get(models.Contract, other_id)
        label = relation.kind.replace("_", " ")
        if relation.kind == "addendum_of" and relation.sequence:
            label = f"addendum no. {relation.sequence}"
        return {
            "relation_id": relation.id, "kind": relation.kind, "label": label,
            "direction": direction, "sequence": relation.sequence, "note": relation.note,
            "contract_id": other_id,
            "reference_no": other.reference_no if other else "",
            "title": other.title if other else "(deleted)",
            "status": other.status if other else "",
            "effective_date": other.effective_date if other else None,
            "end_date": other.end_date if other else None,
        }

    return {
        "contract_id": contract.id,
        "ancestors": [_describe(r, r.parent_id, "parent") for r in parents],
        "descendants": [_describe(r, r.child_id, "child") for r in children],
    }


# ---------------------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------------------


def folder_path(db: Session, tenant_id: str, name: str, parent_id: str | None) -> str:
    clean = (name or "").strip().replace("/", "-")
    if not clean:
        raise RepositoryError("A folder needs a name.")
    if parent_id:
        parent = db.get(models.Folder, parent_id)
        if parent is None or parent.tenant_id != tenant_id:
            raise RepositoryError("That parent folder does not exist.")
        return f"{parent.path}/{clean}"
    return f"/{clean}"


def create_folder(db: Session, tenant_id: str, name: str, parent_id: str | None, *,
                  actor: models.User, roles: list[str] | None = None,
                  ip: str = "") -> models.Folder:
    path = folder_path(db, tenant_id, name, parent_id)
    if db.scalar(select(models.Folder).where(models.Folder.tenant_id == tenant_id,
                                             models.Folder.path == path)) is not None:
        raise RepositoryError(f"A folder already exists at {path}.")
    folder = models.Folder(
        tenant_id=tenant_id, name=name.strip()[:150], parent_id=parent_id, path=path,
        visible_to_roles=list(roles or []), created_by=actor.id,
    )
    db.add(folder)
    db.flush()
    record(db, tenant_id=tenant_id, action="folder.created", actor=actor,
           object_type="folder", object_id=folder.id, object_label=path, ip=ip)
    return folder


def move_folder(db: Session, folder: models.Folder, new_parent_id: str | None, *,
                actor: models.User, ip: str = "") -> None:
    """Re-parent a folder and rewrite the subtree's materialised paths.

    Refuses to move a folder into its own descendant — that would detach the subtree from the
    tree entirely, and the materialised path makes the cycle invisible afterwards.
    """
    if new_parent_id == folder.id:
        raise RepositoryError("A folder cannot contain itself.")
    subtree = list(db.scalars(
        select(models.Folder).where(
            models.Folder.tenant_id == folder.tenant_id,
            models.Folder.path.like(f"{folder.path}/%"),
        )
    ).all())
    if new_parent_id and any(f.id == new_parent_id for f in subtree):
        raise RepositoryError("A folder cannot be moved inside itself.")

    old_path = folder.path
    folder.parent_id = new_parent_id
    folder.path = folder_path(db, folder.tenant_id, folder.name, new_parent_id)
    for child in subtree:
        child.path = folder.path + child.path[len(old_path):]

    record(db, tenant_id=folder.tenant_id, action="folder.moved", actor=actor,
           object_type="folder", object_id=folder.id, object_label=folder.path, ip=ip,
           meta={"from": old_path, "to": folder.path, "descendants": len(subtree)})


def visible_folders(db: Session, tenant_id: str, role: str) -> list[models.Folder]:
    """Folders this role may see. An empty `visible_to_roles` means everyone."""
    rows = db.scalars(
        select(models.Folder).where(models.Folder.tenant_id == tenant_id)
        .order_by(models.Folder.path.asc())
    ).all()
    return [f for f in rows if not f.visible_to_roles or role in f.visible_to_roles]


# ---------------------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------------------


def field_defs(db: Session, tenant_id: str, contract_type: str = "") -> list[models.CustomFieldDef]:
    """Definitions applying to a contract type, house-wide ones included."""
    rows = db.scalars(
        select(models.CustomFieldDef).where(
            models.CustomFieldDef.tenant_id == tenant_id,
            models.CustomFieldDef.is_active.is_(True),
        ).order_by(models.CustomFieldDef.position.asc(), models.CustomFieldDef.label.asc())
    ).all()
    if not contract_type:
        return list(rows)
    return [r for r in rows if r.contract_type in ("", contract_type)]


def _as_merge_fields(defs: list[models.CustomFieldDef]) -> list[merge_engine.FieldDef]:
    return merge_engine.parse_fields([{
        "key": d.key, "label": d.label, "type": d.type, "required": d.required,
        "options": list(d.options or []), "help": d.help,
    } for d in defs])


def validate_custom_fields(db: Session, contract: models.Contract, values: dict) -> dict:
    """Clean the submitted custom values against the tenant's definitions.

    Deliberately reuses `merge_engine` rather than growing a second type system: the intake
    form and custom fields are the same idea at different points, and two validators would
    disagree the first time somebody added a type to one of them.
    """
    defs = field_defs(db, contract.tenant_id, contract.type or "")
    cleaned, errors = merge_engine.validate_values(_as_merge_fields(defs), values)
    if errors:
        raise RepositoryError("; ".join(errors))
    return merge_engine.jsonable(cleaned)


def describe_custom_fields(db: Session, contract: models.Contract) -> list[dict]:
    """Definitions plus this contract's values, for rendering a form or a detail panel."""
    values = contract.custom_fields or {}
    return [{
        "key": d.key, "label": d.label or d.key.replace("_", " ").title(), "type": d.type,
        "required": d.required, "options": list(d.options or []), "help": d.help,
        "value": values.get(d.key, ""),
    } for d in field_defs(db, contract.tenant_id, contract.type or "")]
