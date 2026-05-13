import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


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
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)  # base32 TOTP secret (set during setup; "active" once mfa_enabled)
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
    # the per-recipient signing-link token. Scaffold: stored as-is (the table is RLS-protected and
    # the token is high-entropy); production should store only a hash (docs/19).
    access_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
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
