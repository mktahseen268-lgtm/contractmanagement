"""Security administration: roles, access, legal holds, temporary links, step-up.

One router because these are one screen's worth of concerns — who can do what, who can see
what, and what is being preserved. Splitting them would produce five routers that only ever
get opened together.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import access_control as ac
from .. import data_protection, legal_hold_service, models, schemas
from ..access_control import AccessDenied, StepUpRequired
from ..audit import record
from ..database import get_db
from ..deps import client_ip, get_current_user
from ..legal_hold_service import LegalHoldError

router = APIRouter(tags=["security"])


def _keep_failure_state(args: tuple) -> None:
    """Commit what the service deliberately wrote on its way to refusing.

    A refusal is not a no-op. `satisfy` increments the step-up attempt counter before it
    decides, and every refusal records an audit entry — both are written, then the exception
    unwinds the request and nothing commits them. That would mean failed attempts are never
    counted (so `STEP_UP_MAX_ATTEMPTS` is never reached and the challenge can be brute-forced)
    and refusals leave no trace in the audit log. Persisting first is the point of writing them.

    Safe because every caller below guards *before* it writes anything of its own, so the only
    pending state at this point is what the refusing service just put there.
    """
    db = args[0] if args else None
    if isinstance(db, Session):
        try:
            db.commit()
        except Exception:  # noqa: BLE001 — never let bookkeeping replace the real error
            db.rollback()


def _guard(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Map the control exceptions onto HTTP.

    `StepUpRequired` is a 401 carrying a challenge id, not a 403: the caller is not forbidden,
    they are being asked to prove who they are. A client that cannot tell those apart will
    show "access denied" to somebody who simply needs to re-enter their password.
    """
    try:
        return action(*args, **kwargs)
    except StepUpRequired as e:
        _keep_failure_state(args)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "step_up_required", "challenge_id": e.challenge_id,
                    "action": e.action},
        ) from e
    except AccessDenied as e:
        _keep_failure_state(args)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except LegalHoldError as e:
        _keep_failure_state(args)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


def _contract(db: Session, user: models.User, cid: str) -> models.Contract:
    c = db.get(models.Contract, cid)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


# ---------------------------------------------------------------------------------------
# Permissions and roles
# ---------------------------------------------------------------------------------------


