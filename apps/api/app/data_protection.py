"""Watermarking, download control, field masking, antivirus and anti-automation.

Four controls that all limit what leaves the system, or what gets into it.

**Watermarks name the viewer.** A dynamic per-viewer watermark does not stop a screenshot — it
makes the screenshot attributable, which is the actual deterrent. A static "CONFIDENTIAL"
stamp deters nobody because it identifies nobody.

**Masking is applied on the way out, in one place.** Masking in the template would leave the
API returning the real value to anyone who called it directly, which is the version an
attacker uses. So it happens where the response is built.

**Antivirus scans before a file is retrievable, not after.** A file that is stored, indexed,
and *then* scanned has already been downloadable for however long the queue was — so an
upload is quarantined until it passes.

**Anti-automation is layered, not a CAPTCHA.** A CAPTCHA at the application belongs at the
WAF; what this adds is proof-of-work and per-identifier backoff, which raise the cost of
credential stuffing without asking a branch customer with a feature phone to identify
motorcycles.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import secrets
import socket

from .config import settings

log = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------------------

#: Fields masked unless the caller's role is allowed to see them. Values are the roles that
#: may see the real thing.
MASKED_FIELDS: dict[str, set[str]] = {
    "value": {"owner", "admin", "manager", "approver"},
    "cnic": {"owner", "admin", "manager"},
    "account_number": {"owner", "admin", "manager"},
    "contact_phone": {"owner", "admin", "manager", "author"},
    "contact_email": {"owner", "admin", "manager", "author"},
    "registration_no": {"owner", "admin", "manager", "author"},
}

#: Patterns worth masking wherever they appear in free text, because a CNIC pasted into a
#: comment is as exposed as one in its own column.
_CNIC = re.compile(r"\b\d{5}-?\d{7}-?\d\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_LONG_DIGITS = re.compile(r"\b\d{9,}\b")


def mask_value(value, kind: str = "text") -> str:
    """Replace a value with something that proves it exists without disclosing it.

    Keeps the last few characters where they are how a person recognises the record — the
    last four of an account number is what a customer is asked to confirm, and masking it to
    nothing makes the field useless for its actual purpose.
    """
    text = "" if value is None else str(value)
    if not text:
        return ""
    if kind == "money":
        return "•••"
    if kind == "email":
        name, _, domain = text.partition("@")
        if not domain:
            return "•" * len(text)
        head = name[:1]
        return f"{head}{'•' * max(3, len(name) - 1)}@{domain}"
    if kind == "phone":
        return f"{'•' * max(0, len(text) - 4)}{text[-4:]}"
    if len(text) <= 4:
        return "•" * len(text)
    return f"{'•' * (len(text) - 4)}{text[-4:]}"


def mask_text(text: str) -> str:
    """Mask identifiers embedded in free text — comments, clause bodies, extracted content."""
    if not text:
        return text
    masked = _CNIC.sub(lambda m: mask_value(m.group(0)), text)
    masked = _IBAN.sub(lambda m: mask_value(m.group(0)), masked)
    return _LONG_DIGITS.sub(lambda m: mask_value(m.group(0)), masked)


def may_see(field: str, role: str) -> bool:
    allowed = MASKED_FIELDS.get(field)
    return allowed is None or role in allowed


def apply_masking(payload: dict, role: str) -> dict:
    """Mask the fields this role may not see, in the response being sent.

    Applied here rather than in the template because a template-level mask leaves the API
    returning the real value to anyone calling it directly — which is the version that gets
    used.
    """
    kinds = {"value": "money", "contact_email": "email", "contact_phone": "phone"}
    out = dict(payload)
    for field, value in payload.items():
        if not may_see(field, role) and value not in (None, ""):
            out[field] = mask_value(value, kinds.get(field, "text"))
            out[f"{field}_masked"] = True
    return out


# ---------------------------------------------------------------------------------------
# Watermarking
# ---------------------------------------------------------------------------------------


def watermark_text(*, name: str, email: str = "", when: dt.datetime | None = None,
                   reference: str = "") -> str:
    """The line stamped across a viewed document.

    Names the viewer and the moment. That is the whole point: it does not prevent a
    screenshot, it makes one attributable to the person who took it.
    """
    moment = (when or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    who = f"{name} <{email}>" if email else name
    tail = f" · {reference}" if reference else ""
    return f"{who} · {moment}{tail}"


def stamp_watermark(pdf_bytes: bytes, text: str) -> bytes:
    """Overlay the watermark diagonally across every page.

    Falls back to the original bytes if the overlay fails. That is deliberate: the alternative
    is refusing to show a document because a cosmetic layer could not be drawn, and a viewer
    who cannot see the agreement will ask somebody to email it to them instead — which is
    strictly worse for confidentiality than an unwatermarked view inside the system.
    """
    try:
        import io

        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.colors import Color
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas
    except ImportError:  # pragma: no cover - depends on the installed requirement set
        return pdf_bytes

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            width = float(page.mediabox.width) or A4[0]
            height = float(page.mediabox.height) or A4[1]

            overlay_buffer = io.BytesIO()
            overlay = pdf_canvas.Canvas(overlay_buffer, pagesize=(width, height))
            overlay.saveState()
            overlay.setFillColor(Color(0.4, 0.4, 0.45, alpha=0.18))
            overlay.setFont("Helvetica-Bold", 15)
            overlay.translate(width / 2, height / 2)
            overlay.rotate(45)
            # Repeated up the page: a single line across the middle is trivially cropped out
            # of a screenshot, and a crop that removes the attribution defeats the control.
            for offset in range(-4, 5):
                overlay.drawCentredString(0, offset * 90, text)
            overlay.restoreState()
            overlay.save()
            overlay_buffer.seek(0)

            page.merge_page(PdfReader(overlay_buffer).pages[0])
            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001
        log.warning("could not watermark the document: %s", e)
        return pdf_bytes


def download_headers(*, allow_download: bool, filename: str) -> dict:
    """Headers for a controlled view.

    `Content-Disposition: inline` and a restrictive CSP are the honest limit of what a server
    can do — a determined viewer can still save the bytes their browser received. The control
    that matters is the watermark that names them, not a header that pretends to prevent it.
    """
    if allow_download:
        return {"Content-Disposition": f'attachment; filename="{filename}"'}
    return {
        "Content-Disposition": f'inline; filename="{filename}"',
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "X-Download-Options": "noopen",
        "Content-Security-Policy": "default-src 'none'; object-src 'self'; sandbox",
    }


# ---------------------------------------------------------------------------------------
# Antivirus
# ---------------------------------------------------------------------------------------

#: The EICAR test string. Recognised without ClamAV so the scanning path can be exercised in
#: CI and in a deployment where the daemon is not yet running — a scanner nobody has ever
#: seen reject anything is a scanner nobody trusts.
EICAR = (b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")


class VirusFound(ValueError):
    """The upload is infected. Never stored, never retrievable."""


def av_enabled() -> bool:
    return bool(settings.clamav_enabled and settings.clamav_host)


def scan(payload: bytes, *, filename: str = "") -> tuple[bool, str]:
    """(clean, detail). Scans over ClamAV's INSTREAM protocol.

    **Fails closed when the scanner is configured but unreachable.** That is the opposite of
    every other integration here, and deliberately: an antivirus that waves files through when
    it cannot reach the daemon provides no protection at exactly the moment an attacker would
    choose. If AV is off entirely, uploads are accepted and the status says so honestly.
    """
    if EICAR in payload:
        return False, "Eicar-Test-Signature"

    if not av_enabled():
        return True, "not scanned — antivirus is not configured"

    try:
        with socket.create_connection(
            (settings.clamav_host, settings.clamav_port),
            timeout=settings.clamav_timeout,
        ) as sock:
            sock.sendall(b"zINSTREAM\0")
            view = memoryview(payload)
            for start in range(0, len(payload), 8192):
                chunk = view[start:start + 8192]
                sock.sendall(len(chunk).to_bytes(4, "big") + bytes(chunk))
            sock.sendall((0).to_bytes(4, "big"))
            response = sock.recv(4096).decode("utf-8", errors="replace").strip()
    except Exception as e:  # noqa: BLE001
        log.error("antivirus unreachable while scanning %s: %s", filename or "upload", e)
        raise VirusFound(
            "The file could not be scanned for viruses and was not accepted."
        ) from e

    if response.endswith("OK"):
        return True, "clean"
    if "FOUND" in response:
        return False, response.split(":", 1)[-1].replace("FOUND", "").strip()
    return False, response or "unrecognised antivirus response"


def scan_or_raise(payload: bytes, *, filename: str = "") -> str:
    clean, detail = scan(payload, filename=filename)
    if not clean:
        raise VirusFound(f"That file was rejected: {detail}.")
    return detail


# ---------------------------------------------------------------------------------------
# Anti-automation
# ---------------------------------------------------------------------------------------

#: Failures before a proof-of-work is demanded of an identifier.
POW_AFTER_FAILURES = 3

#: Leading zero bits required. 16 is roughly a fraction of a second in a browser and a real
#: cost across millions of attempts — enough to make stuffing uneconomic without being felt
#: by somebody who mistyped their password.
POW_DIFFICULTY_BITS = 16

_failures: dict[str, list[dt.datetime]] = {}
_FAILURE_WINDOW = dt.timedelta(minutes=15)


def record_failure(identifier: str) -> int:
    """Note a failed attempt against an identifier. Returns the count in the window."""
    now = dt.datetime.now(dt.timezone.utc)
    recent = [t for t in _failures.get(identifier, []) if now - t < _FAILURE_WINDOW]
    recent.append(now)
    _failures[identifier] = recent
    return len(recent)


def clear_failures(identifier: str) -> None:
    _failures.pop(identifier, None)


def failures_for(identifier: str) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    return len([t for t in _failures.get(identifier, []) if now - t < _FAILURE_WINDOW])


def challenge_required(identifier: str) -> bool:
    return failures_for(identifier) >= POW_AFTER_FAILURES


def new_challenge() -> dict:
    """A proof-of-work puzzle.

    Chosen over a CAPTCHA on purpose: the signing portal is used by branch customers on
    whatever device they have, and a visual puzzle excludes exactly the people the
    accessibility requirements say must be able to sign. A hash puzzle costs their browser a
    moment and costs a stuffing script the same moment, millions of times over.
    """
    return {
        "challenge": secrets.token_hex(16),
        "difficulty": POW_DIFFICULTY_BITS,
        "algorithm": "sha256",
        "instructions": ("Find a nonce such that sha256(challenge + nonce) starts with "
                         f"{POW_DIFFICULTY_BITS} zero bits."),
    }


def verify_proof(challenge: str, nonce: str, *, bits: int = POW_DIFFICULTY_BITS) -> bool:
    """Check a proof of work. Cheap for us, expensive for them — the whole point."""
    if not challenge or not nonce:
        return False
    digest = hashlib.sha256(f"{challenge}{nonce}".encode()).digest()
    value = int.from_bytes(digest[: (bits // 8) + 1], "big")
    return value >> max(0, ((((bits // 8) + 1) * 8) - bits)) == 0


def status() -> dict:
    """What is switched on, for the security screen."""
    return {
        "antivirus": {
            "enabled": av_enabled(),
            "host": settings.clamav_host,
            # Stated plainly: an operator has to know whether uploads are actually protected.
            "note": ("Uploads are scanned before they become retrievable."
                     if av_enabled() else
                     "Not configured — uploads are accepted without a virus scan."),
        },
        "anti_automation": {
            "enabled": True,
            "proof_of_work_after_failures": POW_AFTER_FAILURES,
            "difficulty_bits": POW_DIFFICULTY_BITS,
            "note": "CAPTCHA belongs at the WAF; this is the application-layer cost.",
        },
        "masking": {"fields": sorted(MASKED_FIELDS)},
        "watermarking": {"enabled": True, "applies_to": "shared and temporary-access views"},
    }
