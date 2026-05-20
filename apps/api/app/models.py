import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class EncryptedString(TypeDecorator):
    """A SQLAlchemy column type that transparently encrypts/decrypts at the application layer
    using AES-256-GCM (via Fernet/MultiFernet, see `secrets_box`). Storage column is a
    String — long enough to fit a Fernet token (≈ 100 chars for short plaintexts). RFI §A.8."""

    impl = String
    cache_ok = True

    def __init__(self, length: int = 256, **kw):
        super().__init__(length=length, **kw)

    def process_bind_param(self, value, dialect):  # noqa: ARG002
        if value is None:
            return None
        from .secrets_box import get_box

        return get_box().encrypt(value)

    def process_result_value(self, value, dialect):  # noqa: ARG002
        if value is None:
            return None
        from .secrets_box import get_box

        return get_box().decrypt(value)


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    locale: Mapped[str] = mapped_column(String(10), default="en")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    plan: Mapped[str] = mapped_column(String(50), default="business")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")

    @property
    def accent_color(self) -> str:
        return (self.settings or {}).get("accent_color", "#3E7BFA")

    @property
    def timezone(self) -> str:
        return (self.settings or {}).get("timezone", "UTC")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="author")  # owner|admin|manager|author|approver|reviewer|viewer|auditor
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_color: Mapped[str] = mapped_column(String(7), default="#3E7BFA")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedString(256), nullable=True)  # base32 TOTP secret — encrypted at rest (AES-256-GCM via secrets_box)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    tenant: Mapped[Tenant] = relationship(back_populates="users")


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    reference_no: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(50), default="other")  # nda|msa|lease|employment|vendor|service|other
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    counterparty: Mapped[str] = mapped_column(String(200), default="")
    department: Mapped[str] = mapped_column(String(100), default="")
    value: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    effective_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    renewal_type: Mapped[str] = mapped_column(String(20), default="none")  # none|auto|manual
    governing_law: Mapped[str] = mapped_column(String(100), default="")
    risk_level: Mapped[str] = mapped_column(String(20), default="low")  # low|medium|high|critical
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    body: Mapped[str] = mapped_column(Text, default="")  # the contract document (markdown for the scaffold)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|template|ocr|import
    renewed_from_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # set on the successor when this contract was created by renewing another
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ContractVersion(Base):
    __tablename__ = "contract_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text, default="")
    change_summary: Mapped[str] = mapped_column(String(400), default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    author_id: Mapped[str] = mapped_column(String(32))
    author_name: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(200), default="system")
    action: Mapped[str] = mapped_column(String(80))  # e.g. 'contract.created', 'contract.status_changed'
    object_type: Mapped[str] = mapped_column(String(40), default="")
    object_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_label: Mapped[str] = mapped_column(String(300), default="")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    # Tamper-evidence chain: each row stores HMAC-SHA256(secret, prev_hash || canonical(row)) so a
    # later auditor can recompute the chain and detect any deletion or in-place edit. The chain is
    # per-tenant; the genesis row stores prev_hash="" (treated as 64 zero hex chars by the
    # verifier). RFI §A.16 / docs/19.
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    row_hash: Mapped[str] = mapped_column(String(64), default="", index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(String(600), default="")
    object_type: Mapped[str] = mapped_column(String(40), default="")
    object_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Session(Base):
    """A refresh-token session. The refresh token is an opaque random string; only its hash is
    stored. Rotated on each use; presenting an already-rotated token (reuse) revokes the chain."""

    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # the session this one rotated from
    chain_id: Mapped[str] = mapped_column(String(32), index=True)  # all rotations of one login share a chain_id
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    last_used_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(40), default="")  # rotated|logout|reuse_detected|password_change|admin


