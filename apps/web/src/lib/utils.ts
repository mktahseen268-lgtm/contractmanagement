import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

// ---------- formatting ----------

export function formatMoney(value: number, currency = "USD"): string {
  if (!value) return "—";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString()}`;
  }
}

export function formatDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(s: string | null | undefined): string {
  if (!s) return "";
  const then = new Date(s).getTime();
  if (isNaN(then)) return "";
  const diff = Date.now() - then;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}d ago`;
  return formatDate(s);
}

export function daysUntil(s: string | null | undefined): number | null {
  if (!s) return null;
  const d = new Date(s).getTime();
  if (isNaN(d)) return null;
  return Math.ceil((d - Date.now()) / 86_400_000);
}

export function formatBytes(n: number): string {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "download";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function titleCase(s: string): string {
  return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------- domain maps ----------

export const CONTRACT_TYPES = [
  { value: "msa", label: "Master Services Agreement" },
  { value: "nda", label: "Non-Disclosure Agreement" },
  { value: "lease", label: "Lease Agreement" },
  { value: "employment", label: "Employment Agreement" },
  { value: "vendor", label: "Vendor Agreement" },
  { value: "service", label: "Service Agreement" },
  { value: "other", label: "Other" },
];

export function contractTypeLabel(v: string): string {
  return CONTRACT_TYPES.find((t) => t.value === v)?.label ?? titleCase(v);
}

// the lifecycle "spine" shown in LifecycleBar (mirrors backend app/lifecycle.py SPINE)
export const LIFECYCLE_SPINE = ["draft", "in_review", "approved", "out_for_signature", "signed", "active", "expiring"] as const;

// status -> { label, classes for pill (text+bg), dot color }
export const STATUS_META: Record<string, { label: string; pill: string; dot: string }> = {
  draft: { label: "Draft", pill: "text-slate-700 bg-slate-100", dot: "#667085" },
  in_review: { label: "In review", pill: "text-amber-800 bg-amber-100", dot: "#F5A623" },
  changes_requested: { label: "Changes requested", pill: "text-orange-800 bg-orange-100", dot: "#FB6514" },
  approved: { label: "Approved", pill: "text-blue-800 bg-blue-100", dot: "#2E90FA" },
  out_for_signature: { label: "Out for signature", pill: "text-violet-800 bg-violet-100", dot: "#9E77ED" },
  signed: { label: "Signed", pill: "text-emerald-800 bg-emerald-100", dot: "#12B76A" },
  active: { label: "Active", pill: "text-emerald-900 bg-emerald-100", dot: "#039855" },
  expiring: { label: "Expiring", pill: "text-amber-900 bg-amber-100", dot: "#DC6803" },
  expired: { label: "Expired", pill: "text-red-800 bg-red-100", dot: "#D92D20" },
  terminated: { label: "Terminated", pill: "text-slate-700 bg-slate-200", dot: "#475467" },
  rejected: { label: "Rejected", pill: "text-red-800 bg-red-100", dot: "#D92D20" },
  declined: { label: "Declined", pill: "text-red-800 bg-red-100", dot: "#D92D20" },
  voided: { label: "Voided", pill: "text-slate-600 bg-slate-100", dot: "#98A2B3" },
  renewed: { label: "Renewed", pill: "text-emerald-800 bg-emerald-100", dot: "#12B76A" },
  superseded: { label: "Superseded", pill: "text-slate-600 bg-slate-100", dot: "#98A2B3" },
};

export function statusMeta(s: string) {
  return STATUS_META[s] ?? { label: titleCase(s), pill: "text-slate-700 bg-slate-100", dot: "#667085" };
}

export const RISK_META: Record<string, { label: string; pill: string }> = {
  low: { label: "Low", pill: "text-emerald-800 bg-emerald-50" },
  medium: { label: "Medium", pill: "text-amber-800 bg-amber-50" },
  high: { label: "High", pill: "text-orange-800 bg-orange-50" },
  critical: { label: "Critical", pill: "text-red-800 bg-red-50" },
};

export function riskMeta(r: string) {
  return RISK_META[r] ?? RISK_META.low;
}

// labels for the transition action buttons (mirrors backend lifecycle.TRANSITION_LABELS)
export const TRANSITION_LABELS: Record<string, string> = {
  in_review: "Submit for approval",
  approved: "Approve",
  changes_requested: "Request changes",
  rejected: "Reject",
  out_for_signature: "Send for signature",
  signed: "Mark as signed",
  active: "Activate",
  declined: "Mark declined",
  expiring: "Flag as expiring",
  expired: "Mark expired",
  renewed: "Mark renewed",
  terminated: "Terminate",
  voided: "Void",
  draft: "Return to draft",
};

// which transitions are "destructive-ish" (render as a quieter / danger button)
export const NEGATIVE_TRANSITIONS = new Set(["rejected", "declined", "terminated", "voided", "changes_requested"]);

export function actorColor(name: string): string {
  const colors = ["#3E7BFA", "#8B7BF5", "#2BC0D4", "#F6B83C", "#F5736B", "#3FBF7F", "#5B8DEF"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return colors[h % colors.length];
}

export function activityVerb(action: string): string {
  const map: Record<string, string> = {
    "contract.created": "created",
    "contract.updated": "edited",
    "contract.status_changed": "changed the status of",
    "contract.commented": "commented on",
    "contract.deleted": "deleted",
    "auth.login": "signed in",
    "user.invited": "invited",
    "user.registered": "registered",
    "tenant.created": "created the workspace",
    "ocr.completed": "ran OCR on",
  };
  return map[action] ?? action.replace(/[._]/g, " ");
}
