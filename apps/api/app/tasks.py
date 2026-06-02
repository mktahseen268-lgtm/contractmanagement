"""Background tasks. The OCR/AI pipeline runs through a pluggable provider (`ocr_provider`):
`stub` (deterministic demo) by default, or a real cloud extractor (Claude) when configured.
See docs/09 + RFI T-5."""

import datetime as dt
import hashlib
import json
import logging
import re
import time
import uuid

from sqlalchemy import select

from .celery_app import celery
from .config import settings
from . import metrics, models
from .database import SessionLocal, set_request_tenant
from .ocr_provider import build_extraction, get_ocr_provider  # noqa: F401 (build_extraction re-exported for compat)
from .pdf import is_draftish, render_certificate_bytes, render_contract_pdf_bytes, render_signed_pdf_bytes, stamp_tabs_on_pdf
from .storage import get_storage, tenant_key

_log = logging.getLogger("uvicorn.error")


def _load_source_bytes(db, job) -> tuple[bytes | None, str]:
    """Fetch the uploaded file's bytes + content type from storage (for real providers)."""
    src_id = (job.result or {}).get("source_file_id")
    if not src_id:
        return None, ""
    fo = db.get(models.FileObject, src_id)
    if fo is None:
        return None, ""
    try:
        stream = get_storage().open_stream(fo.key)
        try:
            return stream.read(), (fo.content_type or "")
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        _log.exception("ocr: could not read source file %s", src_id)
        return None, (fo.content_type or "")


@celery.task(name="ocr.process_job")
def process_ocr_job(job_id: str, tenant_id: str) -> str:
    """OCR → extraction via the configured provider. Marks the job processing, runs the provider,
    then completed (or failed). Provider errors are caught so the UI gets a clean failed state."""
    set_request_tenant(tenant_id)  # scope DB access to the owning tenant (RLS)
    with SessionLocal() as db:
        job = db.get(models.OcrJob, job_id)
        if job is None:
            return "not_found"
        job.status = "processing"
        job.progress = 25
        db.commit()
    if not settings.celery_task_always_eager:
        time.sleep(2)  # let the UI render the processing timeline on a real worker
    with SessionLocal() as db:
        job = db.get(models.OcrJob, job_id)
        if job is None:
            return "not_found"
        provider = get_ocr_provider()
        try:
            file_bytes, content_type = (None, "")
            if provider.name != "stub":
                file_bytes, content_type = _load_source_bytes(db, job)
            extraction = provider.extract(file_bytes=file_bytes, file_name=job.file_name, content_type=content_type)
            job.status = "completed"
            job.progress = 100
            job.result = {**(job.result or {}), **extraction}  # keep source_file_id
            db.commit()
            metrics.record_ocr("completed")
            return "completed"
        except Exception as e:  # noqa: BLE001
            _log.exception("ocr: provider %s failed for job %s", provider.name, job_id)
            job.status = "failed"
            job.progress = 100
            job.result = {**(job.result or {}), "error": str(e)[:500], "provider": provider.name}
            db.commit()
            metrics.record_ocr("failed")
            return "failed"