class OtpCode(Base):
    """One-time email codes (e.g., the email-OTP alternative at the 2FA step)."""

    __tablename__ = "otp_codes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), default="login_2fa")
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class RecoveryCode(Base):
    """Single-use 2FA backup codes (hashed)."""

    __tablename__ = "recovery_codes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class WorkflowDefinition(Base):
    """A named, ordered list of approval steps. v1 is linear (sequential); parallel/conditional
    steps, SLAs and escalation are planned (docs/10)."""

    __tablename__ = "workflow_definitions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | archived
    default_for_types: Mapped[list] = mapped_column(JSON, default=list)  # contract types this is the default workflow for
    steps: Mapped[list] = mapped_column(JSON, default=list)  # [{name, assignee_kind: role|user, assignee_value}]
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    definition_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    definition_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)  # running | approved | rejected | changes_requested | cancelled
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    started_by: Mapped[str] = mapped_column(String(32))
    started_by_name: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowRunStep(Base):
    __tablename__ = "workflow_run_steps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    assignee_kind: Mapped[str] = mapped_column(String(20), default="role")  # role | user
    assignee_value: Mapped[str] = mapped_column(String(64), default="approver")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending | active | approved | rejected | changes_requested | skipped
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_by_name: Mapped[str] = mapped_column(String(200), default="")
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class SignatureEnvelope(Base):
    """An e-signature request for a contract version. v1 has no on-page field placement — each
    recipient adopts a typed signature; the executed PDF appends a signatures page + a certificate
    of completion. (DocViewer field placement, identity OTP, etc. are planned — docs/13.)"""

    __tablename__ = "signature_envelopes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    contract_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)  # draft|sent|partially_signed|completed|declined|voided|expired
    signing_order: Mapped[str] = mapped_column(String(20), default="sequential")  # sequential | parallel
    message: Mapped[str] = mapped_column(Text, default="")
    document_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)   # the contract PDF recipients see
    document_hash: Mapped[str] = mapped_column(String(64), default="")                  # hash of the signed content
    sealed_pdf_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    certificate_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class SignatureRecipient(Base):
    __tablename__ = "signature_recipients"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    envelope_id: Mapped[str] = mapped_column(ForeignKey("signature_envelopes.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20), default="signer")  # signer | cc
    status: Mapped[str] = mapped_column(String(20), default="created")  # created|sent|viewed|signed|declined
    # The per-recipient signing-link secret is *never* persisted in plaintext.
    #  - `access_token_hash`     = SHA-256(raw token). Used to look the recipient up at /sign/{token}.
    #    If the DB is exfiltrated, the hash is one-way and cannot be turned back into a working URL.
    #  - `access_token_secret`   = the raw token, but stored via `EncryptedString` (Fernet/AES-256-GCM
    #    chain in `secrets_box`). Decrypts server-side so reminders can reuse the same URL — at-rest
    #    secrecy depends on `MFA_ENCRYPTION_KEYS`, which lives outside the DB.
    #  - `access_token_expires_at` enforces a maximum lifetime (default 14 days) so leaked links
    #    auto-revoke; void/decline also wipe all three fields.
    # RFI §A.8 / docs/19. (Was a plaintext `access_token` column — replaced by 0013_hardening.)
    access_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    access_token_secret: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    access_token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    signed_name: Mapped[str] = mapped_column(String(200), default="")  # the typed signature
    consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    signed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    declined_reason: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class SignatureEvent(Base):
    __tablename__ = "signature_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    envelope_id: Mapped[str] = mapped_column(ForeignKey("signature_envelopes.id"), index=True)
    recipient_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recipient_name: Mapped[str] = mapped_column(String(200), default="")
    event: Mapped[str] = mapped_column(String(40))  # created|sent|opened|consented|signed|declined|reminder_sent|completed|voided
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class LoginAttempt(Base):
    """Record of every authentication attempt (success or failure). Drives the per-account
    lockout (5 failures / 10 min → 15-min lockout) + serves as security-audit source for
    'who tried to log in as me from where'. Tenant-isolated when we can tell the tenant; rows
    for unknown-email attempts carry tenant_id=''. RFI §A.7."""

    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(default="", index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str] = mapped_column(String(60), default="")   # ok | bad_password | unknown_user | inactive | locked | mfa_failed
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class LockoutState(Base):
    """One row per user capturing the active lockout (if any). Cleared on a successful sign-in
    or admin reset. Reads are O(1) per login attempt."""

    __tablename__ = "lockout_states"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(default="", index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True, unique=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class ContractTemplate(Base):
    """A reusable contract template — body (with {{variables}}) + default metadata so a user can
    spin up a fresh draft in one click. Tenant-scoped; visibility scoped by RLS."""

    __tablename__ = "contract_templates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    contract_type: Mapped[str] = mapped_column(String(50), default="other")
    body: Mapped[str] = mapped_column(Text, default="")
    default_currency: Mapped[str] = mapped_column(String(3), default="USD")
    default_term_months: Mapped[int] = mapped_column(Integer, default=12)
    default_renewal_type: Mapped[str] = mapped_column(String(20), default="none")
    default_risk_level: Mapped[str] = mapped_column(String(20), default="low")
    default_governing_law: Mapped[str] = mapped_column(String(100), default="")
    default_tags: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ApiKey(Base):
    """Long-lived bearer token for headless integrations (CI / scripts / 3rd-party apps). Stored
    as a SHA-256 hash; the plaintext is only returned once at creation time. Tenant-scoped + role-
    inherited from the creator (key acts on that user's behalf, with their role)."""

    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))                  # human label e.g. "CI pipeline"
    prefix: Mapped[str] = mapped_column(String(12), index=True)     # first 8 chars of the token, for display + lookup
    token_hash: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class WebhookEndpoint(Base):
    """Outbound webhook destination — the workspace's URL we POST events to. v1 covers
    contract.signed / .expired / .renewed / .completed-style events. Each delivery is signed with
    an HMAC-SHA256 (header `X-CM-Signature`) using the secret stored here."""

    __tablename__ = "webhook_endpoints"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(String(800))
    description: Mapped[str] = mapped_column(String(300), default="")
    # HMAC signing secret — encrypted at rest (Fernet/AES-256-GCM chain via secrets_box).
    # Was a plaintext VARCHAR(64); migrated by 0013_hardening. RFI §A.8.
    secret: Mapped[str] = mapped_column(EncryptedString(512))
    events: Mapped[list] = mapped_column(JSON, default=list)        # ["*"] for all, or e.g. ["contract.signed"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    last_delivery_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="")  # "" | "ok" | "failed"


class WebhookDelivery(Base):
    """One attempted POST to a webhook endpoint. Logged for visibility + retry."""

    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id"), index=True)
    event: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|ok|failed
    response_code: Mapped[int] = mapped_column(Integer, default=0)
    response_snippet: Mapped[str] = mapped_column(String(500), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class BackgroundJob(Base):
    """A user-visible long-running job (PDF generation, envelope sealing, renewals sweep, …)
    surfaced in the Progress Tray. v1 is a simple record-and-poll. Tenant-scoped."""

    __tablename__ = "background_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    type: Mapped[str] = mapped_column(String(50), index=True)  # contract.pdf | signature.seal | renewals.sweep | ocr | ...
    label: Mapped[str] = mapped_column(String(300))            # human-readable: "Generating PDF for Lease — HQ"
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)  # queued | running | succeeded | failed
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    result_summary: Mapped[str] = mapped_column(String(400), default="")
    error: Mapped[str] = mapped_column(String(600), default="")
    object_type: Mapped[str] = mapped_column(String(40), default="")
    object_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    href: Mapped[str] = mapped_column(String(400), default="")  # frontend route to open the result
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class EmailOutbox(Base):
    """All outbound email goes through here. send_email() inserts a row; the worker (or in
    eager-celery dev, immediately) attempts delivery. Per-row retry + status visible from the
    Progress Tray. (docs/14 §4)"""

    __tablename__ = "email_outbox"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(default="", index=True)  # may be "" for auth / signing-link emails
    to_email: Mapped[str] = mapped_column(String(255))
    to_name: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(400))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Obligation(Base):
    """A checklist item the workspace must do on a given contract — e.g. "renewal notice by 30d
    before end", "invoice quarterly", "deliver report by Q3". Status flows pending → done|skipped;
    a periodic sweep flips pending→overdue when due_date < today."""

    __tablename__ = "obligations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    owner_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|done|skipped|overdue
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_by_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_by_name: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SignatureTab(Base):
    """A field placed on the contract PDF for a specific recipient to fill: signature, initials,
    a date, free text or a checkbox. Coordinates are normalized (0..1 of page width/height) so
    they survive a re-render. Filled on signing; stamped onto the executed PDF on seal."""

    __tablename__ = "signature_tabs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    envelope_id: Mapped[str] = mapped_column(ForeignKey("signature_envelopes.id"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("signature_recipients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="signature")  # signature|initials|date|text|checkbox
    page: Mapped[int] = mapped_column(Integer, default=1)
    x: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1 (left)
    y: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1 (top, so 0 is top-of-page)
    width: Mapped[float] = mapped_column(Float, default=0.2)
    height: Mapped[float] = mapped_column(Float, default=0.05)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    value: Mapped[str] = mapped_column(String(500), default="")  # filled on signing
    filled_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class FileObject(Base):
    __tablename__ = "file_objects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    key: Mapped[str] = mapped_column(String(500))  # storage key (S3 key or local path)
    bucket: Mapped[str] = mapped_column(String(120), default="")  # S3 bucket, or "" for local
    backend: Mapped[str] = mapped_column(String(20), default="local")  # "s3" | "local"
    content_type: Mapped[str] = mapped_column(String(150), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    original_name: Mapped[str] = mapped_column(String(300), default="")
    kind: Mapped[str] = mapped_column(String(30), default="attachment")  # ocr_source|contract_pdf|attachment|export|...
    parent_type: Mapped[str] = mapped_column(String(30), default="")
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class OcrJob(Base):
    __tablename__ = "ocr_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|completed|failed
    file_name: Mapped[str] = mapped_column(String(300))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)  # the (stubbed) extraction
    created_contract_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
