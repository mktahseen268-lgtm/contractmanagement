export type Role =
  | "owner"
  | "admin"
  | "manager"
  | "author"
  | "approver"
  | "reviewer"
  | "viewer"
  | "auditor";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  avatar_color: string;
  department: string;
  mfa_enabled: boolean;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  locale: string;
  currency: string;
  plan: string;
  group_name: string;
  accent_color: string;
  timezone: string;
}

export interface Me {
  user: User;
  tenant: Tenant;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  tenant: Tenant;
}

export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
  methods: string[];
}

export interface SessionInfo {
  id: string;
  user_agent: string;
  ip: string;
  created_at: string;
  last_used_at: string;
  current: boolean;
}

export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
}

export interface ContractListItem {
  id: string;
  reference_no: string;
  title: string;
  type: string;
  status: string;
  owner_id: string;
  owner_name: string;
  counterparty: string;
  /** The client record behind the name, where one has been linked. */
  party_id: string | null;
  department: string;
  value: number;
  currency: string;
  effective_date: string | null;
  end_date: string | null;
  renewal_type: string;
  risk_level: string;
  tags: string[];
  source: string;
  updated_at: string;
  created_at: string;
}

export interface ContractRef {
  id: string;
  reference_no: string;
  title: string;
  status: string;
}

export interface ContractDetail extends ContractListItem {
  governing_law: string;
  ai_summary: string;
  body: string;
  created_by: string;
  available_transitions: string[];
  renewed_from_id: string | null;
  renewed_from: ContractRef | null;
  renewed_to: ContractRef | null;
}

export interface SweepResult {
  flagged_expiring: number;
  moved_to_expired: number;
  reminders_sent: number;
  obligations_overdue: number;
}

export interface ContractTemplate {
  id: string;
  name: string;
  description: string;
  contract_type: string;
  body: string;
  default_currency: string;
  default_term_months: number;
  default_renewal_type: string;
  default_risk_level: string;
  default_governing_law: string;
  default_tags: string[];
  is_active: boolean;
  usage_count: number;
  created_at: string;
  updated_at: string;
  /** draft | pending_approval | active | retired. Authoritative; is_active is derived. */
  status: TemplateStatus;
  fields: TemplateField[];
  version_no: number;
  effective_from: string | null;
  approved_by: string;
  approved_at: string | null;
  approval_note: string;
}

export type TemplateStatus = "draft" | "pending_approval" | "active" | "retired";

export type TemplateFieldType =
  | "text" | "textarea" | "number" | "money" | "date"
  | "select" | "multiselect" | "boolean" | "entity_ref" | "file";

/** One question on a template's intake form. */
export interface TemplateField {
  key: string;
  label: string;
  type: TemplateFieldType;
  required: boolean;
  options: string[];
  default: unknown;
  help: string;
  group: string;
  entity_kind: string;
  minimum: number | null;
  maximum: number | null;
}

export interface TemplateForm {
  template_id: string;
  name: string;
  description: string;
  contract_type: string;
  status: TemplateStatus;
  version_no: number;
  /** False until the template is approved — the form renders read-only rather than letting
   *  someone fill it in and only then discover they cannot submit. */
  usable: boolean;
  fields: TemplateField[];
  placeholders: string[];
  problems: string[];
  /** Per referenced clause, the pre-approved alternatives a drafter may pick, with risk. */
  clause_choices: {
    key: string;
    title: string;
    options: {
      key: string; title: string; position: string; risk_level: string;
      guidance: string; body: string; is_default: boolean;
    }[];
  }[];
  defaults: {
    currency?: string;
    term_months?: number;
    renewal_type?: string;
    risk_level?: string;
    governing_law?: string;
    tags?: string[];
  };
}

export interface TemplatePreview {
  body: string;
  errors: string[];
  /** Placeholders nothing filled — reported, never silently blanked. */
  unresolved: string[];
  substituted: Record<string, string>;
  values: Record<string, unknown>;
  version_no: number | null;
  /** Referenced clauses with no approved wording — generation refuses outright. */
  missing_clauses: string[];
  ok: boolean;
}

export interface TemplateVersion {
  id: string;
  version_no: number;
  name: string;
  status: string;
  change_summary: string;
  approved_by: string;
  approved_at: string | null;
  created_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
  token?: string; // only present on create
}

export interface WebhookEndpoint {
  id: string;
  url: string;
  description: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  last_delivery_at: string | null;
  last_status: string;
  secret?: string; // only present on create
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event: string;
  status: string;
  response_code: number;
  response_snippet: string;
  attempts: number;
  created_at: string;
  delivered_at: string | null;
}

