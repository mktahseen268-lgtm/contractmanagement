from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from .. import signing_service as sig
from ..audit import record
from ..config import settings
from ..database import get_db, set_request_tenant
from ..deps import client_ip, get_current_user
from ..storage import get_storage

router = APIRouter(tags=["signatures"])

_EDIT_ROLES = {"owner", "admin", "manager", "author"}
_MAX_RECIPIENTS = 10


# ---------- helpers ----------


def _get_owned_contract(db: Session, user: models.User, contract_id: str) -> models.Contract:
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


def _get_owned_envelope(db: Session, user: models.User, envelope_id: str) -> models.SignatureEnvelope:
    e = db.get(models.SignatureEnvelope, envelope_id)
    if e is None or e.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature envelope not found")
    return e


def _envelope_out(db: Session, envelope: models.SignatureEnvelope, *, include_links: bool) -> schemas.EnvelopeOut:
    rs = sig.recipients(db, envelope.id)
    rec_out = []
    for r in rs:
        # The raw signing URL is only available when we can decrypt the stored secret AND the
        # token hasn't expired. include_links=False (audit views, list views) always omits.
        link: str | None = None
        if include_links and r.access_token_hash:
            raw = sig.decrypt_token_for(r)
            if raw:
                link = f"/sign/{raw}"
        rec_out.append(schemas.RecipientOut(
            id=r.id, sequence=r.sequence, name=r.name, email=r.email, kind=r.kind, status=r.status,
            signed_name=r.signed_name, signed_at=r.signed_at, declined_reason=r.declined_reason, ip=r.ip,
            signing_link=link,
        ))
    tabs = db.scalars(
        select(models.SignatureTab).where(models.SignatureTab.envelope_id == envelope.id).order_by(models.SignatureTab.page, models.SignatureTab.y, models.SignatureTab.x)
    ).all()
    tab_out = [schemas.SignatureTabOut.model_validate(t) for t in tabs]
    return schemas.EnvelopeOut(
        id=envelope.id, contract_id=envelope.contract_id, status=envelope.status, signing_order=envelope.signing_order,
        message=envelope.message, document_file_id=envelope.document_file_id, sealed_pdf_file_id=envelope.sealed_pdf_file_id,
        certificate_file_id=envelope.certificate_file_id, created_by=envelope.created_by, created_at=envelope.created_at,
        sent_at=envelope.sent_at, completed_at=envelope.completed_at, recipients=rec_out, tabs=tab_out,
    )


def _stream(db: Session, file_id: str | None, not_found_msg: str) -> StreamingResponse:
    fo = db.get(models.FileObject, file_id) if file_id else None
    if fo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_msg)
    stream = get_storage().open_stream(fo.key)

    def _iter():
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(_iter(), media_type=fo.content_type, headers={"Content-Disposition": f'inline; filename="{fo.original_name}"'})


# ---------- contract: prepare / get ----------


