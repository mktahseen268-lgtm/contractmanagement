"""Email sender. All outbound mail goes through `email_outbox` for visibility + retry. The
`console` backend (default in dev) logs the body and marks the row sent immediately; the `smtp`
backend talks to a real server via stdlib smtplib.

Callers use `send_email(to, subject, body, *, tenant_id="")` exactly as before — the queueing /
delivery is internal."""

import logging

from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from . import models

log = logging.getLogger("uvicorn.error")


def _deliver(to: str, subject: str, body: str) -> None:
    """The actual send. Raises on error so the caller can record the failure."""
    if settings.email_backend == "smtp":
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = settings.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            if settings.smtp_starttls and settings.smtp_user:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    else:
        log.info("[email:console] To: %s | Subject: %s\n--- body ---\n%s\n------------", to, subject, body)


def send_email(to: str, subject: str, body: str, *, tenant_id: str = "") -> str:
    """Queue an email through the outbox + attempt immediate delivery. Returns the outbox row id.
    Failures are recorded (status=failed, last_error set) but never raise to the caller — the
    outbox flusher will retry later."""
    import datetime as dt

    with SessionLocal() as db:
        row = models.EmailOutbox(tenant_id=tenant_id, to_email=to, to_name="", subject=subject[:400], body=body, status="queued", attempts=0)
        db.add(row)
        db.flush()
        rid = row.id
        try:
            _deliver(to, subject, body)
            row.status = "sent"
            row.attempts = 1
            row.sent_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        except Exception as e:  # noqa: BLE001
            log.exception("[email] delivery failed (will be retried by the flusher)")
            row.status = "failed"
            row.attempts = 1
            row.last_error = (str(e) or e.__class__.__name__)[:500]
        db.commit()
        return rid


def flush_outbox(db: Session, *, max_attempts: int = 5, batch: int = 50) -> dict[str, int]:
    """Retry failed/queued outbox rows. Called from a Celery task on a schedule; caller commits."""
    from sqlalchemy import select

    rows = db.scalars(
        select(models.EmailOutbox).where(
            models.EmailOutbox.status.in_(["queued", "failed"]),
            models.EmailOutbox.attempts < max_attempts,
        ).order_by(models.EmailOutbox.created_at).limit(batch)
    ).all()
    sent = 0
    failed = 0
    import datetime as dt

    for r in rows:
        try:
            _deliver(r.to_email, r.subject, r.body)
            r.status = "sent"
            r.attempts += 1
            r.sent_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            sent += 1
        except Exception as e:  # noqa: BLE001
            r.status = "failed"
            r.attempts += 1
            r.last_error = (str(e) or e.__class__.__name__)[:500]
            failed += 1
    return {"retried": len(rows), "sent": sent, "failed": failed}
