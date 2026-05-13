from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])

_AUDIT_ROLES = {"owner", "admin", "auditor"}


@router.get("", response_model=schemas.AuditListOut)
def list_audit(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    q: str | None = None,
    action: str | None = None,
    object_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> schemas.AuditListOut:
    stmt = select(models.AuditLog).where(models.AuditLog.tenant_id == user.tenant_id)
    # Non-privileged users only see their own actions + actions on objects they own is non-trivial;
    # for the scaffold: privileged roles see all, others see only their own actor entries.
    if user.role not in _AUDIT_ROLES:
        stmt = stmt.where(models.AuditLog.actor_id == user.id)
    if action:
        stmt = stmt.where(models.AuditLog.action == action)
    if object_id:
        stmt = stmt.where(models.AuditLog.object_id == object_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(models.AuditLog.object_label).like(like), func.lower(models.AuditLog.actor_name).like(like), func.lower(models.AuditLog.action).like(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(desc(models.AuditLog.at)).offset((page - 1) * page_size).limit(page_size)).all()
    return schemas.AuditListOut(items=[schemas.AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)
