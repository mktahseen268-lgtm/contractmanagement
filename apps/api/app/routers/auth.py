import datetime as dt
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth_service as svc
from .. import metrics
from .. import models, schemas, security
from ..audit import record
from ..config import settings
from ..database import get_db, set_request_tenant
from ..deps import client_ip, current_session_id, get_current_user
from ..email import send_email

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- helpers ----------


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return base[:40]


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug, i = base, 2
    while db.scalar(select(models.Tenant).where(models.Tenant.slug == slug)) is not None:
        slug, i = f"{base}-{i}", i + 1
    return slug


def _auth_response(db: Session, response: Response, user: models.User, tenant: models.Tenant, request: Request) -> schemas.AuthOut:
    raw, sid = svc.create_session(db, user, request)
    svc.set_refresh_cookie(response, raw)
    return schemas.AuthOut(
        access_token=security.create_access_token(user.id, tenant.id, user.role, sid),
        expires_in=settings.access_token_expire_minutes * 60,
        user=schemas.UserOut.model_validate(user),
        tenant=schemas.TenantOut.model_validate(tenant),
    )


def _user_from_mfa_token(db: Session, mfa_token: str) -> models.User:
    try:
        payload = security.decode_token(mfa_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your sign-in session expired — please start over.")
    if payload.get("type") != "mfa_pending":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    set_request_tenant(payload.get("tid"))
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.is_active or user.tenant_id != payload.get("tid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found.")
    return user


# ---------- register / login / MFA / refresh / logout ----------


@router.post("/register", response_model=schemas.AuthOut, status_code=status.HTTP_201_CREATED)
def register(data: schemas.RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> schemas.AuthOut:
    email = data.email.lower()
    if db.scalar(select(models.User).where(func.lower(models.User.email) == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    pw_errors = security.validate_password_strength(data.password, email=email, name=data.name)
    if pw_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=" ".join(pw_errors))
    tenant_id = uuid.uuid4().hex
    set_request_tenant(tenant_id)
    tenant = models.Tenant(id=tenant_id, name=data.workspace_name, slug=_unique_slug(db, data.workspace_name))
    db.add(tenant)
    db.flush()
    user = models.User(tenant_id=tenant_id, email=email, name=data.name, password_hash=security.hash_password(data.password), role="owner")
    db.add(user)
    db.flush()
    record(db, tenant_id=tenant_id, action="tenant.created", actor=user, object_type="tenant", object_id=tenant_id, object_label=tenant.name)
    record(db, tenant_id=tenant_id, action="user.registered", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    out = _auth_response(db, response, user, tenant, request)
    db.commit()
    return out


@router.post("/login", response_model=None)
def login(data: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = data.email.lower()
    user = db.scalar(select(models.User).where(func.lower(models.User.email) == email))

    # 1) Lockout check (before checking password — short-circuit constant-time wise it's fine
    #    because the attacker already knows the email exists; the lockout is the deterrent).
    if user is not None:
        set_request_tenant(user.tenant_id)
        locked, until = svc.is_locked_out(db, user)
        if locked:
            record(db, tenant_id=user.tenant_id, action="auth.login.locked", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
            metrics.record_login("locked")
            db.commit()
            retry_after = max(1, int((until - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)).total_seconds()))
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"This account is temporarily locked due to too many failed sign-in attempts. Try again in about {retry_after // 60 + 1} minute(s).",
                headers={"Retry-After": str(retry_after)},
            )

    # 2) Credentials check
    if user is None or not user.is_active or not security.verify_password(data.password, user.password_hash):
        reason = "unknown_user" if user is None else ("inactive" if not user.is_active else "bad_password")
        if user is not None:
            svc.record_failed_login(db, user=user, email=email, reason=reason, request=request)
            record(db, tenant_id=user.tenant_id, action="auth.login.failed", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request), meta={"reason": reason})
        else:
            # don't link to a real user — but still keep the audit trail (unknown-email attempts)
            db.add(models.LoginAttempt(
                tenant_id="", user_id=None, email=email, success=False, reason=reason,
                ip=client_ip(request), user_agent=(request.headers.get("user-agent", "") or "")[:400], at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            ))
        metrics.record_login("failed")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    # 3) Successful primary auth
    if user.mfa_enabled:
        record(db, tenant_id=user.tenant_id, action="auth.mfa_challenge", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
        metrics.record_login("mfa_challenge")
        db.commit()
        return schemas.MfaChallengeOut(mfa_token=security.create_mfa_token(user.id, user.tenant_id))
    svc.record_successful_login(db, user=user, request=request)
    tenant = db.get(models.Tenant, user.tenant_id)
    record(db, tenant_id=user.tenant_id, action="auth.login.success", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    metrics.record_login("success")
    out = _auth_response(db, response, user, tenant, request)
    db.commit()
    return out


@router.post("/mfa/verify", response_model=schemas.AuthOut)
def mfa_verify(data: schemas.MfaVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)) -> schemas.AuthOut:
    user = _user_from_mfa_token(db, data.mfa_token)
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is not enabled for this account.")
    method = None
    if svc.verify_totp(user.mfa_secret, data.code):
        method = "totp"
    elif svc.verify_otp(db, user, data.code, "login_2fa"):
        method = "email_otp"
    elif svc.consume_recovery_code(db, user, data.code):
        method = "recovery"
    if method is None:
        record(db, tenant_id=user.tenant_id, action="auth.mfa_failed", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code didn't work — check your authenticator app or use a recovery code.")
    tenant = db.get(models.Tenant, user.tenant_id)
    record(db, tenant_id=user.tenant_id, action="auth.login", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request), meta={"mfa": method})
    out = _auth_response(db, response, user, tenant, request)
    db.commit()
    return out


@router.post("/otp/send", response_model=schemas.OtpSendOut)
def otp_send(data: schemas.OtpSendIn, request: Request, db: Session = Depends(get_db)) -> schemas.OtpSendOut:
    user = _user_from_mfa_token(db, data.mfa_token)
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is not enabled for this account.")
    code = svc.issue_otp(db, user, "login_2fa")
    send_email(user.email, "Your sign-in code", f"Your one-time sign-in code is: {code}\n\nIt expires in {settings.otp_expire_minutes} minutes. If you didn't try to sign in, ignore this email.")
    record(db, tenant_id=user.tenant_id, action="auth.otp_sent", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    db.commit()
    return schemas.OtpSendOut(sent=True, dev_code=code if settings.is_dev else None)


@router.post("/refresh", response_model=schemas.TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> schemas.TokenOut:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active session.")
    s = svc.get_session_by_raw(db, raw)
    if s is not None:
        set_request_tenant(s.tenant_id)
    status_, new, new_raw = svc.rotate_session(db, raw, request)
    if status_ != "ok" or new is None or new_raw is None:
        svc.clear_refresh_cookie(response)
        if status_ == "reuse":
            db.commit()  # persist the chain revocation
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Suspicious activity detected — all sessions for this account were signed out. Please sign in again.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired — please sign in again.")
    user = db.get(models.User, new.user_id)
    if user is None or not user.is_active:
        svc.clear_refresh_cookie(response)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is no longer active.")
    svc.set_refresh_cookie(response, new_raw)
    db.commit()
    return schemas.TokenOut(
        access_token=security.create_access_token(user.id, user.tenant_id, user.role, new.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if raw:
        s = svc.get_session_by_raw(db, raw)
        if s is not None:
            set_request_tenant(s.tenant_id)
        svc.revoke_session_by_raw(db, raw, "logout")
        db.commit()
    svc.clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> schemas.MeOut:
    tenant = db.get(models.Tenant, user.tenant_id)
    return schemas.MeOut(user=schemas.UserOut.model_validate(user), tenant=schemas.TenantOut.model_validate(tenant))


# ---------- password ----------


@router.post("/change-password")
def change_password(
    data: schemas.ChangePasswordIn,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    sid: str | None = Depends(current_session_id),
) -> dict:
    if not security.verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is incorrect.")
    if security.verify_password(data.new_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a different password from your current one.")
    pw_errors = security.validate_password_strength(data.new_password, email=user.email, name=user.name)
    if pw_errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=" ".join(pw_errors))
    user.password_hash = security.hash_password(data.new_password)
    revoked = svc.revoke_all_user_sessions(db, user.id, "password_change", except_session_id=sid)
    record(db, tenant_id=user.tenant_id, action="auth.password_changed", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request), meta={"revoked_other_sessions": revoked})
    db.commit()
    return {"ok": True, "revoked_other_sessions": revoked}


# ---------- sessions ----------


@router.get("/sessions", response_model=list[schemas.SessionOut])
def list_sessions(user: models.User = Depends(get_current_user), sid: str | None = Depends(current_session_id), db: Session = Depends(get_db)) -> list[schemas.SessionOut]:
    out = []
    for s in svc.active_sessions(db, user.id):
        item = schemas.SessionOut.model_validate(s)
        item.current = s.id == sid
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    s = db.get(models.Session, session_id)
    if s is None or s.user_id != user.id or s.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if svc.revoke_session_by_id(db, session_id, "user_revoked"):
        record(db, tenant_id=user.tenant_id, action="auth.session_revoked", actor=user, object_type="session", object_id=session_id, object_label="", ip=client_ip(request))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-all")
def revoke_all_sessions(request: Request, user: models.User = Depends(get_current_user), sid: str | None = Depends(current_session_id), db: Session = Depends(get_db)) -> dict:
    n = svc.revoke_all_user_sessions(db, user.id, "user_revoked_all", except_session_id=sid)
    record(db, tenant_id=user.tenant_id, action="auth.sessions_revoked_all", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request), meta={"revoked": n})
    db.commit()
    return {"revoked": n}


# ---------- MFA management (authenticated) ----------


@router.post("/mfa/setup", response_model=schemas.MfaSetupOut)
def mfa_setup(request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> schemas.MfaSetupOut:
    if user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is already enabled.")
    secret = svc.new_totp_secret()
    user.mfa_secret = secret
    record(db, tenant_id=user.tenant_id, action="auth.mfa_setup_started", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    db.commit()
    return schemas.MfaSetupOut(secret=secret, otpauth_uri=svc.totp_uri(secret, user.email))


@router.post("/mfa/enable", response_model=schemas.RecoveryCodesOut)
def mfa_enable(data: schemas.CodeIn, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> schemas.RecoveryCodesOut:
    if user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is already enabled.")
    if not user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start setup first (POST /auth/mfa/setup).")
    if not svc.verify_totp(user.mfa_secret, data.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code didn't match — make sure your device clock is correct and try again.")
    user.mfa_enabled = True
    codes = svc.regenerate_recovery_codes(db, user)
    record(db, tenant_id=user.tenant_id, action="auth.mfa_enabled", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    db.commit()
    return schemas.RecoveryCodesOut(recovery_codes=codes)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(data: schemas.PasswordIn, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is not enabled.")
    if not security.verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect.")
    user.mfa_enabled = False
    user.mfa_secret = None
    db.query(models.RecoveryCode).filter(models.RecoveryCode.user_id == user.id).delete()
    record(db, tenant_id=user.tenant_id, action="auth.mfa_disabled", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mfa/recovery-codes", response_model=schemas.RecoveryCodesOut)
def mfa_regenerate_recovery(data: schemas.PasswordIn, request: Request, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> schemas.RecoveryCodesOut:
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is not enabled.")
    if not security.verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect.")
    codes = svc.regenerate_recovery_codes(db, user)
    record(db, tenant_id=user.tenant_id, action="auth.mfa_recovery_regenerated", actor=user, object_type="user", object_id=user.id, object_label=user.name, ip=client_ip(request))
    db.commit()
    return schemas.RecoveryCodesOut(recovery_codes=codes)
