"""PKI HTTP surface — CA administration, the RA queue, the certificate register, and the
**public** distribution points relying parties need.

Two access classes live in this router, deliberately marked:

  authenticated   everything under /pki that mutates or lists. Most operations are owner/admin
                  only, because certificate issuance and revocation are trust-anchor-level
                  powers rather than ordinary workspace administration.

  public          `GET /pki/crl/{ca}.crl`, `GET /pki/ca/{ca}.cer` and `POST|GET /pki/ocsp`.
                  These URLs are baked into every issued certificate's CDP and AIA extensions,
                  so they must be reachable without credentials — a relying party validating a
                  signature is not a user of this system. All three serve public artefacts:
                  a CA certificate, a signed revocation list, and a signed status response,
                  none of which disclose anything a certificate holder has not already been
                  given. They are rate-limited by the global middleware.
"""

from __future__ import annotations

import base64
import datetime as dt
import urllib.parse

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import client_ip, get_current_user
from ..pki import ca as ca_mod
from ..pki import crl as crl_mod
from ..pki import lifecycle, ocsp, ra, validate
from ..pki.keystore import KeyStoreError, get_keystore

router = APIRouter(prefix="/pki", tags=["pki"])

_ADMIN_ROLES = {"owner", "admin"}


def _require_admin(user: models.User) -> models.User:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can administer the PKI.",
        )
    return user


def _pki_error(e: Exception) -> HTTPException:
    """Lifecycle/RA rule violations are conflicts, not server errors — the caller asked for
    something the state machine forbids, and the message says which rule."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


def _owned_cert(db: Session, user: models.User, cert_id: str) -> models.Certificate:
    c = db.get(models.Certificate, cert_id)
    if c is None or c.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return c


def _owned_request(db: Session, user: models.User, req_id: str) -> models.CertificateRequest:
    r = db.get(models.CertificateRequest, req_id)
    if r is None or r.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate request not found")
    return r


def _user_names(db: Session, tenant_id: str) -> dict[str, str]:
    return {
        u.id: u.name
        for u in db.scalars(select(models.User).where(models.User.tenant_id == tenant_id)).all()
    }


# ---------------------------------------------------------------------------------------
# Certificate authorities
# ---------------------------------------------------------------------------------------


@router.post("/provision", response_model=schemas.PkiHealthOut, status_code=status.HTTP_201_CREATED)
def provision(request: Request, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)) -> schemas.PkiHealthOut:
    """Create the root CA, the issuing CA and the OCSP responder. Idempotent."""
    _require_admin(user)
    try:
        ca_mod.provision_hierarchy(db, user.tenant_id, actor_id=user.id)
    except KeyStoreError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    db.commit()
    return _health(db, user.tenant_id)


@router.get("/cas", response_model=list[schemas.CertificateAuthorityOut])
def list_cas(db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)) -> list[schemas.CertificateAuthorityOut]:
    rows = db.scalars(
        select(models.CertificateAuthority)
        .where(models.CertificateAuthority.tenant_id == user.tenant_id)
        .order_by(models.CertificateAuthority.created_at.asc())
    ).all()
    return [schemas.CertificateAuthorityOut.model_validate(r) for r in rows]


@router.get("/cas/{ca_id}", response_model=schemas.CaChainOut)
def get_ca(ca_id: str, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)) -> schemas.CaChainOut:
    ca = db.get(models.CertificateAuthority, ca_id)
    if ca is None or ca.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CA not found")
    return schemas.CaChainOut(
        ca=schemas.CertificateAuthorityOut.model_validate(ca),
        chain_pem=ca_mod.chain_pems(db, ca),
    )


@router.post("/cas/{ca_id}/offline", response_model=dict)
def offline_root(ca_id: str, request: Request, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> dict:
    """Key ceremony: export the root key **once** and destroy it from the online store.

    The response body carries the private key. It is returned exactly once, is never persisted
    afterwards, and never appears in an audit entry — write it to offline media immediately.
    """
    _require_admin(user)
    ca = db.get(models.CertificateAuthority, ca_id)
    if ca is None or ca.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CA not found")
    if ca.kind != "root":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only the root CA can be taken offline.")
    if ca.is_offline:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Root CA is already offline.")
    exported = ca_mod.take_root_offline(db, ca, actor_id=user.id)
    db.commit()
    return {
        "ok": True,
        "private_key_pem": exported,
        "warning": (
            "This is the only time this key is shown. Write it to offline media now. "
            "Without it the root CA can never sign again."
        ),
    }


# ---------------------------------------------------------------------------------------
# Public distribution points  (no authentication — see the module docstring)
# ---------------------------------------------------------------------------------------


@router.get("/ca/{ca_id}.cer", include_in_schema=True)
def public_ca_certificate(ca_id: str, db: Session = Depends(get_db)) -> Response:
    """AIA `caIssuers` target. Serves the CA certificate in DER, as RFC 5280 expects."""
    ca = db.get(models.CertificateAuthority, ca_id)
    if ca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    der = ca_mod.from_pem(ca.pem).public_bytes(serialization.Encoding.DER)
    return Response(content=der, media_type="application/pkix-cert")


@router.get("/crl/{ca_id}.crl")
def public_crl(ca_id: str, db: Session = Depends(get_db)) -> Response:
    """CRL Distribution Point target. Regenerated on demand and cached by `Cache-Control` for
    the CRL's own validity window, so a relying party honours `nextUpdate` naturally."""
    ca = db.get(models.CertificateAuthority, ca_id)
    if ca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    der = crl_mod.publish(db, ca, delta=False)
    db.commit()
    return Response(
        content=der, media_type="application/pkix-crl",
        headers={"Cache-Control": f"public, max-age={settings.crl_validity_hours * 3600}"},
    )


