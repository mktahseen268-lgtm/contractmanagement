"""Minimal email sender. `console` backend (default) just logs the message — so OTP/notification
flows work with zero external services in dev; `smtp` backend does a real send (stdlib smtplib)."""

import logging

from .config import settings

log = logging.getLogger("uvicorn.error")


def send_email(to: str, subject: str, body: str) -> None:
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
