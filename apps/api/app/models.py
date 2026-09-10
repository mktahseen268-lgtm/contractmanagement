import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, TypeDecorator
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
    def group_name(self) -> str:
        """Optional parent-org / group label shown above the workspace name (e.g. a holding
        company or department group). Stored in settings JSON — no dedicated column needed."""
        return (self.settings or {}).get("group_name", "")

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
    #: RFI 3.5 — only DFS/BBCORP coordinators may transmit anything to the counterparty.
    #: Other reviewers can comment internally but cannot share externally. A capability
    #: rather than a role, because it cuts across roles: a Legal reviewer is senior but is
    #: deliberately NOT client-facing.
    is_client_facing: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Which function this user reviews for, used to group the consolidated review view.
    department: Mapped[str] = mapped_column(String(100), default="")
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
    #: Which template revision generated this draft, and the form answers that did it. Kept on
    #: the contract (not just in the audit log) because "was this raised from the approved
    #: template, and with what values?" is a question asked of the contract itself.
    template_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    template_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    merge_values: Mapped[dict] = mapped_column(JSON, default=dict)
    #: The clauses assembled into this draft: [{clause_id, key, version_no, title}]. Recorded
    #: at generation so a policy review knows what the document was *supposed* to contain —
    #: otherwise a clause someone deleted wholesale is indistinguishable from one that was
    #: never required.
    included_clauses: Mapped[list] = mapped_column(JSON, default=list)
    # --- Repository structure (Phase 5) --------------------------------------------------
    #: Authoritative when set; `counterparty` stays populated so existing reports, exports and
    #: PDFs keep working. See the note on `Party`.
    party_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: Likewise authoritative over the free-text `department`.
    department_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    folder_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: Values for the tenant's `CustomFieldDef`s, keyed by field key.
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Need-to-know: when true, `ContractAccess` decides who can see this agreement. Off by
    #: default because applying an ACL to every agreement means an access-control decision on
    #: every list query, and getting that wrong at scale hides the repository rather than
    #: leaking it.
    confidential: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    #: Days before expiry to raise a renewal notice. Per-contract because a 3-year outsourcing
    #: agreement and a 3-month NDA do not need the same warning; defaults to 90/60/30.
    renewal_notice_days: Mapped[list] = mapped_column(JSON, default=list)
    #: What this amendment changed relative to its parent: {fields: {...}, clauses: {...},
    #: value_delta, term_delta_days}. Recorded at execution so the effect of an amendment is a
    #: stored fact rather than something reconstructed by comparing two documents later.
    amendment_impact: Mapped[dict] = mapped_column(JSON, default=dict)
    renewed_from_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # set on the successor when this contract was created by renewing another
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    # --- Retention tiering (Phase 0): "10 years of records, 1 year instantly searchable".
    # `archived_at` set => moved to the cold storage tier and excluded from the live search
    # index. The row itself stays queryable by reference/id, so archived contracts remain
    # retrievable — archival is a search + storage tier change, not a deletion.
    # --- Phase 4: non-standard classification (RFI 3.1) ---------------------------------
    #: Set automatically the moment the counterparty edits the document or a tracked change
    #: is accepted. A non-standard agreement takes the non-standard approval path and forces
    #: Legal into the review set — the classification is what selects the route, so it must
    #: not be a manual checkbox someone forgets to tick.
    is_non_standard: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    non_standard_reason: Mapped[str] = mapped_column(String(400), default="")
    non_standard_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # `legal_hold` blocks archival AND purge, unconditionally. Phase 8 adds matter-scoped
    # holds on top; this flag is the enforcement point both use.
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


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
    # --- Phase 4: consolidated internal review (RFI 3.3 / supplemental requirements) ---
    #: **Hard privacy flag.** An internal-only comment must be provably unreachable from any
    #: externally shared view. This is a data-leak class of bug, not a preference: a Legal
    #: note saying "do not concede clause 7 below 8%" reaching the counterparty is
    #: unrecoverable. Enforced in one place (`comment_service.visible_to`) and asserted in
    #: tests against the external surfaces.
    internal_only: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    #: Which reviewing function raised it, for the consolidated master view.
    department: Mapped[str] = mapped_column(String(100), default="")
    #: `comment` | `amendment` — a proposed change carries more weight than an observation.
    kind: Mapped[str] = mapped_column(String(20), default="comment")
    #: Anchors the comment to a text range in the contract body (Phase 3 redlining uses this).
    anchor_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
    #: Monotonic per-tenant insertion order, assigned under the same advisory lock as the
    #: chain. This is what the chain is built and verified along.
    #:
    #: `at` cannot serve: two rows written inside the same clock tick share a timestamp, and
    #: `(at, id)` then orders by a random uuid rather than by insertion. When that happened,
    #: a row could chain past its true predecessor — and deleting the skipped row left a
    #: chain that still verified, which is precisely the tampering this table exists to
    #: catch. Pre-0023 rows carry seq 0 and are ordered by `(at, id)` as before.
    seq: Mapped[int] = mapped_column(Integer, default=0, index=True)


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
    """A named approval workflow, expressed as ordered **stages** of concurrent **steps**.

    Phase 4 rebuild. The RFI is built entirely around parallel multi-stakeholder review —
    Legal, Finance, Compliance and IS looking at an agreement *at the same time*, each marking
    their own review complete without waiting for the others. The v1 shape (a flat list of
    steps, one active at a time) could not express that, and sequential review is the single
    biggest cause of the cycle times the RFI is trying to fix.

    `stages` is the current shape:

        [{"name": "Legal & Finance review",
          "policy": "all" | "any" | "quorum" | "percentage",
          "threshold": 2,            # for quorum (count) / percentage (0-100)
          "sla_hours": 48,
          "escalate_to_user_id": "...",
          "steps": [{"name": "Legal", "assignee_kind": "role", "assignee_value": "approver"},
                    {"name": "Finance", "assignee_kind": "user", "assignee_value": "u123"}]}]

    `steps` is the legacy flat list, kept so existing definitions keep working — `as_stages()`
    promotes it to one-step-per-stage, which is exactly the old sequential behaviour.
    """

    __tablename__ = "workflow_definitions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | archived
    default_for_types: Mapped[list] = mapped_column(JSON, default=list)  # contract types this is the default workflow for
    steps: Mapped[list] = mapped_column(JSON, default=list)  # legacy flat list — see as_stages()
    stages: Mapped[list] = mapped_column(JSON, default=list)
    #: Applied when this workflow runs on a contract classified non-standard (RFI §3.1) —
    #: typically forcing Legal into the review set.
    non_standard_stages: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    def as_stages(self, *, non_standard: bool = False) -> list[dict]:
        """The stage graph to run, whatever shape this definition was authored in."""
        if non_standard and self.non_standard_stages:
            return list(self.non_standard_stages)
        if self.stages:
            return list(self.stages)
        # Legacy definition: one step per stage IS sequential review.
        return [
            {
                "name": str(s.get("name") or f"Step {i + 1}"),
                "policy": "all",
                "steps": [s],
            }
            for i, s in enumerate(self.steps or [])
        ]


