"""Bulk send — one approved template dispatched to many signers at once (RFP BB-09).

Each row becomes its own contract and its own single-signer envelope. That is deliberate and
it is the expensive choice: one envelope with 500 recipients would be one document 500 people
all see, which is the opposite of what a mass NDA or a branch-agreement roll-out needs. The
signer must receive *their* agreement, with their own name merged into it, and must not be able
to see anybody else's.

Three properties this file exists to guarantee:

1. **One bad row does not stop the batch.** Every row is sent in its own transaction. A row
   that fails records why, on itself, and the next row proceeds.
2. **A failure is answerable.** When 40 of 500 fail the question is always *which* 40 and
   *why*. A task that logs and exits cannot answer that, so every row survives as a
   `BulkSendItem` carrying its outcome, retryable on its own.
3. **The mistakes that matter are caught before anything is sent.** A missing required merge
   field or a malformed address is found at submit time, across every row, and refuses the
   whole batch. Discovering it on row 1 of 500 after the emails have started is not a
   recoverable position — the envelopes are already in inboxes.
"""

from __future__ import annotations

import datetime as dt
import re
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import jobs, merge_engine, models, signing_service, template_service
from .audit import record
from .merge_engine import MergeError
from .clause_service import ClauseError

#: A ceiling, not a target. Each row renders a PDF and writes a contract, so a batch is minutes
#: of work, not milliseconds; an accidental 100,000-row paste should be refused rather than
#: discovered by the mail relay. Raise it when a tenant has a real reason and the queue to
#: absorb it.
MAX_ROWS = 1000

#: Deliberately permissive. Address validity is decided by the receiving mail server, and a
#: stricter pattern here would reject legitimate addresses (plus-tags, new TLDs, non-ASCII
#: locals) while still not proving deliverability. This catches paste damage — a name in the
#: email column, a missing @ — which is what the operator can actually fix before sending.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

