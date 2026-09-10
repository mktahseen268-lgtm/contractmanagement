import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------- auth ----------


class RegisterIn(BaseModel):
    workspace_name: str = Field(min_length=2, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class MfaChallengeOut(BaseModel):
    mfa_required: bool = True
    mfa_token: str
    methods: list[str] = ["totp", "recovery", "email_otp"]


class MfaVerifyIn(BaseModel):
    mfa_token: str
    code: str


class OtpSendIn(BaseModel):
    mfa_token: str


class OtpSendOut(BaseModel):
    sent: bool = True
    dev_code: str | None = None  # only populated when ENV=dev — for local testing


class CodeIn(BaseModel):
    code: str


class PasswordIn(BaseModel):
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_agent: str
    ip: str
    created_at: dt.datetime
    last_used_at: dt.datetime
    current: bool = False


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    locale: str
    currency: str
    plan: str
    group_name: str = ""
    accent_color: str = "#3E7BFA"
    timezone: str = "UTC"


class TenantUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    group_name: str | None = None  # optional parent-org / group label (blank clears it)
    currency: str | None = None
    locale: str | None = None
    timezone: str | None = None
    accent_color: str | None = None  # CSS color (#RRGGBB recommended)


class TextAssistIn(BaseModel):
    text: str
    #: correct | formal | shorten | plain — validated against `text_assist.MODES` in the
    #: service, so the list lives in one place.
    mode: str = "correct"


class TextAssistOut(BaseModel):
    text: str
    changed: bool
    provider: str
    error: str = ""


class TextAssistConfigOut(BaseModel):
    """What the UI needs to decide whether to offer the affordance at all."""
    enabled: bool
    provider: str
    modes: list[str]
    max_chars: int


class UserUpdateIn(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    department: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    avatar_color: str
    department: str = ""
    mfa_enabled: bool = False


class MeOut(BaseModel):
    user: UserOut
    tenant: TenantOut


class AuthOut(TokenOut):
    user: UserOut
    tenant: TenantOut


# ---------- contracts ----------


class ContractCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    type: str = "other"
    counterparty: str = ""
    department: str = ""
    value: float = 0.0
    currency: str = "USD"
    effective_date: dt.date | None = None
    end_date: dt.date | None = None
    renewal_type: str = "none"
    governing_law: str = ""
    tags: list[str] = []
    body: str = ""
    owner_id: str | None = None
    source: str = "manual"
    ai_summary: str = ""
    risk_level: str = "low"


class ContractUpdateIn(BaseModel):
    title: str | None = None
    type: str | None = None
    counterparty: str | None = None
    department: str | None = None
    value: float | None = None
    currency: str | None = None
    effective_date: dt.date | None = None
    end_date: dt.date | None = None
    renewal_type: str | None = None
    governing_law: str | None = None
    risk_level: str | None = None
    tags: list[str] | None = None
    body: str | None = None
    owner_id: str | None = None
    ai_summary: str | None = None


class TransitionIn(BaseModel):
    status: str
    comment: str = ""


class ContractBulkIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["delete"] = "delete"


class ContractBulkSkip(BaseModel):
    id: str
    reason: str


class ContractBulkResult(BaseModel):
    requested: int
    succeeded: int
    deleted_ids: list[str]
    skipped: list[ContractBulkSkip]


class ContractListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    reference_no: str
    title: str
    type: str
    status: str
    owner_id: str
    owner_name: str = ""
    counterparty: str
    department: str
    value: float
    currency: str
    effective_date: dt.date | None
    end_date: dt.date | None
    renewal_type: str
    risk_level: str
    tags: list[str]
    source: str
    updated_at: dt.datetime
    created_at: dt.datetime


class ContractRef(BaseModel):
    """Lightweight pointer to another contract (the predecessor or successor in a renewal chain)."""
    id: str
    reference_no: str
    title: str
    status: str = ""


class ContractDetail(ContractListItem):
    governing_law: str
    ai_summary: str
    body: str
    created_by: str
    available_transitions: list[str] = []
    renewed_from_id: str | None = None
    renewed_from: ContractRef | None = None  # the predecessor we were renewed from (if any)
    renewed_to: ContractRef | None = None    # the successor that renewed us (if any)


class RenewIn(BaseModel):
    """Inputs to /contracts/{id}/renew — the new term."""
    effective_date: dt.date | None = None    # defaults to old.end_date + 1 day (or today)
    end_date: dt.date | None = None          # defaults to effective_date + (old term length) or 12 months
    change_summary: str = ""                 # appears on the successor's initial version
    keep_workflow_status: bool = False       # if true, leaves the successor in current status (default: drops to "draft")


class SweepResultOut(BaseModel):
    flagged_expiring: int = 0
    moved_to_expired: int = 0
    reminders_sent: int = 0
    obligations_overdue: int = 0


class ObligationIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    due_date: dt.date | None = None
    owner_id: str | None = None


class ObligationUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: dt.date | None = None
    owner_id: str | None = None
    status: str | None = None  # "pending" | "done" | "skipped"


# ---------- templates ----------


class ContractTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    contract_type: str = "other"
    body: str = ""
    default_currency: str = "USD"
    default_term_months: int = 12
    default_renewal_type: str = "none"
    default_risk_level: str = "low"
    default_governing_law: str = ""
    default_tags: list[str] = []
    is_active: bool = True
    fields: list[dict] = Field(default_factory=list)


class ContractTemplateUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    contract_type: str | None = None
    body: str | None = None
    default_currency: str | None = None
    default_term_months: int | None = None
    default_renewal_type: str | None = None
    default_risk_level: str | None = None
    default_governing_law: str | None = None
    default_tags: list[str] | None = None
    is_active: bool | None = None
    fields: list[dict] | None = None


class ContractTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    contract_type: str
    body: str
    default_currency: str
    default_term_months: int
    default_renewal_type: str
    default_risk_level: str
    default_governing_law: str
    default_tags: list[str]
    is_active: bool
    usage_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
    # --- merge fields and approval (Phase 3) ---
    fields: list[dict] = Field(default_factory=list)
    status: str = "draft"
    version_no: int = 1
    effective_from: dt.date | None = None
    approved_by: str = ""
    approved_at: dt.datetime | None = None
    approval_note: str = ""


class UseTemplateIn(BaseModel):
    """Spawn a contract from a template — override anything the user wants."""
    title: str = Field(min_length=1, max_length=300)
    counterparty: str = ""
    department: str = ""
    value: float = 0.0
    effective_date: dt.date | None = None
    end_date: dt.date | None = None
    owner_id: str | None = None


# ---------- API keys ----------


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    prefix: str
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None
    created_at: dt.datetime


class ApiKeyCreateOut(ApiKeyOut):
    """Includes the plaintext token — only returned once at creation."""
    token: str = ""


# ---------- webhooks ----------


_WEBHOOK_EVENTS = [
    "*",
    "contract.created", "contract.status_changed", "contract.signed",
    "contract.renewed", "contract.expired", "contract.terminated", "contract.voided",
    "envelope.sent", "envelope.signed", "envelope.completed", "envelope.declined",
    "obligation.overdue",
]


class WebhookEndpointIn(BaseModel):
    url: str = Field(min_length=8, max_length=800)
    description: str = ""
    events: list[str] = ["*"]


class WebhookEndpointUpdateIn(BaseModel):
    url: str | None = None
    description: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookEndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    url: str
    description: str
    events: list[str]
    is_active: bool
    created_at: dt.datetime
    last_delivery_at: dt.datetime | None
    last_status: str


class WebhookEndpointCreateOut(WebhookEndpointOut):
    """Includes the signing secret — only returned once at creation."""
    secret: str


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    endpoint_id: str
    event: str
    status: str
    response_code: int
    response_snippet: str
    attempts: int
    created_at: dt.datetime
    delivered_at: dt.datetime | None


class BackgroundJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    label: str
    status: str        # queued | running | succeeded | failed
    progress: int
    result_summary: str = ""
    error: str = ""
    object_type: str = ""
    object_id: str | None = None
    href: str = ""
    created_at: dt.datetime
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


class ObligationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    title: str
    description: str = ""
    due_date: dt.date | None
    owner_id: str | None
    owner_name: str = ""
    status: str
    completed_at: dt.datetime | None
    completed_by_name: str = ""
    created_at: dt.datetime
    updated_at: dt.datetime


class ContractListOut(BaseModel):
    items: list[ContractListItem]
    total: int
    page: int
    page_size: int


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    #: Character range in the document body this note is about. Optional — a general remark
    #: has no anchor and is not less valid for it.
    anchor_start: int | None = None
    anchor_end: int | None = None
    #: The passage as it read when the note was written. Stored inside the body rather than in
    #: a column: the document is edited afterwards, offsets move, and a quote that shows what
    #: the reviewer was actually looking at survives that where a character range does not.
    quote: str = Field(default="", max_length=1000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    author_id: str
    author_name: str
    body: str
    resolved: bool
    created_at: dt.datetime
    # comment | amendment. An amendment is a proposed change to the wording, not an aside.
    kind: str = "comment"
    #: Internal-only threads never leave the workspace. Fail-closed in `comment_service`.
    internal_only: bool = False
    department: str = ""
    #: Character range in the document this thread is about. Set for redline threads, so the
    #: discussion stays attached to the wording rather than floating free three revisions later.
    anchor_start: int | None = None
    anchor_end: int | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_no: int
    change_summary: str
    created_by: str
    created_at: dt.datetime


class VersionDetailOut(VersionOut):
    body: str


# ---------- dashboard ----------


class StatusCount(BaseModel):
    status: str
    count: int


class ActivityItem(BaseModel):
    id: str
    at: dt.datetime
    actor_name: str
    action: str
    object_type: str
    object_id: str | None
    object_label: str


class DashboardOut(BaseModel):
    total_contracts: int
    pending_approvals: int
    awaiting_signature: int
    expiring_30d: int
    active_value: float
    open_risks: int
    by_status: list[StatusCount]
    by_type: list[StatusCount]
    recent_activity: list[ActivityItem]
    my_open: list[ContractListItem]
    expiring_soon: list[ContractListItem]


# Focused dashboard slices — let the web fetch each widget independently so the fast KPI row
# paints without waiting on the heavier activity / attention queries.
class DashboardKpisOut(BaseModel):
    total_contracts: int
    pending_approvals: int
    awaiting_signature: int
    expiring_30d: int
    active_value: float
    open_risks: int


class DashboardDistributionOut(BaseModel):
    by_status: list[StatusCount]
    by_type: list[StatusCount]


class DashboardTrendPoint(BaseModel):
    label: str          # week start, e.g. "May 12"
    contracts: int      # contracts created that week
    value: float        # total contract value created that week


class DashboardTrendsOut(BaseModel):
    points: list[DashboardTrendPoint]   # oldest → newest (8 weeks)
    total_contracts: int                # sum over the window
    delta_pct: float                    # last week vs the previous week, %


# ---------- audit ----------


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    at: dt.datetime
    actor_id: str | None
    actor_name: str
    action: str
    object_type: str
    object_id: str | None
    object_label: str
    meta: dict
    ip: str


class AuditListOut(BaseModel):
    items: list[AuditOut]
    total: int
    page: int
    page_size: int


# ---------- notifications ----------


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    title: str
    body: str
    object_type: str
    object_id: str | None
    read_at: dt.datetime | None
    created_at: dt.datetime


# ---------- users ----------


class UserInviteIn(BaseModel):
    email: EmailStr
    name: str
    role: str = "author"
    #: Required. Approval routing, the authority matrix and every departmental report key
    #: off this, so a user without one silently drops out of all three.
    department: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=128)  # if omitted the server generates one
    welcome_message: str = ""


class UserInviteOut(UserOut):
    """Returned on POST /users — also includes the temp password (one-shot) so the admin can copy
    it. The password is also emailed to the new user via the outbox."""
    generated_password: str | None = None


# ---------- files ----------


class FileObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    original_name: str
    content_type: str
    size: int
    kind: str
    backend: str
    created_at: dt.datetime


# ---------- ocr ----------


class OcrJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    file_name: str
    progress: int
    result: dict
    created_contract_id: str | None
    created_at: dt.datetime


# ---------- workflows ----------


class WorkflowStep(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    assignee_kind: str = "role"  # "role" | "user"
    assignee_value: str = "approver"  # role name (approver|manager|admin|owner) or a user id


class WorkflowOption(BaseModel):
    id: str
    name: str
    is_default: bool = False


class WorkflowDefinitionListItem(BaseModel):
    id: str
    name: str
    status: str
    default_for_types: list[str]
    step_count: int
    run_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkflowDefinitionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: str
    default_for_types: list[str]
    #: Legacy flat list. Still returned so old clients keep working; `stages` is authoritative
    #: when present, and a definition with only `steps` promotes to one step per stage.
    steps: list[WorkflowStep]
    stages: list[dict] = Field(default_factory=list)
    non_standard_stages: list[dict] = Field(default_factory=list)
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkflowDefinitionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: str = "draft"
    default_for_types: list[str] = []
    steps: list[WorkflowStep] = []
    #: The Phase 4 shape. Supplying `stages` makes the workflow parallel-capable; supplying
    #: only `steps` keeps the old sequential behaviour.
    stages: list[dict] = Field(default_factory=list)
    #: Applied instead of `stages` when the contract is classified non-standard (RFI §3.1).
    non_standard_stages: list[dict] = Field(default_factory=list)


class WorkflowDefinitionUpdateIn(BaseModel):
    name: str | None = None
    status: str | None = None
    default_for_types: list[str] | None = None
    steps: list[WorkflowStep] | None = None
    stages: list[dict] | None = None
    non_standard_stages: list[dict] | None = None


class WorkflowRunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    step_index: int
    name: str
    assignee_kind: str
    assignee_value: str
    status: str
    decision: str | None
    decided_by: str | None
    decided_by_name: str
    decided_at: dt.datetime | None
    comment: str


class WorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    definition_id: str | None
    definition_name: str
    status: str
    current_index: int
    started_by: str
    started_by_name: str
    started_at: dt.datetime
    completed_at: dt.datetime | None
    steps: list[WorkflowRunStepOut] = []


class WorkflowRunListItem(BaseModel):
    id: str
    contract_id: str
    contract_title: str
    definition_name: str
    status: str
    current_step_name: str
    started_by_name: str
    started_at: dt.datetime
    completed_at: dt.datetime | None


class ContractWorkflowOut(BaseModel):
    run: WorkflowRunOut | None = None
    can_decide: bool = False
    default_workflow_id: str | None = None
    available_workflows: list[WorkflowOption] = []


class SubmitForApprovalIn(BaseModel):
    workflow_id: str | None = None  # None -> the contract type's default active workflow, or no workflow (plain review)


class WorkflowDecideIn(BaseModel):
    decision: str  # approve | reject | changes_requested
    comment: str = ""


# ---------- e-signature ----------


class SignatureTabIn(BaseModel):
    recipient_id: str
    kind: str = "signature"   # signature|initials|date|text|checkbox
    page: int = 1
    x: float = 0.5
    y: float = 0.5
    width: float = 0.25
    height: float = 0.05
    required: bool = True
    label: str = ""


class SignatureTabUpdateIn(BaseModel):
    kind: str | None = None
    page: int | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    required: bool | None = None
    label: str | None = None
    value: str | None = None   # used by the signer to fill text/checkbox tabs


class SignatureTabOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    envelope_id: str
    recipient_id: str
    kind: str
    page: int
    x: float
    y: float
    width: float
    height: float
    required: bool
    label: str
    value: str
    filled_at: dt.datetime | None


class TabFillIn(BaseModel):
    """One tab's value during /sign/{token}/sign — only meaningful for text/checkbox tabs."""
    tab_id: str
    value: str


class RecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    kind: str = "signer"  # "signer" | "cc"


class RecipientOut(BaseModel):
    id: str
    sequence: int
    name: str
    email: str
    kind: str
    status: str  # created|sent|viewed|signed|declined
    signed_name: str
    signed_at: dt.datetime | None
    declined_reason: str
    ip: str
    signing_link: str | None = None  # /sign/{token} — populated for the contract owner only


class EnvelopeOut(BaseModel):
    id: str
    contract_id: str
    status: str
    signing_order: str
    message: str
    document_file_id: str | None
    sealed_pdf_file_id: str | None
    certificate_file_id: str | None
    created_by: str
    created_at: dt.datetime
    sent_at: dt.datetime | None
    completed_at: dt.datetime | None
    recipients: list[RecipientOut] = []
    tabs: list[SignatureTabOut] = []  # all tabs across all recipients (sender view)


class PrepareSignatureIn(BaseModel):
    recipients: list[RecipientIn] = Field(min_length=1)
    message: str = ""
    signing_order: str = "sequential"  # "sequential" | "parallel"


class SignIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)  # legal name on record + typed-mode fallback
    consent: bool = True
    # How the signer adopted their mark. For drawn/uploaded, `signature_image` carries a base64
    # PNG/JPEG data URL (validated + size-capped server-side in signing_service.sign).
    signature_kind: Literal["typed", "drawn", "uploaded"] = "typed"
    signature_image: str | None = None
    tab_fills: list[TabFillIn] = []  # values for text/checkbox tabs (signature/initials/date are auto-filled)


class DeclineIn(BaseModel):
    reason: str = ""


# ---------- reports & analytics ----------


class ReportBucket(BaseModel):
    label: str
    count: int = 0
    value: float = 0.0


class ReportSeriesPoint(BaseModel):
    label: str       # e.g. "2026-03"
    count: int = 0
    value: float = 0.0


class ReportCycleTime(BaseModel):
    approval_avg_days: float = 0.0
    approval_median_days: float = 0.0
    approval_n: int = 0
    signature_avg_days: float = 0.0
    signature_median_days: float = 0.0
    signature_n: int = 0
    end_to_end_avg_days: float = 0.0
    end_to_end_n: int = 0


class ReportThroughput(BaseModel):
    workflow_runs_started: int = 0
    workflow_runs_approved: int = 0
    workflow_runs_rejected: int = 0
    workflow_runs_changes_requested: int = 0
    envelopes_sent: int = 0
    envelopes_completed: int = 0
    envelopes_declined: int = 0
    envelopes_voided: int = 0


class ReportApprover(BaseModel):
    user_id: str
    name: str
    approved: int = 0
    rejected: int = 0
    changes_requested: int = 0
    total: int = 0
    avg_response_hours: float = 0.0


class ReportExpiringItem(BaseModel):
    id: str
    reference_no: str
    title: str
    counterparty: str
    end_date: dt.date | None = None
    days_to_end: int = 0
    value: float = 0.0
    currency: str = "USD"
    status: str = ""


class StuckItem(BaseModel):
    """Something blocking a contract from moving forward — surfaced in Reports."""
    kind: str            # "approval_step" | "envelope"
    contract_id: str
    contract_title: str
    contract_reference: str
    contract_status: str
    risk_level: str = "low"
    waiting_hours: float = 0.0
    detail: str = ""     # "Owner sign-off — waiting on @Mark" / "Envelope — 2 of 3 signed; pending Sam, Tara"
    href: str = ""


class ReportSummaryOut(BaseModel):
    range_from: dt.date
    range_to: dt.date
    total_contracts: int = 0          # all in workspace (current)
    created_in_range: int = 0         # created_at within [from, to]
    signed_in_range: int = 0          # envelopes completed within [from, to]
    active_count: int = 0
    active_value: float = 0.0
    expiring_30d: int = 0
    expiring_90d: int = 0
    by_status: list[ReportBucket] = []
    by_type: list[ReportBucket] = []
    by_risk: list[ReportBucket] = []
    by_department: list[ReportBucket] = []
    new_per_month: list[ReportSeriesPoint] = []
    cycle_time: ReportCycleTime = ReportCycleTime()
    throughput: ReportThroughput = ReportThroughput()
    expiring_buckets: list[ReportBucket] = []      # "0–30d" / "31–60d" / "61–90d" / "91–180d"
    expiring_top: list[ReportExpiringItem] = []    # the 10 soonest
    top_approvers: list[ReportApprover] = []       # by total decisions in range


class SigningInfoOut(BaseModel):
    """Public (token-auth) signing-page data."""
    valid: bool
    reason: str = ""  # if not valid: expired | revoked | not_found
    org_name: str = ""
    contract_title: str = ""
    contract_reference: str = ""
    sender_name: str = ""
    message: str = ""
    recipient_name: str = ""
    recipient_email: str = ""
    recipient_status: str = ""  # created|sent|viewed|signed|declined  (the recipient's own state)
    can_sign: bool = False      # the envelope is sent & it's this recipient's turn
    waiting_reason: str = ""    # if can_sign is false: "earlier signer hasn't signed yet" / etc.
    document_path: str = ""     # /sign/{token}/document — download the contract being signed
    consent_text: str = ""
    envelope_status: str = ""
    sealed_pdf_path: str = ""   # populated once the envelope is completed
    tabs: list[SignatureTabOut] = []  # fields THIS recipient must fill


# ---------- inbox ("waiting on you") ----------


class InboxItem(BaseModel):
    """A single thing waiting on the current user — either an approval step or a signature."""
    id: str                       # stable per task ("step:<step_id>" or "sig:<recipient_id>")
    kind: str                     # "approval" | "signature"
    contract_id: str
    contract_title: str = ""
    contract_reference: str = ""
    contract_status: str = ""
    contract_type: str = ""
    risk_level: str = "low"
    value: float = 0.0
    currency: str = "USD"
    title: str = ""               # short headline ("Approve: <step name>" / "Your signature is needed")
    subtitle: str = ""            # second line ("Step 2 of 3 — Owner sign-off" / "MSA — Globex")
    since: dt.datetime | None = None      # when this task became yours (step.created_at or recipient.sent-ish)
    waiting_hours: float = 0.0
    priority: str = "normal"      # "normal" | "high"
    href: str = ""                # frontend route to take action


class InboxSummary(BaseModel):
    approvals: int = 0
    signatures: int = 0
    obligations: int = 0
    total: int = 0
    high_priority: int = 0


# ---------------------------------------------------------------------------------------
# PKI (Phase 1)
# ---------------------------------------------------------------------------------------


class CertificateAuthorityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    kind: str
    subject_dn: str
    issuer_dn: str = ""
    parent_ca_id: str | None = None
    key_algorithm: str
    serial_number: str
    not_before: dt.datetime
    not_after: dt.datetime
    status: str
    is_offline: bool = False
    crl_number: int = 0
    base_crl_number: int = 0
    created_at: dt.datetime


class CaChainOut(BaseModel):
    """A CA plus its ancestors, leaf-first — what a relying party needs to build a path."""
    ca: CertificateAuthorityOut
    chain_pem: list[str] = Field(default_factory=list)


class CertificateRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    subject_dn: str
    subject_user_id: str | None = None
    subject_party_id: str | None = None
    subject_email: str = ""
    profile: str
    status: str
    evidence: dict = Field(default_factory=dict)
    requested_by: str = ""
    reviewed_by: str | None = None
    reviewed_at: dt.datetime | None = None
    second_reviewed_by: str | None = None
    second_reviewed_at: dt.datetime | None = None
    review_note: str = ""
    created_at: dt.datetime
    # Populated by the router so the RA queue does not need a second round-trip.
    subject_name: str = ""
    requested_by_name: str = ""


class EnrolIn(BaseModel):
    subject_user_id: str | None = None
    subject_party_id: str | None = None
    subject_email: str = ""
    common_name: str = ""
    profile: str = "internal"
    evidence: dict = Field(default_factory=dict)


class ReviewIn(BaseModel):
    note: str = Field(default="", max_length=1000)


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ca_id: str
    request_id: str | None = None
    subject_dn: str
    subject_user_id: str | None = None
    subject_party_id: str | None = None
    subject_email: str = ""
    profile: str
    serial_number: str
    key_algorithm: str
    not_before: dt.datetime
    not_after: dt.datetime
    status: str
    revocation_reason: str = ""
    revoked_at: dt.datetime | None = None
    renewed_from_id: str | None = None
    created_at: dt.datetime
    subject_name: str = ""
    days_remaining: int = 0
    # The PEM is only returned on the detail endpoint — the register would be enormous.
    pem: str | None = None


class CertificateListOut(BaseModel):
    items: list[CertificateOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25


class RevokeIn(BaseModel):
    reason: str = "unspecified"
    note: str = Field(default="", max_length=1000)


class TrustAnchorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    subject_dn: str = ""
    fingerprint_sha256: str
    source: str
    is_active: bool
    created_at: dt.datetime
    not_after: dt.datetime | None = None


class TrustAnchorIn(BaseModel):
    pem: str
    name: str = ""


class ValidateIn(BaseModel):
    pem: str
    intermediates: list[str] = Field(default_factory=list)
    check_revocation: bool | None = None


class ValidateOut(BaseModel):
    ok: bool
    reason: str = ""
    chain: list[str] = Field(default_factory=list)
    revocation_checked: bool = False
    warnings: list[str] = Field(default_factory=list)


class PkiHealthOut(BaseModel):
    """What the admin console needs to answer "is the PKI healthy?" in one request."""
    provisioned: bool = False
    keystore_provider: str = "soft"
    hsm_connected: bool | None = None      # None when not using an HSM
    hsm_detail: str = ""
    root_ca: CertificateAuthorityOut | None = None
    issuing_ca: CertificateAuthorityOut | None = None
    ocsp_responder: CertificateAuthorityOut | None = None
    root_offline: bool = False
    certificates_active: int = 0
    certificates_suspended: int = 0
    certificates_revoked: int = 0
    certificates_expired: int = 0
    certificates_expiring_30d: int = 0
    pending_requests: int = 0
    crl_number: int = 0
    crl_last_published: dt.datetime | None = None
    crl_next_update: dt.datetime | None = None
    crl_stale: bool = False
    dual_control: bool = False
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Signatory authority matrix + execution reliability (Phase 2)
# ---------------------------------------------------------------------------------------


class SignatoryAuthorityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    department: str = ""
    contract_type: str = ""
    currency: str = ""
    min_value: float = 0.0
    max_value: float | None = None
    required_role: str = ""
    required_user_id: str | None = None
    required_user_name: str = ""
    signatories_required: int = 1
    escalation_user_id: str | None = None
    priority: int = 0
    is_active: bool = True
    notes: str = ""
    created_at: dt.datetime


class SignatoryAuthorityIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    department: str = ""
    contract_type: str = ""
    currency: str = ""
    min_value: float = 0.0
    max_value: float | None = None
    required_role: str = ""
    required_user_id: str | None = None
    signatories_required: int = Field(default=1, ge=1, le=10)
    escalation_user_id: str | None = None
    priority: int = 0
    is_active: bool = True
    notes: str = Field(default="", max_length=500)


class AuthorityEligible(BaseModel):
    id: str
    name: str
    email: str = ""
    role: str = ""


class AuthorityProposalOut(BaseModel):
    """What the matrix says should happen for a contract, shown when preparing an envelope."""
    rule_id: str | None = None
    rule_name: str = ""
    required_role: str = ""
    required_user_id: str | None = None
    signatories_required: int = 0
    escalation_user_id: str | None = None
    eligible: list[AuthorityEligible] = Field(default_factory=list)
    matrix_silent: bool = True


class AuthorityCheckIn(BaseModel):
    signer_user_ids: list[str] = Field(default_factory=list)


class AuthorityCheckOut(BaseModel):
    compliant: bool
    rule_id: str | None = None
    rule_name: str = ""
    deviations: list[str] = Field(default_factory=list)
    matrix_silent: bool = False


class SigningReceiptOut(BaseModel):
    """One cryptographic signature applied to the executed PDF."""
    recipient_id: str | None = None
    recipient_name: str = ""
    certificate_serial: str = ""
    subject_dn: str = ""
    field_name: str = ""
    algorithm: str = ""
    ok: bool = True
    error: str = ""


class SealFailureOut(BaseModel):
    """An envelope whose executed document did not seal cleanly — the dead-letter view."""
    envelope_id: str
    contract_id: str
    contract_reference: str = ""
    contract_title: str = ""
    seal_status: str
    seal_attempts: int = 0
    seal_error: str = ""
    seal_last_attempt_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


# ---------------------------------------------------------------------------------------
# Visitor eSigning (Phase 2) — the public, unauthenticated surface
# ---------------------------------------------------------------------------------------


class PowChallengeOut(BaseModel):
    required: bool = False
    challenge: str = ""
    bits: int = 0


class EsignLandingOut(BaseModel):
    label: str = ""
    organisation: str = ""
    contract_title: str = ""
    contract_reference: str = ""
    require_otp: bool = True
    otp_channel: str = "any"     # email | sms | any
    collect_cnic: bool = False
    require_scroll: bool = True
    proof_of_work: PowChallengeOut = Field(default_factory=PowChallengeOut)


class EsignStartIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=32)
    channel: str = ""            # email | sms; blank = infer from what was supplied
    cnic: str = Field(default="", max_length=20)   # only the last 4 digits are stored
    entry_point: str = "web"     # web | kiosk | mobile | qr
    device_fingerprint: str = Field(default="", max_length=64)
    pow_challenge: str = ""
    pow_solution: str = ""


class EsignStartOut(BaseModel):
    session_id: str
    masked_identifier: str = ""
    channel: str = "email"
    otp_required: bool = True
    expires_in: int = 600


class EsignSessionIn(BaseModel):
    session_id: str


class EsignVerifyIn(BaseModel):
    session_id: str
    code: str = Field(default="", max_length=12)


class EsignVerifyOut(BaseModel):
    session_id: str
    signing_token: str
    signing_url: str
    recipient_id: str
    certificate_serial: str = ""
    certificate_expires_at: dt.datetime | None = None


class EsignConsentIn(BaseModel):
    session_id: str
    pages_viewed: int = 0
    total_pages: int = 0
    scrolled_to_end: bool = False


class EsignConsentOut(BaseModel):
    may_sign: bool = False
    reason: str = ""
    pages_viewed: int = 0
    total_pages: int = 0


class InvitationIn(BaseModel):
    label: str = Field(default="", max_length=200)
    otp_channel: str = "any"
    require_otp: bool = True
    collect_cnic: bool = False
    max_signatures: int = Field(default=0, ge=0, le=100000)
    ttl_days: int | None = None


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    label: str
    otp_channel: str
    require_otp: bool
    collect_cnic: bool
    max_signatures: int
    signature_count: int
    expires_at: dt.datetime | None = None
    is_active: bool
    created_at: dt.datetime
    #: Present only in the create response — the raw token is never stored or shown again.
    url: str | None = None
    qr_svg: str | None = None


class VisitorSessionOut(BaseModel):
    """An external signatory's journey, for the admin-side audit view."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    otp_channel: str
    entry_point: str
    status: str
    verified_at: dt.datetime | None = None
    scroll_completed_at: dt.datetime | None = None
    pages_viewed: int = 0
    total_pages: int = 0
    ip: str = ""
    created_at: dt.datetime
    masked_identifier: str = ""
    certificate_serial: str = ""


# ---------------------------------------------------------------------------------------
# Smart signature tagging (Phase 2)
# ---------------------------------------------------------------------------------------


class AutoTagIn(BaseModel):
    #: false previews the proposal, true writes the tabs.
    apply: bool = False
    replace_existing: bool = True
    #: Template-declared anchor phrases, for layouts the built-in patterns do not cover.
    extra_anchors: list[str] = Field(default_factory=list)


class DetectedAnchor(BaseModel):
    page: int
    x: float
    y: float
    text: str
    kind: str
    confidence: float = 0.0


class ProposedTab(BaseModel):
    recipient_id: str
    kind: str
    page: int
    x: float
    y: float
    width: float
    height: float
    required: bool = True
    label: str = ""
    anchor_text: str = ""
    confidence: float = 0.0


class AutoTagOut(BaseModel):
    applied: bool = False
    tabs_created: int = 0
    note: str = ""
    anchors: list[DetectedAnchor] = Field(default_factory=list)
    proposed: list[ProposedTab] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Hybrid / wet-signature execution (Phase 2 item 5)
# ---------------------------------------------------------------------------------------


class ExecutionModeIn(BaseModel):
    """Recipients who will sign on paper. Empty returns the envelope to electronic."""
    wet_recipient_ids: list[str] = Field(default_factory=list)


class ExecutionModeOut(BaseModel):
    execution_mode: str = "electronic"   # electronic | hybrid | wet
    wet: list[str] = Field(default_factory=list)
    electronic: list[str] = Field(default_factory=list)


class WetAttestationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    envelope_id: str
    recipient_id: str | None = None
    file_id: str
    file_sha256: str = ""
    declared_execution_date: dt.date | None = None
    signatory_name: str = ""
    signatory_designation: str = ""
    witness_name: str = ""
    witness_designation: str = ""
    notes: str = ""
    attested_by_name: str = ""
    attested_at: dt.datetime


class ExecutionEvidenceOut(BaseModel):
    """What kind of evidence backs this execution. Deliberately explicit: a scanned page must
    never be presented as though it were a cryptographic signature."""
    execution_mode: str = "electronic"
    electronic_signers: list[str] = Field(default_factory=list)
    wet_signers: list[str] = Field(default_factory=list)
    attestations: list[dict] = Field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------------------
# Workflow engine (Phase 4)
# ---------------------------------------------------------------------------------------


class WorkflowStepIn(BaseModel):
    name: str = ""
    assignee_kind: str = "role"       # role | user
    assignee_value: str = "approver"
    sla_hours: int = 0


class WorkflowStageIn(BaseModel):
    name: str = ""
    #: all | any | quorum | percentage. Anything unrecognised is treated as `all` — the
    #: strictest reading, so a typo can never reduce the approvals required.
    policy: str = "all"
    threshold: int = 0                # count for quorum, 0-100 for percentage
    sla_hours: int = 0
    escalate_to_user_id: str | None = None
    steps: list[WorkflowStepIn] = Field(default_factory=list)


class RunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    stage_index: int = 0
    step_index: int = 0
    name: str
    assignee_kind: str
    assignee_value: str
    status: str
    decision: str | None = None
    decided_by_name: str = ""
    decided_at: dt.datetime | None = None
    comment: str = ""
    sla_hours: int = 0
    due_at: dt.datetime | None = None
    activated_at: dt.datetime | None = None
    escalated_at: dt.datetime | None = None
    escalated_to: str | None = None
    delegated_from: str | None = None
    delegated_from_name: str = ""
    added_mid_flight: bool = False
    is_overdue: bool = False
    assignee_name: str = ""


class RunStageOut(BaseModel):
    index: int
    name: str = ""
    policy: str = "all"
    threshold: int = 0
    status: str = "pending"           # pending | active | complete
    approvals: int = 0
    required: int = 0
    steps: list[RunStepOut] = Field(default_factory=list)


class WorkflowRunGraphOut(BaseModel):
    """The run as a STAGE GRAPH — the parallel-review screen.

    Distinct from `WorkflowRunOut`, which is the legacy flat payload the contract detail
    endpoint still returns. Same underlying run, two different questions.
    """
    id: str
    contract_id: str
    definition_name: str = ""
    status: str
    current_stage: int = 0
    started_by_name: str = ""
    started_at: dt.datetime
    completed_at: dt.datetime | None = None
    stages: list[RunStageOut] = Field(default_factory=list)
    my_steps: list[str] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)


class AddReviewerIn(BaseModel):
    stage_index: int = 0
    name: str = Field(default="", max_length=200)
    assignee_kind: str = "role"
    assignee_value: str = "approver"
    sla_hours: int = 0


class RemoveReviewerIn(BaseModel):
    reason: str = Field(default="", max_length=400)


class ApprovalRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contract_type: str = ""
    department: str = ""
    currency: str = ""
    min_value: float = 0.0
    max_value: float | None = None
    risk_level: str = ""
    governing_law: str = ""
    non_standard_only: bool = False
    min_playbook_deviations: int = 0
    stage_name: str = ""
    stage_policy: str = "all"
    stage_threshold: int = 0
    stage_steps: list[WorkflowStepIn] = Field(default_factory=list)
    sla_hours: int = 0
    escalate_to_user_id: str | None = None
    insert_after_stage: int = -1
    priority: int = 0
    is_active: bool = True


class ApprovalRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    contract_type: str = ""
    department: str = ""
    currency: str = ""
    min_value: float = 0.0
    max_value: float | None = None
    risk_level: str = ""
    governing_law: str = ""
    non_standard_only: bool = False
    min_playbook_deviations: int = 0
    stage_name: str = ""
    stage_policy: str = "all"
    stage_threshold: int = 0
    stage_steps: list[dict] = Field(default_factory=list)
    sla_hours: int = 0
    escalate_to_user_id: str | None = None
    insert_after_stage: int = -1
    priority: int = 0
    is_active: bool = True
    created_at: dt.datetime


class DelegationIn(BaseModel):
    to_user_id: str
    scope: str = "all"
    starts_at: dt.datetime
    ends_at: dt.datetime
    reason: str = Field(default="", max_length=400)


class DelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    from_user_id: str
    from_user_name: str = ""
    to_user_id: str
    to_user_name: str = ""
    scope: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    reason: str = ""
    is_active: bool = True
    created_at: dt.datetime


class HolidayIn(BaseModel):
    day: dt.date
    name: str = Field(default="", max_length=200)


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    day: dt.date
    name: str = ""


class EscalationOut(BaseModel):
    step_id: str
    run_id: str
    contract_id: str
    contract_title: str = ""
    contract_reference: str = ""
    step_name: str = ""
    stage_index: int = 0
    sla_hours: int = 0
    due_at: dt.datetime | None = None
    escalated_at: dt.datetime | None = None
    escalated_to: str | None = None
    escalated_to_name: str = ""
    resolved_at: dt.datetime | None = None
    #: Business hours from escalation to decision — "mean time to resolve" in the KPI pack.
    hours_to_resolve: float | None = None
    status: str = ""


class SlaSweepOut(BaseModel):
    reminded: int = 0
    escalated: int = 0
    breached: int = 0


class ConsolidatedGroupOut(BaseModel):
    department: str
    comments: list[CommentOut] = Field(default_factory=list)
    amendments: int = 0
    unresolved: int = 0


class ConsolidatedReviewOut(BaseModel):
    contract_id: str
    audience: str = "internal"
    total: int = 0
    internal_only_count: int = 0
    amendments: int = 0
    groups: list[ConsolidatedGroupOut] = Field(default_factory=list)


class MentionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    comment_id: str
    contract_id: str
    mentioned_by_name: str = ""
    internal_only: bool = False
    read_at: dt.datetime | None = None
    created_at: dt.datetime
    contract_title: str = ""
    body: str = ""


# ---------------------------------------------------------------------------------------
# Word round-trip (Phase 3)
# ---------------------------------------------------------------------------------------


class DocxChangeOut(BaseModel):
    """One tracked change the counterparty made."""
    kind: str                      # insert | delete
    text: str
    author: str = ""
    at: dt.datetime | None = None
    paragraph_index: int = 0
    context: str = ""


class DocxCommentOut(BaseModel):
    comment_id: str
    author: str = ""
    initials: str = ""
    text: str = ""
    at: dt.datetime | None = None
    anchor_text: str = ""
    paragraph_index: int | None = None


class DocxImportOut(BaseModel):
    """The result of reading a returned .docx.

    `applied` is false for a preview — the caller sees what would change before committing
    it, because importing overwrites the contract body and creates a version.
    """
    applied: bool = False
    version_no: int | None = None
    paragraphs: int = 0
    tables: int = 0
    insertions: int = 0
    deletions: int = 0
    comment_count: int = 0
    authors: list[str] = Field(default_factory=list)
    has_revisions: bool = False
    warnings: list[str] = Field(default_factory=list)
    body: str = ""
    changes: list[DocxChangeOut] = Field(default_factory=list)
    comments: list[DocxCommentOut] = Field(default_factory=list)
    #: Set when the import flipped the agreement to non-standard (RFI 3.1).
    classified_non_standard: bool = False

# ---------- Template merge fields (Phase 3) ----------


class TemplateFieldOut(BaseModel):
    """One question on the intake form."""
    key: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    default: object = None
    help: str = ""
    group: str = ""
    entity_kind: str = ""
    minimum: float | None = None
    maximum: float | None = None


class TemplateFormOut(BaseModel):
    """Everything the intake screen needs to render itself and to warn if it cannot."""
    template_id: str
    name: str
    description: str = ""
    contract_type: str = "other"
    status: str = "draft"
    version_no: int = 1
    #: False when the template has not been approved — the form renders read-only rather than
    #: letting someone fill it in and only then discover they cannot submit.
    usable: bool = False
    fields: list[TemplateFieldOut] = Field(default_factory=list)
    placeholders: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    defaults: dict = Field(default_factory=dict)
    #: Clauses this template composes by reference, resolved to their approved wording.
    clauses: list[dict] = Field(default_factory=list)
    #: For each referenced clause, the pre-approved alternatives a drafter may pick instead,
    #: each carrying its risk level — choosing a fallback position is a risk decision.
    clause_choices: list[dict] = Field(default_factory=list)


class TemplatePreviewIn(BaseModel):
    values: dict = Field(default_factory=dict)
    counterparty: str = ""
    title: str = ""
    #: {referenced_clause_key: chosen_alternative_key}
    clause_choices: dict = Field(default_factory=dict)
    #: Optional clauses to append that the template does not reference.
    extra_clauses: list[str] = Field(default_factory=list)


class TemplatePreviewOut(BaseModel):
    body: str = ""
    errors: list[str] = Field(default_factory=list)
    #: Placeholders nothing filled. Reported rather than blanked — a draft with a silent gap
    #: where the fee should be is the failure mode this whole feature exists to remove.
    unresolved: list[str] = Field(default_factory=list)
    substituted: dict = Field(default_factory=dict)
    values: dict = Field(default_factory=dict)
    version_no: int | None = None
    clauses: list[dict] = Field(default_factory=list)
    #: Referenced clauses with no approved wording. Never rendered as a gap — generation
    #: refuses outright, because a contract quietly missing a clause is the worst outcome here.
    missing_clauses: list[str] = Field(default_factory=list)
    ok: bool = False


class GenerateContractIn(UseTemplateIn):
    """Fill the form, get the draft. The RFI's core intake mechanic (2.3)."""
    values: dict = Field(default_factory=dict)
    #: Opt-in escape hatch for "generate it anyway, I will finish the gaps by hand".
    allow_unresolved: bool = False
    #: {referenced_clause_key: chosen_alternative_key}. Only that clause's own approved
    #: alternatives are accepted — anything else is editing the contract through a drop-down.
    clause_choices: dict = Field(default_factory=dict)
    extra_clauses: list[str] = Field(default_factory=list)


class TemplateApprovalIn(BaseModel):
    note: str = ""
    effective_from: dt.date | None = None


class TemplateRejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TemplateVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_no: int
    name: str
    status: str
    change_summary: str
    approved_by: str
    approved_at: dt.datetime | None = None
    created_at: dt.datetime


class SuggestFieldsIn(BaseModel):
    body: str = ""


class SuggestFieldsOut(BaseModel):
    fields: list[TemplateFieldOut] = Field(default_factory=list)


# ---------- Clause library and playbooks (Phase 3, items 2 + 6) ----------


class ClauseIn(BaseModel):
    #: The handle templates point at with [[clause:key]].
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=80)
    body: str = ""
    #: preferred | acceptable | fallback — the negotiating position this wording represents.
    position: str = "preferred"
    risk_level: str = "low"
    #: Set to make this an alternative (fallback) for another clause.
    parent_id: str | None = None
    fallback_rank: int = 0
    guidance: str = ""
    jurisdiction: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list)


