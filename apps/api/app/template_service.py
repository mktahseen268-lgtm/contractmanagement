"""Template lifecycle — draft → approved → in use → retired, with the merge engine on top.

The RFI's intake journey (§2.3) is: pick an agreement type, fill a form of drop-downs and
lists-of-values, submit, and the system generates the draft **from the pre-approved template**.
Two words in that sentence carry the weight:

- **pre-approved** — a template is not usable because someone saved it. It becomes usable when
  a reviewer approves it, and the wording that was approved is frozen in a version snapshot.
  Otherwise "generated from the approved template" is unprovable the moment anyone edits it.
- **generates** — the draft is rendered by `merge_engine`, deterministically, with unresolved
  placeholders treated as an error rather than a blank.

Editing an active template does **not** silently change it under everyone: the edit lands on
the live row and knocks it back to `draft`, so it has to be re-approved before the next
generation picks it up. In-flight contracts already carry their own copy of the body.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from . import clause_service, merge_engine, models
from .audit import record
from .merge_engine import MergeError

#: Roles allowed to approve a template into use. Deliberately narrower than the roles allowed
#: to *author* one — approving your own template is the control this feature exists to add.
APPROVER_ROLES = {"owner", "admin", "manager"}

STATUSES = ("draft", "pending_approval", "active", "retired")


def _sync_active_flag(template: models.ContractTemplate) -> None:
    """`is_active` predates `status` and is still read by older callers. One source of truth
    (`status`), one derived flag, updated in exactly this one place."""
    template.is_active = template.status == "active"


def set_fields(db: Session, template: models.ContractTemplate, raw_fields: list,
               *, actor: models.User | None = None, ip: str = "") -> list[merge_engine.FieldDef]:
    """Replace the template's intake form. Rejects a definition that cannot work."""
    fields = merge_engine.parse_fields(raw_fields)
    assembled, _included, _unresolved = clause_service.expand(db, template.tenant_id,
                                                              template.body or "")
    problems = merge_engine.validate_definition(fields, assembled)
    if problems:
        raise MergeError("; ".join(problems))
    template.fields = [f.to_dict() for f in fields]
    if template.status == "active":
        # The form changed, so the approved shape no longer describes this template.
        template.status = "draft"
        _sync_active_flag(template)
    if actor is not None:
        record(db, tenant_id=template.tenant_id, action="template.fields_updated", actor=actor,
               object_type="template", object_id=template.id, object_label=template.name, ip=ip,
               meta={"field_count": len(fields)})
    return fields


def submit_for_approval(db: Session, template: models.ContractTemplate, *,
                        actor: models.User, ip: str = "") -> None:
    if template.status == "active":
        raise MergeError("This template is already approved and in use.")
    body = template.body or ""
    fields = merge_engine.parse_fields(template.fields)
    # Clause references resolve first, so the merge-field check sees the assembled document:
    # a `{{fee}}` that lives inside a clause is supplied by the template's form, and checking
    # the unexpanded body would report it as an unfillable placeholder.
    assembled, _included, unresolved = clause_service.expand(db, template.tenant_id, body)
    problems = [
        f"The template references clause [[clause:{key}]], which has no approved wording."
        for key in unresolved
    ]
    problems += merge_engine.validate_definition(fields, assembled)
    if problems:
        raise MergeError("; ".join(problems))
    if not body.strip():
        raise MergeError("A template needs a body before it can be approved.")
    template.status = "pending_approval"
    _sync_active_flag(template)
    record(db, tenant_id=template.tenant_id, action="template.submitted", actor=actor,
           object_type="template", object_id=template.id, object_label=template.name, ip=ip,
           meta={"version_no": template.version_no})


