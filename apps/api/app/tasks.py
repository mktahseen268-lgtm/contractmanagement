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


def _certificates_for_signers(db, recipients) -> list[tuple]:
    """Pair each signed recipient with the certificate to sign as.

    A recipient is matched to a certificate by user id when they are an internal user, and by
    the external-party binding minted for a visitor (Phase 2 §3). A signatory with no usable
    certificate is skipped rather than signed with somebody else's — silently falling back to
    a shared certificate is precisely the failure this phase exists to remove.
    """
    from .pki import lifecycle as pki_lifecycle

    pairs: list[tuple] = []
    for r in recipients:
        if r.status != "signed" or r.kind != "signer":
            continue
        cert = None
        if r.signer_user_id:
            cert = pki_lifecycle.active_certificate_for(db, r.tenant_id, user_id=r.signer_user_id)
        if cert is None and r.party_ref:
            cert = pki_lifecycle.active_certificate_for(db, r.tenant_id, party_id=r.party_ref)
        if cert is None:
            _log.warning(
                "seal_envelope: recipient %s (%s) has no active certificate — signing skipped "
                "for this signatory", r.id, r.email,
            )
            continue
        pairs.append((r, cert))
    return pairs


def _record_signing_receipts(db, env, receipts: list[dict]) -> None:
    """One `SignatureEvent` per cryptographic signature, naming the certificate serial used.

    The RFP asks that every SignatureEvent records the certificate serial — this is what makes
    "who signed this, with which credential" answerable years later from the audit trail alone.
    """
    for receipt in receipts:
        db.add(models.SignatureEvent(
            tenant_id=env.tenant_id,
            envelope_id=env.id,
            recipient_id=receipt.get("recipient_id"),
            recipient_name=receipt.get("recipient_name", ""),
            event="crypto_signed" if receipt.get("ok") else "crypto_sign_failed",
            meta=receipt,
        ))


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
        # Stamp the attempt BEFORE doing the work: if the worker dies mid-seal, the envelope
        # still shows an attempt that never completed rather than looking untouched.
        env.seal_attempts = (env.seal_attempts or 0) + 1
        env.seal_last_attempt_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        env.seal_error = ""
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
            # Cryptographic signature, applied last over the final executed PDF.
            #
            # With SIGNING_PROVIDER=pki each signatory signs with *their own* certificate, so
            # the document ends up carrying one independently verifiable signature per signer
            # (RFP: no shared or role-based certificates). Other providers apply a single
            # org-level seal. Either way a failure degrades to the visual-only PDF rather than
            # losing the execution — but it is recorded, not swallowed.
            from .signing_provider import get_signing_provider

            _sp = get_signing_provider()
            signing_receipts: list[dict] = []
            if _sp.per_signatory:
                pairs = _certificates_for_signers(db, recips)
                signed_bytes, signing_receipts = _sp.sign_for_recipients(
                    db, signed_bytes, pairs, contract_ref=c.reference_no or "",
                )
                _record_signing_receipts(db, env, signing_receipts)
            elif _sp.cryptographic:
                try:
                    signed_bytes = _sp.seal_pdf(signed_bytes, contract_ref=c.reference_no or "", reason=f"Executed: {c.title}")
                except Exception:  # noqa: BLE001
                    _log.exception("seal_envelope: %s signing failed; storing visual-only PDF", _sp.name)
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

            # A signatory whose cryptographic signature failed is a real problem even though a
            # document was produced — `partial` is what surfaces it in the dead-letter view
            # instead of letting it pass as a clean execution.
            failed = [r for r in signing_receipts if not r.get("ok")]
            if failed:
                env.seal_status = "partial"
                env.seal_error = "; ".join(
                    f"{r.get('recipient_name') or r.get('recipient_id')}: {r.get('error', 'signature failed')}"
                    for r in failed
                )[:1000]
                jobs.succeed(
                    db, job,
                    summary=f"Executed PDF produced for {ref}, but {len(failed)} signature(s) failed.",
                )
            else:
                env.seal_status = "sealed"
                jobs.succeed(db, job, summary=f"Executed PDF + certificate produced for {ref}.")
            db.commit()
            return env.id
        except Exception as e:  # noqa: BLE001
            env.seal_status = "failed"
            env.seal_error = str(e)[:1000]
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


@celery.task(name="archive.sweep")
def archive_sweep() -> dict:
    """Move executed contracts past the hot-search window to the cold storage tier.
    Idempotent. See `app/archive_service.py`. RFP §4c — "1 year instantly searchable"."""
    from . import archive_service

    with SessionLocal() as db:
        out = archive_service.archive_sweep(db)
        db.commit()
        return out


