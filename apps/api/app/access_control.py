"""Permissions, separation of duties, step-up authentication and need-to-know access.

Four controls that all answer "may this person do this, right now, to this thing?" — kept
together because they compose, and splitting them would mean four modules each of which has to
know about the other three.

**The five built-in roles stay.** A custom role names a built-in as its base and adds or
removes individual permissions on top. Replacing the enum outright would mean auditing every
`user.role ==` in the codebase in one change, and an unrecognised role would degrade to *no*
access — which locks a bank out of its own contract system. This way an unknown role still
resolves to a known baseline.

**Separation of duties is enforced in the service layer, not the UI.** Hiding a button is not
a control; the API is the boundary. Every refusal is audited, and every *override* is audited
more loudly, because "we knew and did it anyway" is the fact an auditor is looking for.

**Step-up challenges are bound to the action and the object.** A session-scoped "recently
authenticated" flag would let a challenge passed to reveal one webhook secret be replayed to
reveal every other one in the next five minutes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import models
from .audit import record

#: The built-in roles, weakest first. Order matters: `at_least` compares by position.
BUILTIN_ROLES = ("viewer", "author", "approver", "manager", "admin", "owner")

#: Every permission the application checks. Named rather than inferred from role so a custom
#: role can be described in terms an administrator recognises.
PERMISSIONS = (
    "contract.read", "contract.write", "contract.delete", "contract.approve",
    "contract.sign", "contract.terminate",
    "template.write", "template.approve",
    "clause.write", "clause.approve",
    "playbook.write", "party.write", "party.screen",
    "user.manage", "role.manage", "settings.manage",
    "audit.read", "audit.verify", "export.run",
    "webhook.manage", "apikey.manage", "legalhold.manage", "access.grant",
    # Help copy, knowledge base and training content. Separate from `settings.manage` because
    # the people who should be correcting legal guidance are Legal, not whoever administers the
    # deployment — and requiring an admin for a wording fix is how wording fixes stop happening.
    "content.manage",
)

#: What each built-in role can do. A custom role starts from one of these.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"contract.read"},
    "author": {"contract.read", "contract.write", "template.write", "clause.write",
               "party.write", "export.run"},
    "approver": {"contract.read", "contract.approve", "export.run"},
    "manager": {"contract.read", "contract.write", "contract.approve", "contract.terminate",
                "template.write", "template.approve", "clause.write", "clause.approve",
                "playbook.write", "party.write", "party.screen", "export.run",
                "audit.read", "legalhold.manage", "access.grant", "content.manage"},
    "admin": set(PERMISSIONS) - {"contract.sign"},
    "owner": set(PERMISSIONS),
}

#: Actions that require a fresh re-authentication however recently the user signed in.
STEP_UP_ACTIONS = {
    "user.role_changed", "webhook.secret_revealed", "signature.voided",
    "certificate.revoked", "ra.approved", "contract.purged", "apikey.created",
    "legalhold.released", "access.granted",
}

#: How long a satisfied challenge stays usable. Short: it exists to prove the person at the
#: keyboard is still the account holder, and that claim decays quickly.
STEP_UP_TTL = dt.timedelta(minutes=5)
STEP_UP_MAX_ATTEMPTS = 3

#: Conflicting duties. Each entry is (first action, second action, what it means) — the same
#: identity may not do both on the same object.
SEGREGATED: tuple[tuple[str, str, str], ...] = (
    ("contract.authored", "contract.approved",
     "the author of an agreement cannot be its final approver"),
    ("template.authored", "template.approved",
     "the author of a template cannot approve it"),
    ("clause.authored", "clause.approved",
     "the author of a clause cannot approve it"),
    ("ra.requested", "ra.approved",
     "a certificate requester cannot approve their own request"),
    ("webhook.created", "webhook.secret_revealed",
     "the creator of a webhook cannot be the one to reveal its secret"),
    ("contract.authored", "contract.signed",
     "the author of an agreement cannot be the signatory of record"),
)


class AccessDenied(PermissionError):
    """Refused. Routers map to 403."""


class StepUpRequired(PermissionError):
    """The action needs a fresh re-authentication. Routers map to 401 with a challenge id."""

    def __init__(self, challenge_id: str, action: str):
        super().__init__("This action needs you to confirm your identity.")
        self.challenge_id = challenge_id
        self.action = action


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------------------


def permissions_for(db: Session, user: models.User) -> set[str]:
    """Everything this user may do.

    A custom role resolves against its base; an unknown role falls back to `viewer` rather
    than to nothing, so a typo in a role name restricts somebody instead of locking them out
    of a system they are supposed to administer.
    """
    role = user.role or "viewer"
    if role in ROLE_PERMISSIONS:
        return set(ROLE_PERMISSIONS[role])

    custom = db.scalar(select(models.CustomRole).where(
        models.CustomRole.tenant_id == user.tenant_id,
        models.CustomRole.key == role,
        models.CustomRole.is_active.is_(True)))
    if custom is None:
        return set(ROLE_PERMISSIONS["viewer"])

    base = set(ROLE_PERMISSIONS.get(custom.base_role, ROLE_PERMISSIONS["viewer"]))
    base |= {p for p in (custom.grants or []) if p in PERMISSIONS}
    # Revokes last, unconditionally: "this role must never do X" is only worth writing down
    # if nothing can grant it back.
    base -= set(custom.revokes or [])
    return base


def can(db: Session, user: models.User, permission: str) -> bool:
    return permission in permissions_for(db, user)


def require(db: Session, user: models.User, permission: str) -> None:
    if not can(db, user, permission):
        raise AccessDenied(f"Your role does not allow {permission.replace('.', ' ')}.")


def at_least(user: models.User, role: str) -> bool:
    """Built-in role comparison, for the checks that predate named permissions."""
    try:
        return BUILTIN_ROLES.index(user.role) >= BUILTIN_ROLES.index(role)
    except ValueError:
        return False


# ---------------------------------------------------------------------------------------
# Separation of duties
# ---------------------------------------------------------------------------------------


def conflicting_action(first: str, second: str) -> str | None:
    """The reason two actions may not share an identity, or None."""
    for a, b, reason in SEGREGATED:
        if {a, b} == {first, second}:
            return reason
    return None


def check_segregation(db: Session, *, user: models.User, action: str, object_type: str,
                      object_id: str) -> str | None:
    """Has this user already performed a conflicting action on this object?

    Answered from the audit log rather than a separate table: the audit log is already the
    record of who did what to which object, and a second store would be a second thing to keep
    in step.
    """
    conflicts = {a for a, b, _ in SEGREGATED if b == action}
    conflicts |= {b for a, b, _ in SEGREGATED if a == action}
    if not conflicts:
        return None

    prior = db.scalars(
        select(models.AuditLog).where(
            models.AuditLog.tenant_id == user.tenant_id,
            models.AuditLog.object_type == object_type,
            models.AuditLog.object_id == object_id,
            models.AuditLog.actor_id == user.id,
            models.AuditLog.action.in_(tuple(conflicts)),
        )
    ).all()
    for entry in prior:
        reason = conflicting_action(entry.action, action)
        if reason:
            return reason
    return None


def enforce_segregation(db: Session, *, user: models.User, action: str, object_type: str,
                        object_id: str, override_reason: str = "", ip: str = "") -> None:
    """Block a conflicting action, unless overridden with a recorded reason.

    An override is allowed because a small workspace may genuinely have nobody else — but it
    is audited as its own event, so "we knew and did it anyway" is visible rather than
    indistinguishable from "the control did not fire".
    """
    reason = check_segregation(db, user=user, action=action, object_type=object_type,
                               object_id=object_id)
    if reason is None:
        return
    if not override_reason.strip():
        record(db, tenant_id=user.tenant_id, action="sod.blocked", actor=user,
               object_type=object_type, object_id=object_id, ip=ip,
               meta={"attempted": action, "reason": reason})
        raise AccessDenied(f"Separation of duties: {reason}.")

    record(db, tenant_id=user.tenant_id, action="sod.overridden", actor=user,
           object_type=object_type, object_id=object_id, ip=ip,
           meta={"attempted": action, "rule": reason,
                 "override_reason": override_reason[:400]})


# ---------------------------------------------------------------------------------------
# Step-up authentication
# ---------------------------------------------------------------------------------------


def needs_step_up(action: str) -> bool:
    return action in STEP_UP_ACTIONS


def open_challenge(db: Session, user: models.User, action: str, *, object_type: str = "",
                   object_id: str = "") -> models.StepUpChallenge:
    challenge = models.StepUpChallenge(
        tenant_id=user.tenant_id, user_id=user.id, action=action,
        object_type=object_type, object_id=object_id or None,
        status="pending", expires_at=_now() + STEP_UP_TTL,
    )
    db.add(challenge)
    db.flush()
    return challenge


def satisfy(db: Session, challenge: models.StepUpChallenge, user: models.User, *,
            password: str = "", totp: str = "", ip: str = "") -> models.StepUpChallenge:
    """Verify the re-authentication.

    TOTP is preferred where the user has it: a password re-prompt only proves the password is
    known, which it already was five minutes ago when the session started.
    """
    from . import auth_service, security

    if challenge.status != "pending":
        raise AccessDenied("That challenge has already been used.")
    if challenge.expires_at < _now():
        challenge.status = "expired"
        raise AccessDenied("That challenge expired. Try again.")
    if challenge.user_id != user.id:
        raise AccessDenied("That challenge belongs to somebody else.")

    challenge.attempts += 1
    if challenge.attempts > STEP_UP_MAX_ATTEMPTS:
        challenge.status = "failed"
        record(db, tenant_id=user.tenant_id, action="stepup.failed", actor=user,
               object_type=challenge.object_type, object_id=challenge.object_id, ip=ip,
               meta={"action": challenge.action, "reason": "too many attempts"})
        raise AccessDenied("Too many attempts. Start again.")

    verified = ""
    if totp and getattr(user, "mfa_secret", None):
        if auth_service.verify_totp(user.mfa_secret, totp):
            verified = "totp"
    if not verified and password and user.password_hash:
        if security.verify_password(password, user.password_hash):
            verified = "password"

    if not verified:
        record(db, tenant_id=user.tenant_id, action="stepup.failed", actor=user,
               object_type=challenge.object_type, object_id=challenge.object_id, ip=ip,
               meta={"action": challenge.action, "attempt": challenge.attempts})
        raise AccessDenied("That did not match.")

    challenge.status = "satisfied"
    challenge.method = verified
    challenge.satisfied_at = _now()
    record(db, tenant_id=user.tenant_id, action="stepup.satisfied", actor=user,
           object_type=challenge.object_type, object_id=challenge.object_id, ip=ip,
           meta={"action": challenge.action, "method": verified})
    return challenge


def consume(db: Session, user: models.User, action: str, challenge_id: str, *,
            object_type: str = "", object_id: str = "") -> None:
    """Spend a satisfied challenge, or raise `StepUpRequired` with a fresh one.

    Single-use and bound to this action *and* this object. Anything looser turns one
    re-authentication into a five-minute window over every sensitive action at once.
    """
    if not needs_step_up(action):
        return

    challenge = db.get(models.StepUpChallenge, challenge_id) if challenge_id else None
    valid = (
        challenge is not None
        and challenge.tenant_id == user.tenant_id
        and challenge.user_id == user.id
        and challenge.status == "satisfied"
        and challenge.consumed_at is None
        and challenge.action == action
        and (challenge.object_id or "") == (object_id or "")
        and challenge.satisfied_at is not None
        and challenge.satisfied_at + STEP_UP_TTL >= _now()
    )
    if not valid:
        fresh = open_challenge(db, user, action, object_type=object_type,
                               object_id=object_id)
        raise StepUpRequired(fresh.id, action)

    challenge.consumed_at = _now()


# ---------------------------------------------------------------------------------------
# Need-to-know access
# ---------------------------------------------------------------------------------------


def visible_to(db: Session, user: models.User, contract: models.Contract) -> bool:
    """Can this user see this agreement at all?

    Only confidential agreements consult the ACL. The owner and the workspace owner always
    can — an access-control model where somebody can lock the account owner out of a record
    is one that produces an emergency, not security.
    """
    if not contract.confidential:
        return True
    if user.role == "owner" or contract.owner_id == user.id or contract.created_by == user.id:
        return True

    now = _now()
    grants = db.scalars(
        select(models.ContractAccess).where(
            models.ContractAccess.tenant_id == user.tenant_id,
            models.ContractAccess.contract_id == contract.id,
            or_(models.ContractAccess.user_id == user.id,
                models.ContractAccess.role == user.role),
        )
    ).all()
    return any(g.expires_at is None or g.expires_at > now for g in grants)


def require_visible(db: Session, user: models.User, contract: models.Contract, *,
                    ip: str = "") -> None:
    if visible_to(db, user, contract):
        return
    # Logged: a refused read of a confidential agreement is exactly the event an investigation
    # starts from, and it is invisible unless recorded here.
    record(db, tenant_id=user.tenant_id, action="contract.access_denied", actor=user,
           object_type="contract", object_id=contract.id, ip=ip,
           meta={"reason": "not on the access list"})
    raise AccessDenied("You do not have access to this agreement.")


def grant(db: Session, contract: models.Contract, *, actor: models.User,
          user_id: str = "", role: str = "", level: str = "read", reason: str = "",
          expires_at: dt.datetime | None = None, ip: str = "") -> models.ContractAccess:
    if not user_id and not role:
        raise AccessDenied("A grant needs a person or a role.")
    if level not in ("read", "write"):
        raise AccessDenied(f"Unknown access level '{level}'.")

    access = models.ContractAccess(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        user_id=user_id or None, role=role or None, level=level,
        reason=reason[:400], granted_by=actor.id, expires_at=expires_at,
    )
    db.add(access)
    db.flush()
    record(db, tenant_id=contract.tenant_id, action="access.granted", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"to_user": user_id, "to_role": role, "level": level,
                 "reason": reason[:200],
                 "expires_at": expires_at.isoformat() if expires_at else None})
    return access


def break_glass(db: Session, contract: models.Contract, *, actor: models.User, reason: str,
                ip: str = "") -> None:
    """Emergency access to a confidential agreement, loudly.

    Not a silent bypass: it grants an hour, and it writes an audit event of its own so the
    access shows up in a review rather than looking like ordinary traffic.
    """
    if not reason.strip():
        raise AccessDenied("Break-glass access needs a reason.")
    grant(db, contract, actor=actor, user_id=actor.id, level="read",
          reason=f"BREAK-GLASS: {reason.strip()[:300]}",
          expires_at=_now() + dt.timedelta(hours=1), ip=ip)
    record(db, tenant_id=contract.tenant_id, action="access.break_glass", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"reason": reason.strip()[:400]})


# ---------------------------------------------------------------------------------------
# Temporary external access
# ---------------------------------------------------------------------------------------


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_temporary_access(db: Session, contract: models.Contract, *, actor: models.User,
                           email: str, name: str = "", organisation: str = "",
                           scope: str = "view", days: int = 14, watermark: bool = True,
                           allow_download: bool = False,
                           ip: str = "") -> tuple[models.TemporaryAccess, str]:
    """(record, raw token). The raw token is returned once and never stored."""
    if scope not in ("view", "comment"):
        raise AccessDenied(f"Unknown scope '{scope}'.")
    if days < 1 or days > 90:
        raise AccessDenied("Temporary access must last between 1 and 90 days.")

    raw = secrets.token_urlsafe(32)
    access = models.TemporaryAccess(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        email=email.strip().lower()[:320], name=name[:200],
        organisation=organisation[:200], token_hash=hash_token(raw), scope=scope,
        status="active", expires_at=_now() + dt.timedelta(days=days),
        watermark=watermark, allow_download=allow_download, granted_by=actor.id,
    )
    db.add(access)
    db.flush()
    record(db, tenant_id=contract.tenant_id, action="temporary_access.granted", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"email": email, "scope": scope, "days": days,
                 "allow_download": allow_download})
    return access, raw


def resolve_temporary(db: Session, raw: str) -> models.TemporaryAccess | None:
    """Look a link up by its token. Expired or revoked resolves to nothing.

    Returns None rather than an expired record, so a caller cannot accidentally serve content
    from one — and an expired token is indistinguishable from a wrong one to whoever tried it.
    """
    access = db.scalar(select(models.TemporaryAccess).where(
        models.TemporaryAccess.token_hash == hash_token(raw)))
    if access is None or access.status != "active" or access.expires_at < _now():
        return None
    return access


def revoke_temporary(db: Session, access: models.TemporaryAccess, *, actor: models.User,
                     ip: str = "") -> None:
    access.status = "revoked"
    access.revoked_by = actor.id
    access.revoked_at = _now()
    record(db, tenant_id=access.tenant_id, action="temporary_access.revoked", actor=actor,
           object_type="contract", object_id=access.contract_id, ip=ip,
           meta={"email": access.email, "views": access.view_count})


def expire_temporary(db: Session, *, now: dt.datetime | None = None,
                     tenant_id: str = "") -> int:
    """Mark elapsed links expired. Idempotent; safe to run on a beat.

    `tenant_id` scopes it. An unscoped sweep touches every workspace in the database, which is
    right for a global beat and wrong for anything that reports a count back to one tenant.
    """
    moment = now or _now()
    stmt = select(models.TemporaryAccess).where(
        models.TemporaryAccess.status == "active",
        models.TemporaryAccess.expires_at < moment)
    if tenant_id:
        stmt = stmt.where(models.TemporaryAccess.tenant_id == tenant_id)
    stale = db.scalars(stmt).all()
    for access in stale:
        access.status = "expired"
    # The session runs with autoflush off, so without this the next call re-reads the rows as
    # still active and expires them again — a beat that reports the same links every run.
    db.flush()
    return len(stale)