@router.post("/contracts/{contract_id}/prepare-signature", response_model=schemas.EnvelopeOut, status_code=status.HTTP_201_CREATED)
def prepare_signature(contract_id: str, data: schemas.PrepareSignatureIn, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.EnvelopeOut:
    c = _get_owned_contract(db, user, contract_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to prepare contracts for signature.")
    if c.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A contract must be 'approved' before it can be sent for signature (this one is '{c.status}').")
    if len(data.recipients) > _MAX_RECIPIENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"At most {_MAX_RECIPIENTS} recipients.")
    existing = sig.current_envelope(db, c.id)
    if existing is not None:
        if existing.status in ("sent", "partially_signed"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This contract is already out for signature — void that envelope first.")
        if existing.status == "completed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This contract has already been executed.")
        if existing.status == "draft":
            # replace the draft
            db.query(models.SignatureTab).filter(models.SignatureTab.envelope_id == existing.id).delete(synchronize_session=False)
            db.query(models.SignatureEvent).filter(models.SignatureEvent.envelope_id == existing.id).delete(synchronize_session=False)
            db.query(models.SignatureRecipient).filter(models.SignatureRecipient.envelope_id == existing.id).delete(synchronize_session=False)
            db.delete(existing)
            db.flush()
    try:
        env = sig.create_envelope(db, contract=c, recipients_in=data.recipients, message=data.message, signing_order=data.signing_order, by_user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    record(db, tenant_id=user.tenant_id, action="contract.signature_prepared", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"envelope_id": env.id, "recipients": len(data.recipients)})
    db.commit()
    db.refresh(env)
    return _envelope_out(db, env, include_links=True)


@router.get("/contracts/{contract_id}/signature", response_model=schemas.EnvelopeOut | None)
def get_signature(contract_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.EnvelopeOut | None:
    _get_owned_contract(db, user, contract_id)
    env = sig.current_envelope(db, contract_id)
    return _envelope_out(db, env, include_links=True) if env is not None else None


# ---------- envelope: send / void / remind / files ----------


@router.post("/envelopes/{envelope_id}/send", response_model=schemas.EnvelopeOut)
def send_envelope(envelope_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.EnvelopeOut:
    env = _get_owned_envelope(db, user, envelope_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to send for signature.")
    c = _get_owned_contract(db, user, env.contract_id)
    tenant = db.get(models.Tenant, user.tenant_id)
    org = (tenant.name if tenant else "Workspace") or "Workspace"
    try:
        sig.send_envelope(db, envelope=env, contract=c, by_user=user, org_name=org)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    record(db, tenant_id=user.tenant_id, action="contract.sent_for_signature", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"envelope_id": env.id})
    db.commit()
    db.refresh(env)
    return _envelope_out(db, env, include_links=True)


@router.post("/envelopes/{envelope_id}/void", response_model=schemas.EnvelopeOut)
def void_envelope(envelope_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.EnvelopeOut:
    env = _get_owned_envelope(db, user, envelope_id)
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to void this envelope.")
    c = _get_owned_contract(db, user, env.contract_id)
    try:
        sig.void_envelope(db, envelope=env, contract=c, by_user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    record(db, tenant_id=user.tenant_id, action="contract.signature_voided", actor=user, object_type="contract", object_id=c.id, object_label=c.title, ip=client_ip(request), meta={"envelope_id": env.id})
    db.commit()
    db.refresh(env)
    return _envelope_out(db, env, include_links=True)


@router.post("/envelopes/{envelope_id}/recipients/{recipient_id}/remind")
def remind_recipient(envelope_id: str, recipient_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> dict:
    env = _get_owned_envelope(db, user, envelope_id)
    r = db.get(models.SignatureRecipient, recipient_id)
    if r is None or r.envelope_id != env.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    c = _get_owned_contract(db, user, env.contract_id)
    try:
        sig.remind(db, envelope=env, recipient=r, contract=c, by_user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    return {"ok": True}


@router.get("/envelopes/{envelope_id}/document")
def envelope_document(envelope_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> StreamingResponse:
    env = _get_owned_envelope(db, user, envelope_id)
    return _stream(db, env.sealed_pdf_file_id or env.document_file_id, "No document for this envelope yet.")


@router.get("/envelopes/{envelope_id}/signed-pdf")
def envelope_signed_pdf(envelope_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> StreamingResponse:
    env = _get_owned_envelope(db, user, envelope_id)
    return _stream(db, env.sealed_pdf_file_id, "The executed PDF isn't ready yet (the envelope must be fully signed).")


@router.get("/envelopes/{envelope_id}/certificate")
def envelope_certificate(envelope_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> StreamingResponse:
    env = _get_owned_envelope(db, user, envelope_id)
    return _stream(db, env.certificate_file_id, "The certificate of completion isn't ready yet.")


# ---------- tabs (placeable fields on the PDF, per recipient) ----------


_TAB_KINDS = {"signature", "initials", "date", "text", "checkbox"}


def _clamp01(v: float, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


@router.post("/envelopes/{envelope_id}/tabs", response_model=schemas.SignatureTabOut, status_code=status.HTTP_201_CREATED)
def add_tab(envelope_id: str, data: schemas.SignatureTabIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.SignatureTabOut:
    env = _get_owned_envelope(db, user, envelope_id)
    if env.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tabs can only be edited while the envelope is a draft.")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to place tabs.")
    r = db.get(models.SignatureRecipient, data.recipient_id)
    if r is None or r.envelope_id != env.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recipient is not part of this envelope.")
    if data.kind not in _TAB_KINDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tab kind must be one of: {sorted(_TAB_KINDS)}")
    if r.kind == "cc" and data.kind in {"signature", "initials"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CC recipients can't be assigned signature/initials tabs.")
    tab = models.SignatureTab(
        tenant_id=env.tenant_id, envelope_id=env.id, recipient_id=r.id,
        kind=data.kind, page=max(1, int(data.page)),
        x=_clamp01(data.x, 0.5), y=_clamp01(data.y, 0.5),
        width=_clamp01(data.width, 0.25), height=_clamp01(data.height, 0.05),
        required=bool(data.required), label=(data.label or "")[:120],
    )
    db.add(tab)
    db.commit()
    db.refresh(tab)
    return schemas.SignatureTabOut.model_validate(tab)


@router.patch("/envelopes/{envelope_id}/tabs/{tab_id}", response_model=schemas.SignatureTabOut)
def update_tab(envelope_id: str, tab_id: str, data: schemas.SignatureTabUpdateIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.SignatureTabOut:
    env = _get_owned_envelope(db, user, envelope_id)
    tab = db.get(models.SignatureTab, tab_id)
    if tab is None or tab.envelope_id != env.id or tab.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tab not found")
    if env.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tabs can only be edited while the envelope is a draft.")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit tabs.")
    payload = data.model_dump(exclude_unset=True)
    if "kind" in payload and payload["kind"] is not None:
        if payload["kind"] not in _TAB_KINDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tab kind must be one of: {sorted(_TAB_KINDS)}")
        tab.kind = payload["kind"]
    if "page" in payload and payload["page"] is not None:
        tab.page = max(1, int(payload["page"]))
    for fld in ("x", "y", "width", "height"):
        if fld in payload and payload[fld] is not None:
            setattr(tab, fld, _clamp01(payload[fld], getattr(tab, fld)))
    if "required" in payload and payload["required"] is not None:
        tab.required = bool(payload["required"])
    if "label" in payload and payload["label"] is not None:
        tab.label = (payload["label"] or "")[:120]
    db.commit()
    db.refresh(tab)
    return schemas.SignatureTabOut.model_validate(tab)


@router.delete("/envelopes/{envelope_id}/tabs/{tab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tab(envelope_id: str, tab_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> None:
    env = _get_owned_envelope(db, user, envelope_id)
    tab = db.get(models.SignatureTab, tab_id)
    if tab is None or tab.envelope_id != env.id or tab.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tab not found")
    if env.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tabs can only be edited while the envelope is a draft.")
    if user.role not in _EDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete tabs.")
    db.delete(tab)
    db.commit()


# ---------- token-authenticated signing (no account) ----------


def _signing_info(db: Session, recipient: models.SignatureRecipient | None) -> schemas.SigningInfoOut:
    if recipient is None or not recipient.access_token_hash:
        return schemas.SigningInfoOut(valid=False, reason="not_found")
    set_request_tenant(recipient.tenant_id)  # scope subsequent queries
    env = db.get(models.SignatureEnvelope, recipient.envelope_id)
    if env is None:
        return schemas.SigningInfoOut(valid=False, reason="not_found")
    if env.status == "voided":
        return schemas.SigningInfoOut(valid=False, reason="revoked")
    c = db.get(models.Contract, env.contract_id)
    tenant = db.get(models.Tenant, recipient.tenant_id)
    sender = db.get(models.User, env.created_by)
    rs = sig.recipients(db, env.id)
    can_sign = (
        env.status in ("sent", "partially_signed")
        and recipient.kind == "signer"
        and recipient.status in ("sent", "viewed")
        and sig.is_recipients_turn(env, recipient, rs)
    )
    waiting = ""
    if not can_sign:
        if recipient.kind == "cc":
            waiting = "You're on the CC list — you can review the document but don't need to sign."
        elif recipient.status == "signed":
            waiting = "You've already signed."
        elif recipient.status == "declined":
            waiting = "You declined to sign."
        elif env.status == "completed":
            waiting = "This envelope is fully executed."
        elif env.status == "declined":
            waiting = "Another signer declined, so this envelope is closed."
        elif env.status == "draft":
            waiting = "This request hasn't been sent yet."
        else:
            waiting = "It's not your turn to sign yet — an earlier signer hasn't signed."
    my_tabs = list(db.scalars(
        select(models.SignatureTab).where(
            models.SignatureTab.envelope_id == env.id,
            models.SignatureTab.recipient_id == recipient.id,
        ).order_by(models.SignatureTab.page, models.SignatureTab.y, models.SignatureTab.x)
    ).all())
    # Reuse the same raw token the caller arrived with (the `_signing_info` callers carry it
    # in `request.path_params['token']`). We decrypt our stored copy so the document URL is
    # self-contained and matches the URL the recipient is currently visiting.
    raw_token = sig.decrypt_token_for(recipient)
    doc_path = f"/sign/{raw_token}/document" if raw_token else ""
    return schemas.SigningInfoOut(
        valid=True,
        org_name=(tenant.name if tenant else "") or "",
        contract_title=(c.title if c else "") or "",
        contract_reference=(c.reference_no if c else "") or "",
        sender_name=(sender.name if sender else "") or "",
        message=env.message,
        recipient_name=recipient.name,
        recipient_email=recipient.email,
        recipient_status=recipient.status,
        can_sign=can_sign,
        waiting_reason=waiting,
        document_path=doc_path,
        tabs=[schemas.SignatureTabOut.model_validate(t) for t in my_tabs],
        consent_text=sig.CONSENT_TEXT,
        envelope_status=env.status,
    )


@router.get("/sign/{token}", response_model=schemas.SigningInfoOut)
def signing_info(token: str, db: Session = Depends(get_db)) -> schemas.SigningInfoOut:
    return _signing_info(db, sig.recipient_by_token(db, token))


@router.post("/sign/{token}/view", response_model=schemas.SigningInfoOut)
def signing_view(token: str, request: Request, db: Session = Depends(get_db)) -> schemas.SigningInfoOut:
    r = sig.recipient_by_token(db, token)
    if r and r.access_token_hash:
        set_request_tenant(r.tenant_id)
        env = db.get(models.SignatureEnvelope, r.envelope_id)
        if env is not None and env.status != "voided":
            sig.mark_viewed(db, r, env, ip=client_ip(request), ua=request.headers.get("user-agent", ""))
            db.commit()
    return _signing_info(db, sig.recipient_by_token(db, token))


@router.post("/sign/{token}/sign", response_model=schemas.SigningInfoOut)
def signing_sign(token: str, data: schemas.SignIn, request: Request, db: Session = Depends(get_db)) -> schemas.SigningInfoOut:
    r = sig.recipient_by_token(db, token)
    if r is None or not r.access_token_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This signing link is no longer active.")
    if not data.consent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You must agree to use electronic records and signatures to sign.")
    set_request_tenant(r.tenant_id)
    env = db.get(models.SignatureEnvelope, r.envelope_id)
    if env is None or env.status == "voided":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This signing link is no longer active.")
    c = db.get(models.Contract, env.contract_id)
    try:
        sig.sign(db, envelope=env, recipient=r, contract=c, full_name=data.full_name, ip=client_ip(request), ua=request.headers.get("user-agent", ""), tab_fills=data.tab_fills, signature_kind=data.signature_kind, signature_image=data.signature_image)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    # fire webhooks: per-signature + envelope.completed when applicable
    try:
        from .. import webhook_service

        webhook_service.dispatch(
            db, tenant_id=env.tenant_id, event="envelope.signed",
            data={"envelope_id": env.id, "contract_id": c.id, "reference_no": c.reference_no, "recipient": {"id": r.id, "name": r.name, "email": r.email}, "envelope_status": env.status},
        )
        if env.status == "completed":
            webhook_service.dispatch(db, tenant_id=env.tenant_id, event="envelope.completed", data={"envelope_id": env.id, "contract_id": c.id, "reference_no": c.reference_no})
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    if env.status == "completed":
        # render the executed PDF + certificate of completion (in its own session, so commit first)
        from ..tasks import seal_envelope

        seal_envelope.delay(env.id, env.tenant_id)
    return _signing_info(db, sig.recipient_by_token(db, token))


@router.post("/sign/{token}/decline", response_model=schemas.SigningInfoOut)
def signing_decline(token: str, data: schemas.DeclineIn, request: Request, db: Session = Depends(get_db)) -> schemas.SigningInfoOut:
    r = sig.recipient_by_token(db, token)
    if r is None or not r.access_token_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This signing link is no longer active.")
    set_request_tenant(r.tenant_id)
    env = db.get(models.SignatureEnvelope, r.envelope_id)
    if env is None or env.status == "voided":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This signing link is no longer active.")
    c = db.get(models.Contract, env.contract_id)
    try:
        sig.decline(db, envelope=env, recipient=r, contract=c, reason=data.reason, ip=client_ip(request), ua=request.headers.get("user-agent", ""))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    return _signing_info(db, sig.recipient_by_token(db, token))


@router.get("/sign/{token}/document")
def signing_document(token: str, db: Session = Depends(get_db)) -> StreamingResponse:
    r = sig.recipient_by_token(db, token)
    if r is None or not r.access_token_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This signing link is no longer active.")
    set_request_tenant(r.tenant_id)
    env = db.get(models.SignatureEnvelope, r.envelope_id)
    if env is None or env.status == "voided":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No document available.")
    return _stream(db, env.sealed_pdf_file_id if env.status == "completed" else env.document_file_id, "No document available yet.")
