import datetime as dt

from fastapi import APIRouter, Depends, Query
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


# ---------- shared computation (used by both the aggregate and the focused endpoints) ----------


def _kpis(db: Session, tid: str) -> schemas.DashboardKpisOut:
    today = dt.date.today()
    soon = today + dt.timedelta(days=30)

    def count(*conds) -> int:
        return db.scalar(select(func.count(models.Contract.id)).where(models.Contract.tenant_id == tid, *conds)) or 0

    return schemas.DashboardKpisOut(
        total_contracts=count(),
        pending_approvals=count(models.Contract.status == "in_review"),
        awaiting_signature=count(models.Contract.status == "out_for_signature"),
        expiring_30d=count(models.Contract.status.in_(_ACTIVE_STATUSES), models.Contract.end_date.is_not(None), models.Contract.end_date <= soon, models.Contract.end_date >= today),
        open_risks=count(models.Contract.status.notin_(["expired", "terminated", "voided"]), models.Contract.risk_level.in_(list(_RISKY))),
        active_value=db.scalar(select(func.coalesce(func.sum(models.Contract.value), 0.0)).where(models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES))) or 0.0,
    )


def _distribution(db: Session, tid: str) -> schemas.DashboardDistributionOut:
    by_status = [schemas.StatusCount(status=r[0], count=r[1]) for r in db.execute(select(models.Contract.status, func.count()).where(models.Contract.tenant_id == tid).group_by(models.Contract.status)).all()]
    by_type = [schemas.StatusCount(status=r[0], count=r[1]) for r in db.execute(select(models.Contract.type, func.count()).where(models.Contract.tenant_id == tid).group_by(models.Contract.type)).all()]
    return schemas.DashboardDistributionOut(by_status=by_status, by_type=by_type)


def _activity(db: Session, tid: str) -> list[schemas.ActivityItem]:
    return [
        schemas.ActivityItem(id=r.id, at=r.at, actor_name=r.actor_name, action=r.action, object_type=r.object_type, object_id=r.object_id, object_label=r.object_label)
        for r in db.scalars(select(models.AuditLog).where(models.AuditLog.tenant_id == tid).order_by(desc(models.AuditLog.at)).limit(15)).all()
    ]


def _my_open(db: Session, tid: str, user_id: str, names: dict[str, str]) -> list[schemas.ContractListItem]:
    return [
        _list_item(c, names)
        for c in db.scalars(
            select(models.Contract).where(models.Contract.tenant_id == tid, models.Contract.owner_id == user_id, models.Contract.status.notin_(["expired", "terminated", "voided", "active"])).order_by(desc(models.Contract.updated_at)).limit(6)
        ).all()
    ]


def _expiring_soon(db: Session, tid: str, names: dict[str, str]) -> list[schemas.ContractListItem]:
    today = dt.date.today()
    soon = today + dt.timedelta(days=30)
    return [
        _list_item(c, names)
        for c in db.scalars(
            select(models.Contract).where(models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES), models.Contract.end_date.is_not(None), models.Contract.end_date <= soon).order_by(models.Contract.end_date).limit(6)
        ).all()
    ]


# ---------- focused endpoints (web fetches these in parallel; each card renders on arrival) ----------


@router.get("/kpis", response_model=schemas.DashboardKpisOut)
def dashboard_kpis(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.DashboardKpisOut:
    return _kpis(db, user.tenant_id)


@router.get("/distribution", response_model=schemas.DashboardDistributionOut)
def dashboard_distribution(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.DashboardDistributionOut:
    return _distribution(db, user.tenant_id)


@router.get("/activity", response_model=list[schemas.ActivityItem])
def dashboard_activity(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.ActivityItem]:
    return _activity(db, user.tenant_id)


@router.get("/attention", response_model=list[schemas.ContractListItem])
def dashboard_attention(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.ContractListItem]:
    names = _owner_names(db, user.tenant_id)
    return _my_open(db, user.tenant_id, user.id, names)


@router.get("/trends", response_model=schemas.DashboardTrendsOut)
def dashboard_trends(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    weeks: int = Query(8, ge=4, le=26),
) -> schemas.DashboardTrendsOut:
    """Real weekly trend of contracts created (count + value), bucketed by ISO week. `weeks`
    drives the time-range toggle (4–26). Computed in Python so it's dialect-agnostic (no
    date_trunc) and tenant-scoped at the query."""
    tid = user.tenant_id
    today = dt.date.today()
    start_of_week = today - dt.timedelta(days=today.weekday())  # Monday of this week
    window_start = start_of_week - dt.timedelta(weeks=weeks - 1)
    window_start_dt = dt.datetime.combine(window_start, dt.time.min)

    rows = db.execute(
        select(models.Contract.created_at, models.Contract.value).where(
            models.Contract.tenant_id == tid, models.Contract.created_at >= window_start_dt
        )
    ).all()

    counts = [0] * weeks
    values = [0.0] * weeks
    for created_at, value in rows:
        d = created_at.date() if hasattr(created_at, "date") else created_at
        idx = (d - window_start).days // 7
        if 0 <= idx < weeks:
            counts[idx] += 1
            values[idx] += float(value or 0.0)

    points = [
        schemas.DashboardTrendPoint(label=(window_start + dt.timedelta(weeks=i)).strftime("%b %d"), contracts=counts[i], value=values[i])
        for i in range(weeks)
    ]
    last, prev = counts[-1], (counts[-2] if weeks >= 2 else 0)
    delta_pct = ((last - prev) / prev * 100.0) if prev > 0 else (100.0 if last > 0 else 0.0)
    return schemas.DashboardTrendsOut(points=points, total_contracts=sum(counts), delta_pct=round(delta_pct, 1))


# ---------- aggregate (kept for backward compatibility; same data, one round-trip) ----------


@router.get("", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.DashboardOut:
    tid = user.tenant_id
    names = _owner_names(db, tid)
    kpis = _kpis(db, tid)
    dist = _distribution(db, tid)
    return schemas.DashboardOut(
        total_contracts=kpis.total_contracts,
        pending_approvals=kpis.pending_approvals,
        awaiting_signature=kpis.awaiting_signature,
        expiring_30d=kpis.expiring_30d,
        active_value=kpis.active_value,
        open_risks=kpis.open_risks,
        by_status=dist.by_status,
        by_type=dist.by_type,
        recent_activity=_activity(db, tid),
        my_open=_my_open(db, tid, user.id, names),
        expiring_soon=_expiring_soon(db, tid, names),
    )