class ApprovalRule(Base):
    """Dynamic approval matrix — *who* must review, decided from the contract's own attributes.

    RFP §4a "Dynamic approval matrix: value thresholds, risk categories, dept-specific
    approvers". A fixed workflow per contract type cannot express "anything over 10 million
    also needs the CFO" without duplicating the whole workflow per band.

    Rules ADD stages to a run rather than replacing it: the base workflow says how a contract
    of this type is normally reviewed, and matching rules layer on the extra scrutiny its
    value, risk or jurisdiction demands. Evaluated at run start and re-evaluated when a
    material field changes, with the re-route audited.
    """

    __tablename__ = "approval_rules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Conditions. Empty/NULL means "any" and never narrows the match.
    contract_type: Mapped[str] = mapped_column(String(50), default="")
    department: Mapped[str] = mapped_column(String(100), default="")
    currency: Mapped[str] = mapped_column(String(3), default="")
    min_value: Mapped[float] = mapped_column(Float, default=0.0)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="")
    governing_law: Mapped[str] = mapped_column(String(100), default="")
    #: Fires only when the contract is flagged non-standard (RFI §3.1).
    non_standard_only: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Fires when the playbook deviation count reaches this (Phase 3 feeds it). 0 = ignore.
    min_playbook_deviations: Mapped[int] = mapped_column(Integer, default=0)
    # What the rule adds: one stage, appended at `insert_after_stage` (-1 = end).
    stage_name: Mapped[str] = mapped_column(String(200), default="")
    stage_policy: Mapped[str] = mapped_column(String(20), default="all")
    stage_threshold: Mapped[int] = mapped_column(Integer, default=0)
    stage_steps: Mapped[list] = mapped_column(JSON, default=list)
    sla_hours: Mapped[int] = mapped_column(Integer, default=0)
    escalate_to_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    insert_after_stage: Mapped[int] = mapped_column(Integer, default=-1)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Delegation(Base):
    """Out-of-office proxy. RFP §4a "Delegation / out-of-office proxy approvers".

    Assignments route to the proxy automatically for the window, and **both** the principal
    and the proxy appear in the audit trail — an approval given under delegation must never
    look like the principal personally approved it.
    """

    __tablename__ = "delegations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    from_user_id: Mapped[str] = mapped_column(String(32), index=True)
    to_user_id: Mapped[str] = mapped_column(String(32), index=True)
    #: `all` or a contract type. Narrow delegation is common — "Ali covers my NDAs only".
    scope: Mapped[str] = mapped_column(String(50), default="all")
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    reason: Mapped[str] = mapped_column(String(400), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Holiday(Base):
    """Non-working days for the SLA clock.

    An SLA measured in wall-clock hours is wrong for a bank: a request raised at 16:00 on a
    Friday before Eid is not overdue on Saturday morning. The business calendar is what makes
    "48-hour SLA" mean what a reviewer thinks it means.
    """

    __tablename__ = "holidays"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    day: Mapped[dt.date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Mention(Base):
    """An @mention of a user inside a comment. RFI §3.4.

    A row rather than a JSON blob on the comment, because the useful query is the inverse —
    "everything that mentions me" for the inbox filter — and that has to be indexed.
    """

    __tablename__ = "mentions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    comment_id: Mapped[str] = mapped_column(String(32), index=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    mentioned_user_id: Mapped[str] = mapped_column(String(32), index=True)
    mentioned_by: Mapped[str] = mapped_column(String(32), default="")
    mentioned_by_name: Mapped[str] = mapped_column(String(200), default="")
    #: Carried from the comment so an internal-only mention never leaks into an external view.
    internal_only: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    definition_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    definition_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)  # running | approved | rejected | changes_requested | cancelled
    current_index: Mapped[int] = mapped_column(Integer, default=0)   # legacy step pointer
    started_by: Mapped[str] = mapped_column(String(32))
    started_by_name: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # --- Phase 4: stage graph ---------------------------------------------------------
    #: The stage definitions, **snapshotted at start**. A definition edited mid-review must
    #: not silently change the rules an in-flight approval is being judged by.
    stages: Mapped[list] = mapped_column(JSON, default=list)
    current_stage: Mapped[int] = mapped_column(Integer, default=0, index=True)
    #: Rules from the approval matrix that fired, for the audit trail and re-evaluation.
    applied_rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    #: Snapshot of the fields the matrix was evaluated against, so a material change can be
    #: detected and the run re-routed.
    routing_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


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
    # --- Phase 4 ---------------------------------------------------------------------
    #: Which stage this step belongs to. Every step in a stage goes active together — that
    #: is what makes the review parallel.
    stage_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    #: Business hours allowed for this decision. 0 = no SLA.
    sla_hours: Mapped[int] = mapped_column(Integer, default=0)
    #: When it becomes overdue, computed on the business calendar (not wall-clock).
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    reminded_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    escalated_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Set when the assignment was routed to a proxy. BOTH parties stay visible — an approval
    #: given under delegation must never read as though the principal gave it personally.
    delegated_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: A reviewer added after the run started (RFI §3.6), and who added them.
    added_mid_flight: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: When this step went active — the denominator for cycle-time and SLA-adherence metrics.
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


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
    # --- Execution reliability (Phase 2 §8) ------------------------------------------
    # RFP §4a(ii) 4.4 asks for a signing process "free from execution/signature failures".
    # You cannot claim that without being able to see the failures, so sealing records its
    # own outcome instead of only logging it.
    #   pending  — not yet attempted
    #   sealed   — executed PDF + certificate produced
    #   partial  — produced, but at least one signatory's cryptographic signature failed
    #   failed   — sealing did not produce a document; `seal_error` says why
    # No `index=True`: the query that matters is the dead-letter sweep, which filters on
    # (tenant_id, seal_status) together — migration 0017 creates that composite index. A
    # second single-column index would be dead weight on every write.
    seal_status: Mapped[str] = mapped_column(String(20), default="pending")
    seal_attempts: Mapped[int] = mapped_column(Integer, default=0)
    seal_error: Mapped[str] = mapped_column(String(1000), default="")
    seal_last_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    #: Bumped on every state transition. `signing_service` checks it before writing, so two
    #: concurrent signers cannot both advance the envelope from the same starting state.
    lock_version: Mapped[int] = mapped_column(Integer, default=0)
    #: `electronic` (default) · `hybrid` (some parties sign on paper) · `wet` (all on paper).
    execution_mode: Mapped[str] = mapped_column(String(20), default="electronic")

    # --- Chasing and expiry (Phase 10, bulk send) -------------------------------------
    # These live on the envelope rather than on the bulk batch that usually sets them. An
    # envelope sent one at a time from the contract page needs chasing just as much as one of
    # five hundred, and a reminder schedule that only exists for bulk sends would have to be
    # reimplemented the first time somebody asked for it here.
    #: When the whole envelope stops being signable. NULL = never (the previous behaviour;
    #: the per-recipient link still expires on its own `access_token_expires_at`).
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    #: 0 disables automatic chasing. Manual "remind now" is unaffected either way.
    reminder_interval_days: Mapped[int] = mapped_column(Integer, default=0)
    max_reminders: Mapped[int] = mapped_column(Integer, default=0)
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


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
    signed_name: Mapped[str] = mapped_column(String(200), default="")  # the typed/legal name on record
    # How the signer adopted their mark, and (for drawn/uploaded) the captured image.
    #  - signature_kind: 'typed' (default — render '/s/ name' text) | 'drawn' | 'uploaded'.
    #  - signature_image: a base64 PNG/JPEG *data URL* (e.g. 'data:image/png;base64,…'); NULL for
    #    typed. Capped at ~1 MB decoded (validated in signing_service.sign). Stamped into the
    #    executed PDF (Signatures page + signature tabs) when present.
    signature_kind: Mapped[str] = mapped_column(String(20), default="typed")
    signature_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    signed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    declined_reason: Mapped[str] = mapped_column(String(500), default="")
    # --- PKI binding (Phase 2) -------------------------------------------------------
    # Which identity this recipient *is*, so the sealer can find the certificate to sign
    # with. Exactly one is normally set: `signer_user_id` for an internal user,
    # `party_ref` for an external signatory enrolled through the visitor flow.
    # Without these the sealer would have to guess, and guessing means falling back to a
    # shared certificate — the thing the RFP forbids.
    signer_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    party_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: The certificate actually used, recorded once the document is cryptographically signed.
    certificate_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: How this signatory's identity was bound (`sso`, `email_otp`, `sms_otp`, `internal`),
    #: plus the evidence — masked identifier, channel, IP, user agent, timestamp.
    identity_method: Mapped[str] = mapped_column(String(30), default="")
    identity_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    identity_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    #: `electronic` (default) or `wet` — which path THIS party takes. A hybrid envelope has
    #: both, which is the whole point: one government counterparty signing on paper must not
    #: force everyone else off the electronic flow.
    signing_mode: Mapped[str] = mapped_column(String(20), default="electronic")
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
    #: Derived from `status` (see below) and kept in step by `template_service`. Defaults to
    #: False so it agrees with the `draft` default: a template nobody has approved must not
    #: come into existence usable. `0001_initial` builds a fresh schema straight from these
    #: models, so a mismatch here would ship as a real one.
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # --- Merge fields and approval (Phase 3) ---------------------------------------------
    #: The intake form: a list of typed field definitions (see `app/merge_engine.py`). This is
    #: what turns a template from "a body someone edits by hand" into "select the agreement
    #: type, fill the form, the draft generates itself" (RFI 2.3).
    fields: Mapped[list] = mapped_column(JSON, default=list)
    #: draft | pending_approval | active | retired. `is_active` is kept in step with this for
    #: existing callers, but `status` is the authoritative one — a template awaiting legal
    #: approval is neither active nor archived, which a boolean cannot express.
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    effective_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    retired_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str] = mapped_column(String(32), default="")
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    approval_note: Mapped[str] = mapped_column(String(500), default="")


