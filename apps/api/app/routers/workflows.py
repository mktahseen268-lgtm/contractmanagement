from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from .. import workflow_service as wf
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/workflows", tags=["workflows"])

_MANAGE_ROLES = {"owner", "admin", "manager"}
_VALID_TYPES = {"nda", "msa", "lease", "employment", "vendor", "service", "other"}
_VALID_ASSIGNEE_ROLES = {"approver", "manager", "admin", "owner"}
_VALID_STATUSES = {"draft", "active", "archived"}


def _require_manage(user: models.User) -> None:
    if user.role not in _MANAGE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners, admins, or managers can manage workflows.")


def _validate_steps(db: Session, tenant_id: str, steps: list[schemas.WorkflowStep]) -> list[dict]:
    if len(steps) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A workflow can have at most 20 steps.")
    out: list[dict] = []
    for s in steps:
        kind = "user" if s.assignee_kind == "user" else "role"
        if kind == "role":
            if s.assignee_value not in _VALID_ASSIGNEE_ROLES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid assignee role '{s.assignee_value}'.")
        else:
            u = db.get(models.User, s.assignee_value)
            if u is None or u.tenant_id != tenant_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A step is assigned to an unknown user.")
        out.append({"name": (s.name or "").strip()[:200] or "Approval step", "assignee_kind": kind, "assignee_value": s.assignee_value})
    return out


def _validate_types(types: list[str]) -> list[str]:
    bad = [t for t in types if t not in _VALID_TYPES]
    if bad:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown contract type(s): {', '.join(bad)}")
    return types


def _list_item(db: Session, w: models.WorkflowDefinition) -> schemas.WorkflowDefinitionListItem:
    run_count = db.scalar(select(func.count(models.WorkflowRun.id)).where(models.WorkflowRun.definition_id == w.id)) or 0
    return schemas.WorkflowDefinitionListItem(
        id=w.id, name=w.name, status=w.status, default_for_types=w.default_for_types or [],
        step_count=len(w.steps or []), run_count=run_count, created_at=w.created_at, updated_at=w.updated_at,
    )


def _get_owned(db: Session, user: models.User, wf_id: str) -> models.WorkflowDefinition:
    w = db.get(models.WorkflowDefinition, wf_id)
    if w is None or w.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return w


@router.get("", response_model=list[schemas.WorkflowDefinitionListItem])
def list_workflows(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.WorkflowDefinitionListItem]:
    rows = db.scalars(select(models.WorkflowDefinition).where(models.WorkflowDefinition.tenant_id == user.tenant_id).order_by(desc(models.WorkflowDefinition.updated_at))).all()
    return [_list_item(db, r) for r in rows]


@router.post("", response_model=schemas.WorkflowDefinitionDetail, status_code=status.HTTP_201_CREATED)
def create_workflow(data: schemas.WorkflowDefinitionIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.WorkflowDefinitionDetail:
    _require_manage(user)
    steps = _validate_steps(db, user.tenant_id, data.steps)
    st = data.status if data.status in _VALID_STATUSES else "draft"
    if st == "active" and not steps:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An active workflow needs at least one step.")
    w = models.WorkflowDefinition(
        tenant_id=user.tenant_id, name=(data.name or "").strip() or "Untitled workflow", status=st,
        default_for_types=_validate_types(data.default_for_types or []), steps=steps, created_by=user.id,
    )
    db.add(w)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="workflow.created", actor=user, object_type="workflow", object_id=w.id, object_label=w.name, ip=client_ip(request))
    db.commit()
    db.refresh(w)
    return schemas.WorkflowDefinitionDetail.model_validate(w)


@router.get("/{wf_id}", response_model=schemas.WorkflowDefinitionDetail)
def get_workflow(wf_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.WorkflowDefinitionDetail:
    return schemas.WorkflowDefinitionDetail.model_validate(_get_owned(db, user, wf_id))


@router.patch("/{wf_id}", response_model=schemas.WorkflowDefinitionDetail)
def update_workflow(wf_id: str, data: schemas.WorkflowDefinitionUpdateIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.WorkflowDefinitionDetail:
    _require_manage(user)
    w = _get_owned(db, user, wf_id)
    if data.name is not None and data.name.strip():
        w.name = data.name.strip()
    if data.steps is not None:
        w.steps = _validate_steps(db, user.tenant_id, data.steps)
    if data.default_for_types is not None:
        w.default_for_types = _validate_types(data.default_for_types)
    if data.status is not None:
        if data.status not in _VALID_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status.")
        if data.status == "active" and not (w.steps or []):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An active workflow needs at least one step.")
        w.status = data.status
        if data.status == "archived":
            w.default_for_types = []
    record(db, tenant_id=user.tenant_id, action="workflow.updated", actor=user, object_type="workflow", object_id=w.id, object_label=w.name, ip=client_ip(request))
    db.commit()
    db.refresh(w)
    return schemas.WorkflowDefinitionDetail.model_validate(w)


@router.delete("/{wf_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_workflow(wf_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> Response:
    _require_manage(user)
    w = _get_owned(db, user, wf_id)
    w.status = "archived"
    w.default_for_types = []
    record(db, tenant_id=user.tenant_id, action="workflow.archived", actor=user, object_type="workflow", object_id=w.id, object_label=w.name, ip=client_ip(request))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{wf_id}/runs", response_model=list[schemas.WorkflowRunListItem])
def workflow_runs(wf_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.WorkflowRunListItem]:
    _get_owned(db, user, wf_id)
    runs = db.scalars(
        select(models.WorkflowRun).where(models.WorkflowRun.tenant_id == user.tenant_id, models.WorkflowRun.definition_id == wf_id).order_by(desc(models.WorkflowRun.started_at)).limit(200)
    ).all()
    out: list[schemas.WorkflowRunListItem] = []
    for r in runs:
        c = db.get(models.Contract, r.contract_id)
        cur = next((s for s in wf.run_steps(db, r.id) if s.step_index == r.current_index), None)
        out.append(
            schemas.WorkflowRunListItem(
                id=r.id, contract_id=r.contract_id, contract_title=(c.title if c else "—"), definition_name=r.definition_name,
                status=r.status, current_step_name=(cur.name if (cur and r.status == "running") else "—"),
                started_by_name=r.started_by_name, started_at=r.started_at, completed_at=r.completed_at,
            )
        )
    return out
