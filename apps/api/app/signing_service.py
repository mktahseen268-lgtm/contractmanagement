"""E-signature engine. v1: no on-page field placement — recipients adopt a typed signature; the
executed PDF appends a Signatures page + a Certificate of Completion. Sequential or parallel
signing. The signing link (`/sign/{token}`) is unauthenticated. (DocViewer field placement,
identity OTP, in-person/kiosk signing, etc. are planned — docs/13.)

Token model (post 0013_hardening): the raw URL token is *never* persisted in plaintext.
We store:
  - `access_token_hash` (SHA-256 of raw)  — used for /sign/{token} lookup
  - `access_token_secret` (EncryptedString) — Fernet/AES-256-GCM ciphertext of the raw, so
    server-side reminders can decrypt to email the same link without a fresh URL
  - `access_token_expires_at`              — hard expiry (default 14 days)
"""

import datetime as dt
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, security
from .config import settings
from .email import send_email
from .pdf import render_contract_pdf_bytes
from .storage import get_storage, tenant_key

CONSENT_TEXT = (
    "By signing electronically you agree to use electronic records and signatures for this "
    "agreement, and that your electronic signature is the legal equivalent of your handwritten "
    "signature. Your IP address and the time of signing are recorded as evidence."
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# Max decoded size of an adopted-signature image (drawn canvas export / uploaded file).
_MAX_SIGNATURE_IMAGE_BYTES = 1_000_000  # ~1 MB
_ALLOWED_SIGNATURE_MIME = ("image/png", "image/jpeg")


def validate_signature_image(data_url: str | None) -> str | None:
    """Validate a base64 image *data URL* for a drawn/uploaded signature. Returns the data URL
    unchanged when valid, or None when absent/invalid. Enforces PNG/JPEG, a real decodable
    payload, and a ~1 MB decoded cap so a recipient can't store an arbitrarily large blob."""
    import base64
    import binascii

    if not data_url or not isinstance(data_url, str):
        return None
    s = data_url.strip()
    if not s.startswith("data:"):
        return None
    try:
        header, b64 = s.split(",", 1)
    except ValueError:
        return None
    mime = header[5:].split(";", 1)[0].strip().lower()
    if mime not in _ALLOWED_SIGNATURE_MIME or "base64" not in header.lower():
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw or len(raw) > _MAX_SIGNATURE_IMAGE_BYTES:
        return None
    # Sanity-check magic bytes so a mislabeled payload can't slip through.
    is_png = raw[:8] == b"\x89PNG\r\n\x1a\n"
    is_jpeg = raw[:3] == b"\xff\xd8\xff"
    if not (is_png or is_jpeg):
        return None
    return s


def _token_ttl() -> dt.timedelta:
    return dt.timedelta(days=max(1, settings.signing_token_ttl_days))


def _mint_token_for(recipient: "models.SignatureRecipient") -> str:
    """Generate a fresh raw token, persist the hash + encrypted copy + expiry on the recipient,
    and return the raw value for embedding in the URL. The raw is *only* known transiently to
    the caller; reading it back later requires `decrypt_token_for(recipient)`."""
    raw, h = security.new_signing_token()
    recipient.access_token_hash = h
    recipient.access_token_secret = raw  # EncryptedString encrypts on flush
    recipient.access_token_expires_at = _now() + _token_ttl()
    return raw


def decrypt_token_for(recipient: "models.SignatureRecipient") -> str | None:
    """Return the raw signing token from the encrypted column (used for reminders). Returns None
    if no token has been minted or it has expired/been revoked."""
    if not recipient.access_token_secret:
        return None
    if recipient.access_token_expires_at and recipient.access_token_expires_at <= _now():
        return None
    return recipient.access_token_secret  # EncryptedString decrypts on load


def _clear_token(recipient: "models.SignatureRecipient") -> None:
    recipient.access_token_hash = None
    recipient.access_token_secret = None
    recipient.access_token_expires_at = None


def _log(db: Session, env: models.SignatureEnvelope, event: str, *, recipient: models.SignatureRecipient | None = None, ip: str = "", ua: str = "", meta: dict | None = None) -> None:
    db.add(models.SignatureEvent(
        tenant_id=env.tenant_id, envelope_id=env.id,
        recipient_id=(recipient.id if recipient else None), recipient_name=(recipient.name if recipient else ""),
        event=event, ip=ip, user_agent=ua[:400], meta=meta or {},
    ))
    from . import metrics
    metrics.record_signature(event)


def _notify_owner(db: Session, contract: models.Contract, title: str, body: str) -> None:
    if contract.owner_id:
        db.add(models.Notification(tenant_id=contract.tenant_id, user_id=contract.owner_id, type="contract.signature_update", title=title, body=body, object_type="contract", object_id=contract.id))


def _email_recipient(db: Session, recipient: models.SignatureRecipient, contract: models.Contract, sender_name: str, *, raw_token: str | None = None, reminder: bool = False) -> None:
    """Email the signer their /sign/{token} URL. `raw_token` is the token returned by
    `_mint_token_for` at the call site; if omitted we decrypt from the stored ciphertext
    (used by reminders). Returns early without emailing if no live token exists.

    `db=` is passed so the outbox row joins **this** transaction. Without it `send_email` opens
    its own session and commits, which means the invitation is committed and delivered even
    when the surrounding request later rolls back — the recipient gets a link to an envelope
    that was never sent. On SQLite the same omission deadlocks outright, which is how this was
    found.
    """
    token = raw_token or decrypt_token_for(recipient)
    if not token:
        return
    link = f"{settings.frontend_url.rstrip('/')}/sign/{token}"
    asked = f"{sender_name} has asked you" if sender_name else "You have been asked"
    # A reminder that reads exactly like the first invitation gets skimmed as a duplicate and
    # ignored, which defeats the point of sending it.
    subject = ("Reminder — please sign: " if reminder else "Please sign: ") + contract.title
    opening = f"This is a reminder that {asked[0].lower()}{asked[1:]}" if reminder else asked
    send_email(
        recipient.email,
        subject,
        f"Hi {recipient.name},\n\n{opening} to sign \"{contract.title}\" ({contract.reference_no}).\n\nReview and sign here:\n{link}\n\nThis link is unique to you — please don't forward it.",
        tenant_id=contract.tenant_id,
        db=db,
    )


# ---------- queries ----------


# Ordering for "the latest envelope". `created_at` alone is not enough: the system clock has
# coarse resolution on some platforms, so two envelopes created in quick succession — a
# double-submit, a script — can share a timestamp exactly. With no tiebreak the database is
# free to return either, and "which envelope is current" becomes non-deterministic between two
# calls with no writes in between. `id` is a random uuid, so it does not say which came first;
# what it does give is a *stable* answer, which is the difference between a bug you can
# reproduce and one you cannot.
_LATEST_FIRST = (models.SignatureEnvelope.created_at.desc(), models.SignatureEnvelope.id.desc())


def current_envelope(db: Session, contract_id: str) -> models.SignatureEnvelope | None:
    """The latest non-voided envelope for the contract (draft/sent/partially_signed/completed/declined)."""
    return db.scalar(
        select(models.SignatureEnvelope).where(models.SignatureEnvelope.contract_id == contract_id, models.SignatureEnvelope.status != "voided").order_by(*_LATEST_FIRST)
    )


def active_envelope(db: Session, contract_id: str) -> models.SignatureEnvelope | None:
    """An envelope that's out for signature (blocks plain status transitions)."""
    return db.scalar(
        select(models.SignatureEnvelope).where(models.SignatureEnvelope.contract_id == contract_id, models.SignatureEnvelope.status.in_(["sent", "partially_signed"])).order_by(*_LATEST_FIRST)
    )


def recipient_by_token(db: Session, token: str) -> models.SignatureRecipient | None:
    """Resolve `/sign/{token}` to a recipient by hashing the inbound URL token and matching
    against `access_token_hash`. Expired tokens return None (look like 'not found' to the
    public portal, which is correct behavior — don't leak whether a token *was* ever valid)."""
    if not token:
        return None
    h = security.hash_token(token)
    rec = db.scalar(select(models.SignatureRecipient).where(models.SignatureRecipient.access_token_hash == h))
    if rec is None:
        return None
    if rec.access_token_expires_at is not None and rec.access_token_expires_at <= _now():
        return None
    return rec


def recipients(db: Session, envelope_id: str) -> list[models.SignatureRecipient]:
    return list(db.scalars(select(models.SignatureRecipient).where(models.SignatureRecipient.envelope_id == envelope_id).order_by(models.SignatureRecipient.sequence)).all())


def _signers(rs: list[models.SignatureRecipient]) -> list[models.SignatureRecipient]:
    return [r for r in rs if r.kind == "signer"]


def is_recipients_turn(envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient, rs: list[models.SignatureRecipient]) -> bool:
    """In sequential mode, true only if every earlier signer has signed."""
    if recipient.kind != "signer":
        return False
    if envelope.signing_order == "parallel":
        return True
    for r in _signers(rs):
        if r.sequence < recipient.sequence and r.status != "signed":
            return False
    return True


# ---------- lifecycle ----------


def _match_internal_user(db: Session, tenant_id: str, email: str) -> str | None:
    """The workspace user with this email, if any.

    Matched on email because that is what the envelope carries. Deliberately scoped to the
    tenant: matching across tenants would let one workspace's envelope resolve to another's
    user, and from there to their certificate.
    """
    if not email:
        return None
    user = db.scalar(
        select(models.User).where(
            models.User.tenant_id == tenant_id,
            func.lower(models.User.email) == email.lower(),
        )
    )
    return user.id if user is not None else None


def create_envelope(db: Session, *, contract: models.Contract, recipients_in: list, message: str, signing_order: str, by_user: models.User) -> models.SignatureEnvelope:
    signers = [r for r in recipients_in if r.kind != "cc"]
    if not signers:
        raise ValueError("Add at least one signer.")
    env = models.SignatureEnvelope(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        status="draft", signing_order=("parallel" if signing_order == "parallel" else "sequential"),
        message=(message or "").strip()[:4000], created_by=by_user.id,
    )
    db.add(env)
    db.flush()
    for i, r in enumerate(recipients_in):
        email = str(r.email).lower()
        db.add(models.SignatureRecipient(
            tenant_id=contract.tenant_id, envelope_id=env.id, sequence=i,
            name=(r.name or "").strip()[:200], email=email,
            kind=("cc" if r.kind == "cc" else "signer"), status="created",
            # Bind the recipient to a workspace identity where one exists. This is what lets
            # the sealer find *this signatory's* certificate instead of falling back to a
            # shared one (Phase 2). An external counterparty simply has no match here and is
            # bound later, through the OTP flow.
            signer_user_id=_match_internal_user(db, contract.tenant_id, email),
            party_ref=getattr(r, "party_ref", None),
        ))
    _log(db, env, "created", recipient=None, meta={"recipients": len(recipients_in)})
    # Flush the recipients, not just the envelope. The session runs with `autoflush=False`, so
    # a caller that creates and sends in one transaction — bulk send does exactly that — would
    # have `send_envelope`'s `recipients()` query return nothing and refuse with "the envelope
    # has no signers", on an envelope that has three. The two-request path never saw it because
    # the commit in between did this flush by accident.
    db.flush()
    return env


def send_envelope(db: Session, *, envelope: models.SignatureEnvelope, contract: models.Contract, by_user: models.User, org_name: str) -> models.SignatureEnvelope:
    if envelope.status != "draft":
        raise ValueError("This envelope has already been sent.")
    rs = recipients(db, envelope.id)
    if not _signers(rs):
        raise ValueError("The envelope has no signers.")
    # snapshot the version + a hash of the content being signed
    cur_v = db.scalar(select(models.ContractVersion).where(models.ContractVersion.contract_id == contract.id).order_by(models.ContractVersion.version_no.desc()))
    envelope.contract_version_id = cur_v.id if cur_v else None
    envelope.document_hash = hashlib.sha256((contract.body or "").encode("utf-8")).hexdigest()
    # render the contract PDF the recipients will review (DRAFT — not executed yet)
    pdf_bytes = render_contract_pdf_bytes(contract=contract, org_name=org_name, draft=True)
    storage = get_storage()
    storage.ensure_ready()
    import re
    import uuid

    fid = uuid.uuid4().hex
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{contract.reference_no}_for_signature").strip("_")[:120] or "contract"
    key = tenant_key(contract.tenant_id, "contract_pdf", f"{fid}-{safe}.pdf")
    storage.put(key, pdf_bytes, "application/pdf")
    db.add(models.FileObject(
        id=fid, tenant_id=contract.tenant_id, key=key, bucket=settings.s3_bucket if settings.use_s3 else "", backend=storage.name,
        content_type="application/pdf", size=len(pdf_bytes), sha256=hashlib.sha256(pdf_bytes).hexdigest(), original_name=f"{safe}.pdf",
        kind="contract_pdf", parent_type="contract", parent_id=contract.id, created_by=by_user.id,
    ))
    envelope.document_file_id = fid
    # tokens + statuses. Each recipient gets a fresh hashed+encrypted token; the raw is held
    # in memory only long enough to embed it in the email URL (no plaintext persisted).
    sender_name = by_user.name
    signers = _signers(rs)
    raw_tokens: dict[str, str] = {r.id: _mint_token_for(r) for r in rs}
    if envelope.signing_order == "parallel":
        for r in rs:
            r.status = "sent"
            _log(db, envelope, "sent", recipient=r)
            if r.kind == "signer":
                _email_recipient(db, r, contract, sender_name, raw_token=raw_tokens[r.id])
    else:
        # only the first signer is "sent"; others become "sent" when their turn comes. CC recipients are "sent" immediately.
        first_signer_seq = min(r.sequence for r in signers)
        for r in rs:
            if r.kind == "cc" or r.sequence == first_signer_seq:
                r.status = "sent"
                _log(db, envelope, "sent", recipient=r)
                if r.kind == "signer":
                    _email_recipient(db, r, contract, sender_name, raw_token=raw_tokens[r.id])
    envelope.status = "sent"
    envelope.sent_at = _now()
    if contract.status == "approved":
        contract.status = "out_for_signature"
    _log(db, envelope, "sent", recipient=None)
    _notify_owner(db, contract, f"\"{contract.title}\" sent for signature", f"{by_user.name} sent it to {len(signers)} signer(s).")
    return envelope


def mark_viewed(db: Session, recipient: models.SignatureRecipient, envelope: models.SignatureEnvelope, *, ip: str = "", ua: str = "") -> None:
    if recipient.status == "sent":
        recipient.status = "viewed"
        recipient.ip = ip or recipient.ip
        recipient.user_agent = (ua or recipient.user_agent)[:400]
        _log(db, envelope, "opened", recipient=recipient, ip=ip, ua=ua)


def _initials_of(name: str) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def fill_tabs_for_recipient(db: Session, *, envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient,
                             full_name: str, fills: list | None = None) -> tuple[int, list[str]]:
    """Fill this recipient's tabs as part of signing. Returns (filled_count, missing_required_labels).
    signature/initials/date are auto-filled; text/checkbox tabs use values from `fills` (a list of
    objects with .tab_id and .value, or dicts)."""
    rows = list(db.scalars(
        select(models.SignatureTab).where(
            models.SignatureTab.envelope_id == envelope.id,
            models.SignatureTab.recipient_id == recipient.id,
        )
    ).all())
    if not rows:
        return 0, []
    by_id: dict[str, str] = {}
    for f in (fills or []):
        tid = f.tab_id if hasattr(f, "tab_id") else f.get("tab_id")
        val = f.value if hasattr(f, "value") else f.get("value", "")
        if tid:
            by_id[tid] = str(val or "")
    now = _now()
    today_str = now.date().isoformat()
    filled = 0
    missing: list[str] = []
    signed_name = (full_name or recipient.name).strip()[:200]
    for t in rows:
        if t.kind == "signature":
            t.value = signed_name
        elif t.kind == "initials":
            t.value = _initials_of(signed_name)
        elif t.kind == "date":
            t.value = today_str
        elif t.kind == "text":
            t.value = (by_id.get(t.id, "") or "").strip()[:500]
        elif t.kind == "checkbox":
            t.value = "true" if (by_id.get(t.id, "") or "").lower() in ("true", "1", "yes", "on") else ""
        else:
            t.value = ""
        if t.required and not t.value:
            missing.append(t.label or f"{t.kind} (p.{t.page})")
        else:
            filled += 1
        t.filled_at = now
    return filled, missing


class ConcurrentSigningError(RuntimeError):
    """Two signers raced on the same envelope. Routers map this to 409 so the client retries
    against fresh state rather than writing over the other signature."""


def _claim_envelope(db: Session, envelope: models.SignatureEnvelope) -> None:
    """Optimistic lock: bump `lock_version` only if it still holds the value we read.

    Parallel signing means two people can legitimately hit `sign()` at the same moment. Without
    this, both read `partially_signed`, both compute "who is still pending" from the same stale
    snapshot, and the second write can flip the envelope to `completed` while a signature is
    still in flight — or lose one entirely. RFP §4a(ii) 4.4 asks for execution free from
    signature failures; this is the cheapest correct way to get it.
    """
    expected = envelope.lock_version or 0
    result = db.execute(
        models.SignatureEnvelope.__table__.update()
        .where(
            models.SignatureEnvelope.id == envelope.id,
            models.SignatureEnvelope.lock_version == expected,
        )
        .values(lock_version=expected + 1)
    )
    if (result.rowcount or 0) == 0:
        raise ConcurrentSigningError(
            "Another signer updated this envelope at the same moment. Reload and try again."
        )
    envelope.lock_version = expected + 1


def sign(db: Session, *, envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient, contract: models.Contract, full_name: str, ip: str, ua: str, tab_fills: list | None = None, signature_kind: str = "typed", signature_image: str | None = None) -> models.SignatureEnvelope:
    if envelope.status not in ("sent", "partially_signed"):
        raise ValueError("This envelope is no longer open for signing.")
    if recipient.kind != "signer":
        raise ValueError("This recipient is a CC, not a signer.")
    if recipient.status in ("signed", "declined"):
        # Idempotency: a retried request (double-tap, flaky network, client retry) must not
        # produce a second signature or a second audit event.
        raise ValueError("You have already responded.")
    _claim_envelope(db, envelope)
    rs = recipients(db, envelope.id)
    if not is_recipients_turn(envelope, recipient, rs):
        raise ValueError("It's not your turn to sign yet — an earlier signer hasn't signed.")
    # Validate the adopted-signature image for drawn/uploaded modes. Typed mode keeps text-only.
    kind = signature_kind if signature_kind in ("typed", "drawn", "uploaded") else "typed"
    image: str | None = None
    if kind in ("drawn", "uploaded"):
        image = validate_signature_image(signature_image)
        if image is None:
            raise ValueError("A drawn or uploaded signature is required. Please add your signature, or switch to Type.")
    # fill any tabs assigned to this recipient (required tabs must end up non-empty)
    _, missing = fill_tabs_for_recipient(db, envelope=envelope, recipient=recipient, full_name=full_name, fills=tab_fills)
    if missing:
        raise ValueError(f"Please fill these required fields: {', '.join(missing)}")
    now = _now()
    recipient.signed_name = (full_name or recipient.name).strip()[:200]
    recipient.signature_kind = kind
    recipient.signature_image = image
    recipient.consent_at = now
    recipient.signed_at = now
    recipient.status = "signed"
    recipient.ip = ip or recipient.ip
    recipient.user_agent = (ua or recipient.user_agent)[:400]
    _log(db, envelope, "consented", recipient=recipient, ip=ip, ua=ua)
    _log(db, envelope, "signed", recipient=recipient, ip=ip, ua=ua, meta={"signed_name": recipient.signed_name})

    rs = recipients(db, envelope.id)
    pending = [r for r in _signers(rs) if r.status not in ("signed",)]
    if not pending:
        envelope.status = "completed"
        envelope.completed_at = now
        _log(db, envelope, "completed", recipient=None)
        if contract.status == "out_for_signature":
            contract.status = "signed"
        _notify_owner(db, contract, f"\"{contract.title}\" is fully executed", "All signers have signed. The executed copy and certificate are being prepared.")
        # NB: the caller schedules seal_envelope() *after committing* — the task reads the
        # envelope in its own session, so it must see status="completed" already persisted.
    else:
        envelope.status = "partially_signed"
        if envelope.signing_order == "sequential":
            nxt = min(pending, key=lambda r: r.sequence)
            if nxt.status == "created":
                nxt.status = "sent"
                # Mint a token only if this recipient doesn't already have a live one (they
                # were created with `status=created` and no token at envelope-creation time).
                raw_next = decrypt_token_for(nxt) or _mint_token_for(nxt)
                _log(db, envelope, "sent", recipient=nxt)
                send_email(
                    nxt.email,
                    f"Please sign: {contract.title}",
                    f"Hi {nxt.name},\n\nIt's now your turn to sign \"{contract.title}\" ({contract.reference_no}).\n\n"
                    f"Review and sign here:\n{settings.frontend_url.rstrip('/')}/sign/{raw_next}",
                    tenant_id=contract.tenant_id,
                    db=db,
                )
        _notify_owner(db, contract, f"\"{contract.title}\" — {recipient.name} signed", f"{len([r for r in _signers(rs) if r.status=='signed'])} of {len(_signers(rs))} signers done.")
    return envelope


def decline(db: Session, *, envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient, contract: models.Contract, reason: str, ip: str, ua: str) -> models.SignatureEnvelope:
    if envelope.status not in ("sent", "partially_signed"):
        raise ValueError("This envelope is no longer open.")
    if recipient.status in ("signed", "declined"):
        raise ValueError("You have already responded.")
    now = _now()
    recipient.status = "declined"
    recipient.declined_reason = (reason or "").strip()[:500]
    recipient.ip = ip or recipient.ip
    recipient.user_agent = (ua or recipient.user_agent)[:400]
    _log(db, envelope, "declined", recipient=recipient, ip=ip, ua=ua, meta={"reason": recipient.declined_reason})
    envelope.status = "declined"
    envelope.completed_at = now
    if contract.status == "out_for_signature":
        contract.status = "declined"
    _notify_owner(db, contract, f"\"{contract.title}\" was declined", f"{recipient.name} declined to sign." + (f" Reason: {recipient.declined_reason}" if recipient.declined_reason else ""))
    return envelope


def void_envelope(db: Session, *, envelope: models.SignatureEnvelope, contract: models.Contract, by_user: models.User) -> models.SignatureEnvelope:
    if envelope.status not in ("draft", "sent", "partially_signed"):
        raise ValueError("This envelope can't be voided.")
    envelope.status = "voided"
    for r in recipients(db, envelope.id):
        _clear_token(r)  # invalidate the links (hash + ciphertext + expiry all wiped)
    if contract.status == "out_for_signature":
        contract.status = "approved"
    _log(db, envelope, "voided", recipient=None, meta={"by": by_user.name})
    _notify_owner(db, contract, f"Signature request for \"{contract.title}\" was voided", f"{by_user.name} voided the envelope.")
    return envelope


def remind(db: Session, *, envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient, contract: models.Contract, by_name: str) -> None:
    """Chase one recipient. `by_name` rather than a `User` because the automatic sweep has
    no user to attribute it to and must not have to invent one."""
    if envelope.status not in ("sent", "partially_signed") or recipient.status not in ("sent", "viewed"):
        raise ValueError("Nothing to remind about for this recipient.")
    _email_recipient(db, recipient, contract, by_name, reminder=True)
    _log(db, envelope, "reminder_sent", recipient=recipient, meta={"by": by_name})


def delete_envelopes_for_contract(db: Session, contract_id: str) -> None:
    env_ids = [e[0] for e in db.execute(select(models.SignatureEnvelope.id).where(models.SignatureEnvelope.contract_id == contract_id)).all()]
    if env_ids:
        db.query(models.SignatureTab).filter(models.SignatureTab.envelope_id.in_(env_ids)).delete(synchronize_session=False)
        db.query(models.SignatureEvent).filter(models.SignatureEvent.envelope_id.in_(env_ids)).delete(synchronize_session=False)
        db.query(models.SignatureRecipient).filter(models.SignatureRecipient.envelope_id.in_(env_ids)).delete(synchronize_session=False)
        db.query(models.SignatureEnvelope).filter(models.SignatureEnvelope.contract_id == contract_id).delete(synchronize_session=False)


# ---------------------------------------------------------------------------------------
# Chasing and expiry — the unattended half of sending
# ---------------------------------------------------------------------------------------
#
# A bulk dispatch of five hundred is only useful if the ones that go unsigned chase themselves.
# Both halves run cross-tenant with no tenant GUC set, like the other sweeps.


def _due_for_reminder(env: models.SignatureEnvelope, now: dt.datetime) -> bool:
    if not env.reminder_interval_days or env.reminders_sent >= (env.max_reminders or 0):
        return False
    since = env.last_reminder_at or env.sent_at
    if since is None:
        return False
    return since + dt.timedelta(days=env.reminder_interval_days) <= now


def expire_envelope(db: Session, env: models.SignatureEnvelope) -> int:
    """Close an envelope that ran out of time and revoke every outstanding link.

    Clearing the tokens is the point. Leaving the envelope marked `expired` while the signing
    URLs still resolve would mean the deadline was a label on a screen and not a control.
    """
    revoked = 0
    for r in recipients(db, env.id):
        if r.status in ("sent", "viewed"):
            r.status = "expired"
            _clear_token(r)
            revoked += 1
    env.status = "expired"
    _log(db, env, "expired", meta={"links_revoked": revoked})
    return revoked


def chase_and_expire(db: Session, *, now: dt.datetime | None = None) -> dict:
    """Send the reminders that have come due and expire the envelopes that have run out.

    Expiry runs first: an envelope whose deadline has passed must not be chased on the way
    out, which is exactly what would happen if the order were reversed and both were due in
    the same sweep.
    """
    now = now or _now()
    live = ("sent", "partially_signed")
    expired = reminded = 0

    for env in db.scalars(
        select(models.SignatureEnvelope).where(
            models.SignatureEnvelope.status.in_(live),
            models.SignatureEnvelope.expires_at.is_not(None),
            models.SignatureEnvelope.expires_at <= now,
        )
    ).all():
        expire_envelope(db, env)
        expired += 1

    # Flush the expiries before selecting candidates to chase. The session runs with
    # `autoflush=False`, so without this the reminder query below still sees every envelope it
    # just expired as `sent` — and chases the signer towards a link the same sweep revoked
    # seconds earlier. The email arrives, the page is dead.
    db.flush()

    for env in db.scalars(
        select(models.SignatureEnvelope).where(
            models.SignatureEnvelope.status.in_(live),
            models.SignatureEnvelope.reminder_interval_days > 0,
        )
    ).all():
        if not _due_for_reminder(env, now):
            continue
        contract = db.get(models.Contract, env.contract_id)
        if contract is None:
            continue
        tenant = db.get(models.Tenant, env.tenant_id)
        org_name = tenant.name if tenant else ""
        rs = recipients(db, env.id)
        sent_any = False
        for r in rs:
            # `is_recipients_turn` keeps a sequential envelope from chasing signer three before
            # signer one has signed — that email names a document the recipient cannot open.
            if r.kind != "signer" or r.status not in ("sent", "viewed"):
                continue
            if not is_recipients_turn(env, r, rs):
                continue
            _email_recipient(db, r, contract, org_name, reminder=True)
            _log(db, env, "reminder_sent", recipient=r, meta={"by": "automatic"})
            sent_any = True
        if sent_any:
            # Counted per envelope, not per recipient: "three reminders" means the signer got
            # three emails, and counting per recipient would send a two-signer envelope only
            # half its configured chases.
            env.reminders_sent = (env.reminders_sent or 0) + 1
            env.last_reminder_at = now
            reminded += 1

    return {"envelopes_expired": expired, "envelopes_reminded": reminded}
