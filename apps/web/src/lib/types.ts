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
  mfa_enabled: boolean;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  locale: string;
  currency: string;
  plan: string;
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

export interface ContractDetail extends ContractListItem {
  governing_law: string;
  ai_summary: string;
  body: string;
  created_by: string;
  available_transitions: string[];
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
  steps: WorkflowStep[];
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
