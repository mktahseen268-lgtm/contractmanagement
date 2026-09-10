"""Repository: parties, relationships, departments, folders, custom fields, and search.

One router because these are one feature — the structure a contract sits in. Search lives here
too rather than under `/contracts` because what it searches is the repository, not one
agreement.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from .. import models, repository_service, schemas, search_service
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user
from ..repository_service import RepositoryError

router = APIRouter(tags=["repository"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}
_ADMIN_ROLES = {"owner", "admin", "manager"}


def _guard(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return action(*args, **kwargs)
    except RepositoryError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


def _owned(db: Session, user: models.User, model, oid: str, what: str):  # type: ignore[no-untyped-def]
    row = db.get(model, oid)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")
    return row


# ---------------------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------------------


@router.post("/search", response_model=schemas.SearchResultOut)
def search_repository(data: schemas.SearchIn, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.SearchResultOut:
    """Full-text plus structured filters across the repository.

    POST rather than GET: the filter set is a nested object (date ranges, value bands, tag
    lists), and encoding that into a query string produces URLs nobody can read and a parser
    nobody wants to maintain.
    """
    result = search_service.search(
        db, user.tenant_id, q=data.q, filters=data.model_dump(exclude={"q", "page", "page_size"}),
        page=data.page, page_size=data.page_size,
    )
    return schemas.SearchResultOut(**result)


# ---------------------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------------------


@router.get("/parties", response_model=list[schemas.PartyOut])
def list_parties(q: str = "", kyc_status: str = "", region: str = "",
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> list[schemas.PartyOut]:
    stmt = select(models.Party).where(models.Party.tenant_id == user.tenant_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(models.Party.name.ilike(pattern),
                              models.Party.registration_no.ilike(pattern)))
    if kyc_status:
        stmt = stmt.where(models.Party.kyc_status == kyc_status)
    if region:
        stmt = stmt.where(models.Party.region == region)
    rows = db.scalars(stmt.order_by(models.Party.name.asc())).all()
    return [schemas.PartyOut.model_validate(r) for r in rows]


@router.post("/parties/check-duplicates", response_model=list[schemas.DuplicateMatchOut])
def check_duplicates(data: schemas.PartyDuplicateCheckIn, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> list[schemas.DuplicateMatchOut]:
    """What onboarding would block on, so the form can warn before the user hits save."""
    hits = repository_service.find_duplicates(
        db, user.tenant_id, data.name, data.registration_no, exclude_id=data.exclude_id or "")
    return [schemas.DuplicateMatchOut(**h) for h in hits]


@router.get("/parties/{pid}", response_model=schemas.PartyOut)
def get_party(pid: str, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)) -> schemas.PartyOut:
    return schemas.PartyOut.model_validate(_owned(db, user, models.Party, pid, "Party"))


@router.post("/parties", response_model=schemas.PartyOut, status_code=status.HTTP_201_CREATED)
def create_party(data: schemas.PartyIn, request: Request, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.PartyOut:
    """Onboard a party. Blocks on a likely duplicate unless `override_reason` is supplied."""
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to onboard parties.")
    party = _guard(repository_service.create_party, db, user.tenant_id,
                   data.model_dump(exclude={"override_reason"}), actor=user,
                   override_reason=data.override_reason, ip=client_ip(request))
    db.commit()
    db.refresh(party)
    return schemas.PartyOut.model_validate(party)


@router.patch("/parties/{pid}", response_model=schemas.PartyOut)
def update_party(pid: str, data: schemas.PartyUpdateIn, request: Request,
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.PartyOut:
    party = _owned(db, user, models.Party, pid, "Party")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to edit parties.")
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        if v is not None:
            setattr(party, k, v)
    if "name" in payload and payload["name"]:
        # The comparison key is derived, so it has to move with the name or the duplicate
        # check silently starts matching against the old spelling.
        party.name_key = repository_service.name_key(party.name)[:300]
    record(db, tenant_id=user.tenant_id, action="party.updated", actor=user,
           object_type="party", object_id=party.id, object_label=party.name,
           ip=client_ip(request), meta={"fields": list(payload.keys())})
    db.commit()
    db.refresh(party)
    return schemas.PartyOut.model_validate(party)


@router.get("/parties/{pid}/contracts", response_model=list[schemas.ContractListItem])
def party_contracts(pid: str, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> list[schemas.ContractListItem]:
    """Everything on this party's paper — the question a free-text counterparty cannot answer."""
    party = _owned(db, user, models.Party, pid, "Party")
    rows = db.scalars(
        select(models.Contract)
        .where(models.Contract.tenant_id == user.tenant_id,
               models.Contract.party_id == party.id)
        .order_by(desc(models.Contract.updated_at))
    ).all()
    return [schemas.ContractListItem.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/relations", response_model=schemas.ContractHistoryOut)
def contract_relations(contract_id: str, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> schemas.ContractHistoryOut:
    """The agreement family: what this descends from, and what descends from it."""
    contract = _owned(db, user, models.Contract, contract_id, "Contract")
    return schemas.ContractHistoryOut(**repository_service.history(db, contract))


@router.post("/contracts/{contract_id}/relations", response_model=schemas.ContractHistoryOut,
             status_code=status.HTTP_201_CREATED)
def add_relation(contract_id: str, data: schemas.RelationIn, request: Request,
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.ContractHistoryOut:
    """Link this agreement to another. `contract_id` is the child (the addendum/amendment)."""
    child = _owned(db, user, models.Contract, contract_id, "Contract")
    parent = _owned(db, user, models.Contract, data.parent_id, "Contract")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to link agreements.")
    _guard(repository_service.relate, db, parent, child, data.kind, actor=user,
           note=data.note, ip=client_ip(request))
    if data.inherit:
        repository_service.inherit_from_parent(child, parent)
    db.commit()
    db.refresh(child)
    return schemas.ContractHistoryOut(**repository_service.history(db, child))


@router.delete("/contracts/{contract_id}/relations/{relation_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def remove_relation(contract_id: str, relation_id: str, request: Request,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> None:
    _owned(db, user, models.Contract, contract_id, "Contract")
    relation = _owned(db, user, models.ContractRelation, relation_id, "Relationship")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to unlink agreements.")
    db.delete(relation)
    record(db, tenant_id=user.tenant_id, action="contract.unrelated", actor=user,
           object_type="contract", object_id=contract_id, ip=client_ip(request),
           meta={"kind": relation.kind, "parent_id": relation.parent_id})
    db.commit()


# ---------------------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------------------


@router.get("/departments", response_model=list[schemas.DepartmentOut])
def list_departments(db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> list[schemas.DepartmentOut]:
    rows = db.scalars(
        select(models.Department).where(models.Department.tenant_id == user.tenant_id)
        .order_by(models.Department.name.asc())
    ).all()
    out = []
    for d in rows:
        item = schemas.DepartmentOut.model_validate(d)
        item.contract_count = db.query(models.Contract).filter_by(
            tenant_id=user.tenant_id, department_id=d.id).count()
        if d.lead_user_id:
            lead = db.get(models.User, d.lead_user_id)
            item.lead_name = lead.name if lead else ""
        out.append(item)
    return out


@router.post("/departments", response_model=schemas.DepartmentOut,
             status_code=status.HTTP_201_CREATED)
def create_department(data: schemas.DepartmentIn, request: Request,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.DepartmentOut:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to manage departments.")
    existing = db.scalar(select(models.Department).where(
        models.Department.tenant_id == user.tenant_id,
        models.Department.name == data.name.strip()))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"A department called '{data.name}' already exists.")
    d = models.Department(tenant_id=user.tenant_id, **data.model_dump())
    d.name = d.name.strip()[:150]
    db.add(d)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="department.created", actor=user,
           object_type="department", object_id=d.id, object_label=d.name,
           ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return schemas.DepartmentOut.model_validate(d)


@router.patch("/departments/{did}", response_model=schemas.DepartmentOut)
def update_department(did: str, data: schemas.DepartmentUpdateIn, request: Request,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.DepartmentOut:
    d = _owned(db, user, models.Department, did, "Department")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to manage departments.")
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        if v is not None:
            setattr(d, k, v)
    record(db, tenant_id=user.tenant_id, action="department.updated", actor=user,
           object_type="department", object_id=d.id, object_label=d.name,
           ip=client_ip(request), meta={"fields": list(payload.keys())})
    db.commit()
    db.refresh(d)
    return schemas.DepartmentOut.model_validate(d)


# ---------------------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------------------


@router.get("/folders", response_model=list[schemas.FolderOut])
def list_folders(db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> list[schemas.FolderOut]:
    """The tree this role may see, with per-folder contract counts."""
    folders = repository_service.visible_folders(db, user.tenant_id, user.role)
    out = []
    for f in folders:
        item = schemas.FolderOut.model_validate(f)
        item.contract_count = db.query(models.Contract).filter_by(
            tenant_id=user.tenant_id, folder_id=f.id).count()
        item.depth = f.path.count("/") - 1
        out.append(item)
    return out


@router.post("/folders", response_model=schemas.FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(data: schemas.FolderIn, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.FolderOut:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to manage folders.")
    folder = _guard(repository_service.create_folder, db, user.tenant_id, data.name,
                    data.parent_id, actor=user, roles=data.visible_to_roles,
                    ip=client_ip(request))
    db.commit()
    db.refresh(folder)
    return schemas.FolderOut.model_validate(folder)


@router.post("/folders/{fid}/move", response_model=schemas.FolderOut)
def move_folder(fid: str, data: schemas.FolderMoveIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.FolderOut:
    folder = _owned(db, user, models.Folder, fid, "Folder")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to manage folders.")
    _guard(repository_service.move_folder, db, folder, data.parent_id, actor=user,
           ip=client_ip(request))
    db.commit()
    db.refresh(folder)
    return schemas.FolderOut.model_validate(folder)


@router.delete("/folders/{fid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(fid: str, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> None:
    """Delete an empty leaf folder. Refuses if anything is filed in it or under it —
    deleting a folder must never orphan an agreement."""
    folder = _owned(db, user, models.Folder, fid, "Folder")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to manage folders.")
    children = db.scalar(select(models.Folder).where(
        models.Folder.tenant_id == user.tenant_id,
        models.Folder.path.like(f"{folder.path}/%")))
    if children is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="That folder still has subfolders.")
    filed = db.query(models.Contract).filter_by(
        tenant_id=user.tenant_id, folder_id=folder.id).count()
    if filed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"{filed} agreement(s) are filed here.")
    path = folder.path
    db.delete(folder)
    record(db, tenant_id=user.tenant_id, action="folder.deleted", actor=user,
           object_type="folder", object_id=fid, object_label=path, ip=client_ip(request))
    db.commit()


# ---------------------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------------------


@router.get("/custom-fields", response_model=list[schemas.CustomFieldDefOut])
def list_custom_fields(contract_type: str = Query(default=""),
                       db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> list[schemas.CustomFieldDefOut]:
    return [schemas.CustomFieldDefOut.model_validate(d)
            for d in repository_service.field_defs(db, user.tenant_id, contract_type)]


@router.post("/custom-fields", response_model=schemas.CustomFieldDefOut,
             status_code=status.HTTP_201_CREATED)
def create_custom_field(data: schemas.CustomFieldDefIn, request: Request,
                        db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> schemas.CustomFieldDefOut:
    from ..merge_engine import FIELD_TYPES

    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to define fields.")
    if data.type not in FIELD_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown field type '{data.type}'.")
    if data.type in ("select", "multiselect") and not data.options:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"A {data.type} field needs at least one option.")
    existing = db.scalar(select(models.CustomFieldDef).where(
        models.CustomFieldDef.tenant_id == user.tenant_id,
        models.CustomFieldDef.contract_type == data.contract_type,
        models.CustomFieldDef.key == data.key))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"A field '{data.key}' already exists for that type.")
    d = models.CustomFieldDef(tenant_id=user.tenant_id, created_by=user.id,
                              **data.model_dump())
    db.add(d)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="custom_field.created", actor=user,
           object_type="custom_field", object_id=d.id, object_label=d.label or d.key,
           ip=client_ip(request), meta={"type": d.type, "contract_type": d.contract_type})
    db.commit()
    db.refresh(d)
    return schemas.CustomFieldDefOut.model_validate(d)


@router.delete("/custom-fields/{fid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_field(fid: str, request: Request, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> None:
    """Deactivate a field definition.

    The values already captured on contracts are left alone: they were recorded facts, and
    removing a definition should not quietly rewrite history.
    """
    d = _owned(db, user, models.CustomFieldDef, fid, "Field")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to define fields.")
    d.is_active = False
    record(db, tenant_id=user.tenant_id, action="custom_field.deactivated", actor=user,
           object_type="custom_field", object_id=d.id, object_label=d.label or d.key,
           ip=client_ip(request))
    db.commit()


@router.get("/contracts/{contract_id}/custom-fields", response_model=list[dict])
def contract_custom_fields(contract_id: str, db: Session = Depends(get_db),
                           user: models.User = Depends(get_current_user)) -> list[dict]:
    contract = _owned(db, user, models.Contract, contract_id, "Contract")
    return repository_service.describe_custom_fields(db, contract)


@router.put("/contracts/{contract_id}/custom-fields", response_model=list[dict])
def set_contract_custom_fields(contract_id: str, data: schemas.CustomFieldValuesIn,
                               request: Request, db: Session = Depends(get_db),
                               user: models.User = Depends(get_current_user)) -> list[dict]:
    contract = _owned(db, user, models.Contract, contract_id, "Contract")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You cannot edit this contract.")
    contract.custom_fields = _guard(repository_service.validate_custom_fields,
                                    db, contract, data.values)
    record(db, tenant_id=user.tenant_id, action="contract.custom_fields_updated", actor=user,
           object_type="contract", object_id=contract.id, object_label=contract.title,
           ip=client_ip(request), meta={"fields": sorted(contract.custom_fields.keys())})
    db.commit()
    db.refresh(contract)
    return repository_service.describe_custom_fields(db, contract)


# ---------------------------------------------------------------------------------------
# Exports (Phase 5, item 10)
# ---------------------------------------------------------------------------------------


@router.post("/exports", response_model=schemas.ExportJobOut,
             status_code=status.HTTP_201_CREATED)
def create_export(data: schemas.ExportIn, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ExportJobOut:
    """Build a spreadsheet of the repository (or a report) and return the job to download it.

    Recorded as a `BackgroundJob` so the progress tray already built for OCR and sealing
    surfaces it, and so a large export can move to the queue later without the client
    changing.
    """
    from .. import export_service
    from ..export_service import ExportError

    tenant = db.get(models.Tenant, user.tenant_id)
    try:
        job = export_service.run_export(
            db, user.tenant_id, data.kind, data.filters, actor=user,
            org_name=tenant.name if tenant else "", ip=client_ip(request),
        )
    except ExportError as e:
        db.commit()          # keep the failed job row: a failure the user cannot see is worse
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.commit()
    db.refresh(job)
    return schemas.ExportJobOut.model_validate(job)


@router.get("/exports", response_model=list[schemas.ExportJobOut])
def list_exports(db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> list[schemas.ExportJobOut]:
    rows = db.scalars(
        select(models.BackgroundJob)
        .where(models.BackgroundJob.tenant_id == user.tenant_id,
               models.BackgroundJob.type.like("export.%"))
        .order_by(desc(models.BackgroundJob.created_at))
        .limit(50)
    ).all()
    return [schemas.ExportJobOut.model_validate(r) for r in rows]


@router.get("/exports/{job_id}/download")
def download_export(job_id: str, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> StreamingResponse:
    """Fetch a finished export."""
    from .. import export_service
    from ..storage import get_storage

    job = db.get(models.BackgroundJob, job_id)
    if job is None or job.tenant_id != user.tenant_id or not job.type.startswith("export."):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    if job.status != "succeeded":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"That export {job.status}.")
    key = export_service.storage_key(job)
    storage = get_storage()
    if not storage.exists(key):
        raise HTTPException(status_code=status.HTTP_410_GONE,
                            detail="That export is no longer available. Generate it again.")
    return StreamingResponse(
        storage.open_stream(key),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="{export_service.filename(job)}"'},
    )


# ---------------------------------------------------------------------------------------
# Sanctions screening (Phase 7, item 7)
# ---------------------------------------------------------------------------------------


@router.get("/sanctions/status", response_model=schemas.SanctionsStatusOut)
def sanctions_status(db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.SanctionsStatusOut:
    """Which lists are loaded and how old they are.

    Surfaced because a screen against a list nobody has refreshed for eight months is a
    different fact from a current one, and the person relying on it has to be able to tell.
    """
    from .. import sanctions

    return schemas.SanctionsStatusOut(**sanctions.snapshot_status(db))


@router.post("/sanctions/import", response_model=dict)
def import_sanctions(data: schemas.SanctionsImportIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> dict:
    """Load a list snapshot, replacing the previous one from that source.

    Replacement rather than merge: a sanctions list is a statement about a moment, and merging
    an old snapshot into a new one silently keeps delisted people on it.
    """
    from .. import sanctions
    from ..sanctions import SanctionsError

    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to load sanctions lists.")
    try:
        result = sanctions.import_entries(
            db, data.source, data.entries, snapshot_date=data.snapshot_date,
            list_name=data.list_name, actor=user, ip=client_ip(request))
    except SanctionsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.commit()
    return {**result, "snapshot_date": str(result["snapshot_date"])}


@router.post("/parties/{pid}/screen", response_model=schemas.SanctionsScreeningOut,
             status_code=status.HTTP_201_CREATED)
def screen_party(pid: str, data: schemas.SanctionsScreenIn, request: Request,
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.SanctionsScreeningOut:
    """Screen a party against the loaded lists. A hit raises a review, never an auto-reject."""
    from .. import sanctions

    party = _owned(db, user, models.Party, pid, "Party")
    screening = sanctions.screen_party(
        db, party, actor=user,
        threshold=data.threshold if data.threshold is not None else sanctions.MATCH_THRESHOLD,
        ip=client_ip(request))
    db.commit()
    db.refresh(screening)
    return schemas.SanctionsScreeningOut.model_validate(screening)


@router.get("/sanctions/queue", response_model=list[schemas.SanctionsScreeningOut])
def sanctions_queue(status_filter: str = "review", db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> list[schemas.SanctionsScreeningOut]:
    """The analyst's queue, oldest first — the longest-waiting hit is holding somebody up."""
    from .. import sanctions

    return [schemas.SanctionsScreeningOut.model_validate(s)
            for s in sanctions.queue(db, user.tenant_id, status=status_filter)]


@router.post("/sanctions/screenings/{sid}/decide",
             response_model=schemas.SanctionsScreeningOut)
def decide_screening(sid: str, data: schemas.SanctionsDecisionIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.SanctionsScreeningOut:
    """Clear or confirm a hit. A confirmed match deactivates the party."""
    from .. import sanctions
    from ..sanctions import SanctionsError

    screening = _owned(db, user, models.SanctionsScreening, sid, "Screening")
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to decide sanctions hits.")
    try:
        sanctions.decide(db, screening, actor=user, cleared=data.cleared, note=data.note,
                         ip=client_ip(request))
    except SanctionsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.commit()
    db.refresh(screening)
    return schemas.SanctionsScreeningOut.model_validate(screening)


# ---------------------------------------------------------------------------------------
# SIEM (Phase 7, item 2)
# ---------------------------------------------------------------------------------------


@router.get("/siem/status", response_model=schemas.SiemStatusOut)
def siem_status(user: models.User = Depends(get_current_user)) -> schemas.SiemStatusOut:
    """Where security events are being shipped, and whether delivery is working."""
    from .. import siem
    from ..config import settings as cfg

    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to see the SIEM configuration.")
    return schemas.SiemStatusOut(
        enabled=siem.is_enabled(), host=cfg.siem_host, port=cfg.siem_port,
        tls=cfg.siem_tls, verify=cfg.siem_verify, format=cfg.siem_format,
        consecutive_failures=siem.get_sender().failures if siem.is_enabled() else 0,
    )


@router.post("/siem/replay", response_model=dict)
def siem_replay(since_seq: int = 0, limit: int = 1000, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> dict:
    """Re-ship audit entries to the SIEM from a given chain position.

    The recovery path for a collector outage. Because the SIEM feed is a projection of the
    audit log rather than a second log, nothing was lost while the collector was down — it can
    simply be sent again.
    """
    from .. import siem

    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to replay the SIEM feed.")
    if not siem.is_enabled():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The SIEM feed is not configured.")
    entries = db.scalars(
        select(models.AuditLog)
        .where(models.AuditLog.tenant_id == user.tenant_id,
               models.AuditLog.seq > since_seq)
        .order_by(models.AuditLog.seq.asc())
        .limit(min(10_000, max(1, limit)))
    ).all()
    return {**siem.emit_many(entries), "from_seq": since_seq, "considered": len(entries)}


# ---------------------------------------------------------------------------------------
# Connectors and the SOAP facade (Phase 7, items 4, 5, 9, 10)
# ---------------------------------------------------------------------------------------


@router.get("/connectors", response_model=dict)
def connector_status(user: models.User = Depends(get_current_user)) -> dict:
    """What is wired up. Reports destinations, never credentials."""
    from .. import connectors, siem, soap
    from ..config import settings as cfg

    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to see integrations.")
    return {
        **connectors.status(),
        "siem": {"enabled": siem.is_enabled(), "host": cfg.siem_host,
                 "format": cfg.siem_format, "tls": cfg.siem_tls},
        "sms": {"enabled": cfg.sms_backend != "null", "backend": cfg.sms_backend},
        "soap": {"enabled": soap.is_enabled(), "wsdl": "/soap?wsdl" if soap.is_enabled() else ""},
    }


@router.post("/connectors/teams/test", response_model=dict)
def test_teams(request: Request, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> dict:
    """Post a test card to the configured Teams channel.

    Worth having: a webhook URL that was pasted with a trailing space fails silently forever,
    and the first time anyone notices is when an escalation does not arrive.
    """
    from .. import connectors

    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to test integrations.")
    if not connectors.teams_enabled():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Teams is not configured.")
    ok = connectors.notify_teams(
        title="Contract Management test message",
        subtitle=f"Sent by {user.name}",
        body="If you can see this, workflow notifications will arrive in this channel.",
    )
    record(db, tenant_id=user.tenant_id, action="connector.tested", actor=user,
           object_type="connector", object_label="teams", ip=client_ip(request),
           meta={"delivered": ok})
    db.commit()
    return {"delivered": ok}


@router.get("/contracts/{contract_id}/calendar.ics")
def contract_calendar(contract_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> Response:
    """A renewal reminder as a calendar invite.

    An `.ics` attachment rather than an Exchange integration: every mail client understands
    it, it works against on-prem Exchange with no configuration, and there is no token to
    rotate. The UID is derived from the contract, so re-issuing after a date change updates
    the existing entry instead of leaving both in the calendar.
    """
    from .. import connectors

    contract = _owned(db, user, models.Contract, contract_id, "Contract")
    ics = connectors.renewal_invite(contract, attendees=[user.email])
    if ics is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="That agreement has no end date to remind you about.")
    name = f"{contract.reference_no or 'agreement'}-renewal.ics".replace("/", "_")
    return Response(content=ics, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
