"""Signatory authority matrix + execution-reliability surface (Phase 2).

Two related things live here because they answer the same operational question — *did this get
signed by the right people, and did it actually work?*

  /authority/rules        the delegation-of-authority matrix (RFP §4a(ii) 4.1-4.2)
  /authority/proposal     what the matrix says for a given contract, shown when preparing
  /authority/check        validate a chosen signatory set before sending
  /authority/seal-failures the dead-letter view: envelopes whose document did not seal
                          cleanly (§4.4 — you cannot claim "free from signature failures"
                          without somewhere that shows the failures)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authority_service, models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/authority", tags=["authority"])

_ADMIN_ROLES = {"owner", "admin"}


def _require_admin(user: models.User) -> models.User:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can change the authority matrix.",
        )
    return user


def _owned_contract(db: Session, user: models.User, contract_id: str) -> models.Contract:
    c = db.get(models.Contract, contract_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


def _out(db: Session, rule: models.SignatoryAuthority) -> schemas.SignatoryAuthorityOut:
    item = schemas.SignatoryAuthorityOut.model_validate(rule)
    if rule.required_user_id:
        u = db.get(models.User, rule.required_user_id)
        item.required_user_name = u.name if u is not None else ""
    return item


# ---------------------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------------------


@router.get("/rules", response_model=list[schemas.SignatoryAuthorityOut])
def list_rules(db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> list[schemas.SignatoryAuthorityOut]:
    rows = db.scalars(
        select(models.SignatoryAuthority)
        .where(models.SignatoryAuthority.tenant_id == user.tenant_id)
        .order_by(models.SignatoryAuthority.priority.desc(), models.SignatoryAuthority.name.asc())
    ).all()
    return [_out(db, r) for r in rows]


@router.post("/rules", response_model=schemas.SignatoryAuthorityOut,
             status_code=status.HTTP_201_CREATED)
def create_rule(data: schemas.SignatoryAuthorityIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.SignatoryAuthorityOut:
    _require_admin(user)
    rule = authority_service.upsert(db, user.tenant_id, data.model_dump(), actor=user)
    db.commit()
    return _out(db, rule)


@router.patch("/rules/{rule_id}", response_model=schemas.SignatoryAuthorityOut)
def update_rule(rule_id: str, data: schemas.SignatoryAuthorityIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.SignatoryAuthorityOut:
    _require_admin(user)
    existing = db.get(models.SignatoryAuthority, rule_id)
    if existing is None or existing.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    rule = authority_service.upsert(db, user.tenant_id, data.model_dump(), actor=user, rule_id=rule_id)
    db.commit()
    return _out(db, rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, request: Request, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> Response:
    _require_admin(user)
    rule = db.get(models.SignatoryAuthority, rule_id)
    if rule is None or rule.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    # Deactivated rather than deleted: an auditor reviewing a past execution needs to see the
    # rule that was in force at the time, not a gap where it used to be.
    authority_service.upsert(db, user.tenant_id, {"is_active": False}, actor=user, rule_id=rule_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------
# Applying the matrix
# ---------------------------------------------------------------------------------------


@router.get("/proposal/{contract_id}", response_model=schemas.AuthorityProposalOut)
def proposal(contract_id: str, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)) -> schemas.AuthorityProposalOut:
    """Who the matrix requires for this contract. Called when preparing an envelope so the
    signatory list starts correct rather than being corrected afterwards."""
    contract = _owned_contract(db, user, contract_id)
    return schemas.AuthorityProposalOut(**authority_service.propose(db, contract))


@router.post("/check/{contract_id}", response_model=schemas.AuthorityCheckOut)
def check(contract_id: str, data: schemas.AuthorityCheckIn, db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)) -> schemas.AuthorityCheckOut:
    """Validate a chosen signatory set. Non-blocking — it reports deviations so the UI can ask
    for an override reason before sending."""
    contract = _owned_contract(db, user, contract_id)
    result = authority_service.check_selection(db, contract, data.signer_user_ids)
    return schemas.AuthorityCheckOut(
        compliant=result["compliant"], rule_id=result["rule_id"], rule_name=result["rule_name"],
        deviations=result["deviations"], matrix_silent=result["matrix_silent"],
    )


# ---------------------------------------------------------------------------------------
# Execution reliability
# ---------------------------------------------------------------------------------------


@router.get("/seal-failures", response_model=list[schemas.SealFailureOut])
def seal_failures(include_partial: bool = Query(True), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> list[schemas.SealFailureOut]:
    """Envelopes whose executed document did not seal cleanly.

    `partial` means the PDF exists but at least one signatory's cryptographic signature
    failed — visible by default, because a document that looks executed but is missing a
    signature is worse than one that obviously failed.
    """
    statuses = ["failed", "partial"] if include_partial else ["failed"]
    rows = db.scalars(
        select(models.SignatureEnvelope)
        .where(
            models.SignatureEnvelope.tenant_id == user.tenant_id,
            models.SignatureEnvelope.seal_status.in_(statuses),
        )
        .order_by(models.SignatureEnvelope.seal_last_attempt_at.desc())
        .limit(200)
    ).all()

    out: list[schemas.SealFailureOut] = []
    for env in rows:
        contract = db.get(models.Contract, env.contract_id)
        out.append(schemas.SealFailureOut(
            envelope_id=env.id, contract_id=env.contract_id,
            contract_reference=contract.reference_no if contract else "",
            contract_title=contract.title if contract else "",
            seal_status=env.seal_status, seal_attempts=env.seal_attempts or 0,
            seal_error=env.seal_error or "", seal_last_attempt_at=env.seal_last_attempt_at,
            completed_at=env.completed_at,
        ))
    return out


@router.post("/seal-failures/{envelope_id}/retry", response_model=dict)
def retry_seal(envelope_id: str, request: Request, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> dict:
    """Re-run sealing for an envelope that failed. Idempotent — sealing rebuilds the executed
    PDF from the recipients and tabs, so a retry after a transient fault is safe."""
    _require_admin(user)
    env = db.get(models.SignatureEnvelope, envelope_id)
    if env is None or env.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    if env.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Envelope is {env.status}; only a completed envelope can be sealed.",
        )

    from ..audit import record
    from ..deps import client_ip

    record(db, tenant_id=user.tenant_id, action="signature.seal_retried", actor=user,
           object_type="contract", object_id=env.contract_id, object_label=env.id,
           ip=client_ip(request),
           meta={"envelope_id": env.id, "previous_status": env.seal_status,
                 "previous_error": env.seal_error, "attempts": env.seal_attempts})
    db.commit()

    from ..tasks import seal_envelope

    seal_envelope.delay(env.id, env.tenant_id)
    return {"ok": True, "envelope_id": env.id, "queued": True}


@router.get("/envelopes/{envelope_id}/signatures", response_model=list[schemas.SigningReceiptOut])
def envelope_signatures(envelope_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> list[schemas.SigningReceiptOut]:
    """The cryptographic signatures applied to an executed document, each naming the
    certificate serial that produced it."""
    env = db.get(models.SignatureEnvelope, envelope_id)
    if env is None or env.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    events = db.scalars(
        select(models.SignatureEvent)
        .where(
            models.SignatureEvent.envelope_id == env.id,
            models.SignatureEvent.event.in_(("crypto_signed", "crypto_sign_failed")),
        )
        .order_by(models.SignatureEvent.at.asc())
    ).all()
    return [
        schemas.SigningReceiptOut(
            recipient_id=e.recipient_id, recipient_name=e.recipient_name,
            certificate_serial=(e.meta or {}).get("certificate_serial", ""),
            subject_dn=(e.meta or {}).get("subject_dn", ""),
            field_name=(e.meta or {}).get("field_name", ""),
            algorithm=(e.meta or {}).get("algorithm", ""),
            ok=bool((e.meta or {}).get("ok", e.event == "crypto_signed")),
            error=(e.meta or {}).get("error", ""),
        )
        for e in events
    ]
