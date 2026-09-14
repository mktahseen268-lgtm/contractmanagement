"""Contract templates — a library of pre-fab contracts the workspace can spawn drafts from.
Save-as-template + use-template are the two common shapes (DocuSign / PandaDoc / Deel pattern)."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import clause_service, merge_engine, models, schemas, template_service
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user
from ..clause_service import ClauseError
from ..merge_engine import MergeError

router = APIRouter(prefix="/templates", tags=["templates"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}


def _get_owned(db: Session, user: models.User, tid: str) -> models.ContractTemplate:
    t = db.get(models.ContractTemplate, tid)
    if t is None or t.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return t


@router.get("", response_model=list[schemas.ContractTemplateOut])
def list_templates(
    active: bool | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.ContractTemplateOut]:
    stmt = select(models.ContractTemplate).where(models.ContractTemplate.tenant_id == user.tenant_id)
    if active is True:
        stmt = stmt.where(models.ContractTemplate.is_active.is_(True))
    rows = db.scalars(stmt.order_by(desc(models.ContractTemplate.updated_at))).all()
    return [schemas.ContractTemplateOut.model_validate(r) for r in rows]


@router.post("", response_model=schemas.ContractTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(data: schemas.ContractTemplateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to create templates.")
    t = models.ContractTemplate(
        tenant_id=user.tenant_id, name=data.name.strip()[:200], description=(data.description or "").strip()[:500],
        contract_type=data.contract_type, body=data.body or "", default_currency=data.default_currency,
        default_term_months=max(1, int(data.default_term_months or 12)), default_renewal_type=data.default_renewal_type,
        default_risk_level=data.default_risk_level, default_governing_law=data.default_governing_law,
        default_tags=list(data.default_tags or []), is_active=bool(data.is_active), created_by=user.id,
    )
    # A new template always starts as a draft: `is_active` no longer decides whether it can be
    # used, approval does. Otherwise anyone who can author a template could put it into use.
    t.status = "draft"
    t.is_active = False
    db.add(t)
    db.flush()
    if data.fields:
        try:
            template_service.set_fields(db, t, data.fields)
        except MergeError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    record(db, tenant_id=user.tenant_id, action="template.created", actor=user, object_type="template", object_id=t.id, object_label=t.name, ip=client_ip(request))
    db.commit()
    db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.get("/{tid}", response_model=schemas.ContractTemplateOut)
def get_template(tid: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    return schemas.ContractTemplateOut.model_validate(_get_owned(db, user, tid))


@router.patch("/{tid}", response_model=schemas.ContractTemplateOut)
def update_template(tid: str, data: schemas.ContractTemplateUpdateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    t = _get_owned(db, user, tid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit templates.")
    payload = data.model_dump(exclude_unset=True)
    changed = False
    new_fields = payload.pop("fields", None)
    for k, v in payload.items():
        if v is None:
            continue
        if isinstance(v, str) and k in {"name", "description", "default_governing_law"}:
            v = v.strip()
        if k == "default_term_months":
            v = max(1, int(v))
        setattr(t, k, v)
        changed = True
    if new_fields is not None:
        try:
            template_service.set_fields(db, t, new_fields)
        except MergeError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        changed = True
    if "body" in payload and t.status == "active":
        # Editing approved wording un-approves it. The alternative — letting the edit go live
        # immediately — would make "generated from the approved template" untrue for every
        # contract raised afterwards.
        t.status = "draft"
        t.is_active = False
    if changed:
        record(db, tenant_id=user.tenant_id, action="template.updated", actor=user, object_type="template", object_id=t.id, object_label=t.name, ip=client_ip(request), meta={"fields": list(payload.keys())})
        db.commit()
        db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.delete("/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(tid: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    t = _get_owned(db, user, tid)
    if user.role not in {"owner", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete templates.")
    name = t.name
    db.delete(t)
    record(db, tenant_id=user.tenant_id, action="template.deleted", actor=user, object_type="template", object_id=tid, object_label=name, ip=client_ip(request))
    db.commit()


def _spawn(db: Session, user: models.User, t: models.ContractTemplate,
           data: schemas.UseTemplateIn, request: Request, *, body: str,
           values: dict | None = None, version_no: int | None = None,
           source_note: str = "template",
           included_clauses: list[dict] | None = None) -> models.Contract:
    """Unpack the request shape and hand off. The creation itself lives in `template_service`
    so bulk send — which has no `Request` to take an IP from — runs the identical path."""
    from .contracts import _link_client

    client = _link_client(db, user.tenant_id, data.party_id)
    try:
        c = template_service.spawn_from_template(
            db, template=t, actor=user, title=data.title, body=body,
            counterparty=client.name if client else (data.counterparty or ""),
            department=data.department or "",
            value=data.value, effective_date=data.effective_date, end_date=data.end_date,
            owner_id=data.owner_id, values=values, version_no=version_no,
            source_note=source_note, ip=client_ip(request), included_clauses=included_clauses,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if client:
        c.party_id = client.id
    return c


@router.post("/{tid}/use", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
def use_template(tid: str, data: schemas.UseTemplateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    """Spawn a new DRAFT contract from a template — body + metadata defaults copied, caller can
    override title/counterparty/value/dates/owner.

    This is the copy-it-and-edit path. A template with an intake form should go through
    `/generate` instead, which fills the merge fields rather than leaving them in the text.
    """
    from .contracts import _detail

    t = _get_owned(db, user, tid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to create contracts.")
    if t.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This template has not been approved for use.")
    body, _fields, version_no = template_service.usable_source(db, t)
    body, included, missing = clause_service.expand(db, user.tenant_id, body)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("These clauses have no approved wording to insert: " + ", ".join(missing)),
        )
    c = _spawn(db, user, t, data, request, body=body, version_no=version_no,
               included_clauses=included)
    db.commit()
    db.refresh(c)
    return _detail(db, c)


# ---------------------------------------------------------------------------------------
# Merge fields — the RFI's intake mechanic (§2.3)
# ---------------------------------------------------------------------------------------


@router.get("/{tid}/form", response_model=schemas.TemplateFormOut)
def template_form(tid: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.TemplateFormOut:
    """The intake form for this agreement type: fields, permitted values, defaults.

    Also reports `problems` — an approved template whose body references a placeholder no
    field supplies is a defect the author needs to see, not something to discover at
    generation time.
    """
    t = _get_owned(db, user, tid)
    return schemas.TemplateFormOut(**template_service.form_schema(db, t))


@router.post("/{tid}/preview", response_model=schemas.TemplatePreviewOut)
def preview_template(tid: str, data: schemas.TemplatePreviewIn, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.TemplatePreviewOut:
    """Render the draft without creating anything — see the wording before committing to it."""
    t = _get_owned(db, user, tid)
    org = db.get(models.Tenant, user.tenant_id)
    contract_vars = {
        "counterparty": data.counterparty, "title": data.title,
        "our_entity": org.name if org else "", "org": org.name if org else "",
        "us": org.name if org else "", "today": dt.date.today(),
        "type": (t.contract_type or "other").replace("_", " ").title(),
        "currency": t.default_currency, "governing_law": t.default_governing_law,
    }
    return schemas.TemplatePreviewOut(
        **template_service.preview(db, t, data.values, contract_vars=contract_vars,
                                   choices=data.clause_choices, extras=data.extra_clauses)
    )


@router.post("/{tid}/generate", response_model=schemas.ContractDetail,
             status_code=status.HTTP_201_CREATED)
def generate_contract(tid: str, data: schemas.GenerateContractIn, request: Request,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    """Fill the form, and the system generates the draft from the approved template.

    Validation is server-side and refuses rather than producing a document with gaps in it.
    """
    from .contracts import _detail

    t = _get_owned(db, user, tid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to create contracts.")
    org = db.get(models.Tenant, user.tenant_id)
    contract_vars = {
        "counterparty": data.counterparty, "title": data.title,
        "our_entity": org.name if org else "", "org": org.name if org else "",
        "us": org.name if org else "", "today": dt.date.today(),
        "type": (t.contract_type or "other").replace("_", " ").title(),
        "currency": t.default_currency, "governing_law": t.default_governing_law,
        "effective_date": data.effective_date or dt.date.today(),
        "end_date": data.end_date, "value": data.value or 0.0,
    }
    try:
        body, values, version_no, included = template_service.generate_body(
            db, t, data.values, contract_vars=contract_vars,
            allow_unresolved=data.allow_unresolved,
            choices=data.clause_choices, extras=data.extra_clauses,
        )
    except (MergeError, ClauseError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    c = _spawn(db, user, t, data, request, body=body, values=values, version_no=version_no,
               source_note="template_merge", included_clauses=included)
    db.commit()
    db.refresh(c)
    return _detail(db, c)


@router.post("/suggest-fields", response_model=schemas.SuggestFieldsOut)
def suggest_fields(data: schemas.SuggestFieldsIn,
                   user: models.User = Depends(get_current_user)) -> schemas.SuggestFieldsOut:
    """Scaffold field definitions from the placeholders a pasted body already uses.

    Authoring aid: paste a Word template full of {{merchant_name}} and get the form built
    rather than transcribing every placeholder by hand.
    """
    suggested = merge_engine.suggest_fields(data.body, [])
    return schemas.SuggestFieldsOut(
        fields=[schemas.TemplateFieldOut(**f.to_dict()) for f in suggested]
    )


# ---------------------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------------------


def _apply(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Run a template_service call, turning its refusals into 400s."""
    try:
        return action(*args, **kwargs)
    except MergeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{tid}/submit", response_model=schemas.ContractTemplateOut)
