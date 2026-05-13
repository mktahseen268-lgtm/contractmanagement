"""Reports & analytics — portfolio dashboards (status/type/value, expiring & renewal pipeline,
cycle-time, approver throughput) + a contracts CSV export. v1 returns one consolidated summary;
charts/cards in the UI read from it. (Reports are designed in docs/12; ↑expand later: comparisons
across periods, saved report definitions, scheduled email exports, per-contract obligations.)"""

import csv
import datetime as dt
import io
import statistics
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])

_ACTIVE_STATUSES = ["active", "expiring"]
_OPEN_STATUSES = ["draft", "in_review", "changes_requested", "approved", "out_for_signature", "signed"]
_CLOSED_STATUSES = ["expired", "terminated", "voided"]


def _parse_range(date_from: dt.date | None, date_to: dt.date | None) -> tuple[dt.date, dt.date]:
    """Default range is the last 90 days, ending today."""
    today = dt.date.today()
    if date_to is None:
        date_to = today
    if date_from is None:
        date_from = date_to - dt.timedelta(days=90)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _bounds_dt(date_from: dt.date, date_to: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Half-open [from 00:00, to+1 00:00) — comparing against the naive UTC datetimes the app stores."""
    return dt.datetime.combine(date_from, dt.time.min), dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min)


def _bucket(label: str, count: int, value: float = 0.0) -> schemas.ReportBucket:
    return schemas.ReportBucket(label=label, count=count, value=round(value, 2))


def _median(xs: list[float]) -> float:
    return round(statistics.median(xs), 2) if xs else 0.0


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 2) if xs else 0.0


def _months_between(a: dt.date, b: dt.date) -> list[str]:
    """List of YYYY-MM labels from month-of-a through month-of-b, inclusive."""
    cur = dt.date(a.year, a.month, 1)
    end = dt.date(b.year, b.month, 1)
    out: list[str] = []
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        ny, nm = (cur.year + (cur.month // 12), (cur.month % 12) + 1)
        cur = dt.date(ny, nm, 1)
    return out


@router.get("/summary", response_model=schemas.ReportSummaryOut)
def summary(
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.ReportSummaryOut:
    rfrom, rto = _parse_range(date_from, date_to)
    dt_from, dt_to = _bounds_dt(rfrom, rto)
    tid = user.tenant_id
    today = dt.date.today()

    # --- KPI strip
    total = db.scalar(select(func.count(models.Contract.id)).where(models.Contract.tenant_id == tid)) or 0
    created_in_range = db.scalar(select(func.count(models.Contract.id)).where(
        models.Contract.tenant_id == tid, models.Contract.created_at >= dt_from, models.Contract.created_at < dt_to,
    )) or 0
    signed_in_range = db.scalar(select(func.count(models.SignatureEnvelope.id)).where(
        models.SignatureEnvelope.tenant_id == tid, models.SignatureEnvelope.status == "completed",
        models.SignatureEnvelope.completed_at >= dt_from, models.SignatureEnvelope.completed_at < dt_to,
    )) or 0
    active_count = db.scalar(select(func.count(models.Contract.id)).where(
        models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
    )) or 0
    active_value = db.scalar(select(func.coalesce(func.sum(models.Contract.value), 0.0)).where(
        models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
    )) or 0.0
    exp30 = today + dt.timedelta(days=30)
    exp90 = today + dt.timedelta(days=90)
    expiring_30d = db.scalar(select(func.count(models.Contract.id)).where(
        models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
        models.Contract.end_date.is_not(None), models.Contract.end_date >= today, models.Contract.end_date <= exp30,
    )) or 0
    expiring_90d = db.scalar(select(func.count(models.Contract.id)).where(
        models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
        models.Contract.end_date.is_not(None), models.Contract.end_date >= today, models.Contract.end_date <= exp90,
    )) or 0

    # --- distributions (current snapshot)
    by_status = [_bucket(r[0], r[1]) for r in db.execute(
        select(models.Contract.status, func.count()).where(models.Contract.tenant_id == tid).group_by(models.Contract.status).order_by(desc(func.count()))
    ).all()]
    by_type = [_bucket(r[0], r[1], r[2] or 0.0) for r in db.execute(
        select(models.Contract.type, func.count(), func.coalesce(func.sum(models.Contract.value), 0.0))
        .where(models.Contract.tenant_id == tid)
        .group_by(models.Contract.type).order_by(desc(func.count()))
    ).all()]
    by_risk = [_bucket(r[0], r[1]) for r in db.execute(
        select(models.Contract.risk_level, func.count()).where(
            models.Contract.tenant_id == tid, models.Contract.status.notin_(_CLOSED_STATUSES),
        ).group_by(models.Contract.risk_level).order_by(desc(func.count()))
    ).all()]
    by_department = [
        _bucket((r[0] or "Unassigned"), r[1], r[2] or 0.0)
        for r in db.execute(
            select(models.Contract.department, func.count(), func.coalesce(func.sum(models.Contract.value), 0.0))
            .where(models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES))
            .group_by(models.Contract.department).order_by(desc(func.coalesce(func.sum(models.Contract.value), 0.0)))
        ).all()
    ]

    # --- new per month (calendar months in the requested range)
    month_rows = db.execute(
        select(models.Contract.created_at, models.Contract.value).where(
            models.Contract.tenant_id == tid, models.Contract.created_at >= dt_from, models.Contract.created_at < dt_to,
        )
    ).all()
    month_buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "value": 0.0})
    for created_at, value in month_rows:
        key = created_at.strftime("%Y-%m")
        month_buckets[key]["count"] += 1
        month_buckets[key]["value"] += float(value or 0.0)
    new_per_month = [
        schemas.ReportSeriesPoint(label=m, count=int(month_buckets[m]["count"]), value=round(month_buckets[m]["value"], 2))
        for m in _months_between(rfrom, rto)
    ]

    # --- cycle time (approval = workflow_runs; signature = envelopes; end-to-end = contract.created → first envelope.completed)
    approval_runs = db.execute(
        select(models.WorkflowRun.started_at, models.WorkflowRun.completed_at).where(
            models.WorkflowRun.tenant_id == tid, models.WorkflowRun.status == "approved",
            models.WorkflowRun.completed_at.is_not(None),
            models.WorkflowRun.completed_at >= dt_from, models.WorkflowRun.completed_at < dt_to,
        )
    ).all()
    approval_days = [max((c - s).total_seconds() / 86400, 0.0) for s, c in approval_runs]

    sig_completed = db.execute(
        select(models.SignatureEnvelope.contract_id, models.SignatureEnvelope.sent_at, models.SignatureEnvelope.completed_at).where(
            models.SignatureEnvelope.tenant_id == tid, models.SignatureEnvelope.status == "completed",
            models.SignatureEnvelope.sent_at.is_not(None), models.SignatureEnvelope.completed_at.is_not(None),
            models.SignatureEnvelope.completed_at >= dt_from, models.SignatureEnvelope.completed_at < dt_to,
        )
    ).all()
    signature_days = [max((c - s).total_seconds() / 86400, 0.0) for _, s, c in sig_completed]

    end_to_end_days: list[float] = []
    if sig_completed:
        cids = [cid for cid, _, _ in sig_completed]
        created_lookup = {r[0]: r[1] for r in db.execute(select(models.Contract.id, models.Contract.created_at).where(models.Contract.id.in_(cids))).all()}
        for cid, _s, c in sig_completed:
            cr = created_lookup.get(cid)
            if cr is not None:
                end_to_end_days.append(max((c - cr).total_seconds() / 86400, 0.0))

    cycle = schemas.ReportCycleTime(
        approval_avg_days=_mean(approval_days), approval_median_days=_median(approval_days), approval_n=len(approval_days),
        signature_avg_days=_mean(signature_days), signature_median_days=_median(signature_days), signature_n=len(signature_days),
        end_to_end_avg_days=_mean(end_to_end_days), end_to_end_n=len(end_to_end_days),
    )

    # --- throughput counts in range
    def _wf_count(status: str | None, *, by_start: bool) -> int:
        q = select(func.count(models.WorkflowRun.id)).where(models.WorkflowRun.tenant_id == tid)
        if status:
            q = q.where(models.WorkflowRun.status == status)
        ts = models.WorkflowRun.started_at if by_start else models.WorkflowRun.completed_at
        if not by_start:
            q = q.where(models.WorkflowRun.completed_at.is_not(None))
        q = q.where(ts >= dt_from, ts < dt_to)
        return db.scalar(q) or 0

    def _env_count(status: str | None, ts_col) -> int:
        q = select(func.count(models.SignatureEnvelope.id)).where(models.SignatureEnvelope.tenant_id == tid, ts_col.is_not(None), ts_col >= dt_from, ts_col < dt_to)
        if status:
            q = q.where(models.SignatureEnvelope.status == status)
        return db.scalar(q) or 0

    throughput = schemas.ReportThroughput(
        workflow_runs_started=_wf_count(None, by_start=True),
        workflow_runs_approved=_wf_count("approved", by_start=False),
        workflow_runs_rejected=_wf_count("rejected", by_start=False),
        workflow_runs_changes_requested=_wf_count("changes_requested", by_start=False),
        envelopes_sent=_env_count(None, models.SignatureEnvelope.sent_at),
        envelopes_completed=_env_count("completed", models.SignatureEnvelope.completed_at),
        envelopes_declined=_env_count("declined", models.SignatureEnvelope.completed_at),
        envelopes_voided=db.scalar(
            select(func.count(models.SignatureEnvelope.id)).where(
                models.SignatureEnvelope.tenant_id == tid, models.SignatureEnvelope.status == "voided",
                # voided envelopes don't have a "voided_at" — approximate by created_at within range
                models.SignatureEnvelope.created_at >= dt_from, models.SignatureEnvelope.created_at < dt_to,
            )
        ) or 0,
    )

    # --- expiring pipeline buckets + top 10
    horizons = [(0, 30, "0–30d"), (31, 60, "31–60d"), (61, 90, "61–90d"), (91, 180, "91–180d")]
    expiring_buckets: list[schemas.ReportBucket] = []
    for lo, hi, label in horizons:
        n = db.scalar(select(func.count(models.Contract.id)).where(
            models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
            models.Contract.end_date.is_not(None),
            models.Contract.end_date >= today + dt.timedelta(days=lo),
            models.Contract.end_date <= today + dt.timedelta(days=hi),
        )) or 0
        v = db.scalar(select(func.coalesce(func.sum(models.Contract.value), 0.0)).where(
            models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
            models.Contract.end_date.is_not(None),
            models.Contract.end_date >= today + dt.timedelta(days=lo),
            models.Contract.end_date <= today + dt.timedelta(days=hi),
        )) or 0.0
        expiring_buckets.append(_bucket(label, n, v))

    expiring_top = [
        schemas.ReportExpiringItem(
            id=c.id, reference_no=c.reference_no, title=c.title, counterparty=c.counterparty,
            end_date=c.end_date, days_to_end=(c.end_date - today).days if c.end_date else 0,
            value=c.value or 0.0, currency=c.currency, status=c.status,
        )
        for c in db.scalars(
            select(models.Contract).where(
                models.Contract.tenant_id == tid, models.Contract.status.in_(_ACTIVE_STATUSES),
                models.Contract.end_date.is_not(None),
                models.Contract.end_date >= today, models.Contract.end_date <= today + dt.timedelta(days=180),
            ).order_by(models.Contract.end_date).limit(10)
        ).all()
    ]

    # --- top approvers (by decisions in range)
    rows = db.execute(
        select(models.WorkflowRunStep.decided_by, models.WorkflowRunStep.decided_by_name, models.WorkflowRunStep.decision,
               models.WorkflowRunStep.decided_at, models.WorkflowRunStep.created_at)
        .where(
            models.WorkflowRunStep.tenant_id == tid, models.WorkflowRunStep.decided_by.is_not(None),
            models.WorkflowRunStep.decided_at.is_not(None),
            models.WorkflowRunStep.decided_at >= dt_from, models.WorkflowRunStep.decided_at < dt_to,
        )
    ).all()
    by_user: dict[str, dict] = {}
    for uid, uname, decision, decided_at, created_at in rows:
        rec = by_user.setdefault(uid, {"name": uname or "", "approved": 0, "rejected": 0, "changes_requested": 0, "wait": []})
        if decision == "approve":
            rec["approved"] += 1
        elif decision == "reject":
            rec["rejected"] += 1
        elif decision == "changes_requested":
            rec["changes_requested"] += 1
        if created_at is not None and decided_at is not None:
            rec["wait"].append(max((decided_at - created_at).total_seconds() / 3600.0, 0.0))
    top_approvers = sorted(
        (
            schemas.ReportApprover(
                user_id=uid, name=rec["name"],
                approved=rec["approved"], rejected=rec["rejected"], changes_requested=rec["changes_requested"],
                total=rec["approved"] + rec["rejected"] + rec["changes_requested"],
                avg_response_hours=round(sum(rec["wait"]) / len(rec["wait"]), 1) if rec["wait"] else 0.0,
            )
            for uid, rec in by_user.items()
        ),
        key=lambda x: x.total, reverse=True,
    )[:10]

    return schemas.ReportSummaryOut(
        range_from=rfrom, range_to=rto,
        total_contracts=total, created_in_range=created_in_range, signed_in_range=signed_in_range,
        active_count=active_count, active_value=active_value,
        expiring_30d=expiring_30d, expiring_90d=expiring_90d,
        by_status=by_status, by_type=by_type, by_risk=by_risk, by_department=by_department,
        new_per_month=new_per_month, cycle_time=cycle, throughput=throughput,
        expiring_buckets=expiring_buckets, expiring_top=expiring_top, top_approvers=top_approvers,
    )


@router.get("/stuck", response_model=list[schemas.StuckItem])
def reports_stuck(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.StuckItem]:
    """Across the workspace: every running approval step + every open signature envelope,
    sorted oldest-waiting first. The "Where contracts are stuck" card on /reports reads this."""
    tid = user.tenant_id
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    items: list[schemas.StuckItem] = []
    names_by_id = {r[0]: r[1] for r in db.execute(select(models.User.id, models.User.name).where(models.User.tenant_id == tid)).all()}

    # active workflow steps
    rows = db.execute(
        select(models.WorkflowRunStep, models.WorkflowRun, models.Contract)
        .join(models.WorkflowRun, models.WorkflowRunStep.run_id == models.WorkflowRun.id)
        .join(models.Contract, models.WorkflowRun.contract_id == models.Contract.id)
        .where(
            models.WorkflowRunStep.tenant_id == tid, models.WorkflowRunStep.status == "active",
            models.WorkflowRun.status == "running",
        )
    ).all()
    for step, run, c in rows:
        since = step.created_at or run.started_at
        waiting_h = max((now - since).total_seconds() / 3600.0, 0.0)
        if step.assignee_kind == "user":
            assignee = f"@{names_by_id.get(step.assignee_value, '—')}"
        else:
            assignee = f"any {(step.assignee_value or 'approver').lower()}+"
        items.append(schemas.StuckItem(
            kind="approval_step", contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no,
            contract_status=c.status, risk_level=c.risk_level, waiting_hours=round(waiting_h, 1),
            detail=f"Approval — “{step.name}” → {assignee}", href=f"/contracts/{c.id}?tab=approvals",
        ))

    # open envelopes
    envs = db.scalars(
        select(models.SignatureEnvelope).where(
            models.SignatureEnvelope.tenant_id == tid,
            models.SignatureEnvelope.status.in_(["sent", "partially_signed"]),
        )
    ).all()
    for env in envs:
        c = db.get(models.Contract, env.contract_id)
        if c is None:
            continue
        signers = list(db.scalars(
            select(models.SignatureRecipient).where(
                models.SignatureRecipient.envelope_id == env.id,
                models.SignatureRecipient.kind == "signer",
            )
        ).all())
        pending = [r for r in signers if r.status in ("sent", "viewed", "created")]
        if not pending:
            continue
        signed_n = sum(1 for r in signers if r.status == "signed")
        since = env.sent_at or env.created_at
        waiting_h = max((now - since).total_seconds() / 3600.0, 0.0)
        names = ", ".join(p.name for p in pending[:3]) + (f" +{len(pending) - 3}" if len(pending) > 3 else "")
        items.append(schemas.StuckItem(
            kind="envelope", contract_id=c.id, contract_title=c.title, contract_reference=c.reference_no,
            contract_status=c.status, risk_level=c.risk_level, waiting_hours=round(waiting_h, 1),
            detail=f"Signature — {signed_n} of {len(signers)} signed; pending {names}",
            href=f"/contracts/{c.id}?tab=signatures",
        ))

    items.sort(key=lambda i: -i.waiting_hours)
    return items[:limit]


@router.get("/contracts.csv")
def contracts_csv(
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    status: str | None = None,
    type: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream a CSV export of contracts (filterable by created_at range, status, type).
    Header: reference_no, title, type, status, owner, counterparty, department, value, currency,
    risk_level, effective_date, end_date, renewal_type, tags, created_at, updated_at."""
    rfrom, rto = _parse_range(date_from, date_to)
    dt_from, dt_to = _bounds_dt(rfrom, rto)
    tid = user.tenant_id

    q = select(models.Contract).where(
        models.Contract.tenant_id == tid,
        models.Contract.created_at >= dt_from, models.Contract.created_at < dt_to,
    )
    if status:
        q = q.where(models.Contract.status == status)
    if type:
        q = q.where(models.Contract.type == type)
    q = q.order_by(desc(models.Contract.created_at))

    owners = {r[0]: r[1] for r in db.execute(select(models.User.id, models.User.name).where(models.User.tenant_id == tid)).all()}

    def _row_iter():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "reference_no", "title", "type", "status", "owner", "counterparty", "department",
            "value", "currency", "risk_level", "effective_date", "end_date", "renewal_type",
            "tags", "created_at", "updated_at",
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        for c in db.scalars(q).yield_per(200):
            w.writerow([
                c.reference_no, c.title, c.type, c.status, owners.get(c.owner_id, ""), c.counterparty,
                c.department, c.value or 0.0, c.currency, c.risk_level,
                c.effective_date.isoformat() if c.effective_date else "",
                c.end_date.isoformat() if c.end_date else "",
                c.renewal_type,
                ";".join(c.tags or []),
                c.created_at.isoformat() if c.created_at else "",
                c.updated_at.isoformat() if c.updated_at else "",
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    fname = f"contracts_{rfrom.isoformat()}_to_{rto.isoformat()}.csv"
    return StreamingResponse(_row_iter(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{fname}"'})
