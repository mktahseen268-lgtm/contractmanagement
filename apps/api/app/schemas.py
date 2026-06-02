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
    accent_color: str = "#3E7BFA"
    timezone: str = "UTC"


class TenantUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    currency: str | None = None
    locale: str | None = None
    timezone: str | None = None
    accent_color: str | None = None  # CSS color (#RRGGBB recommended)


class UserUpdateIn(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    avatar_color: str
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


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    contract_id: str
    author_id: str
    author_name: str
    body: str
    resolved: bool
    created_at: dt.datetime


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
    steps: list[WorkflowStep]
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkflowDefinitionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: str = "draft"
    default_for_types: list[str] = []
    steps: list[WorkflowStep] = []


class WorkflowDefinitionUpdateIn(BaseModel):
    name: str | None = None
    status: str | None = None
    default_for_types: list[str] | None = None
    steps: list[WorkflowStep] | None = None


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
