import datetime as dt

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


class ContractDetail(ContractListItem):
    governing_law: str
    ai_summary: str
    body: str
    created_by: str
    available_transitions: list[str] = []


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
    password: str = Field(min_length=8, max_length=128)


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