class Clause(Base):
    """One piece of approved contract language.

    The library is what makes "standard wording" a fact rather than an intention: a template
    composes clauses by reference (`[[clause:key]]`), so improving a clause improves every
    template that uses it, and a deviation from it is detectable rather than a matter of
    someone reading carefully.

    **Alternatives are clauses too.** A fallback position for a negotiation is `parent_id`-
    linked to the clause it softens, rather than living in its own table. That is not a
    shortcut: an alternative is wording that will end up in a signed agreement, so it needs
    the same approval gate and the same version history as anything else here. Giving it a
    lesser model would be the shortcut.
    """

    __tablename__ = "clauses"
    __table_args__ = (
        Index("ix_clause_key", "tenant_id", "key", unique=True),
        Index("ix_clause_lookup", "tenant_id", "category", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    #: Stable handle used in template bodies. Immutable once the clause is approved, because
    #: templates in the wild point at it.
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(80), default="", index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    #: preferred | acceptable | fallback — the negotiating position this wording represents,
    #: which is what a reviewer actually needs to know when a counterparty pushes back.
    position: Mapped[str] = mapped_column(String(20), default="preferred")
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    #: draft | pending_approval | active | retired. Same gate as templates.
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    #: Set on an alternative: the clause this is a fallback for.
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: Order among a clause's alternatives — 1 is the first fallback to reach for.
    fallback_rank: Mapped[int] = mapped_column(Integer, default=0)
    #: When to use this wording. Shown to whoever is negotiating.
    guidance: Mapped[str] = mapped_column(Text, default="")
    jurisdiction: Mapped[str] = mapped_column(String(100), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    approved_by: Mapped[str] = mapped_column(String(32), default="")
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    approval_note: Mapped[str] = mapped_column(String(500), default="")
    retired_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ClauseVersion(Base):
    """A frozen snapshot of a clause at the moment it was approved.

    Same reason as `ContractTemplateVersion`: an agreement signed last year was signed against
    the wording in force then, and the live row cannot answer that once it has been edited.
    """

    __tablename__ = "clause_versions"
    __table_args__ = (
        Index("ix_clause_version", "clause_id", "version_no", unique=True),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    clause_id: Mapped[str] = mapped_column(String(32), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[str] = mapped_column(String(20), default="preferred")
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    #: active | superseded | retired
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    change_summary: Mapped[str] = mapped_column(String(500), default="")
    approved_by: Mapped[str] = mapped_column(String(32), default="")
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ExtractionReview(Base):
    """A captured set of fields awaiting human confirmation.

    Extraction never writes to a contract. A confidence score is not a fact — a document
    saying "the term is 12 months from the Effective Date" and a model guessing which date
    that is produces a plausible, wrong end date that then drives renewal reminders. So the
    capture lands here, a person ticks what is right, and what they accepted is audited.
    """

    __tablename__ = "extraction_reviews"
    __table_args__ = (
        Index("ix_extraction_contract", "tenant_id", "contract_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    file_name: Mapped[str] = mapped_column(String(300), default="")
    #: Which provider produced this. `stub` means it did NOT read the document.
    provider: Mapped[str] = mapped_column(String(40), default="stub")
    #: {field: {value, confidence}}
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    detected_clauses: Mapped[list] = mapped_column(JSON, default=list)
    #: pending | applied | discarded
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    applied_fields: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_by: Mapped[str] = mapped_column(String(32), default="")
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Playbook(Base):
    """The policy an agreement is measured against: which clauses must appear, which must not.

    Without this the clause library is a well-organised text store. With it, "is this draft
    within policy?" is a question the system answers on every revision instead of a question
    that depends on which reviewer read which paragraph.

    `rules` is JSON, matching `WorkflowDefinition.stages` — these are read as a whole set every
    time and never queried individually, so a child table would buy nothing.
    Each rule: {clause_key, kind: required|prohibited|preferred, severity: blocker|warning,
    guidance}.
    """

    __tablename__ = "playbooks"
    __table_args__ = (
        Index("ix_playbook_scope", "tenant_id", "contract_type", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(String(500), default="")
    #: Empty string means "every type" — a house-wide policy.
    contract_type: Mapped[str] = mapped_column(String(50), default="")
    #: Narrowing conditions: {min_value, max_value, department, risk_level}. A rule set that
    #: only bites above PKR 10m is a different policy from one that always applies.
    applies_when: Mapped[dict] = mapped_column(JSON, default=dict)
    rules: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ContractTemplateVersion(Base):
    """A frozen snapshot of a template at the moment it was approved.

    Templates change. Agreements generated from them do not, and two years later somebody has
    to answer "which approved wording did this contract come from?". The live template row
    cannot answer that once it has been edited, so every approved revision is snapshotted here
    and each generated contract records the version number it used.
    """

    __tablename__ = "contract_template_versions"
    __table_args__ = (
        Index("ix_ctv_template_version", "template_id", "version_no", unique=True),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    #: active | superseded | retired
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    change_summary: Mapped[str] = mapped_column(String(500), default="")
    approved_by: Mapped[str] = mapped_column(String(32), default="")
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


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
    # `email` | `sms` (Phase 2). One outbox for both so delivery is auditable in one place —
    # but the SMTP flush beat MUST filter on this, or it will try to email a phone number.
    channel: Mapped[str] = mapped_column(String(10), default="email", index=True)
    #: Gateway/provider reference for the sent message, when the provider returns one.
    provider_ref: Mapped[str] = mapped_column(String(200), default="")


class WebAuthnCredential(Base):
    """A registered passkey.

    The public key is stored; there is no private key here and never can be — which is the
    property that makes a passkey phishing-resistant and also means a database breach does
    not yield anything an attacker can authenticate with.
    """

    __tablename__ = "webauthn_credentials"
    __table_args__ = (
        Index("ix_webauthn_credential", "credential_id", unique=True),
        Index("ix_webauthn_user", "tenant_id", "user_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    #: Base64url, as it travels on the wire.
    credential_id: Mapped[str] = mapped_column(String(400))
    public_key: Mapped[str] = mapped_column(Text)
    #: The authenticator's counter. A value no higher than the one last seen means a clone or
    #: a replay — the one clone-detection signal WebAuthn provides.
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(120), default="Security key")
    transports: Mapped[str] = mapped_column(String(120), default="")
    #: True for a synced passkey (iCloud, Google). Worth knowing: a synced credential is
    #: recoverable by the user but also present on every device their account touches.
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)
    aaguid: Mapped[str] = mapped_column(String(64), default="")
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CustomRole(Base):
    """A tenant-defined role and the permissions it carries.

    The five built-in roles stay: they are what every existing check reads, and replacing them
    wholesale would mean auditing every `user.role ==` in the codebase at once. A custom role
    instead *names* a built-in as its base and adds or removes individual permissions, so an
    unrecognised custom role still degrades to a known set rather than to no access at all.
    """

    __tablename__ = "custom_roles"
    __table_args__ = (Index("ix_custom_role_key", "tenant_id", "key", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    key: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400), default="")
    #: The built-in role this starts from — owner|admin|manager|approver|author|viewer.
    base_role: Mapped[str] = mapped_column(String(20), default="viewer")
    #: Permissions added on top of the base.
    grants: Mapped[list] = mapped_column(JSON, default=list)
    #: Permissions removed from the base. Applied after grants, so a revoke always wins —
    #: "this role must never do X" has to be unconditional to be worth writing down.
    revokes: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ContractAccess(Base):
    """Need-to-know access to one agreement.

    Only consulted for agreements marked `confidential`. Applying an ACL to everything would
    mean an access-control decision on every list query, and the failure mode of getting that
    wrong at scale is a repository nobody can see rather than one that leaks.
    """

    __tablename__ = "contract_access"
    __table_args__ = (
        Index("ix_access_lookup", "tenant_id", "contract_id", "user_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    #: One of these is set, not both.
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: read | write
    level: Mapped[str] = mapped_column(String(10), default="read")
    reason: Mapped[str] = mapped_column(String(400), default="")
    granted_by: Mapped[str] = mapped_column(String(32), default="")
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class LegalHold(Base):
    """A matter-scoped hold that blocks deletion, purge and archival.

    Matter-scoped rather than a boolean on the contract, because two matters can cover the
    same agreement and releasing one must not release the other. `Contract.legal_hold` stays
    as the fast flag every existing check already reads; it is derived from whether any
    active hold covers the agreement.
    """

    __tablename__ = "legal_holds"
    __table_args__ = (Index("ix_hold_matter", "tenant_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    matter: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(String(100), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    #: Agreements covered. A list rather than a join table: a hold covers tens of agreements,
    #: is read whole, and never queried by contract alone.
    contract_ids: Mapped[list] = mapped_column(JSON, default=list)
    #: active | released
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    custodian: Mapped[str] = mapped_column(String(200), default="")
    placed_by: Mapped[str] = mapped_column(String(32), default="")
    placed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    released_by: Mapped[str] = mapped_column(String(32), default="")
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    release_reason: Mapped[str] = mapped_column(String(500), default="")


class TemporaryAccess(Base):
    """A time-bound link for an external collaborator — the negotiation room.

    Scoped, expiring and revocable. The token is stored as a hash only, like every other
    bearer credential here: a link that leaks from a mailbox must not be replayable from the
    database if the database itself is later exposed.
    """

    __tablename__ = "temporary_access"
    __table_args__ = (
        Index("ix_temp_access_lookup", "tenant_id", "contract_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200), default="")
    organisation: Mapped[str] = mapped_column(String(200), default="")
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    #: view | comment — a collaborator can be allowed to discuss without editing.
    scope: Mapped[str] = mapped_column(String(20), default="view")
    #: active | expired | revoked
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    #: Watermarks name the viewer, so a screenshot carries its source.
    watermark: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_download: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    granted_by: Mapped[str] = mapped_column(String(32), default="")
    revoked_by: Mapped[str] = mapped_column(String(32), default="")
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class StepUpChallenge(Base):
    """A re-authentication a user must pass before a sensitive action.

    Short-lived and single-use. Bound to the action *and* the object, so a challenge passed to
    reveal one webhook secret cannot be replayed to reveal another — which is what a
    session-scoped "recently authenticated" flag would allow.
    """

    __tablename__ = "step_up_challenges"
    __table_args__ = (Index("ix_stepup_lookup", "tenant_id", "user_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(40), default="")
    object_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: pending | satisfied | expired | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    #: password | totp — what the user actually presented.
    method: Mapped[str] = mapped_column(String(20), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    satisfied_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class SanctionsEntry(Base):
    """One name from a sanctions list snapshot, held locally.

    **Not tenant-scoped.** OFAC's list is the same list for everybody, and a per-tenant copy
    would multiply a 20,000-row list by the number of workspaces for no gain. Screening
    results *are* tenant-scoped; the source data is not.

    Held locally because the RFP forbids a runtime dependency on a foreign-hosted service, and
    screening is exactly where that bites: a check that fails open because a US endpoint was
    unreachable is a control that does not exist.
    """

    __tablename__ = "sanctions_entries"
    __table_args__ = (
        Index("ix_sanctions_lookup", "source", "is_active"),
        Index("ix_sanctions_name", "name_key"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    #: OFAC | UN | EU | HMT | LOCAL
    source: Mapped[str] = mapped_column(String(20), index=True)
    list_name: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(400))
    #: Normalised for matching: unaccented, lower case, noise words dropped.
    name_key: Mapped[str] = mapped_column(String(400), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    entity_type: Mapped[str] = mapped_column(String(30), default="unknown")
    country: Mapped[str] = mapped_column(String(100), default="")
    programme: Mapped[str] = mapped_column(String(200), default="")
    reference: Mapped[str] = mapped_column(String(100), default="")
    #: The date of the snapshot this row came from. A screen is only as current as this.
    snapshot_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    #: False once a newer snapshot supersedes it. Kept rather than deleted so a past screening
    #: result can still be explained against the list that produced it.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class SanctionsScreening(Base):
    """The result of screening one party, kept whether or not anything matched.

    A clean screen is recorded too: "we checked on this date and found nothing" is the fact an
    auditor asks for, and it cannot be reconstructed from an absence of records.
    """

    __tablename__ = "sanctions_screenings"
    __table_args__ = (
        Index("ix_screening_queue", "tenant_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    party_id: Mapped[str] = mapped_column(String(32), index=True)
    #: Denormalised so the queue reads without joining, and so the record still says who was
    #: screened if the party is later renamed.
    party_name: Mapped[str] = mapped_column(String(300), default="")
    #: [{entry_id, name, source, score, confidence, matched_on, ...}]
    hits: Mapped[list] = mapped_column(JSON, default=list)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    #: clear | review | cleared | confirmed
    status: Mapped[str] = mapped_column(String(20), default="clear", index=True)
    threshold: Mapped[float] = mapped_column(Float, default=0.85)
    #: The oldest active list snapshot at the time — the screen is only as good as its
    #: stalest list, so this is what gets reported.
    list_snapshot_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    screened_by: Mapped[str] = mapped_column(String(32), default="")
    decided_by: Mapped[str] = mapped_column(String(32), default="")
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class TerminationRequest(Base):
    """A request to end an agreement early, and who signed off on it.

    Terminating is not a status change somebody types into a form: it ends obligations, may
    trigger notice periods and exit fees, and Legal, Compliance and Finance all have a stake.
    So it is a record with its own approvals, and the notice served on the counterparty is
    generated from it rather than written by hand.
    """

    __tablename__ = "termination_requests"
    __table_args__ = (
        Index("ix_termination_contract", "tenant_id", "contract_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    #: convenience | cause | mutual | expiry | regulatory
    reason_code: Mapped[str] = mapped_column(String(30), default="convenience")
    reason: Mapped[str] = mapped_column(Text, default="")
    #: The day the agreement actually ends — usually today plus the notice period.
    effective_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    notice_days: Mapped[int] = mapped_column(Integer, default=0)
    #: [{file_id, name}] — the evidence supporting the request.
    documents: Mapped[list] = mapped_column(JSON, default=list)
    #: pending | approved | rejected | executed | withdrawn
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    #: [{role, user_id, name, decision, at, comment}] — one entry per stakeholder sign-off.
    approvals: Mapped[list] = mapped_column(JSON, default=list)
    #: Roles that must approve before this can be executed.
    required_roles: Mapped[list] = mapped_column(JSON, default=list)
    notice_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(32), default="")
    requested_by_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class LegalChecklist(Base):
    """A checklist Legal (or any other function) publishes for everyone to work against.

    Versioned because a checklist that changes silently cannot be used as evidence that a
    given agreement met the requirements in force at the time.
    """

    __tablename__ = "legal_checklists"
    __table_args__ = (
        Index("ix_checklist_lookup", "tenant_id", "status", "contract_type"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    #: Which function owns it — Legal, Compliance, Finance, …
    owner_function: Mapped[str] = mapped_column(String(80), default="Legal")
    #: Empty means it applies to every agreement type.
    contract_type: Mapped[str] = mapped_column(String(50), default="")
    #: [{text, required, guidance}]
    items: Mapped[list] = mapped_column(JSON, default=list)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    #: draft | published | retired
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    #: Optional uploaded document backing the checklist.
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Party(Base):
    """A counterparty as a record rather than a string.

    `Contract.counterparty` was free text, which means "Acme Trading (Pvt) Ltd", "Acme Trading
    Private Limited" and "ACME TRADING" are three different vendors as far as any report is
    concerned. That is the whole reason a vendor master exists: you cannot ask "what is our
    total exposure to Acme?" of a text column.

    The free-text field is kept and populated alongside `party_id` — every existing contract,
    report, export and PDF reads it, and migrating them all in one change would be a much
    larger blast radius than the problem justifies. `party_id` is authoritative when set.
    """

    __tablename__ = "parties"
    __table_args__ = (
        Index("ix_party_lookup", "tenant_id", "name"),
        Index("ix_party_registration", "tenant_id", "registration_no"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(300))
    #: Normalised for duplicate detection: case-folded, punctuation and entity suffixes
    #: stripped. Stored rather than computed so the check is an index lookup, not a scan.
    name_key: Mapped[str] = mapped_column(String(300), default="", index=True)
    registration_no: Mapped[str] = mapped_column(String(100), default="")
    entity_type: Mapped[str] = mapped_column(String(50), default="company")
    jurisdiction: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(100), default="", index=True)
    #: none | pending | verified | rejected
    kyc_status: Mapped[str] = mapped_column(String(20), default="none", index=True)
    kyc_note: Mapped[str] = mapped_column(String(500), default="")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    #: [{name, file_id, uploaded_at}] — compliance documents held for this party.
    documents: Mapped[list] = mapped_column(JSON, default=list)
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    contact_phone: Mapped[str] = mapped_column(String(64), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    #: Set when someone onboarded this despite a duplicate warning. Kept with the reason,
    #: because "we knew and did it anyway" is a different fact from "nobody noticed".
    duplicate_override_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duplicate_override_reason: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ContractRelation(Base):
    """A typed link between two agreements.

    An addendum that is merely "related to" its parent cannot answer "what is actually in force
    between us and this vendor today?" — which is the question the repository exists to answer.
    So the relation is typed, directional, and carries the addendum sequence.
    """

    __tablename__ = "contract_relations"
    __table_args__ = (
        Index("ix_relation_parent", "tenant_id", "parent_id", "kind"),
        Index("ix_relation_child", "tenant_id", "child_id"),
        Index("ix_relation_unique", "parent_id", "child_id", "kind", unique=True),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    #: The agreement being referred to (the original).
    parent_id: Mapped[str] = mapped_column(String(32), index=True)
    #: The agreement doing the referring (the addendum / amendment / renewal).
    child_id: Mapped[str] = mapped_column(String(32), index=True)
    #: addendum_of | amendment_of | renewal_of | supersedes | related_to
    kind: Mapped[str] = mapped_column(String(30), default="related_to", index=True)
    #: Sequential per parent for addenda — "Addendum No. 3", not "an addendum".
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Department(Base):
    """A department as a record, for the same reason as `Party`: free text cannot be reported
    on, assigned to, or given a lead."""

    __tablename__ = "departments"
    __table_args__ = (Index("ix_department_name", "tenant_id", "name", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(150))
    lead_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_centre: Mapped[str] = mapped_column(String(60), default="")
    region: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Folder(Base):
    """A node in the repository tree.

    `path` is materialised (``/Legal/Vendors/2026``) so "everything under Legal" is a prefix
    match rather than a recursive walk — the query the repository actually runs.
    """

    __tablename__ = "folders"
    __table_args__ = (
        Index("ix_folder_path", "tenant_id", "path", unique=True),
        Index("ix_folder_parent", "tenant_id", "parent_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(150))
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    path: Mapped[str] = mapped_column(String(1000), default="")
    #: Roles allowed to see this subtree. Empty means "everyone in the workspace".
    visible_to_roles: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CustomFieldDef(Base):
    """A tenant-defined field on a contract type.

    Reuses the merge-engine field vocabulary (`text|number|money|date|select|…`) rather than
    inventing a second type system — the intake form and custom fields are the same idea
    applied at different points, and two vocabularies would drift.
    """

    __tablename__ = "custom_field_defs"
    __table_args__ = (
        Index("ix_custom_field_key", "tenant_id", "contract_type", "key", unique=True),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    #: Empty means the field applies to every contract type.
    contract_type: Mapped[str] = mapped_column(String(50), default="", index=True)
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200), default="")
    #: One of `merge_engine.FIELD_TYPES`.
    type: Mapped[str] = mapped_column(String(20), default="text")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[list] = mapped_column(JSON, default=list)
    help: Mapped[str] = mapped_column(String(500), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


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
    # Retention tiering (Phase 0). "cold" objects live under `archive_storage_prefix` inside
    # the same bucket — still inside the deployment, just off the hot tier. `key` is rewritten
    # to the cold key when the object moves, so reads keep working with no special-casing.
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    storage_tier: Mapped[str] = mapped_column(String(10), default="hot")  # hot|cold


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


# ---------------------------------------------------------------------------------------
# PKI (Phase 1) — in-platform Certificate Authority.
#
# The RFP requires an in-house CA with enrolment, issuance, renewal, suspension, revocation,
# CRL publication and an OCSP responder, with HSM-protected keys and **one certificate per
# signatory** (shared or role certificates are explicitly forbidden). See docs/PKI-ARCHITECTURE.md.
#
# Private keys never live in these tables. A row carries a `key_id` handle that the KeyStore
# resolves — an encrypted blob for SoftKeyStore, a PKCS#11 object label for Pkcs11KeyStore,
# where the key is generated inside the HSM and cannot be exported.
# ---------------------------------------------------------------------------------------


class WetSignatureAttestation(Base):
    """Evidence that a physically-signed copy was received, and what it is.

    RFP §4a "Hybrid flexibility": some counterparties — government bodies especially — will
    not sign electronically. They need a printed pack, a wet signature and a company stamp,
    and the executed paper scanned back. Without this the digital trail simply stops at the
    print button, and the agreement's provenance lives in someone's email.

    The attestation is what makes a scan admissible alongside a cryptographic signature. A
    scanned image proves nothing on its own — anyone can scan anything. What carries weight
    is a named person inside the bank asserting, in an append-only audit chain, that *this
    file* (by SHA-256) is the executed copy of *this agreement*, received on *this date*,
    optionally witnessed. That assertion is the evidence; the image is the artefact.

    Deliberately not a signature record: `SignatureRecipient.status` still moves to `signed`
    so the hybrid and electronic paths converge on one status flow, but the *nature* of the
    evidence stays distinguishable — the Certificate of Completion must never present a
    scanned page as though it were a cryptographic signature.
    """

    __tablename__ = "wet_signature_attestations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    envelope_id: Mapped[str] = mapped_column(ForeignKey("signature_envelopes.id"), index=True)
    #: NULL means the attestation covers the whole envelope (all parties signed one paper copy).
    recipient_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: The scanned executed copy.
    file_id: Mapped[str] = mapped_column(String(32), index=True)
    #: SHA-256 of the scan, copied here so the attestation stands on its own even if the file
    #: row is later moved to the cold tier or re-keyed.
    file_sha256: Mapped[str] = mapped_column(String(64), default="")
    #: When the parties actually signed the paper — which is NOT when it was uploaded, and is
    #: the date that governs the agreement.
    declared_execution_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    signatory_name: Mapped[str] = mapped_column(String(200), default="")
    signatory_designation: Mapped[str] = mapped_column(String(200), default="")
    witness_name: Mapped[str] = mapped_column(String(200), default="")
    witness_designation: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(String(1000), default="")
    #: The bank employee making the assertion. This is the accountable party.
    attested_by: Mapped[str] = mapped_column(String(32), default="")
    attested_by_name: Mapped[str] = mapped_column(String(200), default="")
    attested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    ip: Mapped[str] = mapped_column(String(64), default="")


class SigningInvitation(Base):
    """A shareable, reusable signing link for external signatories — the "visitor" surface.

    RFP §4a: merchants, customers and counterparties must be able to sign **without any
    per-visitor user provisioning**, reached by web link, branch-tablet kiosk, mobile link or
    QR code, and the deployment must carry 100,000 external signatories a year.

    The existing `/sign/{token}` portal requires a `SignatureRecipient` row minted in advance
    by staff, which does not scale to that and cannot serve a walk-in. An invitation inverts
    it: staff publish one link per document (or per branch), and each visitor who opens it
    creates their own session, proves who they are by OTP, and gets a recipient row and a
    certificate minted on the spot.

    The raw token is never stored — same hash-plus-encrypted-secret construction as
    `SignatureRecipient`, so a database leak cannot reconstruct a working URL, but the server
    can still re-render the QR code.
    """

    __tablename__ = "signing_invitations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_secret: Mapped[str | None] = mapped_column(EncryptedString(512), nullable=True)
    #: `email`, `sms`, or `any` (the visitor picks). Drives which identifier is collected.
    otp_channel: Mapped[str] = mapped_column(String(10), default="any")
    require_otp: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Optional CNIC capture. Only the last four digits are ever persisted — see visitor_service.
    collect_cnic: Mapped[bool] = mapped_column(Boolean, default=False)
    #: 0 = unlimited. A branch kiosk link is unlimited; a link for one named merchant is 1.
    max_signatures: Mapped[int] = mapped_column(Integer, default=0)
    signature_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class VisitorSession(Base):
    """One external signatory's journey through a `SigningInvitation`.

    Holds the identity binding and the consent evidence that make the resulting signature
    defensible: which channel proved the identity, the masked identifier, when the document
    was actually read, and the network context. All of it is copied onto the Certificate of
    Completion, because "an OTP was sent to a number ending 4417 at 14:03 and the document was
    scrolled to the end before signing" is the part that survives being challenged.

    Deliberately NOT a `User`: a visitor never gets an account, a password, or a login.
    """

    __tablename__ = "visitor_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("signing_invitations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    #: Last four digits only. A full CNIC is sensitive PII with no operational value here —
    #: the last four are enough to reconcile against a branch record.
    cnic_last4: Mapped[str] = mapped_column(String(4), default="")

    otp_channel: Mapped[str] = mapped_column(String(10), default="email")
    otp_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    otp_sent_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    #: Stable identifier this visitor's certificate is bound to (`Certificate.subject_party_id`).
    party_ref: Mapped[str] = mapped_column(String(64), index=True, default="")
    recipient_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    certificate_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- consent evidence ---
    opened_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    #: Set only when the viewer actually reached the end of the document.
    scroll_completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    pages_viewed: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    #: `web` | `kiosk` | `mobile` | `qr` — how the visitor arrived, for the MIS breakdown.
    entry_point: Mapped[str] = mapped_column(String(20), default="web")

    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    device_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    geo: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="started", index=True)
    # started|otp_sent|verified|signed|abandoned|blocked
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class SignatoryAuthority(Base):
    """Who is authorised to sign what — the delegation-of-authority matrix.

    RFP §4a(ii) 4.1–4.2: signatories must be tagged per an authority matrix rather than picked
    freely. A rule matches on department, contract type, currency and a value band; the
    narrowest matching rule wins. When an envelope is prepared, the system proposes the
    signatory the matrix requires; choosing someone else is an **override** that demands a
    reason and is audited.

    Deliberately advisory rather than blocking: a bank sometimes has to execute an agreement
    with a deputy while the authorised signatory is unreachable, and a system that made that
    impossible would be routed around entirely. Making the deviation visible and attributable
    is the control that actually holds.
    """

    __tablename__ = "signatory_authorities"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Match conditions. Empty string / NULL means "any" — an unset field never narrows a rule.
    department: Mapped[str] = mapped_column(String(100), default="")
    contract_type: Mapped[str] = mapped_column(String(50), default="")
    currency: Mapped[str] = mapped_column(String(3), default="")
    min_value: Mapped[float] = mapped_column(Float, default=0.0)
    #: NULL = unbounded upper band.
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Required signatory: a named user, or any user holding a role.
    required_role: Mapped[str] = mapped_column(String(40), default="")
    required_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: How many signatories matching this rule the envelope needs (joint signatures).
    signatories_required: Mapped[int] = mapped_column(Integer, default=1)
    #: Who to escalate to when the required signatory is unavailable.
    escalation_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Higher wins when two rules match equally well.
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class PkiKey(Base):
    """Private key material for the **software** keystore only.

    Deliberately its own table rather than a column on `certificates`: the certificate
    register is read by the admin UI, the CRL builder and the auditor tooling, and none of
    those should ever have key material in the row they just loaded.

    `material` is an `EncryptedString`, so a database dump alone yields nothing without the
    Fernet chain. When `KEYSTORE_PROVIDER=pkcs11` this table stays empty — the key lives in
    the HSM and only its label is referenced.
    """

    __tablename__ = "pki_keys"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)  # the KeyStore handle
    algorithm: Mapped[str] = mapped_column(String(30), default="ec-p256")
    provider: Mapped[str] = mapped_column(String(20), default="soft")
    # PKCS#8 PEM, encrypted at rest. 4096 covers RSA-4096 plus the Fernet envelope.
    material: Mapped[str] = mapped_column(EncryptedString(length=8192), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CertificateAuthority(Base):
    """A CA certificate. The offline root signs issuing CAs; an issuing CA signs end-entity
    and OCSP-responder certificates.

    ECAC re-chaining readiness (Electronic Transactions Ordinance 2002): a CA's *identity* is
    its `key_id` + `subject_dn`, not this row. To cross-certify under an accredited root later,
    insert a second row with the same `key_id` and `subject_dn` and a different `issuer_dn` /
    `parent_ca_id` — the new chain validates existing end-entity certificates unchanged,
    because they were signed by that key. Nothing already issued has to be reissued.
    """

    __tablename__ = "certificate_authorities"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="issuing")  # root|issuing|ocsp
    subject_dn: Mapped[str] = mapped_column(String(500), index=True)
    issuer_dn: Mapped[str] = mapped_column(String(500), default="")
    parent_ca_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    key_id: Mapped[str] = mapped_column(String(200), index=True)  # KeyStore handle
    key_algorithm: Mapped[str] = mapped_column(String(30), default="ec-p384")
    serial_number: Mapped[str] = mapped_column(String(64), index=True)  # hex, no 0x
    pem: Mapped[str] = mapped_column(Text, default="")
    not_before: Mapped[dt.datetime] = mapped_column(DateTime)
    not_after: Mapped[dt.datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|retired|revoked
    # True once the root's key material has been exported for cold storage and removed from
    # the online keystore. An offline CA cannot sign until an operator restores it.
    is_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    crl_number: Mapped[int] = mapped_column(Integer, default=0)       # monotonic, per CA
    base_crl_number: Mapped[int] = mapped_column(Integer, default=0)  # base for the current delta
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class TrustAnchor(Base):
    """Roots this deployment trusts when validating *third-party* certificates (DigiCert,
    GlobalSign, Sectigo, Entrust — and later the ECAC root).

    Deliberately a table, not a file on disk: the RFP asks for chaining readiness without
    re-architecture, and a runtime-extensible trust store is what makes that a config change
    rather than a redeploy.
    """

    __tablename__ = "trust_anchors"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    subject_dn: Mapped[str] = mapped_column(String(500), default="")
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), index=True)
    pem: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="external")  # internal|external
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CertificateRequest(Base):
    """A Registration Authority enrolment request. **No certificate is issued without one.**

    `evidence` carries whatever bound the subject's identity: OIDC/SCIM/SAML claims for an
    internal user, or the OTP channel + masked identifier + IP + user agent for an external
    visitor (Phase 2). It is written into the audit trail and reproduced on the Certificate of
    Completion, so an auditor can see *why* the CA believed this subject was who they claimed.
    """

    __tablename__ = "certificate_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    subject_dn: Mapped[str] = mapped_column(String(500))
    subject_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subject_party_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subject_email: Mapped[str] = mapped_column(String(320), default="")
    profile: Mapped[str] = mapped_column(String(30), default="internal")  # internal|visitor|ocsp
    csr_pem: Mapped[str] = mapped_column(Text, default="")  # empty when the CA generates the key
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending|approved|rejected|issued|cancelled
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(String(32), default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # Second RA officer, when RA_DUAL_CONTROL is on. Must differ from `reviewed_by`.
    second_reviewed_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    second_reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Certificate(Base):
    """An issued end-entity certificate, bound to exactly one signatory.

    The RFP forbids shared or role-based certificates. That is enforced twice: in
    `pki/lifecycle.py` at issuance time, and by a partial unique index over
    (tenant_id, subject_user_id) / (tenant_id, subject_party_id) restricted to
    status='active' — see migration 0016_pki.
    """

    __tablename__ = "certificates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    ca_id: Mapped[str] = mapped_column(String(32), index=True)
    request_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subject_dn: Mapped[str] = mapped_column(String(500), index=True)
    subject_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subject_party_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subject_email: Mapped[str] = mapped_column(String(320), default="")
    profile: Mapped[str] = mapped_column(String(30), default="internal")
    serial_number: Mapped[str] = mapped_column(String(64), index=True)  # hex, no 0x
    key_id: Mapped[str] = mapped_column(String(200), default="")        # KeyStore handle
    key_algorithm: Mapped[str] = mapped_column(String(30), default="ec-p256")
    pem: Mapped[str] = mapped_column(Text, default="")
    not_before: Mapped[dt.datetime] = mapped_column(DateTime)
    not_after: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # active|suspended|revoked|expired
    revocation_reason: Mapped[str] = mapped_column(String(40), default="")  # RFC 5280 reason
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # Set when this certificate replaced another (renewal). The subject binding is preserved;
    # the serial is always new — a renewal is a new certificate, never a re-dated one.
    renewed_from_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    issued_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------------------------
# Adoption: contextual help, knowledge base, training (Phase 9, items 1-3)
# ---------------------------------------------------------------------------------------


class HelpTopic(Base):
    """One piece of contextual help, addressed by the key the UI asks for.

    In the database rather than a file in the bundle, because the requirement is that Legal can
    correct the wording without a deploy. Help text that is wrong is worse than none — it is
    read as authoritative — and a correction that waits on a release train stays wrong for a
    fortnight.

    Seeded from `app/content/help.en.json` on first start. The seed only fills gaps: once
    somebody has edited a topic, redeploying must not silently revert their wording.
    """

    __tablename__ = "help_topics"
    __table_args__ = (Index("ix_help_key", "tenant_id", "key", "locale", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    #: Stable address, e.g. `contract.effective_date`. The UI never hard-codes the copy.
    key: Mapped[str] = mapped_column(String(120), index=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    #: Where it appears — a screen name, so an editor can find what they are changing.
    surface: Mapped[str] = mapped_column(String(80), default="")
    #: True while the row still holds the shipped default. Cleared on first edit.
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class KnowledgeArticle(Base):
    """A knowledge-base article: a playbook, an FAQ, a quick-start guide.

    `video_file_id` points at a file in this deployment\'s own storage. Embedding YouTube would
    be less work and would send a record of who watched which internal playbook, and when, to a
    third party — which the on-prem constraint exists to prevent.
    """

    __tablename__ = "knowledge_articles"
    __table_args__ = (
        Index("ix_kb_slug", "tenant_id", "slug", "locale", unique=True),
        Index("ix_kb_category", "tenant_id", "category"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    #: `playbook` | `faq` | `quickstart` | `release_note`
    category: Mapped[str] = mapped_column(String(40), default="faq", index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    #: Self-hosted video, served from this deployment\'s storage.
    video_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    video_duration_s: Mapped[int] = mapped_column(Integer, default=0)
    #: Roles the article is for. Empty means everyone.
    audience_roles: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrainingCourse(Base):
    """A course in the training hub.

    MMBL scores "Training Mechanism" at 8% and wants at least 15 people trained onsite. Onsite
    training happens once and the people who attended move on; this is the half that is still
    there in eighteen months when a new joiner needs the same thing.
    """

    __tablename__ = "training_courses"
    __table_args__ = (Index("ix_course_slug", "tenant_id", "slug", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(String(500), default="")
    #: Who it is for — matched against the user\'s role to build "assigned to me".
    for_roles: Mapped[list] = mapped_column(JSON, default=list)
    #: Ordered module list: [{"title", "body", "article_slug", "video_file_id", "minutes"}]
    modules: Mapped[list] = mapped_column(JSON, default=list)
    #: Ordered questions: [{"q", "options": [...], "answer": <index>, "why": "..."}]
    #: The answer key lives here and is stripped before the quiz is served — see
    #: `training_service.quiz_for`.
    quiz: Mapped[list] = mapped_column(JSON, default=list)
    pass_mark: Mapped[int] = mapped_column(Integer, default=80)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    #: A certificate is only meaningful if it can go stale.
    certificate_valid_months: Mapped[int] = mapped_column(Integer, default=12)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrainingProgress(Base):
    """One user\'s progress through one course."""

    __tablename__ = "training_progress"
    __table_args__ = (
        Index("ix_progress_user_course", "tenant_id", "user_id", "course_id", unique=True),
        Index("ix_progress_status", "tenant_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    course_id: Mapped[str] = mapped_column(String(32), index=True)
    #: `not_started` | `in_progress` | `passed` | `failed`
    status: Mapped[str] = mapped_column(String(20), default="not_started", index=True)
    #: Indices of completed modules. A set would be nicer; JSON columns hold lists.
    completed_modules: Mapped[list] = mapped_column(JSON, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    best_score: Mapped[int] = mapped_column(Integer, default=0)
    last_score: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    passed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    #: When the certificate stops being current. Null until passed.
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    certificate_no: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrainingSession(Base):
    """A scheduled live session — the webinar calendar, and the onsite sessions.

    Onsite sessions are recorded here too. A training plan that only tracks what happened in the
    browser cannot answer "have the 15 named people been trained", which is the question the
    RFP actually asks.
    """

    __tablename__ = "training_sessions"
    __table_args__ = (Index("ix_session_start", "tenant_id", "starts_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    #: `webinar` | `onsite` | `office_hours`
    kind: Mapped[str] = mapped_column(String(20), default="webinar")
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    #: A room for onsite, a meeting link for a webinar. Free text on purpose.
    location: Mapped[str] = mapped_column(String(300), default="")
    trainer: Mapped[str] = mapped_column(String(200), default="")
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    #: User ids who registered, and who actually turned up. Attendance is what gets reported.
    registered_user_ids: Mapped[list] = mapped_column(JSON, default=list)
    attended_user_ids: Mapped[list] = mapped_column(JSON, default=list)
    recording_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class BulkSendBatch(Base):
    """One template dispatched to many signers, each getting their own contract and envelope.

    A batch is a record, not just a fan-out: when 40 of 500 fail, the question is always
    *which* 40 and *why*, and a task that logs and exits cannot answer it. Every row survives
    as a `BulkSendItem` carrying its own outcome, so the batch can be inspected, retried for
    just the failures, or cancelled before the rest go out.
    """

    __tablename__ = "bulk_send_batches"
    __table_args__ = (Index("ix_bulk_batch_tenant_status", "tenant_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    #: What the operator called it. Defaults to the template name plus the date.
    name: Mapped[str] = mapped_column(String(240), default="")
    #: queued | running | completed | completed_with_errors | cancelled | failed
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    #: Message shown to every recipient, and the signing-order for each single-signer envelope.
    message: Mapped[str] = mapped_column(Text, default="")
    #: Merge values shared by every row. A row's own values win on a key collision.
    shared_values: Mapped[dict] = mapped_column(JSON, default=dict)
    reminder_interval_days: Mapped[int] = mapped_column(Integer, default=0)
    max_reminders: Mapped[int] = mapped_column(Integer, default=0)
    #: Days from dispatch until the envelope stops being signable. 0 = no envelope expiry.
    expiry_days: Mapped[int] = mapped_column(Integer, default=0)
    #: The progress-tray row, so a batch of 500 is visible while it runs.
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class BulkSendItem(Base):
    """One recipient in a batch: their merge values, and what became of them."""

    __tablename__ = "bulk_send_items"
    __table_args__ = (Index("ix_bulk_item_batch_seq", "batch_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("bulk_send_batches.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    #: This row's merge values, already layered over the batch's shared ones.
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    #: pending | sent | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    contract_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    envelope_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Why this row did not go out. Shown verbatim in the UI — a tester or an operator has to
    #: be able to fix the row from it without reading a log.
    error: Mapped[str] = mapped_column(String(600), default="")
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