@celery.task(name="archive.purge_contracts")
def archive_purge_contracts() -> dict:
    """Hard-delete contracts past RETENTION_YEARS. Skips anything under legal hold.
    Irreversible — every purge writes an audit entry first. RFP §4c — "Data purging"."""
    from . import archive_service

    with SessionLocal() as db:
        out = archive_service.purge_sweep(db)
        db.commit()
        return out


@celery.task(name="pki.publish_crls")
def pki_publish_crls() -> dict:
    """Republish every active issuing CA's CRL before the previous one goes stale.

    A CRL past its `nextUpdate` is treated as invalid by correct relying parties, which fails
    signature validation across the board — so this runs on a schedule rather than only on
    revocation. Revocation also publishes immediately; this is the freshness floor.
    """
    from sqlalchemy import select

    from . import models
    from .pki import crl as crl_mod

    published = 0
    with SessionLocal() as db:
        cas = db.scalars(
            select(models.CertificateAuthority).where(
                models.CertificateAuthority.kind == "issuing",
                models.CertificateAuthority.status == "active",
            )
        ).all()
        for ca in cas:
            try:
                crl_mod.publish(db, ca)
                published += 1
            except Exception:  # noqa: BLE001
                logging.getLogger("uvicorn.error").exception(
                    "pki.publish_crls: failed for CA %s", ca.id
                )
        db.commit()
    return {"cas": len(cas), "published": published}


@celery.task(name="pki.expire_certificates")
def pki_expire_certificates() -> dict:
    """Flip past-validity certificates to `expired` so the register reflects reality and the
    subject's one active-certificate slot is freed for a renewal."""
    from .pki import lifecycle

    with SessionLocal() as db:
        n = lifecycle.expire_sweep(db)
        db.commit()
    return {"expired": n}


@celery.task(name="workflow.sla_sweep")
def workflow_sla_sweep() -> dict:
    """Remind reviewers approaching their SLA and escalate the ones who passed it.

    Idempotent: both actions stamp the step, so re-running does not spam. Reminders and
    escalations are only as timely as this beat's interval — see SLA_SWEEP_SECONDS.
    """
    from . import workflow_service

    with SessionLocal() as db:
        out = workflow_service.sla_sweep(db)
        db.commit()
        return out


# Beat schedule. Honoured when a beat scheduler is running (celery -A app.celery_app beat ...).
# For the scaffold the manual endpoint + immediate delivery cover most needs.

@celery.task(name="bulk.send_batch")
def run_bulk_send(batch_id: str) -> dict:
    """Fan a bulk-send batch out into one contract and one envelope per recipient.

    Commits per row inside `run_batch`, so a worker killed halfway leaves the rows it already
    sent marked sent and the rest pending — re-running the task picks up exactly the remainder
    rather than re-sending to people who already have their envelope.
    """
    from . import bulk_send_service

    with SessionLocal() as db:
        return bulk_send_service.run_batch(db, batch_id)


@celery.task(name="signatures.chase_sweep")
def signature_chase_sweep() -> dict:
    """Send due signing reminders and expire envelopes past their deadline."""
    from . import signing_service

    with SessionLocal() as db:
        out = signing_service.chase_and_expire(db)
        db.commit()
        return out


celery.conf.beat_schedule = {
    "renewals-sweep-hourly": {"task": "renewals.sweep", "schedule": 3600.0},
    "email-outbox-flush-1m": {"task": "email.flush_outbox", "schedule": 60.0},
    "retention-purge-nightly": {"task": "retention.purge", "schedule": 86400.0},  # 24h
    # Archive runs before purge so a contract crossing both horizons in one night is archived
    # (and audited as such) before it is considered for deletion.
    "archive-sweep-nightly": {"task": "archive.sweep", "schedule": 86400.0},
    "archive-purge-nightly": {"task": "archive.purge_contracts", "schedule": 86400.0},
    # Half the CRL validity window, so a republish failure still leaves a valid CRL in place
    # for one more cycle before relying parties start rejecting it.
    "pki-publish-crls": {"task": "pki.publish_crls", "schedule": settings.crl_validity_hours * 1800.0},
    "pki-expire-certificates": {"task": "pki.expire_certificates", "schedule": 3600.0},
    # Review SLAs. A reminder that arrives an hour late is nearly useless, so this runs far
    # more often than the other sweeps.
    "workflow-sla-sweep": {"task": "workflow.sla_sweep", "schedule": settings.sla_sweep_seconds},
    # Signing reminders and envelope expiry. Hourly rather than daily because an expiry
    # configured in days still has an hour of the day attached to it, and a link that stays
    # live for most of a day past its deadline is not an expiry.
    "signature-chase-sweep": {"task": "signatures.chase_sweep", "schedule": 3600.0},
}