TERMINAL = {"completed", "completed_with_errors", "cancelled", "failed"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class BulkSendError(ValueError):
    """Refusal at submit time. `problems` names the offending rows so the operator can fix the
    spreadsheet rather than guess which of 500 lines is wrong."""

    def __init__(self, message: str, problems: list[dict] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or []


# ---------------------------------------------------------------------------------------
# Building a batch
# ---------------------------------------------------------------------------------------


def _row_values(shared: dict, row: dict) -> dict:
    """Layer a row's own values over the batch's shared ones.

    Precedence is shared → row identity → row values. The row's identity beats the shared
    values because a shared `name` would otherwise stamp the same person's name onto all five
    hundred agreements, and that failure is silent — every document renders, every one is
    wrong.
    """
    merged = dict(shared or {})
    merged["name"] = row.get("name", "")
    merged["signer_name"] = row.get("name", "")
    merged["email"] = row.get("email", "")
    merged["signer_email"] = row.get("email", "")
    merged.update(row.get("values") or {})
    return merged


def validate_rows(template: models.ContractTemplate, rows: list[dict],
                  shared_values: dict) -> list[dict]:
    """Every problem across every row, at submit time. Returns [] when the batch is sendable."""
    problems: list[dict] = []
    if not rows:
        raise BulkSendError("Add at least one recipient.")
    if len(rows) > MAX_ROWS:
        raise BulkSendError(f"A batch is limited to {MAX_ROWS:,} recipients; this one has "
                            f"{len(rows):,}. Split it.")

    fields = merge_engine.parse_fields(template.fields or [])
    seen: dict[str, int] = {}

    for i, row in enumerate(rows):
        name = str(row.get("name") or "").strip()
        email = str(row.get("email") or "").strip().lower()
        errors: list[str] = []

        if not name:
            errors.append("Name is required.")
        if not email:
            errors.append("Email is required.")
        elif not _EMAIL.match(email):
            errors.append(f"{email!r} is not a valid email address.")
        elif email in seen:
            # Two envelopes for the same agreement to the same person is a paste error in
            # every case we have seen. Sending both is unrecoverable — you cannot unsend one.
            errors.append(f"Duplicate of row {seen[email] + 1}.")
        elif email:
            seen[email] = i

        _cleaned, merge_errors = merge_engine.validate_values(
            fields, _row_values(shared_values, row))
        errors.extend(merge_errors)

        if errors:
            problems.append({"row": i + 1, "name": name, "email": email, "errors": errors})

    return problems


def create_batch(db: Session, *, template: models.ContractTemplate, actor: models.User,
                 rows: list[dict], name: str = "", message: str = "",
                 shared_values: dict | None = None, reminder_interval_days: int = 0,
                 max_reminders: int = 0, expiry_days: int = 0,
                 ip: str = "") -> models.BulkSendBatch:
    """Validate everything, then persist the batch and its rows. Caller commits and enqueues."""
    if template.status != "active":
        raise BulkSendError("This template has not been approved for use.")

    shared_values = dict(shared_values or {})
    problems = validate_rows(template, rows, shared_values)
    if problems:
        raise BulkSendError(
            f"{len(problems)} of {len(rows)} rows cannot be sent. Nothing has been sent.",
            problems)

    batch = models.BulkSendBatch(
        tenant_id=actor.tenant_id, template_id=template.id,
        name=(name or f"{template.name} — {dt.date.today():%d %b %Y}")[:240],
        status="queued", total=len(rows), message=(message or "")[:4000],
        shared_values=merge_engine.jsonable(shared_values),
        # Clamped rather than trusted: a negative interval would make every envelope due for a
        # reminder on every sweep, which is a mail-bomb with the bank's name on it.
        reminder_interval_days=max(0, int(reminder_interval_days or 0)),
        max_reminders=max(0, int(max_reminders or 0)),
        expiry_days=max(0, int(expiry_days or 0)),
        created_by=actor.id,
    )
    db.add(batch)
    db.flush()

    for i, row in enumerate(rows):
        db.add(models.BulkSendItem(
            tenant_id=actor.tenant_id, batch_id=batch.id, sequence=i,
            name=str(row.get("name") or "").strip()[:200],
            email=str(row.get("email") or "").strip().lower()[:255],
            values=merge_engine.jsonable(_row_values(shared_values, row)),
            status="pending",
        ))

    job = jobs.create_job(
        db, tenant_id=actor.tenant_id, type="bulk.send",
        label=f"Sending {len(rows)} envelope{'s' if len(rows) != 1 else ''} — {batch.name}",
        created_by=actor.id, object_type="bulk_send", object_id=batch.id,
        href=f"/bulk-send/{batch.id}",
    )
    batch.job_id = job.id

    record(db, tenant_id=actor.tenant_id, action="bulk_send.created", actor=actor,
           object_type="bulk_send", object_id=batch.id, object_label=batch.name, ip=ip,
           meta={"template_id": template.id, "recipients": len(rows),
                 "reminder_interval_days": batch.reminder_interval_days,
                 "max_reminders": batch.max_reminders, "expiry_days": batch.expiry_days})
    return batch


# ---------------------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------------------


def _send_one(db: Session, *, batch: models.BulkSendBatch, item: models.BulkSendItem,
              template: models.ContractTemplate, actor: models.User, org_name: str) -> None:
    """Generate this row's contract and send its envelope. Raises on anything it cannot do."""
    values = dict(item.values or {})
    contract_vars = {
        "counterparty": values.get("company") or item.name,
        "title": f"{template.name} — {item.name}",
        "our_entity": org_name, "org": org_name, "us": org_name,
        "today": dt.date.today(),
        "type": (template.contract_type or "other").replace("_", " ").title(),
        "currency": template.default_currency,
        "governing_law": template.default_governing_law,
        "effective_date": dt.date.today(),
        "signer_name": item.name, "signer_email": item.email,
    }
    body, cleaned, version_no, included = template_service.generate_body(
        db, template, values, contract_vars=contract_vars)

    contract = template_service.spawn_from_template(
        db, template=template, actor=actor,
        title=contract_vars["title"], body=body,
        counterparty=str(contract_vars["counterparty"]),
        values=cleaned, version_no=version_no, source_note="bulk_send",
        included_clauses=included,
    )
    # Bulk send is the one path that dispatches without a human reading the draft, so the
    # contract goes out at `approved` rather than `draft` — the template was the approval, and
    # `send_envelope` only advances a contract that reached that state.
    contract.status = "approved"

    envelope = signing_service.create_envelope(
        db, contract=contract,
        recipients_in=[SimpleNamespace(name=item.name, email=item.email, kind="signer")],
        message=batch.message, signing_order="sequential", by_user=actor,
    )
    envelope.reminder_interval_days = batch.reminder_interval_days
    envelope.max_reminders = batch.max_reminders
    if batch.expiry_days:
        envelope.expires_at = _now() + dt.timedelta(days=batch.expiry_days)
    signing_service.send_envelope(db, envelope=envelope, contract=contract,
                                  by_user=actor, org_name=org_name)

    item.contract_id = contract.id
    item.envelope_id = envelope.id
    item.status = "sent"
    item.error = ""
    item.sent_at = _now()


def _counts(db: Session, batch_id: str) -> dict[str, int]:
    rows = db.execute(
        select(models.BulkSendItem.status, func.count(models.BulkSendItem.id))
        .where(models.BulkSendItem.batch_id == batch_id)
        .group_by(models.BulkSendItem.status)
    ).all()
    return {status: count for status, count in rows}


def run_batch(db: Session, batch_id: str) -> dict:
    """Send every pending row. Commits per row; safe to re-run after a worker restart.

    Returns the counts dict the worker metrics exporter reads.
    """
    batch = db.get(models.BulkSendBatch, batch_id)
    if batch is None:
        return {"bulk_missing": 1}
    if batch.status in TERMINAL:
        return {"bulk_already_finished": 1}

    template = db.get(models.ContractTemplate, batch.template_id)
    actor = db.get(models.User, batch.created_by)
    tenant = db.get(models.Tenant, batch.tenant_id)
    if template is None or actor is None:
        batch.status = "failed"
        batch.completed_at = _now()
        db.commit()
        return {"bulk_failed_batches": 1}

    batch.status = "running"
    batch.started_at = batch.started_at or _now()
    db.commit()

    org_name = tenant.name if tenant else ""
    item_ids = [
        row[0] for row in db.execute(
            select(models.BulkSendItem.id)
            .where(models.BulkSendItem.batch_id == batch.id,
                   models.BulkSendItem.status == "pending")
            .order_by(models.BulkSendItem.sequence)
        ).all()
    ]

    sent = failed = 0
    for item_id in item_ids:
        # Re-read the batch each time: cancellation arrives on another connection, and a batch
        # that keeps sending for ten minutes after somebody pressed Cancel is not cancellable.
        db.expire(batch)
        if batch.status == "cancelled":
            break
        item = db.get(models.BulkSendItem, item_id)
        if item is None or item.status != "pending":
            continue
        try:
            _send_one(db, batch=batch, item=item, template=template, actor=actor,
                      org_name=org_name)
            db.commit()
            sent += 1
        except (MergeError, ClauseError, ValueError, RuntimeError) as e:
            db.rollback()
            failed += _record_failure(db, item_id, str(e))
        except Exception as e:  # noqa: BLE001
            # Anything else — storage down, mail relay refusing, a bug — is still this row's
            # failure and not the batch's. The message is kept verbatim because the operator
            # has to be able to act on it without opening a log.
            db.rollback()
            failed += _record_failure(db, item_id, f"{type(e).__name__}: {e}")

    return _finish(db, batch.id, sent=sent, failed=failed)


def _record_failure(db: Session, item_id: str, error: str) -> int:
    """Persist a row's failure on its own transaction.

    The rollback that precedes this discarded everything the failed attempt wrote — including,
    if it were written before the rollback, the record of the failure itself. So it is written
    afterwards, from a fresh read.
    """
    item = db.get(models.BulkSendItem, item_id)
    if item is None:
        return 0
    item.status = "failed"
    item.error = (error or "Send failed.")[:600]
    db.commit()
    return 1


def _finish(db: Session, batch_id: str, *, sent: int, failed: int) -> dict:
    batch = db.get(models.BulkSendBatch, batch_id)
    if batch is None:
        return {"bulk_missing": 1}

    counts = _counts(db, batch.id)
    batch.succeeded = counts.get("sent", 0)
    batch.failed = counts.get("failed", 0)
    still_pending = counts.get("pending", 0)

    if batch.status == "cancelled":
        # Whatever never went out is cancelled, not left pending forever. A row in `pending` on
        # a finished batch reads as "still going" to anyone looking at it later.
        db.query(models.BulkSendItem).filter(
            models.BulkSendItem.batch_id == batch.id,
            models.BulkSendItem.status == "pending",
        ).update({"status": "cancelled"}, synchronize_session=False)
    elif still_pending:
        # The loop ended with work left and no cancellation — a worker restart. Leave the batch
        # running so a re-run picks the remainder up.
        batch.status = "running"
    else:
        batch.status = "completed_with_errors" if batch.failed else "completed"

    if batch.status != "running":
        batch.completed_at = _now()

    job = db.get(models.BackgroundJob, batch.job_id) if batch.job_id else None
    if job is not None and batch.status != "running":
        summary = f"{batch.succeeded} sent, {batch.failed} failed"
        if batch.status == "cancelled":
            jobs.fail(db, job, error=f"Cancelled — {summary}")
        elif batch.failed:
            jobs.fail(db, job, error=summary)
        else:
            jobs.succeed(db, job, summary=summary)
    db.commit()

    return {"bulk_sent": sent, "bulk_failed": failed,
            "bulk_batches_completed": 0 if batch.status == "running" else 1}


# ---------------------------------------------------------------------------------------
# Operator actions
# ---------------------------------------------------------------------------------------


def cancel(db: Session, batch: models.BulkSendBatch, *, actor: models.User,
           ip: str = "") -> models.BulkSendBatch:
    """Stop the rest. Envelopes already sent are untouched — they are in somebody's inbox and
    the only honest way to withdraw one is to void it, which is a per-envelope decision."""
    if batch.status in TERMINAL:
        raise BulkSendError("This batch has already finished.")
    batch.status = "cancelled"
    batch.completed_at = _now()
    cancelled = db.query(models.BulkSendItem).filter(
        models.BulkSendItem.batch_id == batch.id,
        models.BulkSendItem.status == "pending",
    ).update({"status": "cancelled"}, synchronize_session=False)
    record(db, tenant_id=batch.tenant_id, action="bulk_send.cancelled", actor=actor,
           object_type="bulk_send", object_id=batch.id, object_label=batch.name, ip=ip,
           meta={"cancelled_rows": cancelled})
    return batch


def retry_failed(db: Session, batch: models.BulkSendBatch, *, actor: models.User,
                 ip: str = "") -> int:
    """Put the failed rows back in the queue. Rows that already sent are never re-sent."""
    reset = db.query(models.BulkSendItem).filter(
        models.BulkSendItem.batch_id == batch.id,
        models.BulkSendItem.status == "failed",
    ).update({"status": "pending", "error": ""}, synchronize_session=False)
    if not reset:
        raise BulkSendError("There are no failed rows to retry.")
    batch.status = "queued"
    batch.completed_at = None
    record(db, tenant_id=batch.tenant_id, action="bulk_send.retried", actor=actor,
           object_type="bulk_send", object_id=batch.id, object_label=batch.name, ip=ip,
           meta={"rows": reset})
    return reset