class ClauseUpdateIn(BaseModel):
    key: str | None = Field(default=None, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    title: str | None = None
    category: str | None = None
    body: str | None = None
    position: str | None = None
    risk_level: str | None = None
    fallback_rank: int | None = None
    guidance: str | None = None
    jurisdiction: str | None = None
    tags: list[str] | None = None


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    title: str
    category: str
    body: str
    position: str
    risk_level: str
    status: str
    version_no: int
    parent_id: str | None = None
    fallback_rank: int = 0
    guidance: str = ""
    jurisdiction: str = ""
    tags: list[str] = Field(default_factory=list)
    usage_count: int = 0
    approved_by: str = ""
    approved_at: dt.datetime | None = None
    approval_note: str = ""
    created_at: dt.datetime
    updated_at: dt.datetime
    #: Pre-approved fallback positions, best first. Populated on detail reads.
    alternatives: list["ClauseOut"] = Field(default_factory=list)


class ClauseVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_no: int
    title: str
    body: str
    position: str
    risk_level: str
    status: str
    change_summary: str
    approved_by: str
    approved_at: dt.datetime | None = None
    created_at: dt.datetime


class PlaybookRuleIn(BaseModel):
    clause_key: str
    #: required | prohibited | preferred
    kind: str = "required"
    #: blocker | warning. A blocker classifies the agreement non-standard.
    severity: str = "warning"
    guidance: str = ""


class PlaybookIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    #: Empty means every type — a house-wide policy.
    contract_type: str = ""
    applies_when: dict = Field(default_factory=dict)
    rules: list[dict] = Field(default_factory=list)
    status: str = "draft"


class PlaybookUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    contract_type: str | None = None
    applies_when: dict | None = None
    rules: list[dict] | None = None
    status: str | None = None


class PlaybookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    contract_type: str
    applies_when: dict = Field(default_factory=dict)
    rules: list[dict] = Field(default_factory=list)
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class PolicyFindingOut(BaseModel):
    """One clause measured against policy.

    `status` is the whole point: `missing` and `altered` are different problems needing
    different responses, and lumping them together is how a changed liability cap gets
    reported as "clause present".
    """
    clause_key: str
    clause_id: str = ""
    title: str = ""
    kind: str = "required"
    severity: str = "warning"
    #: missing | altered | present | prohibited
    status: str = "present"
    #: Similarity to the approved wording, 0..1. Exposed so a reviewer can judge a borderline
    #: call rather than trusting the threshold blindly.
    ratio: float = 0.0
    risk_level: str = "low"
    guidance: str = ""
    playbook: str = ""
    #: Word-level diff against the approved wording, for `altered`.
    diff: list[str] = Field(default_factory=list)


class PolicyReviewOut(BaseModel):
    ok: bool = True
    checked: int = 0
    deviation_count: int = 0
    blocker_count: int = 0
    findings: list[PolicyFindingOut] = Field(default_factory=list)
    playbooks: list[dict] = Field(default_factory=list)
    classified_non_standard: bool = False


# ---------- Redline (Phase 3, item 8) ----------


class RedlineChangeOut(BaseModel):
    """One accept-or-reject decision.

    `index` is what the client sends back to accept it. Stable for a given (base, compare)
    pair because versions are immutable and the diff is deterministic.
    """
    index: int
    #: insert | delete | replace
    kind: str
    before: str = ""
    after: str = ""
    before_context: str = ""
    after_context: str = ""
    #: Character range in the compared text, so a comment can be anchored to the proposal.
    anchor_start: int = 0
    anchor_end: int = 0


class RedlineOut(BaseModel):
    base_label: str = ""
    compare_label: str = ""
    base_version_no: int | None = None
    compare_version_no: int | None = None
    changes: list[RedlineChangeOut] = Field(default_factory=list)
    change_count: int = 0
    added: int = 0
    removed: int = 0
    unchanged: int = 0
    identical: bool = True
    base_body: str = ""
    compare_body: str = ""


class RedlineApplyIn(BaseModel):
    base_version_no: int | None = None
    compare_version_no: int | None = None
    #: Indices to accept. Everything not listed is rejected and keeps the base wording.
    accept: list[int] = Field(default_factory=list)


class RedlineCommentIn(BaseModel):
    """A discussion thread anchored to one proposed change."""
    body: str = Field(min_length=1)
    anchor_start: int
    anchor_end: int
    internal_only: bool = True


# ---------- Sign-off readiness pack (Phase 4, item 10) ----------


class ReadinessDecisionOut(BaseModel):
    stage: int
    name: str
    who: str
    decision: str
    at: str
    on_time: bool | None = None
    escalated: bool = False
    delegated: bool = False
    comment: str = ""


class ReadinessOut(BaseModel):
    """"Is this safe to sign, and who said so?" in one response.

    `ready` is the answer; `blockers` is why not. Blockers lead because the failure this
    prevents is a signatory executing an agreement whose deviations nobody resolved.
    """
    contract_id: str
    reference_no: str = ""
    title: str = ""
    status: str = ""
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    decisions: list[ReadinessDecisionOut] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    policy: dict = Field(default_factory=dict)
    generated_at: dt.datetime


# ---------- AI assist (Phase 3, item 7) ----------


class ClauseSuggestionOut(BaseModel):
    key: str
    title: str
    #: Why this is suggested, in words a reviewer can act on.
    reason: str
    #: policy | peers | risk — what the suggestion is grounded in.
    basis: str
    severity: str = "warning"
    risk_level: str = "low"
    body: str = ""
    guidance: str = ""


class CapturedFieldOut(BaseModel):
    field: str
    value: str = ""
    #: 0..1. Not a fact — a reason to look.
    confidence: float = 0.0
    current: str = ""
    changes: bool = False
    #: Pre-ticked in the UI. Only above the confidence threshold AND only when it would
    #: actually change something.
    suggested: bool = False


class ExtractionReviewOut(BaseModel):
    id: str
    contract_id: str
    file_name: str = ""
    #: `stub` means the document was NOT read. Surfaced so nobody mistakes demo output for
    #: extraction.
    provider: str = "stub"
    status: str = "pending"
    summary: str = ""
    detected_clauses: list[str] = Field(default_factory=list)
    fields: list[CapturedFieldOut] = Field(default_factory=list)
    applied_fields: list[str] = Field(default_factory=list)
    created_at: dt.datetime
    reviewed_at: dt.datetime | None = None


class ApplyCaptureIn(BaseModel):
    """Only the fields a person ticked are written."""
    accept: list[str] = Field(default_factory=list)


# ---------- Repository: parties, relations, departments, folders, custom fields ----------


class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    registration_no: str = Field(default="", max_length=100)
    entity_type: str = "company"
    jurisdiction: str = Field(default="", max_length=100)
    region: str = Field(default="", max_length=100)
    kyc_status: str = "none"
    risk_score: int = 0
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    address: str = ""
    tags: list[str] = Field(default_factory=list)
    #: Required to onboard a party that looks like an existing one. Recorded, because
    #: "we knew and did it anyway" is a different fact from "nobody noticed".
    override_reason: str = ""


class PartyUpdateIn(BaseModel):
    name: str | None = None
    registration_no: str | None = None
    entity_type: str | None = None
    jurisdiction: str | None = None
    region: str | None = None
    kyc_status: str | None = None
    kyc_note: str | None = None
    risk_score: int | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    registration_no: str
    entity_type: str
    jurisdiction: str
    region: str
    kyc_status: str
    kyc_note: str = ""
    risk_score: int = 0
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    address: str = ""
    tags: list[str] = Field(default_factory=list)
    duplicate_override_of: str | None = None
    duplicate_override_reason: str = ""
    is_active: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime


class PartyDuplicateCheckIn(BaseModel):
    name: str = ""
    registration_no: str = ""
    exclude_id: str | None = None


class DuplicateMatchOut(BaseModel):
    id: str
    name: str
    registration_no: str = ""
    reason: str
    #: `exact` (registration number) or `likely` (name similarity). Different evidence,
    #: reported separately so a caller does not block on coincidence.
    certainty: str
    ratio: float = 0.0


class RelationIn(BaseModel):
    #: The agreement this one descends from.
    parent_id: str
    #: addendum_of | amendment_of | renewal_of | supersedes | related_to
    kind: str = "related_to"
    note: str = ""
    #: Copy the parent's counterparty, department, governing law and folder onto this one.
    inherit: bool = True


class RelatedContractOut(BaseModel):
    relation_id: str
    kind: str
    label: str
    direction: str
    sequence: int = 0
    note: str = ""
    contract_id: str
    reference_no: str = ""
    title: str = ""
    status: str = ""
    effective_date: dt.date | None = None
    end_date: dt.date | None = None


class ContractHistoryOut(BaseModel):
    contract_id: str
    ancestors: list[RelatedContractOut] = Field(default_factory=list)
    descendants: list[RelatedContractOut] = Field(default_factory=list)


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    lead_user_id: str | None = None
    cost_centre: str = ""
    region: str = ""


class DepartmentUpdateIn(BaseModel):
    name: str | None = None
    lead_user_id: str | None = None
    cost_centre: str | None = None
    region: str | None = None
    is_active: bool | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    lead_user_id: str | None = None
    lead_name: str = ""
    cost_centre: str = ""
    region: str = ""
    is_active: bool = True
    contract_count: int = 0


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    parent_id: str | None = None
    #: Empty means everyone in the workspace.
    visible_to_roles: list[str] = Field(default_factory=list)


class FolderMoveIn(BaseModel):
    parent_id: str | None = None


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    parent_id: str | None = None
    #: Materialised, e.g. /Legal/Vendors/2026.
    path: str
    visible_to_roles: list[str] = Field(default_factory=list)
    contract_count: int = 0
    depth: int = 0


class CustomFieldDefIn(BaseModel):
    #: Empty applies the field to every contract type.
    contract_type: str = ""
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = ""
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    help: str = ""
    position: int = 0


class CustomFieldDefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_type: str
    key: str
    label: str
    type: str
    required: bool
    options: list[str] = Field(default_factory=list)
    help: str = ""
    position: int = 0
    is_active: bool = True


class CustomFieldValuesIn(BaseModel):
    values: dict = Field(default_factory=dict)


class SearchIn(BaseModel):
    """Free text plus structured filters. POSTed because the filter set is a nested object."""
    q: str = ""
    status: list[str] = Field(default_factory=list)
    type: list[str] = Field(default_factory=list)
    risk_level: list[str] = Field(default_factory=list)
    owner_id: str = ""
    department_id: str = ""
    party_id: str = ""
    folder_id: str = ""
    #: Matches this folder and everything beneath it.
    folder_path: str = ""
    counterparty: str = ""
    department: str = ""
    currency: str = ""
    tags: list[str] = Field(default_factory=list)
    #: Only agreements composing this library clause.
    clause_key: str = ""
    effective_from: dt.date | None = None
    effective_to: dt.date | None = None
    end_from: dt.date | None = None
    end_to: dt.date | None = None
    value_min: float | None = None
    value_max: float | None = None
    include_archived: bool = False
    page: int = 1
    page_size: int = 25


class SearchHitOut(BaseModel):
    id: str
    reference_no: str = ""
    title: str = ""
    type: str = ""
    status: str = ""
    counterparty: str = ""
    value: float = 0.0
    currency: str = ""
    risk_level: str = ""
    effective_date: dt.date | None = None
    end_date: dt.date | None = None
    owner_id: str = ""
    updated_at: dt.datetime
    #: Text around the match, with **bold** markers on the query terms.
    snippet: str = ""


class SearchResultOut(BaseModel):
    items: list[SearchHitOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25
    #: Counts over the whole result set, not the current page — a facet describing one page
    #: would be actively misleading.
    facets: dict = Field(default_factory=dict)


# ---------- Post-execution changes: amendments, terminations, renewals, checklists ----------


class AmendmentIn(BaseModel):
    title: str = ""
    reason: str = ""


class AmendmentImpactOut(BaseModel):
    """What an amendment changes relative to what it amends.

    Recorded at execution rather than derived later: two years on nobody can reconstruct it
    from two documents without guessing.
    """
    fields: dict = Field(default_factory=dict)
    clauses: dict = Field(default_factory=dict)
    body_changed: bool = False
    value_delta: float = 0.0
    term_delta_days: int | None = None
    parent_id: str = ""
    parent_reference: str = ""


class TerminationIn(BaseModel):
    #: convenience | cause | mutual | expiry | regulatory
    reason_code: str = "convenience"
    reason: str = Field(min_length=1)
    notice_days: int = 0
    effective_date: dt.date | None = None
    documents: list[dict] = Field(default_factory=list)
    #: Roles that must sign off before this can be executed.
    required_roles: list[str] = Field(default_factory=list)


class TerminationDecisionIn(BaseModel):
    approve: bool
    comment: str = ""


class TerminationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    reason_code: str
    reason: str
    effective_date: dt.date | None = None
    notice_days: int = 0
    documents: list[dict] = Field(default_factory=list)
    #: pending | approved | rejected | executed | withdrawn
    status: str
    approvals: list[dict] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    notice_sent_at: dt.datetime | None = None
    requested_by: str = ""
    requested_by_name: str = ""
    created_at: dt.datetime


class TerminationNoticeOut(BaseModel):
    request_id: str
    contract_id: str
    #: Markdown, generated from the recorded request.
    body: str


class RenewalScheduleIn(BaseModel):
    #: Days before expiry at which to raise a notice.
    notice_days: list[int] = Field(default_factory=list)


class RenewalScheduleOut(BaseModel):
    notice_days: list[int] = Field(default_factory=list)
    #: Thresholds already reached for this agreement.
    due: list[int] = Field(default_factory=list)
    end_date: dt.date | None = None
    renewal_type: str = "none"


class ObligationRollupItem(BaseModel):
    id: str
    contract_id: str
    contract_reference: str = ""
    contract_title: str = ""
    contract_status: str = ""
    title: str
    description: str = ""
    due_date: dt.date | None = None
    days_left: int | None = None
    overdue: bool = False
    status: str = "pending"
    owner_id: str | None = None
    owner_name: str = ""


class ObligationRollupOut(BaseModel):
    items: list[ObligationRollupItem] = Field(default_factory=list)
    total: int = 0
    summary: dict = Field(default_factory=dict)


class ChecklistIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    owner_function: str = "Legal"
    #: Empty applies it to every agreement type.
    contract_type: str = ""
    #: [{text, required, guidance}]
    items: list[dict] = Field(default_factory=list)
    status: str = "draft"
    file_id: str | None = None


class ChecklistUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    owner_function: str | None = None
    contract_type: str | None = None
    items: list[dict] | None = None
    status: str | None = None
    file_id: str | None = None


class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str
    owner_function: str
    contract_type: str
    items: list[dict] = Field(default_factory=list)
    version_no: int = 1
    status: str = "draft"
    file_id: str | None = None
    published_at: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Exports (Phase 5, item 10) ----------


class ExportIn(BaseModel):
    """What to export and with which filters.

    The filter set is echoed onto the workbook's first sheet: an export whose provenance is
    not on its own face is one nobody can defend in a meeting six weeks later.
    """
    #: contracts | obligations | parties | audit
    kind: str = "contracts"
    filters: dict = Field(default_factory=dict)


class ExportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    label: str
    status: str
    progress: int = 0
    result_summary: str = ""
    error: str = ""
    #: Where to fetch the finished file.
    href: str = ""
    created_at: dt.datetime
    completed_at: dt.datetime | None = None


# ---------- Analytics (Phase 6) ----------


class MetricOut(BaseModel):
    """A figure with the sample it came from.

    `sample` is not decoration: a mean cycle time over four agreements and one over four
    hundred are different claims, and a dashboard that hides the difference gets quoted in a
    board pack as though they were the same.
    """
    mean: float | None = None
    median: float | None = None
    p90: float | None = None
    sample: int = 0


class CycleTimesOut(BaseModel):
    overall: MetricOut = Field(default_factory=MetricOut)
    by_type: dict[str, MetricOut] = Field(default_factory=dict)
    #: Agreements not yet executed, and therefore not in the averages above.
    still_in_flight: int = 0


class StageOut(BaseModel):
    stage: str
    mean_hours: float | None = None
    p90_hours: float | None = None
    decided: int = 0
    awaiting: int = 0
    escalations: int = 0
    #: Percentage decided within their SLA, or null when none had one.
    sla_adherence: float | None = None
    sla_sample: int = 0


class StagePerformanceOut(BaseModel):
    stages: list[StageOut] = Field(default_factory=list)
    #: The slowest stage — where agreements actually wait.
    bottleneck: str | None = None


class ReviewerLoadOut(BaseModel):
    user_id: str
    name: str
    role: str = ""
    open: int = 0
    overdue: int = 0
    decided: int = 0
    mean_hours: float | None = None


class RenewalItemOut(BaseModel):
    id: str
    reference_no: str = ""
    title: str = ""
    counterparty: str = ""
    end_date: dt.date | None = None
    days: int = 0
    value: float = 0.0
    currency: str = ""
    renewal_type: str = ""


class RenewalPipelineOut(BaseModel):
    buckets: dict[str, list[RenewalItemOut]] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    #: Total value of everything expiring within 90 days or already past.
    value_at_risk: float = 0.0


class EscalationPointOut(BaseModel):
    month: str
    count: int


class EscalationTrendOut(BaseModel):
    series: list[EscalationPointOut] = Field(default_factory=list)
    total: int = 0
    #: Hours from escalation to decision — how long it took once escalated, not the whole step.
    mean_resolution_hours: float | None = None
    resolution_sample: int = 0


class NegotiatedContractOut(BaseModel):
    contract_id: str
    reference_no: str = ""
    title: str = ""
    redlines: int = 0
    counterparty_returns: int = 0


class NegotiationEffortOut(BaseModel):
    mean_redline_rounds: float | None = None
    max_redline_rounds: int = 0
    contracts_negotiated: int = 0
    counterparty_returns: int = 0
    most_negotiated: list[NegotiatedContractOut] = Field(default_factory=list)


class ClausePressureOut(BaseModel):
    clause_key: str
    title: str
    used: int = 0
    altered: int = 0
    missing: int = 0
    #: altered + missing — how often this clause is a fight.
    pressure: int = 0


class DeviatingContractOut(BaseModel):
    contract_id: str
    reference_no: str = ""
    title: str = ""
    status: str = ""
    deviations: int = 0
    blockers: int = 0
    findings: list[str] = Field(default_factory=list)


class CompliancePostureOut(BaseModel):
    checked: int = 0
    compliant: int = 0
    deviating: int = 0
    blockers: int = 0
    missing_mandatory_clauses: int = 0
    non_standard: int = 0
    overdue_obligations: int = 0
    worst: list[DeviatingContractOut] = Field(default_factory=list)


class VolumePointOut(BaseModel):
    period: str
    raised: int = 0
    executed: int = 0
    #: The same period a year earlier, aligned by period key rather than list offset.
    raised_year_ago: int | None = None


class VolumeTrendOut(BaseModel):
    granularity: str = "month"
    series: list[VolumePointOut] = Field(default_factory=list)


class SegmentOut(BaseModel):
    label: str
    count: int = 0
    value: float = 0.0


class SegmentationOut(BaseModel):
    by_department: list[SegmentOut] = Field(default_factory=list)
    by_region: list[SegmentOut] = Field(default_factory=list)
    by_entity_type: list[SegmentOut] = Field(default_factory=list)
    by_type: list[SegmentOut] = Field(default_factory=list)
    by_status: list[SegmentOut] = Field(default_factory=list)
    by_currency: list[SegmentOut] = Field(default_factory=list)


class TypeCountOut(BaseModel):
    type: str
    count: int


class MyReviewOut(BaseModel):
    step_id: str
    name: str
    contract_id: str = ""
    reference_no: str = ""
    title: str = ""
    due_at: dt.datetime | None = None
    overdue: bool = False
    escalated: bool = False


class MyObligationOut(BaseModel):
    id: str
    title: str
    due_date: dt.date | None = None
    contract_id: str
    reference_no: str = ""
    overdue: bool = False


class MyRenewalOut(BaseModel):
    id: str
    reference_no: str = ""
    title: str = ""
    end_date: dt.date | None = None
    days: int = 0
    renewal_type: str = ""


class MyDashboardOut(BaseModel):
    """One call rather than four — this is the first screen after login."""
    reviews: list[MyReviewOut] = Field(default_factory=list)
    reviews_due_today: list[MyReviewOut] = Field(default_factory=list)
    escalations: list[MyReviewOut] = Field(default_factory=list)
    obligations: list[MyObligationOut] = Field(default_factory=list)
    renewals: list[MyRenewalOut] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class ExecutiveSummaryOut(BaseModel):
    cycle_times: CycleTimesOut = Field(default_factory=CycleTimesOut)
    stages: StagePerformanceOut = Field(default_factory=StagePerformanceOut)
    renewals: RenewalPipelineOut = Field(default_factory=RenewalPipelineOut)
    escalations: EscalationTrendOut = Field(default_factory=EscalationTrendOut)
    compliance: CompliancePostureOut = Field(default_factory=CompliancePostureOut)
    most_requested: list[TypeCountOut] = Field(default_factory=list)


# ---------- SAML (Phase 7, item 1) ----------


class SamlConfigOut(BaseModel):
    """Public SAML status for the login page and the SSO admin screen.

    Reports URLs and whether a certificate is configured — never the certificate itself and
    never a secret. Everything here is already visible to the IdP administrator.
    """
    enabled: bool = False
    entity_id: str = ""
    acs_url: str = ""
    sls_url: str = ""
    metadata_url: str = ""
    idp_sso_url: str = ""
    idp_slo_url: str = ""
    login_url: str = ""
    default_role: str = "author"
    group_role_map: dict = Field(default_factory=dict)
    certificate_configured: bool = False


# ---------- Sanctions screening + SIEM (Phase 7, items 2 and 7) ----------


class SanctionsHitOut(BaseModel):
    entry_id: str
    name: str
    source: str
    list_name: str = ""
    programme: str = ""
    entity_type: str = ""
    country: str = ""
    #: 0..1 similarity.
    score: float = 0.0
    #: `probable` or `possible` — an analyst triages differently on each.
    confidence: str = "possible"
    #: Which field matched, so a reviewer can see why without re-deriving it.
    matched_on: str = "name"
    reference: str = ""
    snapshot_date: dt.date | None = None


class SanctionsScreeningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    party_id: str
    party_name: str
    hits: list[SanctionsHitOut] = Field(default_factory=list)
    hit_count: int = 0
    #: clear | review | cleared | confirmed
    status: str
    threshold: float = 0.85
    #: The oldest active list snapshot at screening time — a screen is only as current as its
    #: stalest list.
    list_snapshot_date: dt.date | None = None
    decision_note: str = ""
    screened_by: str = ""
    decided_by: str = ""
    decided_at: dt.datetime | None = None
    created_at: dt.datetime


class SanctionsDecisionIn(BaseModel):
    cleared: bool
    #: Required either way. "Cleared" with no reason is indistinguishable from somebody
    #: clicking through it.
    note: str = Field(min_length=1, max_length=1000)


class SanctionsScreenIn(BaseModel):
    #: Override the match threshold for one screen. Lower finds more and costs review time.
    threshold: float | None = None


class SanctionsImportIn(BaseModel):
    #: OFAC | UN | EU | HMT | LOCAL
    source: str
    list_name: str = ""
    snapshot_date: dt.date | None = None
    #: [{name, aliases, entity_type, country, programme, reference}]
    entries: list[dict] = Field(default_factory=list)


class SanctionsSourceOut(BaseModel):
    source: str
    snapshot_date: dt.date | None = None
    entries: int = 0
    age_days: int | None = None
    stale: bool = False


class SanctionsStatusOut(BaseModel):
    sources: list[SanctionsSourceOut] = Field(default_factory=list)
    loaded: bool = False
    #: Oldest snapshot across sources — what the screen is actually worth.
    oldest: dt.date | None = None
    any_stale: bool = False


class SiemStatusOut(BaseModel):
    """SIEM feed status. Reports the destination, never a credential."""
    enabled: bool = False
    host: str = ""
    port: int = 0
    tls: bool = True
    verify: bool = True
    format: str = "cef"
    #: Consecutive delivery failures. Non-zero means the collector is unreachable — and the
    #: audit log is still intact, so the gap can be replayed.
    consecutive_failures: int = 0


# ---------- Access control and data protection (Phase 8) ----------


class MyPermissionsOut(BaseModel):
    role: str
    permissions: list[str] = Field(default_factory=list)


class CustomRoleIn(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    #: A custom role always starts from a built-in, so an unrecognised role degrades to a
    #: known baseline rather than to no access at all.
    base_role: str = "viewer"
    grants: list[str] = Field(default_factory=list)
    #: Applied after grants — a revoke always wins.
    revokes: list[str] = Field(default_factory=list)


class CustomRoleUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    base_role: str | None = None
    grants: list[str] | None = None
    revokes: list[str] | None = None
    is_active: bool | None = None


class CustomRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    name: str
    description: str
    base_role: str
    grants: list[str] = Field(default_factory=list)
    revokes: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: dt.datetime


class RolesOut(BaseModel):
    builtin: list[dict] = Field(default_factory=list)
    custom: list[CustomRoleOut] = Field(default_factory=list)
    #: Every permission the application checks, so an administrator can compose a role from
    #: names they recognise rather than guessing.
    permissions: list[str] = Field(default_factory=list)


class StepUpIn(BaseModel):
    password: str = ""
    totp: str = ""


class StepUpOut(BaseModel):
    challenge_id: str
    status: str
    method: str = ""
    action: str = ""


class GrantAccessIn(BaseModel):
    user_id: str | None = None
    role: str | None = None
    #: read | write
    level: str = "read"
    reason: str = ""
    expires_at: dt.datetime | None = None
    #: A satisfied step-up challenge. Granting access to a confidential agreement is one of
    #: the actions that needs re-authentication.
    challenge_id: str = ""


class ContractAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    user_id: str | None = None
    user_name: str = ""
    role: str | None = None
    level: str
    reason: str = ""
    granted_by: str = ""
    expires_at: dt.datetime | None = None
    created_at: dt.datetime


class BreakGlassIn(BaseModel):
    reason: str = Field(min_length=1, max_length=400)


class ConfidentialIn(BaseModel):
    confidential: bool
    reason: str = ""


class LegalHoldIn(BaseModel):
    matter: str = Field(min_length=1, max_length=200)
    contract_ids: list[str] = Field(min_length=1)
    reason: str = ""
    reference: str = ""
    custodian: str = ""


class ReleaseHoldIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    challenge_id: str = ""


class LegalHoldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    matter: str
    reference: str = ""
    reason: str = ""
    contract_ids: list[str] = Field(default_factory=list)
    status: str
    custodian: str = ""
    placed_by: str = ""
    placed_at: dt.datetime
    released_by: str = ""
    released_at: dt.datetime | None = None
    release_reason: str = ""


class TemporaryAccessIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = ""
    organisation: str = ""
    #: view | comment
    scope: str = "view"
    days: int = 14
    #: Watermarks name the viewer, so a screenshot carries its source.
    watermark: bool = True
    allow_download: bool = False


class TemporaryAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    email: str
    name: str = ""
    organisation: str = ""
    scope: str
    status: str
    expires_at: dt.datetime
    watermark: bool = True
    allow_download: bool = False
    last_seen_at: dt.datetime | None = None
    view_count: int = 0
    created_at: dt.datetime


class TemporaryAccessCreatedOut(TemporaryAccessOut):
    """The link, returned once. Only its hash is stored, so it cannot be shown again."""
    url: str = ""


# ---------- WebAuthn / passkeys (Phase 8, item 1) ----------


class PasskeyOut(BaseModel):
    id: str
    label: str
    transports: list[str] = Field(default_factory=list)
    #: True for a synced passkey (iCloud, Google). Worth surfacing: a synced credential is
    #: recoverable by the user but also present on every device their account touches.
    backed_up: bool = False
    created_at: dt.datetime
    last_used_at: dt.datetime | None = None


class PasskeyStatusOut(BaseModel):
    enabled: bool = False
    rp_id: str = ""
    credentials: list[PasskeyOut] = Field(default_factory=list)
    count: int = 0
    #: Whether this account could still sign in if every passkey were lost.
    has_fallback: bool = False


class PasskeyRegisterIn(BaseModel):
    #: The raw credential object from `navigator.credentials.create()`.
    credential: dict
    label: str = ""


class PasskeyAuthenticateIn(BaseModel):
    credential: dict


class PasskeyRenameIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)


# ---------- Adoption: help, knowledge base, training, guidance (Phase 9) ----------


class HelpTopicOut(BaseModel):
    key: str
    title: str = ""
    body: str = ""
    surface: str = ""
    locale: str = "en"
    #: False when this topic fell back to English because the locale has no translation yet.
    is_translated: bool = True


class HelpTopicIn(BaseModel):
    title: str | None = None
    body: str | None = None
    surface: str | None = None
    locale: str = "en"


class HelpAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    locale: str
    title: str
    body: str
    surface: str
    #: True while the row still holds the wording that shipped. The editor shows it so nobody
    #: wonders whether a topic has been reviewed.
    is_default: bool
    updated_at: dt.datetime


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    locale: str
    title: str
    summary: str = ""
    category: str
    tags: list[str] = Field(default_factory=list)
    video_file_id: str | None = None
    video_duration_s: int = 0
    audience_roles: list[str] = Field(default_factory=list)
    sort_order: int = 0
    is_published: bool = True
    view_count: int = 0
    updated_at: dt.datetime


class ArticleDetailOut(ArticleOut):
    body: str = ""


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body: str = ""
    slug: str = ""
    summary: str = ""
    category: Literal["quickstart", "playbook", "faq", "release_note"] = "faq"
    locale: str = "en"
    tags: list[str] = Field(default_factory=list)
    audience_roles: list[str] = Field(default_factory=list)
    video_file_id: str | None = None
    video_duration_s: int = 0
    sort_order: int = 0
    is_published: bool = True


class KnowledgeIndexOut(BaseModel):
    categories: list[dict] = Field(default_factory=list)
    articles: list[ArticleOut] = Field(default_factory=list)


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    title: str
    summary: str = ""
    for_roles: list[str] = Field(default_factory=list)
    pass_mark: int = 80
    estimated_minutes: int = 0
    certificate_valid_months: int = 12
    is_required: bool = False
    is_published: bool = True
    sort_order: int = 0


class CourseDetailOut(CourseOut):
    modules: list[dict] = Field(default_factory=list)
    #: The quiz **without its answer key** — see `training_service.quiz_for`.
    quiz: list[dict] = Field(default_factory=list)


class CourseIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = ""
    summary: str = ""
    for_roles: list[str] = Field(default_factory=list)
    modules: list[dict] = Field(default_factory=list)
    #: Each entry: {"q", "options": [...], "answer": <index>, "why": "..."}. The answer never
    #: leaves the server again once stored.
    quiz: list[dict] = Field(default_factory=list)
    pass_mark: int = Field(default=80, ge=1, le=100)
    certificate_valid_months: int = Field(default=12, ge=0, le=120)
    is_required: bool = False
    is_published: bool = True
    sort_order: int = 0


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str = "not_started"
    completed_modules: list[int] = Field(default_factory=list)
    attempts: int = 0
    best_score: int = 0
    last_score: int = 0
    started_at: dt.datetime | None = None
    passed_at: dt.datetime | None = None
    expires_at: dt.datetime | None = None
    certificate_no: str = ""


class TrainingItemOut(BaseModel):
    course: CourseOut
    progress: ProgressOut | None = None
    modules_total: int = 0
    modules_done: int = 0
    percent: int = 0
    #: `none` | `valid` | `expired` — computed, never stored.
    certificate: str = "none"


class MyTrainingOut(BaseModel):
    items: list[TrainingItemOut] = Field(default_factory=list)
    required_total: int = 0
    required_done: int = 0


class QuizSubmitIn(BaseModel):
    #: One chosen option index per question, in order.
    answers: list[int]


class QuizResultOut(BaseModel):
    score: int
    passed: bool
    pass_mark: int
    correct: int
    total: int
    attempt: int
    certificate_no: str = ""
    expires_at: dt.datetime | None = None
    #: Only the questions that were wrong, and only after the attempt was recorded.
    review: list[dict] = Field(default_factory=list)


class TrainingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str = ""
    kind: str = "webinar"
    starts_at: dt.datetime
    duration_minutes: int = 60
    location: str = ""
    trainer: str = ""
    capacity: int = 0
    registered_user_ids: list[str] = Field(default_factory=list)
    attended_user_ids: list[str] = Field(default_factory=list)
    is_cancelled: bool = False


class TrainingSessionIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    starts_at: dt.datetime
    kind: Literal["webinar", "onsite", "office_hours"] = "webinar"
    description: str = ""
    duration_minutes: int = Field(default=60, ge=1, le=1440)
    location: str = ""
    trainer: str = ""
    capacity: int = Field(default=0, ge=0)


class AttendanceIn(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class TrainingReportOut(BaseModel):
    active_users: int = 0
    people_with_a_valid_certificate: int = 0
    courses: list[dict] = Field(default_factory=list)
    sessions_scheduled: int = 0
    sessions_delivered: int = 0
    people_attended: int = 0


class SuggestionOut(BaseModel):
    key: str
    title: str
    detail: str = ""
    action: str = ""
    #: The permission needed to carry it out, so the caller can show guidance rather than an
    #: offer somebody cannot accept.
    permission: str = ""
    severity: Literal["critical", "warning", "info"] = "info"
    href: str = ""


class StageOut(BaseModel):
    stage: str
    label: str
    index: int
    total: int
    stages: list[dict] = Field(default_factory=list)
    is_closed: bool = False


class GuidanceOut(BaseModel):
    progress: StageOut
    actions: list[SuggestionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Bulk send (Phase 10 / BB-09)
# ---------------------------------------------------------------------------------------


class BulkSendRowIn(BaseModel):
    """One recipient. `values` carries this row's merge fields; anything not set here falls
    back to the batch's shared values.

    Deliberately no `min_length` on name or email. A field constraint here rejects the whole
    request with a Pydantic locator — `body.rows.3.name` — and the operator learns that one of
    five hundred rows is wrong but not which others are, because validation stopped at the
    first. Emptiness is checked in `bulk_send_service.validate_rows`, which reports every bad
    row in one pass with a sentence a person can act on. Length caps stay: they bound the
    request, they do not decide whether it is sendable.
    """
    name: str = Field(max_length=200)
    email: str = Field(max_length=255)
    values: dict = Field(default_factory=dict)


class BulkSendIn(BaseModel):
    template_id: str
    rows: list[BulkSendRowIn] = Field(min_length=1)
    name: str = ""
    message: str = ""
    shared_values: dict = Field(default_factory=dict)
    #: 0 disables automatic chasing entirely.
    reminder_interval_days: int = Field(default=0, ge=0, le=365)
    max_reminders: int = Field(default=0, ge=0, le=20)
    #: 0 means the envelope never expires; the per-recipient link still has its own TTL.
    expiry_days: int = Field(default=0, ge=0, le=365)


class BulkSendItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sequence: int
    name: str
    email: str
    status: str
    contract_id: str | None = None
    envelope_id: str | None = None
    error: str = ""
    sent_at: dt.datetime | None = None


class BulkSendBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    template_id: str
    name: str
    status: str
    total: int
    succeeded: int
    failed: int
    message: str = ""
    reminder_interval_days: int = 0
    max_reminders: int = 0
    expiry_days: int = 0
    job_id: str | None = None
    created_by: str
    created_at: dt.datetime
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


class BulkSendBatchDetail(BulkSendBatchOut):
    template_name: str = ""
    items: list[BulkSendItemOut] = Field(default_factory=list)


class BulkSendValidateOut(BaseModel):
    """A dry run. `problems` is empty when the batch would send."""
    rows: int
    problems: list[dict] = Field(default_factory=list)