@router.get("/permissions/me", response_model=schemas.MyPermissionsOut)
def my_permissions(db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.MyPermissionsOut:
    """What the signed-in user may do. Drives which controls the UI offers."""
    return schemas.MyPermissionsOut(
        role=user.role, permissions=sorted(ac.permissions_for(db, user)))


@router.get("/roles", response_model=schemas.RolesOut)
def list_roles(db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> schemas.RolesOut:
    _guard(ac.require, db, user, "role.manage")
    custom = db.scalars(select(models.CustomRole).where(
        models.CustomRole.tenant_id == user.tenant_id)
        .order_by(models.CustomRole.name.asc())).all()
    return schemas.RolesOut(
        builtin=[{"key": key, "name": key.title(),
                  "permissions": sorted(ac.ROLE_PERMISSIONS[key])}
                 for key in ac.BUILTIN_ROLES],
        custom=[schemas.CustomRoleOut.model_validate(r) for r in custom],
        permissions=sorted(ac.PERMISSIONS),
    )


@router.post("/roles", response_model=schemas.CustomRoleOut,
             status_code=status.HTTP_201_CREATED)
def create_role(data: schemas.CustomRoleIn, request: Request, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.CustomRoleOut:
    """Define a role. It always starts from a built-in, so an unrecognised role degrades to a
    known baseline rather than to no access."""
    _guard(ac.require, db, user, "role.manage")
    if data.base_role not in ac.ROLE_PERMISSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown base role '{data.base_role}'.")
    unknown = sorted(set(data.grants + data.revokes) - set(ac.PERMISSIONS))
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown permissions: {', '.join(unknown)}.")
    if db.scalar(select(models.CustomRole).where(
            models.CustomRole.tenant_id == user.tenant_id,
            models.CustomRole.key == data.key)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"A role '{data.key}' already exists.")

    role = models.CustomRole(tenant_id=user.tenant_id, created_by=user.id,
                             **data.model_dump())
    db.add(role)
    db.flush()
    record(db, tenant_id=user.tenant_id, action="role.created", actor=user,
           object_type="role", object_id=role.id, object_label=role.name,
           ip=client_ip(request),
           meta={"base": role.base_role, "grants": role.grants, "revokes": role.revokes})
    db.commit()
    db.refresh(role)
    return schemas.CustomRoleOut.model_validate(role)


@router.patch("/roles/{rid}", response_model=schemas.CustomRoleOut)
def update_role(rid: str, data: schemas.CustomRoleUpdateIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.CustomRoleOut:
    _guard(ac.require, db, user, "role.manage")
    role = db.get(models.CustomRole, rid)
    if role is None or role.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if value is not None:
            setattr(role, key, value)
    record(db, tenant_id=user.tenant_id, action="role.updated", actor=user,
           object_type="role", object_id=role.id, object_label=role.name,
           ip=client_ip(request), meta={"fields": list(payload.keys())})
    db.commit()
    db.refresh(role)
    return schemas.CustomRoleOut.model_validate(role)


# ---------------------------------------------------------------------------------------
# Step-up authentication
# ---------------------------------------------------------------------------------------


@router.post("/step-up/{challenge_id}", response_model=schemas.StepUpOut)
def satisfy_step_up(challenge_id: str, data: schemas.StepUpIn, request: Request,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.StepUpOut:
    """Answer a challenge. TOTP is preferred where the user has it — a password re-prompt only
    proves the password is known, which it already was when the session started."""
    challenge = db.get(models.StepUpChallenge, challenge_id)
    if challenge is None or challenge.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Challenge not found")
    _guard(ac.satisfy, db, challenge, user, password=data.password, totp=data.totp,
           ip=client_ip(request))
    db.commit()
    return schemas.StepUpOut(challenge_id=challenge.id, status=challenge.status,
                             method=challenge.method, action=challenge.action)


# ---------------------------------------------------------------------------------------
# Need-to-know access
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/access", response_model=list[schemas.ContractAccessOut])
def list_access(contract_id: str, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> list[schemas.ContractAccessOut]:
    contract = _contract(db, user, contract_id)
    _guard(ac.require_visible, db, user, contract, ip="")
    rows = db.scalars(select(models.ContractAccess).where(
        models.ContractAccess.tenant_id == user.tenant_id,
        models.ContractAccess.contract_id == contract.id)
        .order_by(desc(models.ContractAccess.created_at))).all()
    out = []
    for row in rows:
        item = schemas.ContractAccessOut.model_validate(row)
        if row.user_id:
            person = db.get(models.User, row.user_id)
            item.user_name = person.name if person else ""
        out.append(item)
    return out


@router.post("/contracts/{contract_id}/access", response_model=schemas.ContractAccessOut,
             status_code=status.HTTP_201_CREATED)
def grant_access(contract_id: str, data: schemas.GrantAccessIn, request: Request,
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.ContractAccessOut:
    """Add somebody to a confidential agreement's access list. Needs step-up."""
    contract = _contract(db, user, contract_id)
    _guard(ac.require, db, user, "access.grant")
    _guard(ac.consume, db, user, "access.granted", data.challenge_id,
           object_type="contract", object_id=contract.id)
    access = _guard(ac.grant, db, contract, actor=user, user_id=data.user_id or "",
                    role=data.role or "", level=data.level, reason=data.reason,
                    expires_at=data.expires_at, ip=client_ip(request))
    db.commit()
    db.refresh(access)
    return schemas.ContractAccessOut.model_validate(access)


@router.post("/contracts/{contract_id}/break-glass", response_model=dict)
def break_glass(contract_id: str, data: schemas.BreakGlassIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> dict:
    """Emergency access, loudly. Grants an hour and writes its own audit event."""
    contract = _contract(db, user, contract_id)
    _guard(ac.break_glass, db, contract, actor=user, reason=data.reason,
           ip=client_ip(request))
    db.commit()
    return {"granted": True, "expires_in_minutes": 60}


@router.patch("/contracts/{contract_id}/confidential", response_model=dict)
def set_confidential(contract_id: str, data: schemas.ConfidentialIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> dict:
    """Mark an agreement need-to-know, or release it."""
    contract = _contract(db, user, contract_id)
    _guard(ac.require, db, user, "access.grant")
    contract.confidential = data.confidential
    record(db, tenant_id=user.tenant_id,
           action="contract.confidential_set" if data.confidential
           else "contract.confidential_cleared",
           actor=user, object_type="contract", object_id=contract.id,
           object_label=contract.title, ip=client_ip(request),
           meta={"reason": data.reason[:300]})
    db.commit()
    return {"confidential": contract.confidential}


# ---------------------------------------------------------------------------------------
# Legal holds
# ---------------------------------------------------------------------------------------


@router.get("/legal-holds", response_model=list[schemas.LegalHoldOut])
def list_holds(include_released: bool = False, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> list[schemas.LegalHoldOut]:
    _guard(ac.require, db, user, "legalhold.manage")
    stmt = select(models.LegalHold).where(models.LegalHold.tenant_id == user.tenant_id)
    if not include_released:
        stmt = stmt.where(models.LegalHold.status == "active")
    rows = db.scalars(stmt.order_by(desc(models.LegalHold.placed_at))).all()
    return [schemas.LegalHoldOut.model_validate(r) for r in rows]


@router.post("/legal-holds", response_model=schemas.LegalHoldOut,
             status_code=status.HTTP_201_CREATED)
def place_hold(data: schemas.LegalHoldIn, request: Request, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> schemas.LegalHoldOut:
    """Place a hold. Blocks deletion, purge and archival for everything it covers."""
    _guard(ac.require, db, user, "legalhold.manage")
    hold = _guard(legal_hold_service.place, db, user.tenant_id, matter=data.matter,
                  contract_ids=data.contract_ids, actor=user, reason=data.reason,
                  reference=data.reference, custodian=data.custodian,
                  ip=client_ip(request))
    db.commit()
    db.refresh(hold)
    return schemas.LegalHoldOut.model_validate(hold)


@router.post("/legal-holds/{hid}/release", response_model=schemas.LegalHoldOut)
def release_hold(hid: str, data: schemas.ReleaseHoldIn, request: Request,
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> schemas.LegalHoldOut:
    """Release a matter. Needs step-up and a reason.

    Only clears an agreement's flag if no *other* active matter still covers it.
    """
    _guard(ac.require, db, user, "legalhold.manage")
    hold = db.get(models.LegalHold, hid)
    if hold is None or hold.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hold not found")
    _guard(ac.consume, db, user, "legalhold.released", data.challenge_id,
           object_type="legal_hold", object_id=hold.id)
    _guard(legal_hold_service.release, db, hold, actor=user, reason=data.reason,
           ip=client_ip(request))
    db.commit()
    db.refresh(hold)
    return schemas.LegalHoldOut.model_validate(hold)


@router.get("/legal-holds/{hid}/export", response_model=dict)
def export_hold(hid: str, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> dict:
    """Everything preserved under this matter, with audit chain positions so counsel can
    verify what they were given against the record it came from."""
    _guard(ac.require, db, user, "legalhold.manage")
    hold = db.get(models.LegalHold, hid)
    if hold is None or hold.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hold not found")
    export = legal_hold_service.export_set(db, hold)
    return {**export,
            "placed_at": export["placed_at"].isoformat() if export["placed_at"] else None,
            "released_at": export["released_at"].isoformat() if export["released_at"] else None}


# ---------------------------------------------------------------------------------------
# Temporary access
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/temporary-access",
            response_model=list[schemas.TemporaryAccessOut])
def list_temporary(contract_id: str, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> list[schemas.TemporaryAccessOut]:
    contract = _contract(db, user, contract_id)
    rows = db.scalars(select(models.TemporaryAccess).where(
        models.TemporaryAccess.tenant_id == user.tenant_id,
        models.TemporaryAccess.contract_id == contract.id)
        .order_by(desc(models.TemporaryAccess.created_at))).all()
    return [schemas.TemporaryAccessOut.model_validate(r) for r in rows]


@router.post("/contracts/{contract_id}/temporary-access",
             response_model=schemas.TemporaryAccessCreatedOut,
             status_code=status.HTTP_201_CREATED)
def create_temporary(contract_id: str, data: schemas.TemporaryAccessIn, request: Request,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.TemporaryAccessCreatedOut:
    """Issue a time-bound link for an external collaborator.

    The link is returned once. Only its hash is stored, so it cannot be shown again — and a
    link that leaks from a mailbox is not replayable out of the database.
    """
    contract = _contract(db, user, contract_id)
    _guard(ac.require, db, user, "access.grant")
    access, raw = _guard(ac.issue_temporary_access, db, contract, actor=user,
                         email=data.email, name=data.name,
                         organisation=data.organisation, scope=data.scope,
                         days=data.days, watermark=data.watermark,
                         allow_download=data.allow_download, ip=client_ip(request))
    db.commit()
    db.refresh(access)
    out = schemas.TemporaryAccessCreatedOut.model_validate(access)
    out.url = f"{request.base_url}room/{raw}".replace("//room", "/room")
    return out


@router.delete("/temporary-access/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_temporary(tid: str, request: Request, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> None:
    access = db.get(models.TemporaryAccess, tid)
    if access is None or access.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    _guard(ac.require, db, user, "access.grant")
    ac.revoke_temporary(db, access, actor=user, ip=client_ip(request))
    db.commit()


# ---------------------------------------------------------------------------------------
# Posture
# ---------------------------------------------------------------------------------------


@router.get("/security/posture", response_model=dict)
def security_posture(db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> dict:
    """What is switched on. Reports honestly, including what is *not* protected."""
    _guard(ac.require, db, user, "settings.manage")
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return {
        **data_protection.status(),
        "separation_of_duties": {
            "enabled": True,
            "rules": [{"first": a, "second": b, "reason": r} for a, b, r in ac.SEGREGATED],
        },
        "step_up": {
            "enabled": True,
            "actions": sorted(ac.STEP_UP_ACTIONS),
            "ttl_minutes": int(ac.STEP_UP_TTL.total_seconds() // 60),
        },
        "legal_holds": {
            "active": db.query(models.LegalHold).filter_by(
                tenant_id=user.tenant_id, status="active").count(),
        },
        "temporary_access": {
            "active": db.query(models.TemporaryAccess).filter(
                models.TemporaryAccess.tenant_id == user.tenant_id,
                models.TemporaryAccess.status == "active",
                models.TemporaryAccess.expires_at > now).count(),
        },
        "confidential_agreements": db.query(models.Contract).filter_by(
            tenant_id=user.tenant_id, confidential=True).count(),
    }


# ---------------------------------------------------------------------------------------
# FIDO2 / WebAuthn (Phase 8, item 1)
# ---------------------------------------------------------------------------------------


def _webauthn_guard(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    from ..webauthn_service import WebAuthnError

    try:
        return action(*args, **kwargs)
    except WebAuthnError as e:
        # Same reasoning as `_guard`: a refused assertion records why it was refused, and a
        # counter regression is the one clone signal WebAuthn gives us. Losing it because the
        # request failed would mean the attack that matters is the one nothing records.
        _keep_failure_state(args)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/passkeys", response_model=schemas.PasskeyStatusOut)
def list_passkeys(db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.PasskeyStatusOut:
    """The caller's registered passkeys."""
    from .. import webauthn_service

    return schemas.PasskeyStatusOut(**webauthn_service.status(db, user))


@router.post("/passkeys/register/begin", response_model=dict)
def begin_passkey_registration(db: Session = Depends(get_db),
                               user: models.User = Depends(get_current_user)) -> dict:
    """Options for `navigator.credentials.create()`."""
    from .. import webauthn_service

    return _webauthn_guard(webauthn_service.begin_registration, db, user)


@router.post("/passkeys/register/finish", response_model=schemas.PasskeyOut,
             status_code=status.HTTP_201_CREATED)
def finish_passkey_registration(data: schemas.PasskeyRegisterIn, request: Request,
                                db: Session = Depends(get_db),
                                user: models.User = Depends(get_current_user)) -> schemas.PasskeyOut:
    """Verify the attestation and store the credential."""
    from .. import webauthn_service

    row = _webauthn_guard(webauthn_service.finish_registration, db, user, data.credential,
                          label=data.label, ip=client_ip(request))
    db.commit()
    db.refresh(row)
    return schemas.PasskeyOut(
        id=row.id, label=row.label,
        transports=[t for t in (row.transports or "").split(",") if t],
        backed_up=row.backed_up, created_at=row.created_at, last_used_at=row.last_used_at)


@router.post("/passkeys/authenticate/begin", response_model=dict)
def begin_passkey_authentication(db: Session = Depends(get_db),
                                 user: models.User = Depends(get_current_user)) -> dict:
    """Options for `navigator.credentials.get()`.

    Used as a **step-up factor** for an already-signed-in user. Passwordless first-factor
    sign-in would need the challenge to be issued before anyone is identified, which is a
    different flow and is not implemented — saying so is better than half-building it.
    """
    from .. import webauthn_service

    return _webauthn_guard(webauthn_service.begin_authentication, db, user)


@router.post("/passkeys/authenticate/finish", response_model=dict)
def finish_passkey_authentication(data: schemas.PasskeyAuthenticateIn, request: Request,
                                  db: Session = Depends(get_db),
                                  user: models.User = Depends(get_current_user)) -> dict:
    """Verify an assertion. Refuses a counter that has not advanced — a cloned authenticator."""
    from .. import webauthn_service

    row = _webauthn_guard(webauthn_service.finish_authentication, db, user, data.credential,
                          ip=client_ip(request))
    db.commit()
    return {"verified": True, "label": row.label}


@router.patch("/passkeys/{pid}", response_model=schemas.PasskeyOut)
def rename_passkey(pid: str, data: schemas.PasskeyRenameIn, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.PasskeyOut:
    from .. import webauthn_service

    row = _webauthn_guard(webauthn_service.rename, db, user, pid, data.label)
    db.commit()
    db.refresh(row)
    return schemas.PasskeyOut(
        id=row.id, label=row.label,
        transports=[t for t in (row.transports or "").split(",") if t],
        backed_up=row.backed_up, created_at=row.created_at, last_used_at=row.last_used_at)


@router.delete("/passkeys/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def remove_passkey(pid: str, request: Request, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> None:
    """Delete a passkey. Refuses if it is the only way the account can sign in."""
    from .. import webauthn_service

    _webauthn_guard(webauthn_service.remove, db, user, pid, ip=client_ip(request))
    db.commit()