def approve(db: Session, template: models.ContractTemplate, *, actor: models.User,
            note: str = "", effective_from: dt.date | None = None,
            ip: str = "") -> models.ContractTemplateVersion:
    """Approve the template and freeze the approved wording as a version snapshot."""
    if actor.role not in APPROVER_ROLES:
        raise MergeError("You do not have permission to approve templates.")
    if template.status != "pending_approval":
        raise MergeError("Only a template submitted for approval can be approved.")
    if actor.id == template.created_by and actor.role not in ("owner", "admin"):
        # Separation of duties: the author of a template should not be the one who blesses it.
        # Owners and admins are exempted because a small workspace may have nobody else.
        raise MergeError("A template must be approved by someone other than its author.")

    latest = db.scalar(
        select(models.ContractTemplateVersion)
        .where(models.ContractTemplateVersion.template_id == template.id)
        .order_by(desc(models.ContractTemplateVersion.version_no))
    )
    if latest is not None:
        latest.status = "superseded"
    version_no = (latest.version_no + 1) if latest is not None else 1
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    snapshot = models.ContractTemplateVersion(
        tenant_id=template.tenant_id, template_id=template.id, version_no=version_no,
        name=template.name, body=template.body or "",
        fields=[f.to_dict() for f in merge_engine.parse_fields(template.fields)],
        status="active", change_summary=note[:500],
        approved_by=actor.id, approved_at=now, created_by=template.created_by,
    )
    db.add(snapshot)
    # The session runs with autoflush off, so without this the snapshot stays invisible to the
    # next query — a later approve() would not find it to supersede, and retire() would leave
    # it active. Both would corrupt the "which wording was in force?" answer this table exists
    # to give.
    db.flush()

    template.status = "active"
    template.version_no = version_no
    template.approved_by = actor.id
    template.approved_at = now
    template.approval_note = note[:500]
    template.effective_from = effective_from or dt.date.today()
    template.retired_at = None
    _sync_active_flag(template)

    record(db, tenant_id=template.tenant_id, action="template.approved", actor=actor,
           object_type="template", object_id=template.id, object_label=template.name, ip=ip,
           meta={"version_no": version_no, "note": note[:200]})
    return snapshot


def reject(db: Session, template: models.ContractTemplate, *, actor: models.User,
           reason: str, ip: str = "") -> None:
    if actor.role not in APPROVER_ROLES:
        raise MergeError("You do not have permission to review templates.")
    if template.status != "pending_approval":
        raise MergeError("Only a template submitted for approval can be rejected.")
    template.status = "draft"
    template.approval_note = reason[:500]
    _sync_active_flag(template)
    record(db, tenant_id=template.tenant_id, action="template.rejected", actor=actor,
           object_type="template", object_id=template.id, object_label=template.name, ip=ip,
           meta={"reason": reason[:200]})


def retire(db: Session, template: models.ContractTemplate, *, actor: models.User,
           ip: str = "") -> None:
    """Take a template out of use without deleting it — contracts still reference its versions."""
    template.status = "retired"
    template.retired_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    _sync_active_flag(template)
    for version in db.scalars(
        select(models.ContractTemplateVersion)
        .where(models.ContractTemplateVersion.template_id == template.id,
               models.ContractTemplateVersion.status == "active")
    ).all():
        version.status = "retired"
    record(db, tenant_id=template.tenant_id, action="template.retired", actor=actor,
           object_type="template", object_id=template.id, object_label=template.name, ip=ip)


def active_version(db: Session, template: models.ContractTemplate) -> models.ContractTemplateVersion | None:
    return db.scalar(
        select(models.ContractTemplateVersion)
        .where(models.ContractTemplateVersion.template_id == template.id,
               models.ContractTemplateVersion.version_no == template.version_no)
    )


# ---------------------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------------------


def usable_source(db: Session, template: models.ContractTemplate) -> tuple[str, list[dict], int | None]:
    """(body, field definitions, version) to generate from.

    An approved template generates from its **frozen snapshot**, not the live row — so an
    in-progress edit cannot leak into a contract before it has been re-approved.
    """
    if template.status == "active":
        snapshot = active_version(db, template)
        if snapshot is not None:
            return snapshot.body or "", list(snapshot.fields or []), snapshot.version_no
    return template.body or "", list(template.fields or []), None


def form_schema(db: Session, template: models.ContractTemplate) -> dict:
    """What the intake form should render, plus whether it can be used at all."""
    body, raw_fields, version_no = usable_source(db, template)
    fields = merge_engine.parse_fields(raw_fields)
    assembled, included, unresolved = clause_service.expand(db, template.tenant_id, body)
    problems = [
        f"The template references clause [[clause:{key}]], which has no approved wording."
        for key in unresolved
    ]
    problems += merge_engine.validate_definition(fields, assembled)
    return {
        "clauses": included,
        "clause_choices": clause_choices(db, template),
        "template_id": template.id,
        "name": template.name,
        "description": template.description,
        "contract_type": template.contract_type,
        "status": template.status,
        "version_no": version_no or template.version_no,
        "usable": template.status == "active",
        "fields": [f.to_dict() for f in fields],
        "placeholders": merge_engine.placeholders_in(assembled),
        "problems": problems,
        "defaults": {
            "currency": template.default_currency,
            "term_months": template.default_term_months,
            "renewal_type": template.default_renewal_type,
            "risk_level": template.default_risk_level,
            "governing_law": template.default_governing_law,
            "tags": list(template.default_tags or []),
        },
    }