export interface BackgroundJob {
  id: string;
  type: string;
  label: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  result_summary: string;
  error: string;
  object_type: string;
  object_id: string | null;
  href: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Obligation {
  id: string;
  contract_id: string;
  title: string;
  description: string;
  due_date: string | null;
  owner_id: string | null;
  owner_name: string;
  status: "pending" | "done" | "skipped" | "overdue";
  completed_at: string | null;
  completed_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Comment {
  id: string;
  contract_id: string;
  author_id: string;
  author_name: string;
  body: string;
  resolved: boolean;
  created_at: string;
  kind: "comment" | "amendment";
  internal_only: boolean;
  department: string;
  /** Character range this thread is anchored to, for redline threads. */
  anchor_start: number | null;
  anchor_end: number | null;
}

export interface ActivityItem {
  id: string;
  at: string;
  actor_name: string;
  action: string;
  object_type: string;
  object_id: string | null;
  object_label: string;
}

export interface AuditItem extends ActivityItem {
  actor_id: string | null;
  meta: Record<string, unknown>;
  ip: string;
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface Dashboard {
  total_contracts: number;
  pending_approvals: number;
  awaiting_signature: number;
  expiring_30d: number;
  active_value: number;
  open_risks: number;
  by_status: StatusCount[];
  by_type: StatusCount[];
  recent_activity: ActivityItem[];
  my_open: ContractListItem[];
  expiring_soon: ContractListItem[];
}

// ---------- e-signature ----------

export interface SignatureRecipient {
  id: string;
  sequence: number;
  name: string;
  email: string;
  kind: "signer" | "cc";
  status: "created" | "sent" | "viewed" | "signed" | "declined";
  signed_name: string;
  signed_at: string | null;
  declined_reason: string;
  ip: string;
  signing_link: string | null;
}

export interface SignatureTab {
  id: string;
  envelope_id: string;
  recipient_id: string;
  kind: "signature" | "initials" | "date" | "text" | "checkbox";
  page: number;
  x: number;       // 0..1
  y: number;       // 0..1 (from top)
  width: number;   // 0..1
  height: number;  // 0..1
  required: boolean;
  label: string;
  value: string;
  filled_at: string | null;
}

export interface SignatureEnvelope {
  id: string;
  contract_id: string;
  status: "draft" | "sent" | "partially_signed" | "completed" | "declined" | "voided" | "expired";
  signing_order: "sequential" | "parallel";
  message: string;
  document_file_id: string | null;
  sealed_pdf_file_id: string | null;
  certificate_file_id: string | null;
  created_by: string;
  created_at: string;
  sent_at: string | null;
  completed_at: string | null;
  recipients: SignatureRecipient[];
  tabs: SignatureTab[];
}

export interface SigningInfo {
  valid: boolean;
  reason: string;
  org_name: string;
  contract_title: string;
  contract_reference: string;
  sender_name: string;
  message: string;
  recipient_name: string;
  recipient_email: string;
  recipient_status: string;
  can_sign: boolean;
  waiting_reason: string;
  document_path: string;
  consent_text: string;
  envelope_status: string;
  sealed_pdf_path: string;
  tabs: SignatureTab[];
}

// ---------- workflows ----------

export interface WorkflowStep {
  name: string;
  assignee_kind: "role" | "user";
  assignee_value: string;
}

export interface WorkflowDefinitionListItem {
  id: string;
  name: string;
  status: "draft" | "active" | "archived";
  default_for_types: string[];
  step_count: number;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDefinitionDetail {
  id: string;
  name: string;
  status: "draft" | "active" | "archived";
  default_for_types: string[];
  /** Legacy flat list. `stages` is authoritative when present; a definition with only
   *  `steps` promotes to one step per stage, which is the old sequential behaviour. */
  steps: WorkflowStep[];
  stages: WorkflowStageDef[];
  non_standard_stages: WorkflowStageDef[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowRunStep {
  id: string;
  step_index: number;
  name: string;
  assignee_kind: "role" | "user";
  assignee_value: string;
  status: "pending" | "active" | "approved" | "rejected" | "changes_requested" | "skipped";
  decision: string | null;
  decided_by: string | null;
  decided_by_name: string;
  decided_at: string | null;
  comment: string;
}

export interface WorkflowRun {
  id: string;
  contract_id: string;
  definition_id: string | null;
  definition_name: string;
  status: "running" | "approved" | "rejected" | "changes_requested" | "cancelled";
  current_index: number;
  started_by: string;
  started_by_name: string;
  started_at: string;
  completed_at: string | null;
  steps: WorkflowRunStep[];
}

export interface WorkflowRunListItem {
  id: string;
  contract_id: string;
  contract_title: string;
  definition_name: string;
  status: string;
  current_step_name: string;
  started_by_name: string;
  started_at: string;
  completed_at: string | null;
}

export interface WorkflowOption {
  id: string;
  name: string;
  is_default: boolean;
}

export interface ContractWorkflow {
  run: WorkflowRun | null;
  can_decide: boolean;
  default_workflow_id: string | null;
  available_workflows: WorkflowOption[];
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  object_type: string;
  object_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface FileObject {
  id: string;
  original_name: string;
  content_type: string;
  size: number;
  kind: string;
  backend: string;
  created_at: string;
}

export interface Version {
  id: string;
  version_no: number;
  change_summary: string;
  created_by: string;
  created_at: string;
}

export interface VersionDetail extends Version {
  body: string;
}

// ---------- inbox ("waiting on you") ----------

export interface InboxItem {
  id: string;
  kind: "approval" | "signature" | "obligation";
  contract_id: string;
  contract_title: string;
  contract_reference: string;
  contract_status: string;
  contract_type: string;
  risk_level: string;
  value: number;
  currency: string;
  title: string;
  subtitle: string;
  since: string | null;
  waiting_hours: number;
  priority: "normal" | "high";
  href: string;
}

export interface InboxSummary {
  approvals: number;
  signatures: number;
  obligations: number;
  total: number;
  high_priority: number;
}

// ---------- reports & analytics ----------

export interface ReportBucket {
  label: string;
  count: number;
  value: number;
}

export interface ReportSeriesPoint {
  label: string;
  count: number;
  value: number;
}

export interface ReportCycleTime {
  approval_avg_days: number;
  approval_median_days: number;
  approval_n: number;
  signature_avg_days: number;
  signature_median_days: number;
  signature_n: number;
  end_to_end_avg_days: number;
  end_to_end_n: number;
}

export interface ReportThroughput {
  workflow_runs_started: number;
  workflow_runs_approved: number;
  workflow_runs_rejected: number;
  workflow_runs_changes_requested: number;
  envelopes_sent: number;
  envelopes_completed: number;
  envelopes_declined: number;
  envelopes_voided: number;
}

export interface ReportApprover {
  user_id: string;
  name: string;
  approved: number;
  rejected: number;
  changes_requested: number;
  total: number;
  avg_response_hours: number;
}

export interface ReportExpiringItem {
  id: string;
  reference_no: string;
  title: string;
  counterparty: string;
  end_date: string | null;
  days_to_end: number;
  value: number;
  currency: string;
  status: string;
}

export interface StuckItem {
  kind: "approval_step" | "envelope";
  contract_id: string;
  contract_title: string;
  contract_reference: string;
  contract_status: string;
  risk_level: string;
  waiting_hours: number;
  detail: string;
  href: string;
}

export interface ReportSummary {
  range_from: string; // YYYY-MM-DD
  range_to: string;
  total_contracts: number;
  created_in_range: number;
  signed_in_range: number;
  active_count: number;
  active_value: number;
  expiring_30d: number;
  expiring_90d: number;
  by_status: ReportBucket[];
  by_type: ReportBucket[];
  by_risk: ReportBucket[];
  by_department: ReportBucket[];
  new_per_month: ReportSeriesPoint[];
  cycle_time: ReportCycleTime;
  throughput: ReportThroughput;
  expiring_buckets: ReportBucket[];
  expiring_top: ReportExpiringItem[];
  top_approvers: ReportApprover[];
}

export interface OcrJob {
  id: string;
  status: string;
  file_name: string;
  progress: number;
  result: {
    fields?: Record<string, { value: unknown; confidence: number }>;
    risk_level?: string;
    summary?: string;
    detected_clauses?: string[];
    tables_found?: number;
    languages?: string[];
    pages?: number;
    source_file_id?: string | null;
  };
  created_contract_id: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------------------
// PKI (Phase 1) — mirrors app/schemas.py
// ---------------------------------------------------------------------------------------

export interface CertificateAuthority {
  id: string;
  name: string;
  kind: "root" | "issuing" | "ocsp";
  subject_dn: string;
  issuer_dn: string;
  parent_ca_id: string | null;
  key_algorithm: string;
  serial_number: string;
  not_before: string;
  not_after: string;
  status: string;
  is_offline: boolean;
  crl_number: number;
  base_crl_number: number;
  created_at: string;
}

export interface CaChain {
  ca: CertificateAuthority;
  chain_pem: string[];
}

export interface CertificateRequestRow {
  id: string;
  subject_dn: string;
  subject_user_id: string | null;
  subject_party_id: string | null;
  subject_email: string;
  profile: string;
  status: "pending" | "approved" | "rejected" | "issued" | "cancelled";
  evidence: Record<string, unknown>;
  requested_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  second_reviewed_by: string | null;
  second_reviewed_at: string | null;
  review_note: string;
  created_at: string;
  subject_name: string;
  requested_by_name: string;
}

export interface Certificate {
  id: string;
  ca_id: string;
  request_id: string | null;
  subject_dn: string;
  subject_user_id: string | null;
  subject_party_id: string | null;
  subject_email: string;
  profile: string;
  serial_number: string;
  key_algorithm: string;
  not_before: string;
  not_after: string;
  status: "active" | "suspended" | "revoked" | "expired";
  revocation_reason: string;
  revoked_at: string | null;
  renewed_from_id: string | null;
  created_at: string;
  subject_name: string;
  days_remaining: number;
  pem?: string | null;
}

export interface CertificateList {
  items: Certificate[];
  total: number;
  page: number;
  page_size: number;
}

export interface TrustAnchor {
  id: string;
  name: string;
  subject_dn: string;
  fingerprint_sha256: string;
  source: string;
  is_active: boolean;
  created_at: string;
  not_after: string | null;
}

export interface ValidationResult {
  ok: boolean;
  reason: string;
  chain: string[];
  revocation_checked: boolean;
  warnings: string[];
}

export interface PkiHealth {
  provisioned: boolean;
  keystore_provider: string;
  hsm_connected: boolean | null;
  hsm_detail: string;
  root_ca: CertificateAuthority | null;
  issuing_ca: CertificateAuthority | null;
  ocsp_responder: CertificateAuthority | null;
  root_offline: boolean;
  certificates_active: number;
  certificates_suspended: number;
  certificates_revoked: number;
  certificates_expired: number;
  certificates_expiring_30d: number;
  pending_requests: number;
  crl_number: number;
  crl_last_published: string | null;
  crl_next_update: string | null;
  crl_stale: boolean;
  dual_control: boolean;
  warnings: string[];
}

/** RFC 5280 §5.3.1 revocation reasons the API accepts. `certificate_hold` is not here —
 *  a reversible hold goes through the suspend action instead. */
export const REVOCATION_REASONS = [
  "unspecified",
  "key_compromise",
  "ca_compromise",
  "affiliation_changed",
  "superseded",
  "cessation_of_operation",
  "privilege_withdrawn",
  "aa_compromise",
] as const;

// ---------------------------------------------------------------------------------------
// Visitor eSigning (Phase 2) — the public surface, mirrors app/schemas.py
// ---------------------------------------------------------------------------------------

export interface PowChallenge {
  required: boolean;
  challenge: string;
  bits: number;
}

export interface EsignLanding {
  label: string;
  organisation: string;
  contract_title: string;
  contract_reference: string;
  require_otp: boolean;
  otp_channel: "email" | "sms" | "any";
  collect_cnic: boolean;
  require_scroll: boolean;
  proof_of_work: PowChallenge;
}

export interface EsignStart {
  session_id: string;
  masked_identifier: string;
  channel: string;
  otp_required: boolean;
  expires_in: number;
}

export interface EsignVerify {
  session_id: string;
  signing_token: string;
  signing_url: string;
  recipient_id: string;
  certificate_serial: string;
  certificate_expires_at: string | null;
}

export interface EsignConsent {
  may_sign: boolean;
  reason: string;
  pages_viewed: number;
  total_pages: number;
}

export interface SigningInvitation {
  id: string;
  contract_id: string;
  label: string;
  otp_channel: string;
  require_otp: boolean;
  collect_cnic: boolean;
  max_signatures: number;
  signature_count: number;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  /** Returned only when the invitation is created — the raw token is never stored. */
  url?: string | null;
  qr_svg?: string | null;
}

export interface VisitorSessionRow {
  id: string;
  name: string;
  otp_channel: string;
  entry_point: string;
  status: string;
  verified_at: string | null;
  scroll_completed_at: string | null;
  pages_viewed: number;
  total_pages: number;
  ip: string;
  created_at: string;
  masked_identifier: string;
  certificate_serial: string;
}

// ---------------------------------------------------------------------------------------
// Workflow engine (Phase 4) — mirrors app/schemas.py
// ---------------------------------------------------------------------------------------

export type StagePolicy = "all" | "any" | "quorum" | "percentage";

/** A step as authored in the builder. Same shape as `WorkflowStep`, plus a per-step SLA. */
export interface WorkflowStepDef extends WorkflowStep {
  sla_hours?: number;
}

export interface WorkflowStageDef {
  name: string;
  policy: StagePolicy;
  threshold: number;
  sla_hours: number;
  escalate_to_user_id?: string | null;
  steps: WorkflowStepDef[];
}

export interface RunStep {
  id: string;
  stage_index: number;
  step_index: number;
  name: string;
  assignee_kind: string;
  assignee_value: string;
  status: string;
  decision: string | null;
  decided_by_name: string;
  decided_at: string | null;
  comment: string;
  sla_hours: number;
  due_at: string | null;
  activated_at: string | null;
  escalated_at: string | null;
  escalated_to: string | null;
  delegated_from: string | null;
  delegated_from_name: string;
  added_mid_flight: boolean;
  is_overdue: boolean;
  assignee_name: string;
}

export interface RunStage {
  index: number;
  name: string;
  policy: StagePolicy;
  threshold: number;
  status: "pending" | "active" | "complete";
  approvals: number;
  required: number;
  steps: RunStep[];
}

export interface WorkflowRunGraph {
  id: string;
  contract_id: string;
  definition_name: string;
  status: string;
  current_stage: number;
  started_by_name: string;
  started_at: string;
  completed_at: string | null;
  stages: RunStage[];
  my_steps: string[];
  applied_rules: string[];
}

export interface ApprovalRule {
  id: string;
  name: string;
  contract_type: string;
  department: string;
  currency: string;
  min_value: number;
  max_value: number | null;
  risk_level: string;
  governing_law: string;
  non_standard_only: boolean;
  min_playbook_deviations: number;
  stage_name: string;
  stage_policy: StagePolicy;
  stage_threshold: number;
  stage_steps: WorkflowStepDef[];
  sla_hours: number;
  escalate_to_user_id: string | null;
  insert_after_stage: number;
  priority: number;
  is_active: boolean;
  created_at: string;
}

export interface Delegation {
  id: string;
  from_user_id: string;
  from_user_name: string;
  to_user_id: string;
  to_user_name: string;
  scope: string;
  starts_at: string;
  ends_at: string;
  reason: string;
  is_active: boolean;
  created_at: string;
}

export interface Holiday {
  id: string;
  day: string;
  name: string;
}

export interface Escalation {
  step_id: string;
  run_id: string;
  contract_id: string;
  contract_title: string;
  contract_reference: string;
  step_name: string;
  stage_index: number;
  sla_hours: number;
  due_at: string | null;
  escalated_at: string | null;
  escalated_to: string | null;
  escalated_to_name: string;
  resolved_at: string | null;
  hours_to_resolve: number | null;
  status: string;
}

export interface ConsolidatedComment {
  id: string;
  contract_id: string;
  author_id: string;
  author_name: string;
  body: string;
  resolved: boolean;
  internal_only: boolean;
  department: string;
  kind: string;
  anchor_start: number | null;
  anchor_end: number | null;
  created_at: string;
}

export interface ConsolidatedGroup {
  department: string;
  comments: ConsolidatedComment[];
  amendments: number;
  unresolved: number;
}

export interface ConsolidatedReview {
  contract_id: string;
  audience: string;
  total: number;
  internal_only_count: number;
  amendments: number;
  groups: ConsolidatedGroup[];
}

export interface MentionRow {
  id: string;
  comment_id: string;
  contract_id: string;
  mentioned_by_name: string;
  internal_only: boolean;
  read_at: string | null;
  created_at: string;
  contract_title: string;
  body: string;
}

export const STAGE_POLICIES: { value: StagePolicy; label: string; hint: string }[] = [
  { value: "all", label: "Everyone must approve", hint: "The stage completes only when every reviewer has approved." },
  { value: "any", label: "Any one approval", hint: "The first approval completes the stage; the rest are no longer required." },
  { value: "quorum", label: "A set number", hint: "Completes once this many reviewers have approved." },
  { value: "percentage", label: "A proportion", hint: "Completes once this percentage of reviewers have approved." },
];

// ---------------------------------------------------------------------------------------
// Word round-trip (Phase 3) — mirrors app/schemas.py
// ---------------------------------------------------------------------------------------

export interface DocxChange {
  kind: "insert" | "delete";
  text: string;
  author: string;
  at: string | null;
  paragraph_index: number;
  context: string;
}

export interface DocxComment {
  comment_id: string;
  author: string;
  initials: string;
  text: string;
  at: string | null;
  anchor_text: string;
  paragraph_index: number | null;
}

export interface DocxImportResult {
  applied: boolean;
  version_no: number | null;
  paragraphs: number;
  tables: number;
  insertions: number;
  deletions: number;
  comment_count: number;
  authors: string[];
  has_revisions: boolean;
  warnings: string[];
  body: string;
  changes: DocxChange[];
  comments: DocxComment[];
  classified_non_standard: boolean;
}

// ---------- Clause library and playbooks ----------

export type ClauseStatus = "draft" | "pending_approval" | "active" | "retired";
export type ClausePosition = "preferred" | "acceptable" | "fallback";

export interface Clause {
  id: string;
  key: string;
  title: string;
  category: string;
  body: string;
  position: ClausePosition;
  risk_level: string;
  status: ClauseStatus;
  version_no: number;
  parent_id: string | null;
  fallback_rank: number;
  guidance: string;
  jurisdiction: string;
  tags: string[];
  usage_count: number;
  approved_by: string;
  approved_at: string | null;
  approval_note: string;
  created_at: string;
  updated_at: string;
  /** Pre-approved fallback positions, best first. Populated on detail reads. */
  alternatives: Clause[];
}

export interface ClauseVersion {
  id: string;
  version_no: number;
  title: string;
  body: string;
  position: ClausePosition;
  risk_level: string;
  status: string;
  change_summary: string;
  approved_by: string;
  approved_at: string | null;
  created_at: string;
}

export interface PlaybookRule {
  clause_key: string;
  kind: "required" | "prohibited" | "preferred";
  severity: "blocker" | "warning";
  guidance?: string;
}

export interface Playbook {
  id: string;
  name: string;
  description: string;
  contract_type: string;
  applies_when: { min_value?: number; max_value?: number; department?: string; risk_level?: string };
  rules: PlaybookRule[];
  status: string;
  created_at: string;
  updated_at: string;
}

/** One clause measured against policy. `missing` and `altered` are different problems. */
export interface PolicyFinding {
  clause_key: string;
  clause_id: string;
  title: string;
  kind: string;
  severity: "blocker" | "warning";
  status: "missing" | "altered" | "present" | "prohibited";
  ratio: number;
  risk_level: string;
  guidance: string;
  playbook: string;
  diff: string[];
}

export interface PolicyReview {
  ok: boolean;
  checked: number;
  deviation_count: number;
  blocker_count: number;
  findings: PolicyFinding[];
  playbooks: { id: string; name: string }[];
  classified_non_standard: boolean;
}

// ---------- Redline ----------

export interface RedlineChange {
  /** Position in the change list — what you send back to accept it. Stable for a given pair. */
  index: number;
  kind: "insert" | "delete" | "replace";
  before: string;
  after: string;
  before_context: string;
  after_context: string;
  anchor_start: number;
  anchor_end: number;
}

export interface Redline {
  base_label: string;
  compare_label: string;
  base_version_no: number | null;
  compare_version_no: number | null;
  changes: RedlineChange[];
  change_count: number;
  added: number;
  removed: number;
  unchanged: number;
  identical: boolean;
  base_body: string;
  compare_body: string;
}

// ---------- Sign-off readiness ----------

export interface ReadinessDecision {
  stage: number;
  name: string;
  who: string;
  decision: string;
  at: string;
  on_time: boolean | null;
  escalated: boolean;
  delegated: boolean;
  comment: string;
}

/** "Is this safe to sign, and who said so?" — `ready` is the answer, `blockers` is why not. */
export interface Readiness {
  contract_id: string;
  reference_no: string;
  title: string;
  status: string;
  ready: boolean;
  blockers: string[];
  notes: string[];
  decisions: ReadinessDecision[];
  provenance: {
    source?: string;
    template?: string;
    template_version?: string;
    edited_since_generation?: boolean | null;
    clauses?: { key: string; title: string; used: number | null; current: number | null; stale: boolean }[];
  };
  policy: { checked?: number; deviation_count?: number; blocker_count?: number };
  generated_at: string;
}

// ---------- AI assist ----------

export interface ClauseSuggestion {
  key: string;
  title: string;
  reason: string;
  /** policy | peers | risk — what the suggestion is grounded in. */
  basis: string;
  severity: string;
  risk_level: string;
  body: string;
  guidance: string;
}

export interface CapturedField {
  field: string;
  value: string;
  /** 0..1. Not a fact — a reason to look. */
  confidence: number;
  current: string;
  changes: boolean;
  suggested: boolean;
}

export interface ExtractionReview {
  id: string;
  contract_id: string;
  file_name: string;
  /** `stub` means the document was NOT read. */
  provider: string;
  status: "pending" | "applied" | "discarded";
  summary: string;
  detected_clauses: string[];
  fields: CapturedField[];
  applied_fields: string[];
  created_at: string;
  reviewed_at: string | null;
}

// ---------- Repository ----------

export interface Party {
  id: string;
  name: string;
  registration_no: string;
  entity_type: string;
  jurisdiction: string;
  region: string;
  kyc_status: string;
  kyc_note: string;
  risk_score: number;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  address: string;
  tags: string[];
  duplicate_override_of: string | null;
  duplicate_override_reason: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DuplicateMatch {
  id: string;
  name: string;
  registration_no: string;
  reason: string;
  /** `exact` (registration number) or `likely` (name similarity). */
  certainty: string;
  ratio: number;
}

export interface RelatedContract {
  relation_id: string;
  kind: string;
  label: string;
  direction: string;
  sequence: number;
  note: string;
  contract_id: string;
  reference_no: string;
  title: string;
  status: string;
  effective_date: string | null;
  end_date: string | null;
}

export interface ContractHistory {
  contract_id: string;
  ancestors: RelatedContract[];
  descendants: RelatedContract[];
}

export interface Department {
  id: string;
  name: string;
  lead_user_id: string | null;
  lead_name: string;
  cost_centre: string;
  region: string;
  is_active: boolean;
  contract_count: number;
}

export interface Folder {
  id: string;
  name: string;
  parent_id: string | null;
  /** Materialised, e.g. /Legal/Vendors/2026. */
  path: string;
  visible_to_roles: string[];
  contract_count: number;
  depth: number;
}

export interface CustomFieldDef {
  id: string;
  contract_type: string;
  key: string;
  label: string;
  type: string;
  required: boolean;
  options: string[];
  help: string;
  position: number;
  is_active: boolean;
}

export interface SearchHit {
  id: string;
  reference_no: string;
  title: string;
  type: string;
  status: string;
  counterparty: string;
  value: number;
  currency: string;
  risk_level: string;
  effective_date: string | null;
  end_date: string | null;
  owner_id: string;
  updated_at: string;
  /** Text around the match, with **bold** markers on the query terms. */
  snippet: string;
}

export interface SearchResult {
  items: SearchHit[];
  total: number;
  page: number;
  page_size: number;
  /** Counts over the whole result set, not the current page. */
  facets: Record<string, Record<string, number>>;
}

// ---------- Post-execution changes ----------

export interface ObligationRollupItem {
  id: string;
  contract_id: string;
  contract_reference: string;
  contract_title: string;
  contract_status: string;
  title: string;
  description: string;
  due_date: string | null;
  days_left: number | null;
  overdue: boolean;
  status: string;
  owner_id: string | null;
  owner_name: string;
}

export interface ObligationRollup {
  items: ObligationRollupItem[];
  total: number;
  summary: {
    open?: number;
    overdue?: number;
    due_this_week?: number;
    due_this_month?: number;
    unassigned?: number;
    done?: number;
  };
}

export interface AmendmentImpact {
  fields: Record<string, { from: string; to: string }>;
  clauses: { added?: string[]; removed?: string[] };
  body_changed: boolean;
  value_delta: number;
  term_delta_days: number | null;
  parent_id: string;
  parent_reference: string;
}

export interface TerminationRequest {
  id: string;
  contract_id: string;
  reason_code: string;
  reason: string;
  effective_date: string | null;
  notice_days: number;
  documents: Record<string, unknown>[];
  status: "pending" | "approved" | "rejected" | "executed" | "withdrawn";
  approvals: { role: string; user_id: string; name: string; decision: string; at: string; comment: string }[];
  required_roles: string[];
  notice_sent_at: string | null;
  requested_by: string;
  requested_by_name: string;
  created_at: string;
}

export interface RenewalSchedule {
  notice_days: number[];
  /** Thresholds already reached for this agreement. */
  due: number[];
  end_date: string | null;
  renewal_type: string;
}

export interface LegalChecklist {
  id: string;
  title: string;
  description: string;
  owner_function: string;
  contract_type: string;
  items: { text?: string; required?: boolean; guidance?: string }[];
  version_no: number;
  status: string;
  file_id: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---------- Analytics ----------

/** A figure with the sample it came from — hiding the sample is how numbers get misquoted. */
export interface Metric {
  mean: number | null;
  median: number | null;
  p90: number | null;
  sample: number;
}

export interface CycleTimes {
  overall: Metric;
  by_type: Record<string, Metric>;
  /** Not yet executed, and therefore not in the averages. */
  still_in_flight: number;
}

export interface StagePerformance {
  stages: {
    stage: string;
    mean_hours: number | null;
    p90_hours: number | null;
    decided: number;
    awaiting: number;
    escalations: number;
    sla_adherence: number | null;
    sla_sample: number;
  }[];
  bottleneck: string | null;
}

export interface ReviewerLoad {
  user_id: string;
  name: string;
  role: string;
  open: number;
  overdue: number;
  decided: number;
  mean_hours: number | null;
}

export interface RenewalPipeline {
  buckets: Record<string, { id: string; reference_no: string; title: string; end_date: string | null; days: number; value: number }[]>;
  counts: Record<string, number>;
  value_at_risk: number;
}

export interface EscalationTrend {
  series: { month: string; count: number }[];
  total: number;
  mean_resolution_hours: number | null;
  resolution_sample: number;
}

export interface CompliancePosture {
  checked: number;
  compliant: number;
  deviating: number;
  blockers: number;
  missing_mandatory_clauses: number;
  non_standard: number;
  overdue_obligations: number;
  worst: {
    contract_id: string;
    reference_no: string;
    title: string;
    status: string;
    deviations: number;
    blockers: number;
    findings: string[];
  }[];
}

export interface VolumeTrend {
  granularity: string;
  series: {
    period: string;
    raised: number;
    executed: number;
    raised_year_ago: number | null;
  }[];
}

export interface Segmentation {
  by_department: { label: string; count: number; value: number }[];
  by_region: { label: string; count: number; value: number }[];
  by_entity_type: { label: string; count: number; value: number }[];
  by_type: { label: string; count: number; value: number }[];
  by_status: { label: string; count: number; value: number }[];
  by_currency: { label: string; count: number; value: number }[];
}

export interface ClausePressure {
  clause_key: string;
  title: string;
  used: number;
  altered: number;
  missing: number;
  /** altered + missing — how often this clause is a fight. */
  pressure: number;
}

export interface ExecutiveSummary {
  cycle_times: CycleTimes;
  stages: StagePerformance;
  renewals: RenewalPipeline;
  escalations: EscalationTrend;
  compliance: CompliancePosture;
  most_requested: { type: string; count: number }[];
}

export interface MyDashboard {
  reviews: { step_id: string; name: string; contract_id: string; reference_no: string; title: string; due_at: string | null; overdue: boolean; escalated: boolean }[];
  reviews_due_today: { step_id: string; name: string; contract_id: string; reference_no: string; title: string; due_at: string | null; overdue: boolean; escalated: boolean }[];
  escalations: { step_id: string; name: string; contract_id: string; reference_no: string; title: string; due_at: string | null; overdue: boolean; escalated: boolean }[];
  obligations: { id: string; title: string; due_date: string | null; contract_id: string; reference_no: string; overdue: boolean }[];
  renewals: { id: string; reference_no: string; title: string; end_date: string | null; days: number; renewal_type: string }[];
  counts: Record<string, number>;
}

// ---------- SSO ----------

/** Public OIDC status, as the login page already reads it. */
export interface SsoConfig {
  enabled: boolean;
  registration_enabled?: boolean;
  deployment_mode?: string;
}

// ---------- SAML ----------

/** Public SAML status. URLs and on/off only — never the certificate, never a secret. */
export interface SamlConfig {
  enabled: boolean;
  entity_id: string;
  acs_url: string;
  sls_url: string;
  metadata_url: string;
  idp_sso_url: string;
  idp_slo_url: string;
  login_url: string;
  default_role: string;
  group_role_map: Record<string, string>;
  certificate_configured: boolean;
}

// ---------- Integrations ----------

/** Destinations and on/off only — never a credential. */
export interface ConnectorStatus {
  teams: { enabled: boolean; configured: boolean; events: string[] };
  sharepoint: { enabled: boolean; site_url: string; library: string; authenticated: boolean };
  calendar: { enabled: boolean; transport: string };
  siem: { enabled: boolean; host: string; format: string; tls: boolean };
  sms: { enabled: boolean; backend: string };
  soap: { enabled: boolean; wsdl: string };
}

// ---------- Access control ----------

export interface MyPermissions {
  role: string;
  permissions: string[];
}

export interface CustomRole {
  id: string;
  key: string;
  name: string;
  description: string;
  /** A custom role always starts from a built-in, so an unknown role degrades to a baseline. */
  base_role: string;
  grants: string[];
  /** Applied after grants — a revoke always wins. */
  revokes: string[];
  is_active: boolean;
  created_at: string;
}

export interface RolesResponse {
  builtin: { key: string; name: string; permissions: string[] }[];
  custom: CustomRole[];
  permissions: string[];
}

export interface LegalHold {
  id: string;
  matter: string;
  reference: string;
  reason: string;
  contract_ids: string[];
  status: "active" | "released";
  custodian: string;
  placed_by: string;
  placed_at: string;
  released_by: string;
  released_at: string | null;
  release_reason: string;
}

export interface TemporaryAccess {
  id: string;
  contract_id: string;
  email: string;
  name: string;
  organisation: string;
  scope: "view" | "comment";
  status: "active" | "expired" | "revoked";
  expires_at: string;
  watermark: boolean;
  allow_download: boolean;
  last_seen_at: string | null;
  view_count: number;
  created_at: string;
}

// ---- Passkeys / FIDO2 (Phase 8, item 1) ----

export type Passkey = {
  id: string;
  label: string;
  transports: string[];
  /** Synced to a cloud keychain: recoverable, but present on every device on that account. */
  backed_up: boolean;
  created_at: string;
  last_used_at: string | null;
};

export type PasskeyStatus = {
  enabled: boolean;
  rp_id: string;
  credentials: Passkey[];
  count: number;
  /** Whether the account could still sign in if every passkey were lost. */
  has_fallback: boolean;
};

// ---------------------------------------------------------------------------------------
// Bulk send (BB-09)
// ---------------------------------------------------------------------------------------

export type BulkSendRow = {
  name: string;
  email: string;
  values: Record<string, unknown>;
};

export type BulkSendItem = {
  id: string;
  sequence: number;
  name: string;
  email: string;
  status: "pending" | "sent" | "failed" | "cancelled";
  contract_id: string | null;
  envelope_id: string | null;
  error: string;
  sent_at: string | null;
};

export type BulkSendBatch = {
  id: string;
  template_id: string;
  name: string;
  status: "queued" | "running" | "completed" | "completed_with_errors" | "cancelled" | "failed";
  total: number;
  succeeded: number;
  failed: number;
  message: string;
  reminder_interval_days: number;
  max_reminders: number;
  expiry_days: number;
  job_id: string | null;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type BulkSendBatchDetail = BulkSendBatch & {
  template_name: string;
  items: BulkSendItem[];
};

/** One bad row, with every reason it is bad — not just the first. */
export type BulkSendProblem = {
  row: number;
  name: string;
  email: string;
  errors: string[];
};

export type BulkSendValidation = { rows: number; problems: BulkSendProblem[] };
