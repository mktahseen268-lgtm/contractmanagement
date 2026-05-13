"""Helpers for the Progress Tray. Long-running tasks record themselves in `background_jobs` so
the user can see queued/running/succeeded/failed work + open the result. Tenant-isolated by RLS."""

import datetime as dt

from sqlalchemy.orm import Session

from . import models


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def create_job(db: Session, *, tenant_id: str, type: str, label: str,
               created_by: str | None = None,
               object_type: str = "", object_id: str | None = None, href: str = "") -> models.BackgroundJob:
    """Create and flush a "running" job row. Caller commits."""
    job = models.BackgroundJob(
        tenant_id=tenant_id, type=type, label=label, status="running", progress=0,
        created_by=created_by, object_type=object_type, object_id=object_id, href=href,
        started_at=_now(),
    )
    db.add(job)
    db.flush()
    return job


def succeed(db: Session, job: models.BackgroundJob, *, summary: str = "", href: str | None = None) -> None:
    job.status = "succeeded"
    job.progress = 100
    job.result_summary = (summary or "")[:400]
    if href is not None:
        job.href = href[:400]
    job.completed_at = _now()


def fail(db: Session, job: models.BackgroundJob, *, error: str) -> None:
    job.status = "failed"
    job.error = (error or "")[:600]
    job.completed_at = _now()