def clause_choices(db: Session, template: models.ContractTemplate) -> list[dict]:
    """For every clause the template references, the alternatives a drafter may pick instead.

    Risk level and guidance travel with each option: choosing a fallback position is a risk
    decision, and presenting the options without saying which is riskier would make the
    drop-down worse than no choice at all.
    """
    body, _fields, _v = usable_source(db, template)
    out: list[dict] = []
    for key in clause_service.references_in(body):
        clause = clause_service.by_key(db, template.tenant_id, key)
        if clause is None:
            continue
        options = [{
            "key": clause.key, "title": clause.title, "position": clause.position,
            "risk_level": clause.risk_level, "guidance": clause.guidance,
            "body": clause_service.approved_body(db, clause), "is_default": True,
        }]
        for alt in clause_service.alternatives(db, clause):
            if alt.status != "active":
                continue
            options.append({
                "key": alt.key, "title": alt.title, "position": alt.position,
                "risk_level": alt.risk_level, "guidance": alt.guidance,
                "body": clause_service.approved_body(db, alt), "is_default": False,
            })
        out.append({"key": key, "title": clause.title, "options": options})
    return out


def optional_clauses(db: Session, template: models.ContractTemplate) -> list[dict]:
    """Approved clauses the drafter may add that this template does not already reference."""
    body, _fields, _v = usable_source(db, template)
    already = set(clause_service.references_in(body))
    rows = db.scalars(
        select(models.Clause).where(
            models.Clause.tenant_id == template.tenant_id,
            models.Clause.status == "active",
            models.Clause.parent_id.is_(None),
        ).order_by(models.Clause.category.asc(), models.Clause.title.asc())
    ).all()
    return [{
        "key": c.key, "title": c.title, "category": c.category,
        "risk_level": c.risk_level, "guidance": c.guidance,
    } for c in rows if c.key not in already]


def preview(db: Session, template: models.ContractTemplate, values: dict,
            *, contract_vars: dict | None = None, currency: str = "",
            choices: dict | None = None, extras: list[str] | None = None) -> dict:
    """Render without persisting anything — what the draft will say, before committing to it."""
    body, raw_fields, version_no = usable_source(db, template)
    fields = merge_engine.parse_fields(raw_fields)
    assembled, included, missing_clauses = clause_service.expand(
        db, template.tenant_id, body, choices=choices, extras=extras)
    cleaned, errors = merge_engine.validate_values(fields, values)
    result = merge_engine.render(assembled, fields, cleaned, extra=contract_vars,
                                 currency=currency or template.default_currency)
    return {
        "body": result.text,
        "clauses": included,
        "missing_clauses": missing_clauses,
        "errors": errors,
        "unresolved": result.unresolved,
        "substituted": result.substituted,
        "values": cleaned,
        "version_no": version_no,
        "ok": not errors and result.ok and not missing_clauses,
    }


