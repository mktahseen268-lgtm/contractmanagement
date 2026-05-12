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