@celery.task(name="contracts.render_pdf")
def render_contract_pdf(contract_id: str, tenant_id: str, created_by: str) -> str:
    """Render the contract to a PDF, store it in object storage, and create a FileObject row.
    Returns the new file id (or '' if the contract is gone)."""
    from . import jobs

    set_request_tenant(tenant_id)
    with SessionLocal() as db:
        c = db.get(models.Contract, contract_id)
        if c is None:
            return ""
        job = jobs.create_job(
            db, tenant_id=tenant_id, type="contract.pdf", label=f"Generating PDF — {c.title}",
            created_by=created_by, object_type="contract", object_id=contract_id, href=f"/contracts/{contract_id}",
        )
        db.commit()
        try:
            tenant = db.get(models.Tenant, tenant_id)
            org_name = (tenant.name if tenant else "Workspace") or "Workspace"
            pdf_bytes = render_contract_pdf_bytes(contract=c, org_name=org_name, draft=is_draftish(c.status))
            ref, title = c.reference_no, (c.title or "Contract")

            storage = get_storage()
            storage.ensure_ready()
            fid = uuid.uuid4().hex
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{ref}_{title}").strip("_")[:120] or "contract"
            name = f"{safe}.pdf"
            key = tenant_key(tenant_id, "contract_pdf", f"{fid}-{name}")
            storage.put(key, pdf_bytes, "application/pdf")

            db.add(
                models.FileObject(
                    id=fid, tenant_id=tenant_id, key=key,
                    bucket=settings.s3_bucket if settings.use_s3 else "", backend=storage.name,
                    content_type="application/pdf", size=len(pdf_bytes),
                    sha256=hashlib.sha256(pdf_bytes).hexdigest(), original_name=name,
                    kind="contract_pdf", parent_type="contract", parent_id=contract_id, created_by=created_by,
                )
            )
            jobs.succeed(db, job, summary=f"Generated {name}", href=f"/contracts/{contract_id}")
            db.commit()
            return fid
        except Exception as e:  # noqa: BLE001
            jobs.fail(db, job, error=str(e))
            db.commit()
            raise


@celery.task(name="signatures.seal_envelope")
def seal_envelope(envelope_id: str, tenant_id: str) -> str:
    """Render the executed PDF + the Certificate of Completion for a completed envelope and link them."""
    from . import jobs

    set_request_tenant(tenant_id)
    with SessionLocal() as db:
        env = db.get(models.SignatureEnvelope, envelope_id)
        if env is None or env.status != "completed":
            return ""
        c = db.get(models.Contract, env.contract_id)
        job = jobs.create_job(
            db, tenant_id=tenant_id, type="signature.seal", label=f"Sealing executed PDF — {c.title}",
            created_by=env.created_by, object_type="contract", object_id=c.id, href=f"/contracts/{c.id}?tab=signatures",
        )
        db.commit()
        try:
            tenant = db.get(models.Tenant, tenant_id)
            org = (tenant.name if tenant else "Workspace") or "Workspace"
            recips = list(db.scalars(select(models.SignatureRecipient).where(models.SignatureRecipient.envelope_id == env.id).order_by(models.SignatureRecipient.sequence)).all())
            events = list(db.scalars(select(models.SignatureEvent).where(models.SignatureEvent.envelope_id == env.id).order_by(models.SignatureEvent.at)).all())
            decline_times = {e.recipient_id: e.at for e in events if e.event == "declined"}
            signers = [{"name": r.name, "email": r.email, "signed_name": r.signed_name, "signed_at": r.signed_at, "ip": r.ip, "signature_kind": r.signature_kind, "signature_image": r.signature_image} for r in recips if r.status == "signed" and r.kind == "signer"]
            # recipient_id -> adopted signature image (data URL), for stamping into signature tabs.
            recip_sig_image = {r.id: r.signature_image for r in recips if r.signature_image}
            recip_dicts = [
                {"name": r.name, "email": r.email, "kind": r.kind, "status": r.status, "signed_at": r.signed_at, "declined_at": decline_times.get(r.id), "declined_reason": r.declined_reason, "ip": r.ip}
                for r in recips
            ]
            event_dicts = [{"at": e.at, "event": e.event, "recipient_name": e.recipient_name, "ip": e.ip} for e in events]

            signed_bytes = render_signed_pdf_bytes(contract=c, org_name=org, signers=signers)
            # Stamp placed tabs onto the executed PDF (in-place by page coords).
            tab_rows = list(db.scalars(
                select(models.SignatureTab).where(models.SignatureTab.envelope_id == env.id).order_by(models.SignatureTab.page)
            ).all())
            if tab_rows:
                tab_dicts = [
                    {"page": t.page, "x": t.x, "y": t.y, "width": t.width, "height": t.height, "kind": t.kind, "value": t.value,
                     "signature_image": recip_sig_image.get(t.recipient_id) if t.kind == "signature" else None}
                    for t in tab_rows
                ]
                signed_bytes = stamp_tabs_on_pdf(signed_bytes, tab_dicts)
            # Cryptographic seal (PAdES) when configured — applied last, over the final executed
            # PDF. Fall back to the visual-only PDF on error so sealing never hard-fails.
            from .signing_provider import get_signing_provider

            _sp = get_signing_provider()
            if _sp.cryptographic:
                try:
                    signed_bytes = _sp.seal_pdf(signed_bytes, contract_ref=c.reference_no or "", reason=f"Executed: {c.title}")
                except Exception as e:  # noqa: BLE001
                    import logging as _lg
                    _lg.getLogger("uvicorn.error").exception("seal_envelope: %s signing failed; storing visual-only PDF", _sp.name)
            cert_bytes = render_certificate_bytes(envelope=env, contract=c, org_name=org, recipients=recip_dicts, events=event_dicts)

            storage = get_storage()
            storage.ensure_ready()
            ref = c.reference_no or "contract"

            def _store(data: bytes, kind: str, name: str) -> str:
                fid = uuid.uuid4().hex
                safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:120] or "doc"
                key = tenant_key(tenant_id, kind, f"{fid}-{safe}.pdf")
                storage.put(key, data, "application/pdf")
                db.add(models.FileObject(
                    id=fid, tenant_id=tenant_id, key=key, bucket=settings.s3_bucket if settings.use_s3 else "", backend=storage.name,
                    content_type="application/pdf", size=len(data), sha256=hashlib.sha256(data).hexdigest(), original_name=f"{safe}.pdf",
                    kind=kind, parent_type="contract", parent_id=c.id, created_by=env.created_by,
                ))
                return fid

            env.sealed_pdf_file_id = _store(signed_bytes, "signed_pdf", f"{ref}_executed")
            env.certificate_file_id = _store(cert_bytes, "certificate", f"{ref}_certificate_of_completion")
            jobs.succeed(db, job, summary=f"Executed PDF + certificate produced for {ref}.")
            db.commit()
            return env.id
        except Exception as e:  # noqa: BLE001
            jobs.fail(db, job, error=str(e))
            db.commit()
            raise