def generate_body(db: Session, template: models.ContractTemplate, values: dict,
                  *, contract_vars: dict | None = None, currency: str = "",
                  allow_unresolved: bool = False, choices: dict | None = None,
                  extras: list[str] | None = None) -> tuple[str, dict, int | None, list[dict]]:
    """The strict path used when actually creating a contract.

    Raises rather than returning a partial document. A draft with a gap where the fee should
    be is the failure this whole feature exists to prevent, so refusing is the correct
    behaviour — `allow_unresolved` exists only for the deliberate "save it anyway, I will
    finish it by hand" case, which the caller must opt into explicitly.
    """
    if template.status != "active":
        raise MergeError("This template has not been approved for use.")
    body, raw_fields, version_no = usable_source(db, template)
    fields = merge_engine.parse_fields(raw_fields)
    # Validate every choice up front so an invalid one is refused rather than silently
    # falling back to the default wording — a drafter who picked a fallback and got the
    # standard clause would never know.
    for key, chosen in (choices or {}).items():
        clause_service.resolve_choice(db, template.tenant_id, key, str(chosen))
    assembled, included, missing_clauses = clause_service.expand(
        db, template.tenant_id, body, choices=choices, extras=extras)
    if missing_clauses:
        # Never negotiable, even with allow_unresolved: a contract quietly missing its
        # limitation of liability is the worst thing a clause library can produce.
        raise MergeError(
            "These clauses have no approved wording to insert: "
            + ", ".join(missing_clauses)
        )
    cleaned, errors = merge_engine.validate_values(fields, values)
    if errors:
        raise MergeError("; ".join(errors))
    result = merge_engine.render(assembled, fields, cleaned, extra=contract_vars,
                                 currency=currency or template.default_currency)
    if result.unresolved and not allow_unresolved:
        raise MergeError(
            "These placeholders have nothing to fill them: "
            + ", ".join(f"{{{{{k}}}}}" for k in result.unresolved)
        )
    return result.text, cleaned, version_no, included


def _next_reference(db: Session, tenant_id: str) -> str:
    year = dt.date.today().year
    n = db.scalar(select(func.count(models.Contract.id))
                  .where(models.Contract.tenant_id == tenant_id)) or 0
    return f"C-{year}-{n + 1:04d}"


def spawn_from_template(db: Session, *, template: models.ContractTemplate, actor: models.User,
                        title: str, body: str, counterparty: str = "", department: str = "",
                        value: float | None = None, effective_date: dt.date | None = None,
                        end_date: dt.date | None = None, owner_id: str | None = None,
                        values: dict | None = None, version_no: int | None = None,
                        source_note: str = "template", ip: str = "",
                        included_clauses: list[dict] | None = None) -> models.Contract:
    """Create the draft. Shared by the plain copy path, the merge-field path and bulk send, so
    none of the three can drift on reference numbering, defaults, versioning or audit.

    Takes an `ip` string rather than a `Request` because the bulk-send worker has neither — it
    runs in a Celery task, where the originating request is long gone.
    """
    owner_id = owner_id or actor.id
    if owner_id != actor.id:
        ou = db.get(models.User, owner_id)
        if ou is None or ou.tenant_id != actor.tenant_id:
            raise ValueError("Invalid owner.")
    effective = effective_date or dt.date.today()
    end = end_date or (
        dt.date(effective.year + (template.default_term_months // 12),
                ((effective.month - 1 + (template.default_term_months % 12)) % 12) + 1,
                effective.day)
        if template.default_term_months else None
    )
    c = models.Contract(
        tenant_id=actor.tenant_id,
        reference_no=_next_reference(db, actor.tenant_id),
        title=title.strip()[:300],
        type=template.contract_type, status="draft", owner_id=owner_id,
        counterparty=(counterparty or "").strip()[:200],
        department=(department or "").strip()[:100],
        value=float(value or 0.0), currency=template.default_currency,
        effective_date=effective, end_date=end,
        renewal_type=template.default_renewal_type,
        governing_law=template.default_governing_law,
        risk_level=template.default_risk_level, ai_summary="",
        tags=list(template.default_tags or []), body=body, source="template",
        template_id=template.id, template_version_no=version_no,
        merge_values=merge_engine.jsonable(values or {}),
        included_clauses=list(included_clauses or []),
        created_by=actor.id,
    )
    db.add(c)
    db.flush()
    summary = (f"Generated from template \u201c{template.name}\u201d v{version_no}"
               if version_no else f"Created from template \u201c{template.name}\u201d")
    db.add(models.ContractVersion(tenant_id=actor.tenant_id, contract_id=c.id, version_no=1,
                                  body=c.body, change_summary=summary, created_by=actor.id))
    template.usage_count = (template.usage_count or 0) + 1
    record(db, tenant_id=actor.tenant_id, action="contract.created", actor=actor,
           object_type="contract", object_id=c.id, object_label=c.title, ip=ip,
           meta={"source": source_note, "template_id": template.id,
                 "template_version_no": version_no,
                 "merge_field_count": len(values or {}),
                 "clauses": [entry.get("key") for entry in (included_clauses or [])]})
    clause_service.usage_bump(db, list(included_clauses or []))
    return c
