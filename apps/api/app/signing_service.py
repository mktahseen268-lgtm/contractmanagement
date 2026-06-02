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

from sqlalchemy import select
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


def _email_recipient(recipient: models.SignatureRecipient, contract: models.Contract, sender_name: str, *, raw_token: str | None = None) -> None:
    """Email the signer their /sign/{token} URL. `raw_token` is the token returned by
    `_mint_token_for` at the call site; if omitted we decrypt from the stored ciphertext
    (used by reminders). Returns early without emailing if no live token exists."""
    token = raw_token or decrypt_token_for(recipient)
    if not token:
        return
    link = f"{settings.frontend_url.rstrip('/')}/sign/{token}"
    send_email(
        recipient.email,
        f"Please sign: {contract.title}",
        f"Hi {recipient.name},\n\n{sender_name} has asked you to sign \"{contract.title}\" ({contract.reference_no}).\n\nReview and sign here:\n{link}\n\nThis link is unique to you — please don't forward it.",
    )


# ---------- queries ----------


def current_envelope(db: Session, contract_id: str) -> models.SignatureEnvelope | None:
    """The latest non-voided envelope for the contract (draft/sent/partially_signed/completed/declined)."""
    return db.scalar(
        select(models.SignatureEnvelope).where(models.SignatureEnvelope.contract_id == contract_id, models.SignatureEnvelope.status != "voided").order_by(models.SignatureEnvelope.created_at.desc())
    )


def active_envelope(db: Session, contract_id: str) -> models.SignatureEnvelope | None:
    """An envelope that's out for signature (blocks plain status transitions)."""
    return db.scalar(
        select(models.SignatureEnvelope).where(models.SignatureEnvelope.contract_id == contract_id, models.SignatureEnvelope.status.in_(["sent", "partially_signed"])).order_by(models.SignatureEnvelope.created_at.desc())
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
        db.add(models.SignatureRecipient(
            tenant_id=contract.tenant_id, envelope_id=env.id, sequence=i,
            name=(r.name or "").strip()[:200], email=str(r.email).lower(),
            kind=("cc" if r.kind == "cc" else "signer"), status="created",
        ))
    _log(db, env, "created", recipient=None, meta={"recipients": len(recipients_in)})
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
                _email_recipient(r, contract, sender_name, raw_token=raw_tokens[r.id])
    else:
        # only the first signer is "sent"; others become "sent" when their turn comes. CC recipients are "sent" immediately.
        first_signer_seq = min(r.sequence for r in signers)
        for r in rs:
            if r.kind == "cc" or r.sequence == first_signer_seq:
                r.status = "sent"
                _log(db, envelope, "sent", recipient=r)
                if r.kind == "signer":
                    _email_recipient(r, contract, sender_name, raw_token=raw_tokens[r.id])
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


def sign(db: Session, *, envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient, contract: models.Contract, full_name: str, ip: str, ua: str, tab_fills: list | None = None, signature_kind: str = "typed", signature_image: str | None = None) -> models.SignatureEnvelope:
    if envelope.status not in ("sent", "partially_signed"):
        raise ValueError("This envelope is no longer open for signing.")
    if recipient.kind != "signer":
        raise ValueError("This recipient is a CC, not a signer.")
    if recipient.status in ("signed", "declined"):
        raise ValueError("You have already responded.")
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


def remind(db: Session, *, envelope: models.SignatureEnvelope, recipient: models.SignatureRecipient, contract: models.Contract, by_user: models.User) -> None:
    if envelope.status not in ("sent", "partially_signed") or recipient.status not in ("sent", "viewed"):
        raise ValueError("Nothing to remind about for this recipient.")
    _email_recipient(recipient, contract, by_user.name)
    _log(db, envelope, "reminder_sent", recipient=recipient, meta={"by": by_user.name})


def delete_envelopes_for_contract(db: Session, contract_id: str) -> None:
    env_ids = [e[0] for e in db.execute(select(models.SignatureEnvelope.id).where(models.SignatureEnvelope.contract_id == contract_id)).all()]
    if env_ids:
        db.query(models.SignatureTab).filter(models.SignatureTab.envelope_id.in_(env_ids)).delete(synchronize_session=False)
        db.query(models.SignatureEvent).filter(models.SignatureEvent.envelope_id.in_(env_ids)).delete(synchronize_session=False)
        db.query(models.SignatureRecipient).filter(models.SignatureRecipient.envelope_id.in_(env_ids)).delete(synchronize_session=False)
        db.query(models.SignatureEnvelope).filter(models.SignatureEnvelope.contract_id == contract_id).delete(synchronize_session=False)
