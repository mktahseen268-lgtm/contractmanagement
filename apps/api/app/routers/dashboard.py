import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_ACTIVE_STATUSES = {"active", "expiring"}
_RISKY = {"high", "critical"}


def _owner_names(db: Session, tenant_id: str) -> dict[str, str]:
    return {r[0]: r[1] for r in db.execute(select(models.User.id, models.User.name).where(models.User.tenant_id == tenant_id)).all()}


def _list_item(c: models.Contract, names: dict[str, str]) -> schemas.ContractListItem:
    item = schemas.ContractListItem.model_validate(c)
    item.owner_name = names.get(c.owner_id, "")
    return item


@router.get("", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.DashboardOut:
    tid = user.tenant_id
    today = dt.date.today()
    soon = today + dt.timedelta(days=30)

    def count(*conds) -> int:
        return db.scalar(select(func.count(models.Contract.id)).where(models.Contract.tenant_id == tid, *conds)) or 0

    total = count()
    pending = count(models.Contract.status == "in_review")
    awaiting_sig = count(models.Contract.status == "out_for_signature")
    expiring = count(models.Contract.status.in_(_ACTIVE_STATUSES), models.Contract.end_date.is_not(None), models.Contract.end_date <= soon, models.Contract.end_date >= today)
    open_risks = count(models.Contract.status.notin_(["expired", "terminated", "voided"]), models.Contract.risk_level.in_(list(_RISKY)))
    active_value = db.scalar(select(func.coalesce(func.sum(models.Contract.value), 0.0)).where(models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES))) or 0.0

    by_status = [schemas.StatusCount(status=r[0], count=r[1]) for r in db.execute(select(models.Contract.status, func.count()).where(models.Contract.tenant_id == tid).group_by(models.Contract.status)).all()]
    by_type = [schemas.StatusCount(status=r[0], count=r[1]) for r in db.execute(select(models.Contract.type, func.count()).where(models.Contract.tenant_id == tid).group_by(models.Contract.type)).all()]

    recent = [
        schemas.ActivityItem(id=r.id, at=r.at, actor_name=r.actor_name, action=r.action, object_type=r.object_type, object_id=r.object_id, object_label=r.object_label)
        for r in db.scalars(select(models.AuditLog).where(models.AuditLog.tenant_id == tid).order_by(desc(models.AuditLog.at)).limit(15)).all()
    ]

    names = _owner_names(db, tid)
    my_open = [
        _list_item(c, names)
        for c in db.scalars(
            select(models.Contract).where(models.Contract.tenant_id == tid, models.Contract.owner_id == user.id, models.Contract.status.notin_(["expired", "terminated", "voided", "active"])).order_by(desc(models.Contract.updated_at)).limit(6)
        ).all()
    ]
    expiring_soon = [
        _list_item(c, names)
        for c in db.scalars(
            select(models.Contract).where(models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES), models.Contract.end_date.is_not(None), models.Contract.end_date <= soon).order_by(models.Contract.end_date).limit(6)
        ).all()
    ]

    return schemas.DashboardOut(
        total_contracts=total,
        pending_approvals=pending,
        awaiting_signature=awaiting_sig,
        expiring_30d=expiring,
        active_value=active_value,
        open_risks=open_risks,
        by_status=by_status,
        by_type=by_type,
        recent_activity=recent,
        my_open=my_open,
        expiring_soon=expiring_soon,
    )
