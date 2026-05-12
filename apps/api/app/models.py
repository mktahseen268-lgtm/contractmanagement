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
