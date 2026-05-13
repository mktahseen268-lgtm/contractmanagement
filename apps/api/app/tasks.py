"""Background tasks. For the scaffold the OCR/AI pipeline is a realistic *stub* — in the full
product this is where the real OCR engine + LLM provider run (see docs/09)."""

import datetime as dt
import hashlib
import random
import re
import time
import uuid

from sqlalchemy import select

from .celery_app import celery
from .config import settings
from . import models
from .database import SessionLocal, set_request_tenant
from .pdf import is_draftish, render_certificate_bytes, render_contract_pdf_bytes, render_signed_pdf_bytes
from .storage import get_storage, tenant_key

_STUB_PARTIES = ["Acme Corporation", "Globex LLC", "Northstar Industries", "Initech FZE", "Stark Trading Co.", "Wayne Holdings"]
_STUB_TYPES = ["msa", "nda", "lease", "vendor", "service"]
_TITLE = {"msa": "Master Services Agreement", "nda": "Mutual Non-Disclosure Agreement", "lease": "Office Lease Agreement", "vendor": "Vendor Agreement", "service": "Service Agreement"}


def build_extraction(file_name: str) -> dict:
    """A plausible OCR+AI extraction result, deterministic per file name."""
    rng = random.Random(file_name)
    party = rng.choice(_STUB_PARTIES)
    ctype = rng.choice(_STUB_TYPES)
    start = dt.date.today() - dt.timedelta(days=rng.randint(0, 120))
    months = rng.choice([12, 24, 36])
    end = start + dt.timedelta(days=months * 30)
    value = rng.choice([24000, 48000, 96000, 120000, 250000])
    risk = rng.choice(["low", "low", "medium", "high"])
    title = f"{_TITLE[ctype]} — {party}"
    return {
        "fields": {
            "title": {"value": title, "confidence": round(rng.uniform(0.88, 0.97), 2)},
            "type": {"value": ctype, "confidence": round(rng.uniform(0.9, 0.98), 2)},
            "counterparty": {"value": party, "confidence": round(rng.uniform(0.85, 0.96), 2)},
            "effective_date": {"value": start.isoformat(), "confidence": round(rng.uniform(0.6, 0.95), 2)},
            "end_date": {"value": end.isoformat(), "confidence": round(rng.uniform(0.45, 0.92), 2)},
            "value": {"value": value, "confidence": round(rng.uniform(0.8, 0.95), 2)},
            "currency": {"value": "USD", "confidence": 0.99},
            "renewal_type": {"value": rng.choice(["none", "auto", "manual"]), "confidence": round(rng.uniform(0.6, 0.9), 2)},
            "governing_law": {"value": rng.choice(["Oman", "UAE", "Saudi Arabia", "England & Wales"]), "confidence": round(rng.uniform(0.7, 0.93), 2)},
        },
        "risk_level": risk,
        "summary": f"{months}-month {_TITLE[ctype].lower()} with {party}. Standard commercial terms; governing law as detected. (AI summary — verify before relying.)",
        "detected_clauses": rng.sample(["Confidentiality", "Limitation of Liability", "Termination", "Indemnification", "Governing Law", "Force Majeure", "IP Ownership", "Data Protection", "Payment Terms"], k=rng.randint(5, 8)),
        "tables_found": rng.randint(0, 2),
        "languages": ["en"] + (["ar"] if rng.random() < 0.3 else []),
        "pages": rng.randint(2, 14),
    }


@celery.task(name="ocr.process_job")
def process_ocr_job(job_id: str, tenant_id: str) -> str:
    """Stub of the OCR → layout → AI extraction pipeline. Marks the job processing, then completed."""
    set_request_tenant(tenant_id)  # scope DB access to the owning tenant (RLS)
    with SessionLocal() as db:
        job = db.get(models.OcrJob, job_id)
        if job is None:
            return "not_found"
        job.status = "processing"
        job.progress = 25
        db.commit()
    if not settings.celery_task_always_eager:
        time.sleep(2)  # simulate work when running on a real worker
    with SessionLocal() as db:
        job = db.get(models.OcrJob, job_id)
        if job is None:
            return "not_found"
        job.status = "completed"
        job.progress = 100
        job.result = {**(job.result or {}), **build_extraction(job.file_name)}  # keep source_file_id
        db.commit()
    return "completed"


@celery.task(name="contracts.render_pdf")
def render_contract_pdf(contract_id: str, tenant_id: str, created_by: str) -> str:
    """Render the contract to a PDF, store it in object storage, and create a FileObject row.
    Returns the new file id (or '' if the contract is gone)."""
    set_request_tenant(tenant_id)
    with SessionLocal() as db:
        c = db.get(models.Contract, contract_id)
        if c is None:
            return ""
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
                id=fid,
                tenant_id=tenant_id,
                key=key,
                bucket=settings.s3_bucket if settings.use_s3 else "",
                backend=storage.name,
                content_type="application/pdf",
                size=len(pdf_bytes),
                sha256=hashlib.sha256(pdf_bytes).hexdigest(),
                original_name=name,
                kind="contract_pdf",
                parent_type="contract",
                parent_id=contract_id,
                created_by=created_by,
            )
        )
        db.commit()
        return fid


@celery.task(name="signatures.seal_envelope")
def seal_envelope(envelope_id: str, tenant_id: str) -> str:
    """Render the executed PDF + the Certificate of Completion for a completed envelope and link them."""
    set_request_tenant(tenant_id)
    with SessionLocal() as db:
        env = db.get(models.SignatureEnvelope, envelope_id)
        if env is None or env.status != "completed":
            return ""
        c = db.get(models.Contract, env.contract_id)
        tenant = db.get(models.Tenant, tenant_id)
        org = (tenant.name if tenant else "Workspace") or "Workspace"
        recips = list(db.scalars(select(models.SignatureRecipient).where(models.SignatureRecipient.envelope_id == env.id).order_by(models.SignatureRecipient.sequence)).all())
        events = list(db.scalars(select(models.SignatureEvent).where(models.SignatureEvent.envelope_id == env.id).order_by(models.SignatureEvent.at)).all())
        decline_times = {e.recipient_id: e.at for e in events if e.event == "declined"}
        signers = [{"name": r.name, "email": r.email, "signed_name": r.signed_name, "signed_at": r.signed_at, "ip": r.ip} for r in recips if r.status == "signed" and r.kind == "signer"]
        recip_dicts = [
            {"name": r.name, "email": r.email, "kind": r.kind, "status": r.status, "signed_at": r.signed_at, "declined_at": decline_times.get(r.id), "declined_reason": r.declined_reason, "ip": r.ip}
            for r in recips
        ]
        event_dicts = [{"at": e.at, "event": e.event, "recipient_name": e.recipient_name, "ip": e.ip} for e in events]

        signed_bytes = render_signed_pdf_bytes(contract=c, org_name=org, signers=signers)
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
        db.commit()
        return env.id


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


# Beat schedule: once an hour. Honoured when a beat scheduler is running (celery -A app.celery_app
# beat ...). For the scaffold the manual endpoint covers most needs.
celery.conf.beat_schedule = {
    "renewals-sweep-hourly": {"task": "renewals.sweep", "schedule": 3600.0},
}
