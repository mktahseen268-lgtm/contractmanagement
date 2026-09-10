"""Analytics: executive KPIs, operational load, compliance posture, MIS trends, dashboards.

Every figure here is derived from the audit log and the live records rather than a cached
verdict, and every one reports the sample it was computed from. A metric that hides its own
sample size is a metric somebody will quote in a board pack without knowing it came from four
agreements.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from .. import analytics_service, models, schemas
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])

#: Who may see workspace-wide performance. Reviewer workload names individuals and their
#: lateness, which is management information rather than something everyone should browse.
_MANAGEMENT_ROLES = {"owner", "admin", "manager"}


def _management_only(user: models.User) -> None:
    if user.role not in _MANAGEMENT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to see workspace analytics.")


@router.get("/me", response_model=schemas.MyDashboardOut)
def my_dashboard(db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.MyDashboardOut:
    """My tasks, escalations, obligations and renewals — the first screen after login.

    Deliberately one call rather than four: this is the landing page, and four round trips is
    the difference between instant and flickering. No role gate — it only ever returns the
    caller's own work.
    """
    return schemas.MyDashboardOut(**analytics_service.my_dashboard(db, user))


@router.get("/executive", response_model=schemas.ExecutiveSummaryOut)
def executive(db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)) -> schemas.ExecutiveSummaryOut:
    """The headline KPI set: cycle times, bottleneck stages, renewals, escalations, policy."""
    _management_only(user)
    return schemas.ExecutiveSummaryOut(
        **analytics_service.executive_summary(db, user.tenant_id))


@router.get("/cycle-times", response_model=schemas.CycleTimesOut)
def cycle_times(since: dt.date | None = None, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.CycleTimesOut:
    """Days from raised to executed, per agreement type.

    `still_in_flight` is returned alongside: an average that silently counted unfinished
    drafts as zero would improve every time somebody started a new one.
    """
    _management_only(user)
    return schemas.CycleTimesOut(
        **analytics_service.cycle_times(db, user.tenant_id, since=since))


@router.get("/stages", response_model=schemas.StagePerformanceOut)
def stages(db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)) -> schemas.StagePerformanceOut:
    """Approval stages ordered by how long they take — the bottleneck heatmap."""
    _management_only(user)
    return schemas.StagePerformanceOut(
        **analytics_service.stage_performance(db, user.tenant_id))


@router.get("/workload", response_model=list[schemas.ReviewerLoadOut])
def workload(db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)) -> list[schemas.ReviewerLoadOut]:
    """Who is carrying the review load, ordered by what is still open."""
    _management_only(user)
    return [schemas.ReviewerLoadOut(**row)
            for row in analytics_service.reviewer_workload(db, user.tenant_id)]


@router.get("/renewals", response_model=schemas.RenewalPipelineOut)
def renewals(db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)) -> schemas.RenewalPipelineOut:
    return schemas.RenewalPipelineOut(
        **analytics_service.renewal_pipeline(db, user.tenant_id))


@router.get("/escalations", response_model=schemas.EscalationTrendOut)
def escalations(months: int = Query(default=12, ge=1, le=60), db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.EscalationTrendOut:
    _management_only(user)
    return schemas.EscalationTrendOut(
        **analytics_service.escalation_trend(db, user.tenant_id, months=months))


@router.get("/negotiation", response_model=schemas.NegotiationEffortOut)
def negotiation(db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.NegotiationEffortOut:
    """How much back-and-forth agreements take, and which ones took the most."""
    _management_only(user)
    return schemas.NegotiationEffortOut(
        **analytics_service.negotiation_effort(db, user.tenant_id))


@router.get("/clause-pressure", response_model=list[schemas.ClausePressureOut])
def clause_pressure(db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> list[schemas.ClausePressureOut]:
    """Which clauses counterparties keep pushing back on — the list to fix."""
    _management_only(user)
    return [schemas.ClausePressureOut(**row)
            for row in analytics_service.clause_pressure(db, user.tenant_id)]


@router.get("/compliance", response_model=schemas.CompliancePostureOut)
def compliance(db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> schemas.CompliancePostureOut:
    """Deviations, missing mandatory clauses and overdue obligations, computed live.

    Not read from a cached verdict: a compliance number computed from a stale snapshot is the
    one number that must not be.
    """
    _management_only(user)
    return schemas.CompliancePostureOut(
        **analytics_service.compliance_posture(db, user.tenant_id))


@router.get("/trend", response_model=schemas.VolumeTrendOut)
def trend(granularity: str = Query(default="month", pattern="^(day|week|month)$"),
          months: int = Query(default=24, ge=1, le=120), db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)) -> schemas.VolumeTrendOut:
    """Raised and executed over time, with the same period a year earlier."""
    _management_only(user)
    return schemas.VolumeTrendOut(
        **analytics_service.volume_trend(db, user.tenant_id, granularity=granularity,
                                         months=months))


@router.get("/segmentation", response_model=schemas.SegmentationOut)
def segmentation(db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.SegmentationOut:
    """Volume and value by department, region, entity type, agreement type and status."""
    _management_only(user)
    return schemas.SegmentationOut(**analytics_service.segmentation(db, user.tenant_id))


@router.post("/export", response_model=schemas.ExportJobOut,
             status_code=status.HTTP_201_CREATED)
def export_report(data: schemas.ExportIn, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.ExportJobOut:
    """Export a report to a spreadsheet, through the same job the repository export uses."""
    from .. import export_service
    from ..export_service import ExportError

    _management_only(user)
    tenant = db.get(models.Tenant, user.tenant_id)
    try:
        job = export_service.run_export(
            db, user.tenant_id, data.kind, data.filters, actor=user,
            org_name=tenant.name if tenant else "", ip=client_ip(request),
        )
    except ExportError as e:
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    record(db, tenant_id=user.tenant_id, action="report.exported", actor=user,
           object_type="export", object_id=job.id, object_label=job.label,
           ip=client_ip(request), meta={"kind": data.kind})
    db.commit()
    db.refresh(job)
    return schemas.ExportJobOut.model_validate(job)