@celery.task(name="renewals.sweep")
def sweep_renewals() -> dict:
    """Walk every tenant's active/expiring contracts, flip lifecycle as appropriate, and post
    owner reminders. Returns the counts dict. In production this is scheduled via Celery beat
    (see docs/14 §4); the scaffold also exposes POST /admin/sweep-renewals to run it on-demand."""
    from . import renewal_service

    with SessionLocal() as db:
        out = renewal_service.sweep(db)
        db.commit()
        return out


@celery.task(name="email.flush_outbox")
def flush_email_outbox() -> dict:
    """Retry any queued/failed outbox rows. Called from Celery beat every 60s; safe to re-run."""
    from . import email as email_mod

    with SessionLocal() as db:
        out = email_mod.flush_outbox(db)
        db.commit()
        return out


@celery.task(name="retention.purge")
def retention_purge() -> dict:
    """Archive + delete rows according to the retention policy in `docs/22-infra-deployment.md` §8.
    Idempotent — re-runnable safely. Returns counts. RFI §C.8–C.11."""
    import logging as _logging

    from sqlalchemy import delete

    _log = _logging.getLogger("uvicorn.error")
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    counts = {"audit_archived": 0, "audit_deleted": 0, "webhook_deliveries_deleted": 0,
              "background_jobs_deleted": 0, "email_outbox_deleted": 0, "recovery_codes_deleted": 0, "otp_codes_deleted": 0}
    audit_hot_cutoff = now - dt.timedelta(days=settings.retention_audit_hot_days)
    audit_archive_cutoff = now - dt.timedelta(days=settings.retention_audit_archive_days)
    wh_cutoff = now - dt.timedelta(days=settings.retention_webhook_delivery_days)
    bg_cutoff = now - dt.timedelta(days=settings.retention_background_job_days)
    eo_cutoff = now - dt.timedelta(days=settings.retention_email_outbox_days)
    code_cutoff = now - dt.timedelta(hours=24)

    with SessionLocal() as db:
        # 1) Audit log: archive rows older than the hot window (default 1y) up to the archive
        #    cutoff (default 10y) to object storage as NDJSON. Best-effort: if S3 isn't set,
        #    rows stay in the hot store for the operator to handle out of band.
        try:
            rows = list(db.scalars(select(models.AuditLog).where(
                models.AuditLog.at < audit_hot_cutoff,
                models.AuditLog.at >= audit_archive_cutoff,
            ).limit(50_000)).all())
            if rows and settings.use_s3:
                ndjson_lines = []
                for r in rows:
                    ndjson_lines.append(json.dumps({
                        "id": r.id, "tenant_id": r.tenant_id,
                        "at": r.at.isoformat() if r.at else None,
                        "actor_name": r.actor_name, "action": r.action,
                        "object_type": r.object_type, "object_id": r.object_id,
                        "object_label": r.object_label, "meta": r.meta, "ip": r.ip,
                    }, default=str))
                key = f"archive/audit/{now.strftime('%Y/%m')}/audit-{now.strftime('%Y%m%d-%H%M%S')}.ndjson"
                get_storage().put(key, "\n".join(ndjson_lines).encode("utf-8"), "application/x-ndjson")
                ids = [r.id for r in rows]
                db.execute(delete(models.AuditLog).where(models.AuditLog.id.in_(ids)))
                counts["audit_archived"] = len(ids)
        except Exception:  # noqa: BLE001
            _log.exception("retention.purge: audit archive failed (rows remain in hot store)")

        # 2) Audit log: hard-delete anything older than the archive cutoff (10 yr)
        r = db.execute(delete(models.AuditLog).where(models.AuditLog.at < audit_archive_cutoff))
        counts["audit_deleted"] = r.rowcount or 0
        # 3) Webhook deliveries > 90 days
        r = db.execute(delete(models.WebhookDelivery).where(models.WebhookDelivery.created_at < wh_cutoff))
        counts["webhook_deliveries_deleted"] = r.rowcount or 0
        # 4) Background jobs > 90 days
        r = db.execute(delete(models.BackgroundJob).where(models.BackgroundJob.created_at < bg_cutoff))
        counts["background_jobs_deleted"] = r.rowcount or 0
        # 5) Email outbox > 30 days
        r = db.execute(delete(models.EmailOutbox).where(models.EmailOutbox.created_at < eo_cutoff))
        counts["email_outbox_deleted"] = r.rowcount or 0
        # 6) Used/expired OTP + recovery codes > 24 h
        r = db.execute(delete(models.OtpCode).where(models.OtpCode.created_at < code_cutoff))
        counts["otp_codes_deleted"] = r.rowcount or 0
        r = db.execute(delete(models.RecoveryCode).where(models.RecoveryCode.used_at.is_not(None), models.RecoveryCode.used_at < code_cutoff))
        counts["recovery_codes_deleted"] = r.rowcount or 0

        db.commit()
    return counts


# Beat schedule. Honoured when a beat scheduler is running (celery -A app.celery_app beat ...).
# For the scaffold the manual endpoint + immediate delivery cover most needs.
celery.conf.beat_schedule = {
    "renewals-sweep-hourly": {"task": "renewals.sweep", "schedule": 3600.0},
    "email-outbox-flush-1m": {"task": "email.flush_outbox", "schedule": 60.0},
    "retention-purge-nightly": {"task": "retention.purge", "schedule": 86400.0},  # 24h
}