def submit_template(tid: str, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    """Send a draft template for approval. It cannot be used until somebody approves it."""
    t = _get_owned(db, user, tid)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to edit templates.")
    _apply(template_service.submit_for_approval, db, t, actor=user, ip=client_ip(request))
    db.commit()
    db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.post("/{tid}/approve", response_model=schemas.ContractTemplateOut)
def approve_template(tid: str, data: schemas.TemplateApprovalIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    """Approve the template into use and freeze the approved wording as a version."""
    t = _get_owned(db, user, tid)
    _apply(template_service.approve, db, t, actor=user, note=data.note,
           effective_from=data.effective_from, ip=client_ip(request))
    db.commit()
    db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.post("/{tid}/reject", response_model=schemas.ContractTemplateOut)
def reject_template(tid: str, data: schemas.TemplateRejectIn, request: Request,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    """Send it back to the author with a reason."""
    t = _get_owned(db, user, tid)
    _apply(template_service.reject, db, t, actor=user, reason=data.reason,
           ip=client_ip(request))
    db.commit()
    db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.post("/{tid}/retire", response_model=schemas.ContractTemplateOut)
def retire_template(tid: str, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.ContractTemplateOut:
    """Take a template out of use. Not a delete — contracts still point at its versions."""
    t = _get_owned(db, user, tid)
    if user.role not in {"owner", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to retire templates.")
    template_service.retire(db, t, actor=user, ip=client_ip(request))
    db.commit()
    db.refresh(t)
    return schemas.ContractTemplateOut.model_validate(t)


@router.get("/{tid}/versions", response_model=list[schemas.TemplateVersionOut])
def template_versions(tid: str, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> list[schemas.TemplateVersionOut]:
    """Every approved revision, newest first. The answer to "which wording was in force?"."""
    t = _get_owned(db, user, tid)
    rows = db.scalars(
        select(models.ContractTemplateVersion)
        .where(models.ContractTemplateVersion.template_id == t.id,
               models.ContractTemplateVersion.tenant_id == user.tenant_id)
        .order_by(desc(models.ContractTemplateVersion.version_no))
    ).all()
    return [schemas.TemplateVersionOut.model_validate(r) for r in rows]


@router.get("/{tid}/optional-clauses", response_model=list[dict])
def template_optional_clauses(tid: str, db: Session = Depends(get_db),
                              user: models.User = Depends(get_current_user)) -> list[dict]:
    """Approved clauses a drafter may add on top of what this template already references."""
    t = _get_owned(db, user, tid)
    return template_service.optional_clauses(db, t)
