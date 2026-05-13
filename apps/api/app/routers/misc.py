import datetime as dt
import random

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import jobs, models, renewal_service, schemas, security
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(tags=["misc"])

_ADMIN_ROLES = {"owner", "admin"}


# ---------- admin: renewals sweep ----------


@router.post("/admin/sweep-renewals", response_model=schemas.SweepResultOut)
def admin_sweep_renewals(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.SweepResultOut:
    """Run the renewals sweep across this workspace's contracts on-demand. In production this
    runs hourly via Celery beat (renewals.sweep). Owner/admin only."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can run the renewals sweep.")
    # Limit this on-demand sweep to the caller's tenant (the periodic Celery task runs across
    # all tenants). Tenant scoping is enforced both by RLS (the GUC is set in deps.py from the
    # JWT) and explicitly via a where-filter in renewal_service.sweep when given a tenant_id.
    job = jobs.create_job(db, tenant_id=user.tenant_id, type="renewals.sweep", label="Renewals sweep", created_by=user.id, href="/settings")
    db.commit()
    try:
        out = renewal_service.sweep(db)
        summary = f"Flagged {out['flagged_expiring']} expiring · {out['moved_to_expired']} expired · {out['obligations_overdue']} obligations overdue · {out['reminders_sent']} reminders"
        jobs.succeed(db, job, summary=summary)
        db.commit()
    except Exception as e:  # noqa: BLE001
        jobs.fail(db, job, error=str(e))
        db.commit()
        raise
    record(db, tenant_id=user.tenant_id, action="admin.sweep_renewals", actor=user, object_type="workspace", object_id=user.tenant_id, ip=client_ip(request), meta=out)
    db.commit()
    return schemas.SweepResultOut(**out)


# ---------- progress tray ----------


@router.get("/jobs", response_model=list[schemas.BackgroundJobOut])
def list_jobs(
    status: str | None = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[schemas.BackgroundJobOut]:
    """Recent background jobs for the current workspace (PDF generation, envelope sealing,
    renewals sweep, …). RLS scopes this to the caller's tenant. Defaults to the 30 most recent."""
    stmt = select(models.BackgroundJob).where(models.BackgroundJob.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(models.BackgroundJob.status == status)
    rows = db.scalars(stmt.order_by(desc(models.BackgroundJob.created_at)).limit(max(1, min(limit, 100)))).all()
    return [schemas.BackgroundJobOut.model_validate(r) for r in rows]


# ---------- users ----------


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> list[schemas.UserOut]:
    rows = db.scalars(select(models.User).where(models.User.tenant_id == user.tenant_id).order_by(models.User.name)).all()
    return [schemas.UserOut.model_validate(r) for r in rows]


@router.post("/users", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def invite_user(data: schemas.UserInviteIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.UserOut:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners/admins can add users.")
    if data.role not in {"admin", "manager", "author", "approver", "reviewer", "viewer", "auditor"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.")
    email = data.email.lower()
    if db.scalar(select(models.User).where(models.User.tenant_id == user.tenant_id, func.lower(models.User.email) == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists in this workspace.")
    colors = ["#3E7BFA", "#8B7BF5", "#2BC0D4", "#F6B83C", "#F5736B", "#3FBF7F"]
    u = models.User(tenant_id=user.tenant_id, email=email, name=data.name, password_hash=security.hash_password(data.password), role=data.role, avatar_color=random.choice(colors))
    db.add(u)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="user.invited", actor=user, object_type="user", object_id=u.id, object_label=u.name, ip=client_ip(request), meta={"role": u.role})
    db.commit()
    db.refresh(u)
    return schemas.UserOut.model_validate(u)


# ---------- notifications ----------


@router.get("/notifications", response_model=list[schemas.NotificationOut])
def list_notifications(db: Session = Depends(get_db), user: models.User = Depends(get_current_user), unread: bool = False) -> list[schemas.NotificationOut]:
    stmt = select(models.Notification).where(models.Notification.tenant_id == user.tenant_id, models.Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(models.Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(desc(models.Notification.created_at)).limit(100)).all()
    return [schemas.NotificationOut.model_validate(r) for r in rows]


@router.post("/notifications/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(notification_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.NotificationOut:
    n = db.get(models.Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if n.read_at is None:
        n.read_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        db.refresh(n)
    return schemas.NotificationOut.model_validate(n)


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    updated = db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.read_at.is_(None)).update({models.Notification.read_at: now})
    db.commit()
    return {"updated": updated}


# ---------- OCR / AI ----------
# Multipart: upload a real document (stored in S3-compatible object storage / local fallback)
# OR just pass a file_name for the demo path. Creating the job enqueues a Celery task (queue
# "ocr"); CELERY_TASK_ALWAYS_EAGER=true (local default) runs it inline. The extraction itself
# is a realistic stub — see app/tasks.py and docs/09.


@router.post("/ocr/jobs", response_model=schemas.OcrJobOut, status_code=status.HTTP_201_CREATED)
def create_ocr_job(
    request: Request,
    file: UploadFile | None = File(None),
    file_name: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.OcrJobOut:
    source_file_id: str | None = None
    name = (file_name or "").strip()
    if file is not None and (file.filename or "").strip():
        from .files import save_upload

        obj = save_upload(db, tenant_id=user.tenant_id, file=file, kind="ocr_source", created_by=user.id)
        source_file_id = obj.id
        name = obj.original_name
    if not name:
        name = "scanned_contract.pdf"
    job = models.OcrJob(
        tenant_id=user.tenant_id,
        status="queued",
        file_name=name,
        progress=0,
        result={"source_file_id": source_file_id} if source_file_id else {},
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="ocr.queued", actor=user, object_type="ocr_job", object_id=job.id, object_label=name, ip=client_ip(request), meta={"file_id": source_file_id})
    db.commit()
    job_id = job.id

    from ..tasks import process_ocr_job

    process_ocr_job.delay(job_id, user.tenant_id)
    db.refresh(job)  # in eager mode the task has already completed
    return schemas.OcrJobOut.model_validate(job)


@router.get("/ocr/jobs/{job_id}", response_model=schemas.OcrJobOut)
def get_ocr_job(job_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.OcrJobOut:
    job = db.get(models.OcrJob, job_id)
    if job is None or job.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OCR job not found")
    return schemas.OcrJobOut.model_validate(job)


@router.post("/ocr/jobs/{job_id}/create-contract", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
def create_contract_from_ocr(job_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.ContractDetail:
    job = db.get(models.OcrJob, job_id)
    if job is None or job.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OCR job not found")
    if job.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This scan is still being processed.")
    if job.created_contract_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A contract was already created from this scan.")
    f = job.result.get("fields", {})

    def fv(name, default=None):
        return f.get(name, {}).get("value", default)

    def as_date(s):
        try:
            return dt.date.fromisoformat(s) if s else None
        except (TypeError, ValueError):
            return None

    from .contracts import _detail, _next_reference  # local import to avoid a cycle at module load

    c = models.Contract(
        tenant_id=user.tenant_id,
        reference_no=_next_reference(db, user.tenant_id),
        title=fv("title", job.file_name),
        type=fv("type", "other"),
        status="draft",
        owner_id=user.id,
        counterparty=fv("counterparty", ""),
        value=float(fv("value", 0) or 0),
        currency=fv("currency", user.tenant.currency),
        effective_date=as_date(fv("effective_date")),
        end_date=as_date(fv("end_date")),
        renewal_type=fv("renewal_type", "none"),
        governing_law=fv("governing_law", ""),
        risk_level=job.result.get("risk_level", "low"),
        ai_summary=job.result.get("summary", ""),
        tags=["ocr"],
        body=f"# {fv('title', job.file_name)}\n\n_Imported from scan: {job.file_name}_\n\nDetected clauses: {', '.join(job.result.get('detected_clauses', []))}\n",
        source="ocr",
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    db.add(models.ContractVersion(tenant_id=user.tenant_id, contract_id=c.id, version_no=1, body=c.body, change_summary="Created from OCR", created_by=user.id))
    job.created_contract_id = c.id
    record(db, tenant_id=user.tenant_id, action="contract.created", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"source": "ocr", "ocr_job": job.id})
    db.commit()
    db.refresh(c)
    return _detail(db, c)
