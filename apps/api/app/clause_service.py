"""The clause library — approved language, versioned, and composable into templates.

A template that inlines its own wording is a copy. Ten templates that inline the same
indemnity clause are ten copies, and improving the clause means finding all ten. So a template
refers to a clause by key:

    [[clause:limitation_of_liability]]

and `expand()` resolves the reference to the **approved** wording at assembly time, before the
merge engine substitutes `{{fields}}`. Two stages, in that order, because a clause may itself
contain merge fields.

The approval gate mirrors `template_service` deliberately: same states, same separation of
duties, same frozen version snapshots. Clause text ends up in signed agreements exactly like
template text does, so it earns exactly the same controls. Where the two differ it is because
clauses have something templates do not — **alternatives**: pre-approved fallback positions,
ranked, so a negotiator reaching for one is still inside policy rather than improvising.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import models
from .audit import record

#: `[[clause:key]]`, tolerant of surrounding whitespace.
CLAUSE_REF_RE = re.compile(r"\[\[\s*clause:\s*([a-z][a-z0-9_]{0,79})\s*\]\]")

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")

#: Same narrow set as templates: authoring a clause and blessing it are different acts.
APPROVER_ROLES = {"owner", "admin", "manager"}

POSITIONS = ("preferred", "acceptable", "fallback")
RISK_LEVELS = ("low", "medium", "high", "critical")


class ClauseError(ValueError):
    """Invalid clause definition or a refused state change. Routers map to 400."""


# ---------------------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------------------


def by_key(db: Session, tenant_id: str, key: str) -> models.Clause | None:
    return db.scalar(
        select(models.Clause).where(models.Clause.tenant_id == tenant_id,
                                    models.Clause.key == key)
    )


def active_version(db: Session, clause: models.Clause) -> models.ClauseVersion | None:
    return db.scalar(
        select(models.ClauseVersion)
        .where(models.ClauseVersion.clause_id == clause.id,
               models.ClauseVersion.version_no == clause.version_no)
    )


def alternatives(db: Session, clause: models.Clause) -> list[models.Clause]:
    """Fallback positions for this clause, best first."""
    return list(db.scalars(
        select(models.Clause)
        .where(models.Clause.tenant_id == clause.tenant_id,
               models.Clause.parent_id == clause.id)
        .order_by(models.Clause.fallback_rank.asc(), models.Clause.created_at.asc())
    ).all())


def approved_body(db: Session, clause: models.Clause) -> str:
    """The wording in force: the approved snapshot, never the live row.

    An edit in progress must not reach a contract before somebody has approved it — the same
    rule templates follow, for the same reason.
    """
    if clause.status == "active":
        snapshot = active_version(db, clause)
        if snapshot is not None:
            return snapshot.body or ""
    return ""


# ---------------------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------------------


def references_in(body: str) -> list[str]:
    """Every distinct clause key a body references, in first-appearance order."""
    seen: list[str] = []
    for key in CLAUSE_REF_RE.findall(body or ""):
        if key not in seen:
            seen.append(key)
    return seen


def validate_references(db: Session, tenant_id: str, body: str) -> list[str]:
    """Problems with the clause references in a template body.

    Checked when a template is submitted for approval, on the same principle as merge fields:
    a reference that cannot resolve is a defect the author should see now, not something for
    whoever is raising an agreement to discover under deadline.
    """
    problems: list[str] = []
    for key in references_in(body):
        clause = by_key(db, tenant_id, key)
        if clause is None:
            problems.append(f"The template references clause [[clause:{key}]], which does not exist.")
        elif clause.status != "active":
            problems.append(
                f"Clause [[clause:{key}]] is {clause.status.replace('_', ' ')}, "
                "so it has no approved wording to insert."
            )
    return problems


def resolve_choice(db: Session, tenant_id: str, key: str,
                   chosen_key: str) -> models.Clause:
    """The clause to use where `key` was referenced, given a negotiator's choice.

    A choice may only be the referenced clause itself or one of **its own approved
    alternatives**. Allowing an arbitrary key would let the wizard swap any clause for any
    other — which is not "choosing a fallback position", it is editing the contract through a
    drop-down, without the approval that editing would have required.
    """
    base = by_key(db, tenant_id, key)
    if base is None:
        raise ClauseError(f"Clause '{key}' does not exist.")
    if chosen_key == key:
        return base
    chosen = by_key(db, tenant_id, chosen_key)
    if chosen is None:
        raise ClauseError(f"Clause '{chosen_key}' does not exist.")
    if chosen.parent_id != base.id:
        raise ClauseError(
            f"'{chosen_key}' is not an approved alternative for '{key}'."
        )
    if chosen.status != "active":
        raise ClauseError(f"Alternative '{chosen_key}' has not been approved for use.")
    return chosen


def expand(db: Session, tenant_id: str, body: str, *,
           choices: dict | None = None,
           extras: list[str] | None = None) -> tuple[str, list[dict], list[str]]:
    """Resolve `[[clause:key]]` references to approved wording.

    Returns (text, included, unresolved). An unresolved reference is **left in place and
    reported**, never silently dropped — a contract quietly missing its limitation of
    liability is the worst possible failure of a clause library, and a visible
    `[[clause:limitation_of_liability]]` is at least obviously wrong.

    `choices` maps a referenced key to the alternative chosen in its place (validated by
    `resolve_choice`). `extras` appends optional clauses the drafter selected that the
    template did not reference.
    """
    choices = choices or {}
    included: list[dict] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    def _use(clause: models.Clause | None, key: str) -> str:
        text = approved_body(db, clause) if clause is not None else ""
        if not text:
            if key not in unresolved:
                unresolved.append(key)
            return ""
        if clause.id not in seen:
            seen.add(clause.id)
            included.append({"clause_id": clause.id, "key": clause.key,
                             "version_no": clause.version_no, "title": clause.title,
                             "substituted_for": key if clause.key != key else None})
        return text

    def replace(match: re.Match) -> str:
        key = match.group(1)
        chosen_key = str(choices.get(key) or key)
        try:
            clause = resolve_choice(db, tenant_id, key, chosen_key)
        except ClauseError:
            clause = by_key(db, tenant_id, key)
        text = _use(clause, key)
        return text or match.group(0)

    out = CLAUSE_REF_RE.sub(replace, body or "")

    for extra_key in (extras or []):
        clause = by_key(db, tenant_id, extra_key)
        text = _use(clause, extra_key)
        if text:
            out = out.rstrip() + "\n\n" + text + "\n"

    return out, included, unresolved


# ---------------------------------------------------------------------------------------
# Authoring and approval
# ---------------------------------------------------------------------------------------


def validate(clause: models.Clause) -> list[str]:
    problems: list[str] = []
    if not _KEY_RE.match(clause.key or ""):
        problems.append(
            f"'{clause.key}' is not a valid clause key — use lower-case letters, digits and "
            "underscores, starting with a letter."
        )
    if not (clause.body or "").strip():
        problems.append("A clause needs wording.")
    if clause.position not in POSITIONS:
        problems.append(f"Unknown position '{clause.position}'.")
    if clause.risk_level not in RISK_LEVELS:
        problems.append(f"Unknown risk level '{clause.risk_level}'.")
    return problems


def submit_for_approval(db: Session, clause: models.Clause, *, actor: models.User,
                        ip: str = "") -> None:
    if clause.status == "active":
        raise ClauseError("This clause is already approved and in use.")
    problems = validate(clause)
    if problems:
        raise ClauseError("; ".join(problems))
    clause.status = "pending_approval"
    record(db, tenant_id=clause.tenant_id, action="clause.submitted", actor=actor,
           object_type="clause", object_id=clause.id, object_label=clause.title or clause.key,
           ip=ip, meta={"key": clause.key, "version_no": clause.version_no})


def approve(db: Session, clause: models.Clause, *, actor: models.User, note: str = "",
            ip: str = "") -> models.ClauseVersion:
    """Approve the clause and freeze the approved wording as a version snapshot."""
    if actor.role not in APPROVER_ROLES:
        raise ClauseError("You do not have permission to approve clauses.")
    if clause.status != "pending_approval":
        raise ClauseError("Only a clause submitted for approval can be approved.")
    if actor.id == clause.created_by and actor.role not in ("owner", "admin"):
        raise ClauseError("A clause must be approved by someone other than its author.")

    latest = db.scalar(
        select(models.ClauseVersion)
        .where(models.ClauseVersion.clause_id == clause.id)
        .order_by(desc(models.ClauseVersion.version_no))
    )
    if latest is not None:
        latest.status = "superseded"
    version_no = (latest.version_no + 1) if latest is not None else 1
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    snapshot = models.ClauseVersion(
        tenant_id=clause.tenant_id, clause_id=clause.id, version_no=version_no,
        title=clause.title, body=clause.body or "", position=clause.position,
        risk_level=clause.risk_level, status="active", change_summary=note[:500],
        approved_by=actor.id, approved_at=now, created_by=clause.created_by,
    )
    db.add(snapshot)
    # autoflush is off in this project: without the flush the snapshot stays invisible to the
    # next query, so a later approval would not supersede it and retire() would miss it.
    db.flush()

    clause.status = "active"
    clause.version_no = version_no
    clause.approved_by = actor.id
    clause.approved_at = now
    clause.approval_note = note[:500]
    clause.retired_at = None

    record(db, tenant_id=clause.tenant_id, action="clause.approved", actor=actor,
           object_type="clause", object_id=clause.id, object_label=clause.title or clause.key,
           ip=ip, meta={"key": clause.key, "version_no": version_no, "note": note[:200]})
    return snapshot


def reject(db: Session, clause: models.Clause, *, actor: models.User, reason: str,
           ip: str = "") -> None:
    if actor.role not in APPROVER_ROLES:
        raise ClauseError("You do not have permission to review clauses.")
    if clause.status != "pending_approval":
        raise ClauseError("Only a clause submitted for approval can be rejected.")
    clause.status = "draft"
    clause.approval_note = reason[:500]
    record(db, tenant_id=clause.tenant_id, action="clause.rejected", actor=actor,
           object_type="clause", object_id=clause.id, object_label=clause.title or clause.key,
           ip=ip, meta={"key": clause.key, "reason": reason[:200]})


def retire(db: Session, clause: models.Clause, *, actor: models.User, ip: str = "") -> None:
    """Take a clause out of use.

    Templates that reference it will fail their next approval check rather than silently
    losing a paragraph — which is why `expand` reports an unresolved reference instead of
    dropping it.
    """
    clause.status = "retired"
    clause.retired_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for version in db.scalars(
        select(models.ClauseVersion)
        .where(models.ClauseVersion.clause_id == clause.id,
               models.ClauseVersion.status == "active")
    ).all():
        version.status = "retired"
    record(db, tenant_id=clause.tenant_id, action="clause.retired", actor=actor,
           object_type="clause", object_id=clause.id, object_label=clause.title or clause.key,
           ip=ip, meta={"key": clause.key})


def edit_unapproves(clause: models.Clause) -> None:
    """Editing approved wording sends it back to draft.

    Same rule as templates: letting the edit go live immediately would make every agreement
    raised afterwards claim approved language it never had.
    """
    if clause.status == "active":
        clause.status = "draft"


def usage_bump(db: Session, included: list[dict]) -> None:
    """Count a clause each time it is assembled into a draft."""
    for entry in included:
        clause = db.get(models.Clause, entry.get("clause_id"))
        if clause is not None:
            clause.usage_count = (clause.usage_count or 0) + 1