@router.get("/crl/{ca_id}-delta.crl")
def public_delta_crl(ca_id: str, db: Session = Depends(get_db)) -> Response:
    ca = db.get(models.CertificateAuthority, ca_id)
    if ca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        der = crl_mod.publish(db, ca, delta=True)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    db.commit()
    return Response(
        content=der, media_type="application/pkix-crl",
        headers={"Cache-Control": f"public, max-age={settings.crl_delta_validity_hours * 3600}"},
    )


@router.post("/ocsp")
async def ocsp_post(request: Request, db: Session = Depends(get_db)) -> Response:
    """RFC 6960 responder. The issuing CA is identified from the request's own issuer hashes,
    so this endpoint needs neither a tenant in the URL nor credentials."""
    body = await request.body()
    der = ocsp.build_response(db, None, body)
    return Response(
        content=der, media_type="application/ocsp-response",
        # OCSP responses carry their own nextUpdate; never let a proxy hold one longer.
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ocsp/{encoded:path}")
def ocsp_get(encoded: str, db: Session = Depends(get_db)) -> Response:
    """RFC 6960 §A.1 GET form: the DER request, base64-encoded then URL-encoded.

    Some clients (and most caching proxies) only use GET, so a responder that implements POST
    alone is unreachable from them.
    """
    try:
        raw = base64.b64decode(urllib.parse.unquote(encoded))
    except Exception:  # noqa: BLE001
        raw = b""
    der = ocsp.build_response(db, None, raw)
    return Response(content=der, media_type="application/ocsp-response",
                    headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------------------
# Registration Authority
# ---------------------------------------------------------------------------------------


@router.get("/requests", response_model=list[schemas.CertificateRequestOut])
def list_requests(status_: str | None = Query(None, alias="status"),
                  db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> list[schemas.CertificateRequestOut]:
    stmt = select(models.CertificateRequest).where(
        models.CertificateRequest.tenant_id == user.tenant_id
    )
    if status_:
        stmt = stmt.where(models.CertificateRequest.status == status_)
    rows = db.scalars(stmt.order_by(models.CertificateRequest.created_at.desc()).limit(200)).all()
    names = _user_names(db, user.tenant_id)
    out = []
    for r in rows:
        item = schemas.CertificateRequestOut.model_validate(r)
        item.subject_name = names.get(r.subject_user_id or "", "")
        item.requested_by_name = names.get(r.requested_by, "")
        out.append(item)
    return out


@router.post("/requests", response_model=schemas.CertificateRequestOut,
             status_code=status.HTTP_201_CREATED)
def create_request(data: schemas.EnrolIn, request: Request, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.CertificateRequestOut:
    """Raise an enrolment request. Any authenticated user may enrol *themselves*; enrolling
    someone else is an RA-officer action."""
    target_id = data.subject_user_id or (None if data.subject_party_id else user.id)
    if target_id and target_id != user.id:
        _require_admin(user)
    if data.subject_party_id:
        _require_admin(user)

    try:
        if target_id and not data.subject_party_id:
            subject = db.get(models.User, target_id)
            if subject is None or subject.tenant_id != user.tenant_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject user not found")
            req = ra.enrol_internal_user(db, subject, actor=user, claims=data.evidence or None)
        else:
            req = ra.enrol(
                db, tenant_id=user.tenant_id, subject_email=data.subject_email,
                common_name=data.common_name or data.subject_email,
                subject_party_id=data.subject_party_id, profile=data.profile,
                evidence=data.evidence, actor=user,
            )
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return schemas.CertificateRequestOut.model_validate(req)


@router.post("/requests/{req_id}/approve", response_model=schemas.CertificateRequestOut)
def approve_request(req_id: str, data: schemas.ReviewIn, request: Request,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.CertificateRequestOut:
    req = _owned_request(db, user, req_id)
    try:
        ra.approve(db, req, officer=user, note=data.note)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return schemas.CertificateRequestOut.model_validate(req)


@router.post("/requests/{req_id}/reject", response_model=schemas.CertificateRequestOut)
def reject_request(req_id: str, data: schemas.ReviewIn, request: Request,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> schemas.CertificateRequestOut:
    req = _owned_request(db, user, req_id)
    try:
        ra.reject(db, req, officer=user, note=data.note)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return schemas.CertificateRequestOut.model_validate(req)


@router.post("/requests/{req_id}/issue", response_model=schemas.CertificateOut,
             status_code=status.HTTP_201_CREATED)
def issue_request(req_id: str, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.CertificateOut:
    _require_admin(user)
    req = _owned_request(db, user, req_id)
    try:
        cert = lifecycle.issue_from_request(db, req, actor=user)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    except KeyStoreError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    db.commit()
    return _cert_out(db, cert, include_pem=True)


# ---------------------------------------------------------------------------------------
# Certificate register
# ---------------------------------------------------------------------------------------


def _cert_out(db: Session, c: models.Certificate, *, include_pem: bool = False,
              names: dict[str, str] | None = None) -> schemas.CertificateOut:
    item = schemas.CertificateOut.model_validate(c)
    item.pem = c.pem if include_pem else None
    names = names if names is not None else _user_names(db, c.tenant_id)
    item.subject_name = names.get(c.subject_user_id or "", "")
    delta = c.not_after - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    item.days_remaining = max(0, delta.days)
    return item


@router.get("/certificates", response_model=schemas.CertificateListOut)
def list_certificates(
    status_: str | None = Query(None, alias="status"),
    profile: str | None = None,
    q: str | None = None,
    subject_user_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CertificateListOut:
    stmt = select(models.Certificate).where(models.Certificate.tenant_id == user.tenant_id)
    if status_:
        stmt = stmt.where(models.Certificate.status == status_)
    if profile:
        stmt = stmt.where(models.Certificate.profile == profile)
    if subject_user_id:
        stmt = stmt.where(models.Certificate.subject_user_id == subject_user_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(models.Certificate.subject_dn).like(like)
            | func.lower(models.Certificate.serial_number).like(like)
            | func.lower(models.Certificate.subject_email).like(like)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(models.Certificate.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    names = _user_names(db, user.tenant_id)
    return schemas.CertificateListOut(
        items=[_cert_out(db, c, names=names) for c in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get("/certificates/{cert_id}", response_model=schemas.CertificateOut)
def get_certificate(cert_id: str, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.CertificateOut:
    return _cert_out(db, _owned_cert(db, user, cert_id), include_pem=True)


@router.post("/certificates/{cert_id}/renew", response_model=schemas.CertificateOut,
             status_code=status.HTTP_201_CREATED)
def renew_certificate(cert_id: str, request: Request, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.CertificateOut:
    _require_admin(user)
    cert = _owned_cert(db, user, cert_id)
    try:
        fresh = lifecycle.renew(db, cert, actor=user)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return _cert_out(db, fresh, include_pem=True)


@router.post("/certificates/{cert_id}/suspend", response_model=schemas.CertificateOut)
def suspend_certificate(cert_id: str, data: schemas.ReviewIn, request: Request,
                        db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> schemas.CertificateOut:
    _require_admin(user)
    cert = _owned_cert(db, user, cert_id)
    try:
        lifecycle.suspend(db, cert, actor=user, note=data.note)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return _cert_out(db, cert)


@router.post("/certificates/{cert_id}/resume", response_model=schemas.CertificateOut)
def resume_certificate(cert_id: str, data: schemas.ReviewIn, request: Request,
                       db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> schemas.CertificateOut:
    _require_admin(user)
    cert = _owned_cert(db, user, cert_id)
    try:
        lifecycle.resume(db, cert, actor=user, note=data.note)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return _cert_out(db, cert)


@router.post("/certificates/{cert_id}/revoke", response_model=schemas.CertificateOut)
def revoke_certificate(cert_id: str, data: schemas.RevokeIn, request: Request,
                       db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> schemas.CertificateOut:
    _require_admin(user)
    cert = _owned_cert(db, user, cert_id)
    try:
        lifecycle.revoke(db, cert, reason=data.reason, actor=user, note=data.note)
    except lifecycle.PkiError as e:
        raise _pki_error(e) from e
    db.commit()
    return _cert_out(db, cert)


# ---------------------------------------------------------------------------------------
# Trust store + third-party validation
# ---------------------------------------------------------------------------------------


@router.get("/trust-anchors", response_model=list[schemas.TrustAnchorOut])
def list_trust_anchors(db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> list[schemas.TrustAnchorOut]:
    rows = db.scalars(
        select(models.TrustAnchor)
        .where(models.TrustAnchor.tenant_id == user.tenant_id)
        .order_by(models.TrustAnchor.name.asc())
    ).all()
    out = []
    for r in rows:
        item = schemas.TrustAnchorOut.model_validate(r)
        try:
            item.not_after = ca_mod.from_pem(r.pem).not_valid_after_utc.replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            pass
        out.append(item)
    return out


@router.post("/trust-anchors", response_model=schemas.TrustAnchorOut,
             status_code=status.HTTP_201_CREATED)
def add_trust_anchor(data: schemas.TrustAnchorIn, request: Request, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> schemas.TrustAnchorOut:
    """Adding a root is a trust decision — admin only, and always audited."""
    _require_admin(user)
    try:
        row = validate.add_trust_anchor(db, user.tenant_id, data.pem, name=data.name, actor=user)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a valid PEM certificate: {e}",
        ) from e
    db.commit()
    return schemas.TrustAnchorOut.model_validate(row)


@router.delete("/trust-anchors/{anchor_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_trust_anchor(anchor_id: str, request: Request, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)) -> Response:
    _require_admin(user)
    row = db.get(models.TrustAnchor, anchor_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust anchor not found")
    from ..audit import record

    # Deactivated rather than deleted: an auditor needs to see that this root was once
    # trusted, and when that stopped.
    row.is_active = False
    record(db, tenant_id=user.tenant_id, action="pki.trust_anchor.removed", actor=user,
           object_type="trust_anchor", object_id=row.id, object_label=row.name,
           ip=client_ip(request), meta={"fingerprint_sha256": row.fingerprint_sha256})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/validate", response_model=schemas.ValidateOut)
def validate_certificate(data: schemas.ValidateIn, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)) -> schemas.ValidateOut:
    """Validate a third-party certificate — the path for overseas signatories who cannot be
    issued a certificate by this CA."""
    result = validate.validate(
        db, user.tenant_id, data.pem,
        intermediate_pems=data.intermediates, check_revocation=data.check_revocation,
    )
    return schemas.ValidateOut(
        ok=result.ok, reason=result.reason, chain=result.chain,
        revocation_checked=result.revocation_checked, warnings=result.warnings,
    )


# ---------------------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------------------


def _health(db: Session, tenant_id: str) -> schemas.PkiHealthOut:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    cas = list(db.scalars(
        select(models.CertificateAuthority).where(
            models.CertificateAuthority.tenant_id == tenant_id,
            models.CertificateAuthority.status == "active",
        )
    ).all())
    root = next((c for c in cas if c.kind == "root"), None)
    issuing = next((c for c in cas if c.kind == "issuing"), None)
    responder = next((c for c in cas if c.kind == "ocsp"), None)

    def count(**where) -> int:
        stmt = select(func.count()).select_from(models.Certificate).where(
            models.Certificate.tenant_id == tenant_id
        )
        for k, v in where.items():
            stmt = stmt.where(getattr(models.Certificate, k) == v)
        return db.scalar(stmt) or 0

    expiring = db.scalar(
        select(func.count()).select_from(models.Certificate).where(
            models.Certificate.tenant_id == tenant_id,
            models.Certificate.status == "active",
            models.Certificate.not_after <= now + dt.timedelta(days=30),
            models.Certificate.not_after > now,
        )
    ) or 0

    pending = db.scalar(
        select(func.count()).select_from(models.CertificateRequest).where(
            models.CertificateRequest.tenant_id == tenant_id,
            models.CertificateRequest.status == "pending",
        )
    ) or 0

    last_crl = db.scalar(
        select(models.AuditLog).where(
            models.AuditLog.tenant_id == tenant_id,
            models.AuditLog.action == "pki.crl.published",
        ).order_by(models.AuditLog.at.desc()).limit(1)
    )
    crl_at = last_crl.at if last_crl is not None else None
    next_update = (
        crl_at + dt.timedelta(hours=settings.crl_validity_hours) if crl_at else None
    )

    warnings: list[str] = []
    hsm_connected: bool | None = None
    hsm_detail = ""
    if settings.keystore_provider == "pkcs11":
        try:
            store = get_keystore()
            if issuing is not None:
                hsm_connected = store.exists(db, issuing.key_id)
                hsm_detail = "issuing CA key present in the token" if hsm_connected else \
                             "issuing CA key NOT found in the token"
            else:
                hsm_connected = True
                hsm_detail = "token reachable"
        except Exception as e:  # noqa: BLE001
            hsm_connected, hsm_detail = False, str(e)
            warnings.append(f"HSM unreachable: {e}")
    else:
        warnings.append(
            "Software keystore in use — signing keys are encrypted at rest but not "
            "HSM-protected. Set KEYSTORE_PROVIDER=pkcs11 for a FIPS 140-2 deployment."
        )

    if root is not None and not root.is_offline:
        warnings.append(
            "Root CA key is still online. Run the offlining ceremony "
            "(POST /pki/cas/{id}/offline) and store the key on offline media."
        )
    if next_update is not None and next_update <= now:
        warnings.append("Published CRL is past its nextUpdate — relying parties may reject it.")
    if not settings.pki_base_url:
        warnings.append(
            "PKI_BASE_URL is unset, so CRL/OCSP URLs fall back to FRONTEND_URL. These are "
            "baked into every issued certificate and cannot be changed retroactively."
        )

    return schemas.PkiHealthOut(
        provisioned=issuing is not None,
        keystore_provider=settings.keystore_provider,
        hsm_connected=hsm_connected, hsm_detail=hsm_detail,
        root_ca=schemas.CertificateAuthorityOut.model_validate(root) if root else None,
        issuing_ca=schemas.CertificateAuthorityOut.model_validate(issuing) if issuing else None,
        ocsp_responder=schemas.CertificateAuthorityOut.model_validate(responder) if responder else None,
        root_offline=bool(root and root.is_offline),
        certificates_active=count(status="active"),
        certificates_suspended=count(status="suspended"),
        certificates_revoked=count(status="revoked"),
        certificates_expired=count(status="expired"),
        certificates_expiring_30d=expiring,
        pending_requests=pending,
        crl_number=issuing.crl_number if issuing else 0,
        crl_last_published=crl_at,
        crl_next_update=next_update,
        crl_stale=bool(next_update and next_update <= now),
        dual_control=settings.ra_dual_control,
        warnings=warnings,
    )


@router.get("/health", response_model=schemas.PkiHealthOut)
def health(db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)) -> schemas.PkiHealthOut:
    return _health(db, user.tenant_id)
