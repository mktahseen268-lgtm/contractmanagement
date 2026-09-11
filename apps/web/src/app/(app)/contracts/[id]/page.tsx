"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, BadgeCheck, Check, CheckSquare, MessageSquare, Maximize2, Minimize2, Copy, Download, Eye, FileCheck2, FileDown, FileText, History, ListTodo, Pencil, PenLine, Plus, Repeat, RotateCcw, Send, Shield, Sparkles, Trash2, Workflow as WorkflowIcon, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { TextAssist } from "@/components/text-assist";
import { SelectionActions } from "@/components/selection-actions";
import { DealPoints, DocumentSections } from "@/components/approval-reading";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Skeleton, Textarea } from "@/components/ui";

const BlockEditor = dynamic(() => import("@/components/block-editor").then((m) => m.BlockEditor), {
  ssr: false,
  loading: () => <div className="cm-doc min-h-[42vh] px-1 py-2 text-sm text-ink-3">Loading editor…</div>,
});
import { PageHeader } from "@/components/shell";
import { useToast } from "@/components/toast";
import { ActivityFeed } from "@/components/widgets";
import { LifecycleBar, RiskBadge, StatusPill } from "@/components/lifecycle";
import { ContractGuidance } from "@/components/guidance";
import {
  actorColor,
  cn,
  contractTypeLabel,
  daysUntil,
  downloadBlob,
  formatBytes,
  formatDate,
  formatDateTime,
  formatMoney,
  NEGATIVE_TRANSITIONS,
  resolveContractVariables,
  timeAgo,
  TRANSITION_LABELS,
  titleCase,
} from "@/lib/utils";
import type { ActivityItem, Comment, ContractDetail, Readiness, ReadinessDecision, ContractWorkflow, FileObject, Obligation, PolicyFinding, PolicyReview, SignatureEnvelope, SignatureRecipient, User, Version, VersionDetail, WorkflowRunStep } from "@/lib/types";

// Legacy clipboard fallback for non-secure contexts (plain HTTP behind an IP). Uses an off-
// screen textarea + selection + document.execCommand("copy"). Returns true on success.
function legacyCopy(text: string): boolean {
  if (typeof document === "undefined") return false;
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.top = "0";
  ta.style.left = "-9999px";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  const prevActive = document.activeElement as HTMLElement | null;
  try {
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    return !!ok;
  } catch {
    return false;
  } finally {
    document.body.removeChild(ta);
    prevActive?.focus?.();
  }
}

type Tab = "overview" | "approvals" | "policy" | "readiness" | "signatures" | "obligations" | "document" | "activity" | "comments" | "files" | "versions";
const EDITABLE_STATUSES = new Set(["draft", "changes_requested"]);
const TABS: Tab[] = ["overview", "document", "policy", "approvals", "readiness", "signatures", "obligations", "comments", "versions", "files", "activity"];
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const toast = useToast();
  const [contract, setContract] = useState<ContractDetail | null>(null);
  const [wfState, setWfState] = useState<ContractWorkflow | null>(null);
  const [sigState, setSigState] = useState<SignatureEnvelope | null>(null);
  const initialTab = (search?.get("tab") as Tab | null) && TABS.includes(search!.get("tab") as Tab) ? (search!.get("tab") as Tab) : "overview";
  const [tab, setTab] = useState<Tab>(initialTab);
  const [error, setError] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [renewOpen, setRenewOpen] = useState(false);
  const [renewBusy, setRenewBusy] = useState(false);

  const load = useCallback(() => {
    api.get<ContractDetail>(`/contracts/${id}`).then(setContract).catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load this contract."));
    api.get<ContractWorkflow>(`/contracts/${id}/workflow`).then(setWfState).catch(() => setWfState(null));
    api.get<SignatureEnvelope | null>(`/contracts/${id}/signature`).then(setSigState).catch(() => setSigState(null));
  }, [id]);

  useEffect(load, [load]);

  async function submitForApproval() {
    if (!contract) return;
    setSubmitBusy(true);
    setError("");
    try {
      await api.post<ContractDetail>(`/contracts/${contract.id}/submit-for-approval`, {});
      load();
      setTab("approvals");
      toast.success("Submitted for approval");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't submit for approval.";
      setError(msg);
      toast.error("Couldn't submit for approval", msg);
    } finally {
      setSubmitBusy(false);
    }
  }

  async function transition(toStatus: string) {
    if (!contract) return;
    let comment = "";
    if (NEGATIVE_TRANSITIONS.has(toStatus)) {
      const r = window.prompt(`${TRANSITION_LABELS[toStatus] ?? titleCase(toStatus)} — add a note (optional):`, "");
      if (r === null) return; // cancelled
      comment = r;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await api.post<ContractDetail>(`/contracts/${contract.id}/transition`, { status: toStatus, comment });
      setContract(updated);
      toast.success(`Moved to ${(TRANSITION_LABELS[toStatus] ?? titleCase(toStatus)).replace(/^→\s*/, "")}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't update the contract.";
      setError(msg);
      toast.error("Couldn't update the contract", msg);
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    if (!contract) return;
    setPdfBusy(true);
    setError("");
    try {
      const fo = await api.post<FileObject>(`/contracts/${contract.id}/pdf`);
      const blob = await api.blob(`/files/${fo.id}/download`);
      downloadBlob(blob, fo.original_name);
      toast.success("PDF ready", "Your download has started.");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't generate the PDF.";
      setError(msg);
      toast.error("Couldn't generate the PDF", msg);
    } finally {
      setPdfBusy(false);
    }
  }

  async function remove() {
    if (!contract) return;
    if (!window.confirm(`Delete "${contract.title}"? This can't be undone.`)) return;
    setBusy(true);
    try {
      await api.del(`/contracts/${contract.id}`);
      toast.success("Contract deleted");
      router.push("/contracts");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't delete.";
      setError(msg);
      toast.error("Couldn't delete", msg);
      setBusy(false);
    }
  }

  async function submitRenew(effective: string, end: string, summary: string) {
    if (!contract) return;
    setRenewBusy(true);
    setError("");
    try {
      const succ = await api.post<ContractDetail>(`/contracts/${contract.id}/renew`, {
        effective_date: effective || null,
        end_date: end || null,
        change_summary: summary,
      });
      setRenewOpen(false);
      toast.success("Renewal created", "Opened the successor contract.");
      router.push(`/contracts/${succ.id}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't renew this contract.";
      setError(msg);
      toast.error("Couldn't renew", msg);
    } finally {
      setRenewBusy(false);
    }
  }

  if (error && !contract) {
    return (
      <div className="p-6">
        <ErrorBanner message={error} />
        <Link href="/contracts" className="mt-3 inline-block text-sm text-accent hover:underline">
          ← Back to contracts
        </Link>
      </div>
    );
  }
  if (!contract) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-32 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  const du = daysUntil(contract.end_date);
  const canEdit = EDITABLE_STATUSES.has(contract.status);
  const hasActiveRun = wfState?.run?.status === "running";
  const hasActiveEnvelope = sigState?.status === "sent" || sigState?.status === "partially_signed";
  // "Submit for approval" replaces the in_review transition; approve/reject/changes go through the workflow when a run is active.
  // "Submit for approval" and "Prepare for signature" are tab actions; while a run/envelope is active those moves go through the tab
  const positive = contract.available_transitions.filter(
    (t) => !NEGATIVE_TRANSITIONS.has(t) && t !== "in_review" && t !== "out_for_signature" && !(hasActiveRun && t === "approved") && !(hasActiveEnvelope && t === "signed"),
  );
  const negative = contract.available_transitions.filter(
    (t) => NEGATIVE_TRANSITIONS.has(t) && !(hasActiveRun && (t === "rejected" || t === "changes_requested")) && !(hasActiveEnvelope && (t === "declined" || t === "voided")),
  );
  const canSubmit = EDITABLE_STATUSES.has(contract.status) && !hasActiveRun && contract.available_transitions.includes("in_review");
  const canRenew = ["active", "expiring", "expired"].includes(contract.status);

  return (
    <div>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {contract.title} <StatusPill status={contract.status} />
          </span>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
            <span className="tnum">{contract.reference_no}</span>
            <span>·</span>
            <span>{contractTypeLabel(contract.type)}</span>
            {contract.counterparty && (
              <>
                <span>·</span>
                <span>{contract.counterparty}</span>
              </>
            )}
            <Badge tone="neutral" className="ml-1">
              {titleCase(contract.source)}
            </Badge>
          </span>
        }
        actions={
          <>
            {canSubmit && (
              <Button size="sm" onClick={submitForApproval} loading={submitBusy}>
                <Send className="h-3.5 w-3.5" /> Submit for approval
              </Button>
            )}
            {canRenew && (
              <Button variant="secondary" size="sm" onClick={() => setRenewOpen(true)} title="Create a renewal successor">
                <Repeat className="h-3.5 w-3.5" /> Renew
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={downloadPdf} loading={pdfBusy} title="Generate & download PDF">
              <FileDown className="h-3.5 w-3.5" /> PDF
            </Button>
            {canEdit && (
              <Link href={`/contracts/${contract.id}/edit`}>
                <Button variant="secondary" size="sm">
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </Button>
              </Link>
            )}
            <Button variant="ghost" size="sm" onClick={remove} disabled={busy} title="Delete">
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        }
      />

      {renewOpen && <RenewModal contract={contract} busy={renewBusy} onCancel={() => setRenewOpen(false)} onSubmit={submitRenew} />}

      <div className="space-y-5 p-6">
        {error && <ErrorBanner message={error} />}

        {(contract.renewed_from || contract.renewed_to) && (
          <Card>
            <CardBody className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-sm">
              <Repeat className="h-3.5 w-3.5 shrink-0 text-ink-3" />
              {contract.renewed_from && (
                <span className="text-ink-2">
                  Renewed from{" "}
                  <Link href={`/contracts/${contract.renewed_from.id}`} className="font-medium text-accent hover:underline">
                    {contract.renewed_from.reference_no}
                  </Link>
                  <span className="ml-1 truncate text-ink-3">· {contract.renewed_from.title}</span>
                </span>
              )}
              {contract.renewed_to && (
                <span className="text-ink-2">
                  Renewed by{" "}
                  <Link href={`/contracts/${contract.renewed_to.id}`} className="font-medium text-accent hover:underline">
                    {contract.renewed_to.reference_no}
                  </Link>
                  <span className="ml-1 truncate text-ink-3">· {contract.renewed_to.title}</span>
                </span>
              )}
            </CardBody>
          </Card>
        )}

        {/* header card: lifecycle + key facts + actions */}
        <Card>
          <CardBody className="space-y-4">
            <LifecycleBar status={contract.status} />
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
              <Fact label="Value">{formatMoney(contract.value, contract.currency)}</Fact>
              <Fact label="Effective">{formatDate(contract.effective_date)}</Fact>
              <Fact label="Ends">
                {formatDate(contract.end_date)}
                {du !== null && du >= 0 && <span className="ml-1 text-ink-3">({du}d)</span>}
                {du !== null && du < 0 && <span className="ml-1 text-danger">(past)</span>}
              </Fact>
              <Fact label="Renewal">{titleCase(contract.renewal_type)}</Fact>
              <Fact label="Governing law">{contract.governing_law || "—"}</Fact>
              <Fact label="Risk">{contract.risk_level === "low" ? "Low" : <RiskBadge level={contract.risk_level} />}</Fact>
              <Fact label="Owner">
                <span className="inline-flex items-center gap-1.5">
                  <Avatar name={contract.owner_name} color={actorColor(contract.owner_name)} size={20} />
                  {contract.owner_name}
                </span>
              </Fact>
            </div>
            {contract.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {contract.tags.map((t) => (
                  <Badge key={t} tone="neutral">
                    #{t}
                  </Badge>
                ))}
              </div>
            )}
            {(positive.length > 0 || negative.length > 0) && (
              <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
                <span className="text-xs font-medium text-ink-3">Move to:</span>
                {positive.map((t) => (
                  <Button key={t} size="sm" onClick={() => transition(t)} disabled={busy}>
                    {TRANSITION_LABELS[t] ?? titleCase(t)}
                  </Button>
                ))}
                {negative.map((t) => (
                  <Button key={t} size="sm" variant="outline" onClick={() => transition(t)} disabled={busy}>
                    {TRANSITION_LABELS[t] ?? titleCase(t)}
                  </Button>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {/* tabs */}
        <div className="flex gap-1 border-b border-line">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t ? "border-accent text-accent" : "border-transparent text-ink-3 hover:text-ink",
              )}
            >
              {titleCase(t)}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <>
            {/* Above the detail: what stage it is at, and what to do next. Derived server-side
                every time, so it cannot contradict the buttons beside it. */}
            <div className="mb-4">
              <ContractGuidance contractId={contract.id} />
            </div>
            <OverviewTab contract={contract} />
          </>
        )}
        {tab === "approvals" && <ApprovalsTab contract={contract} wf={wfState} onChanged={load} />}
        {tab === "policy" && <PolicyTab contract={contract} onChanged={load} />}
        {tab === "readiness" && <ReadinessTab contract={contract} />}
        {tab === "signatures" && <SignaturesTab contract={contract} env={sigState} onChanged={load} />}
        {tab === "obligations" && <ObligationsTab contract={contract} />}
        {tab === "document" && <DocumentTab key={contract.id} contract={contract} wf={wfState} onChanged={load} />}
        {tab === "activity" && <ActivityTab contractId={contract.id} />}
        {tab === "comments" && <CommentsTab contractId={contract.id} />}
        {tab === "files" && <FilesTab contractId={contract.id} />}
        {tab === "versions" && <VersionsTab contract={contract} onRestored={load} onGoToDocument={() => setTab("document")} />}
      </div>
    </div>
  );
}

function RenewModal({
  contract,
  busy,
  onCancel,
  onSubmit,
}: {
  contract: ContractDetail;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (effective: string, end: string, summary: string) => void;
}) {
  // Suggested defaults: effective = old.end_date + 1d (or today); end = +1y unless we can compute the old term length.
  const today = new Date();
  function isoPlusDays(d: Date | string | null, days: number): string {
    const base = d ? new Date(d as string) : new Date(today);
    base.setDate(base.getDate() + days);
    return base.toISOString().slice(0, 10);
  }
  const suggestedEffective = contract.end_date ? isoPlusDays(contract.end_date, 1) : isoPlusDays(null, 0);
  let suggestedEnd = isoPlusDays(suggestedEffective, 365);
  if (contract.effective_date && contract.end_date) {
    const termDays = Math.max(
      Math.round((new Date(contract.end_date).getTime() - new Date(contract.effective_date).getTime()) / 86400000),
      30,
    );
    suggestedEnd = isoPlusDays(suggestedEffective, termDays);
  }

  const [effective, setEffective] = useState(suggestedEffective);
  const [end, setEnd] = useState(suggestedEnd);
  const [summary, setSummary] = useState(`Renewed from ${contract.reference_no}`);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <Card className="w-full max-w-md" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <Repeat className="h-4 w-4" /> Renew this contract
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-ink-2">
            Creates a fresh <strong>draft</strong> contract with the same metadata, body and parties, linked back to this one.
            This contract becomes <strong>renewed</strong> and read-only.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">New effective</span>
              <input type="date" value={effective} onChange={(e) => setEffective(e.target.value)} className="h-10 w-full rounded-sm border border-line bg-white px-3 text-sm" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">New end</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="h-10 w-full rounded-sm border border-line bg-white px-3 text-sm" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">What changes? (optional)</span>
            <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="e.g. extended 1y at new rate" className="h-10 w-full rounded-sm border border-line bg-white px-3 text-sm" />
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
            <Button size="sm" loading={busy} onClick={() => onSubmit(effective, end, summary)}>
              <Repeat className="h-3.5 w-3.5" /> Renew &amp; open successor
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-ink-3">{label}</div>
      <div className="mt-0.5 font-medium text-ink">{children}</div>
    </div>
  );
}

function OverviewTab({ contract }: { contract: ContractDetail }) {
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Key terms</CardTitle>
        </CardHeader>
        <CardBody>
          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            <Row k="Type" v={contractTypeLabel(contract.type)} />
            <Row k="Counterparty" v={contract.counterparty || "—"} />
            <Row k="Department" v={contract.department || "—"} />
            <Row k="Reference #" v={contract.reference_no} />
            <Row k="Value" v={formatMoney(contract.value, contract.currency)} />
            <Row k="Currency" v={contract.currency} />
            <Row k="Effective date" v={formatDate(contract.effective_date)} />
            <Row k="End date" v={formatDate(contract.end_date)} />
            <Row k="Renewal" v={titleCase(contract.renewal_type)} />
            <Row k="Governing law" v={contract.governing_law || "—"} />
            <Row k="Created" v={formatDateTime(contract.created_at)} />
            <Row k="Last updated" v={formatDateTime(contract.updated_at)} />
          </dl>
        </CardBody>
      </Card>
      <Card className="ai-aurora border-ai-line/60">
        <CardHeader className="border-ai-line/40">
          <CardTitle className="flex items-center gap-1.5 text-ai">
            <Sparkles className="h-4 w-4" /> AI summary
          </CardTitle>
        </CardHeader>
        <CardBody className="text-sm text-ink-2">
          {contract.ai_summary ? (
            <p>{contract.ai_summary}</p>
          ) : (
            <p className="text-ink-3">No AI summary yet. (In the full product this is generated on creation / OCR import.)</p>
          )}
          <p className="mt-3 text-[11px] text-ink-3">AI can be wrong — verify before relying.</p>
        </CardBody>
      </Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line/60 pb-2 last:border-0">
      <dt className="text-ink-3">{k}</dt>
      <dd className="text-right font-medium text-ink">{v}</dd>
    </div>
  );
}

function DocumentTab({ contract, wf, onChanged }: { contract: ContractDetail; wf: ContractWorkflow | null; onChanged: () => void }) {
  const editable = EDITABLE_STATUSES.has(contract.status);
  const [md, setMd] = useState<string>(contract.body || "");
  const [baseline, setBaseline] = useState<string>(contract.body || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const [full, setFull] = useState(false);
  const dirty = md !== baseline;

  // Escape leaves full screen, and the page behind must not scroll while it is open.
  useEffect(() => {
    if (!full) return;
    function onKey(e: KeyboardEvent) {
      // Only when nothing is being typed into: Escape also dismisses the comment panel, and
      // the panel should close first rather than the whole view vanishing under the author.
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (e.key === "Escape" && tag !== "textarea" && tag !== "input") setFull(false);
    }
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [full]);

  async function save() {
    setSaving(true);
    setError("");
    setSavedNote("");
    try {
      await api.patch<ContractDetail>(`/contracts/${contract.id}`, { body: md });
      setBaseline(md);
      setSavedNote("Saved — a new version was recorded.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save the document.");
    } finally {
      setSaving(false);
    }
  }

  // One definition of the reading surface, rendered into the card or into the overlay. A
  // full-screen view missing the comment markers would be the one people used and the one that
  // could not capture what they found.
  const readingSurface = (
    <>
      {error && <ErrorBanner message={error} className="mb-3" />}
      {!editable && (
        <>
          <DealPoints contract={contract} />
          <DocumentSections body={contract.body || ""} containerRef={bodyRef} />
          <p className="mb-4 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
            <MessageSquare className="h-3.5 w-3.5" />
            Use the icon beside any section — or select a passage and right-click — to comment
            or raise an obligation. The section and wording are recorded with it.
            <span className="text-ink-3">· Read-only while “{titleCase(contract.status)}”.</span>
          </p>
        </>
      )}
      <div ref={bodyRef} className="relative">
        <BlockEditor
          value={editable ? baseline : resolveContractVariables(contract.body || "", contract)}
          editable={editable}
          onChange={editable ? setMd : undefined}
          className={editable ? undefined : "cm-doc--reading"}
        />
        <SelectionActions contractId={contract.id} containerRef={bodyRef} onSaved={onChanged} />
      </div>
      {editable && (
        <details className="mt-4 text-xs text-ink-3">
          <summary className="cursor-pointer select-none">Markdown source · merge variables look like <code>{"{{counterparty}}"}</code> and resolve in the PDF / read-only view</summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-[11px] text-ink-2">{md || "(empty)"}</pre>
        </details>
      )}
    </>
  );

  if (full) {
    return (
      <div className="fixed inset-0 z-40 flex flex-col bg-surface">
        <div className="flex items-center gap-3 border-b border-line px-5 py-2.5">
          <FileText className="h-4 w-4 text-ink-3" />
          <span className="truncate text-sm font-medium text-ink">{contract.title}</span>
          <span className="hidden text-xs text-ink-3 sm:inline">{contract.reference_no}</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-xs text-ink-3 sm:inline">Esc to exit</span>
            <Button size="sm" variant="ghost" onClick={() => setFull(false)}>
              <Minimize2 className="h-3.5 w-3.5" /> Exit full screen
            </Button>
          </div>
        </div>
        {/* The document scrolls; the decision panel below stays put, so a reviewer who has
            finished reading does not have to scroll back to act. */}
        <div className="flex-1 overflow-y-auto px-6 py-5">{readingSurface}</div>
        <div className="max-h-[45vh] overflow-y-auto border-t border-line">
          <ReviewPanel contract={contract} wf={wf} onChanged={onChanged} />
        </div>
      </div>
    );
  }

  return (
    <Card>
      {editable && (
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <FileText className="h-4 w-4" /> Document
            {dirty && <span className="text-xs font-normal text-amber-700">· unsaved changes</span>}
          </CardTitle>
          <div className="flex items-center gap-2">
            {savedNote && !dirty && <span className="text-xs text-ok">{savedNote}</span>}
            <Button size="sm" variant="ghost" onClick={() => setFull(true)}>
              <Maximize2 className="h-3.5 w-3.5" /> Full screen
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMd(baseline)} disabled={!dirty || saving}>
              Discard
            </Button>
            <Button size="sm" onClick={save} loading={saving} disabled={!dirty}>
              Save
            </Button>
          </div>
        </CardHeader>
      )}
      {/* Read-only has no card header of its own, so the control sits above the document. */}
      {!editable && (
        <div className="flex items-center justify-end border-b border-line px-5 py-2">
          <Button size="sm" variant="ghost" onClick={() => setFull(true)}>
            <Maximize2 className="h-3.5 w-3.5" /> Read full screen
          </Button>
        </div>
      )}
      <CardBody>{readingSurface}</CardBody>
      <ReviewPanel contract={contract} wf={wf} onChanged={onChanged} />
    </Card>
  );
}

/** Everything a reviewer needs *while reading*: raise a point, capture an obligation, decide.
 *
 * All three existed already, one per tab. That is fine for looking something up and wrong for
 * reviewing: the reader is holding a paragraph in their head, and making them leave the
 * document to record what they just noticed is how the note stops being written down at all.
 * The obligation box especially — reading the clause that creates one is the moment it gets
 * spotted, and the only moment it reliably does. */
function ReviewPanel({ contract, wf, onChanged }:
  { contract: ContractDetail; wf: ContractWorkflow | null; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [obTitle, setObTitle] = useState("");
  const [obDue, setObDue] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");

  const canDecide = !!wf?.can_decide && wf.run?.status === "running";

  async function run(kind: string, fn: () => Promise<unknown>, ok: string, after?: () => void) {
    setBusy(kind);
    setError("");
    setDone("");
    try {
      await fn();
      setDone(ok);
      after?.();
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not go through.");
    } finally {
      setBusy(null);
    }
  }

  function comment() {
    run("comment", () => api.post(`/contracts/${contract.id}/comments`, { body: note.trim() }),
      "Comment added.", () => setNote(""));
  }

  function obligation() {
    run("obligation", () => api.post(`/contracts/${contract.id}/obligations`, {
      title: obTitle.trim(),
      description: "Raised while reviewing the document.",
      due_date: obDue || null,
      owner_id: null,
    }), "Obligation added.", () => { setObTitle(""); setObDue(""); });
  }

  // The decision carries the reviewer's note, so "approved, but fix clause 7" stays one record
  // instead of a decision here and an unlinked comment somewhere else.
  function decide(decision: "approve" | "reject" | "changes_requested", ok: string) {
    run(decision, () => api.post(`/contracts/${contract.id}/workflow/decide`,
      { decision, comment: note.trim() }), ok, () => setNote(""));
  }

  return (
    <div className="border-t border-line bg-surface-2/40 px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink">Review</span>
        {canDecide && <Badge tone="accent">Waiting on you</Badge>}
        {done && <span className="text-xs text-ok">{done}</span>}
      </div>
      {error && <ErrorBanner message={error} className="mb-3" />}

      <Textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        placeholder={canDecide
          ? "Note for the record - attached to your decision, or posted on its own as a comment."
          : "Add a comment on what you just read..."}
      />
      <TextAssist value={note} onAccept={setNote} />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={comment}
          loading={busy === "comment"} disabled={!note.trim() || !!busy}>
          <Plus className="h-3.5 w-3.5" /> Add comment
        </Button>
        {canDecide && (
          <>
            <Button size="sm" onClick={() => decide("approve", "Approved.")}
              loading={busy === "approve"} disabled={!!busy}>
              <Check className="h-3.5 w-3.5" /> Approve
            </Button>
            <Button size="sm" variant="secondary"
              onClick={() => decide("changes_requested", "Changes requested.")}
              loading={busy === "changes_requested"} disabled={!!busy}>
              <Pencil className="h-3.5 w-3.5" /> Request changes
            </Button>
            <Button size="sm" variant="ghost" onClick={() => decide("reject", "Rejected.")}
              loading={busy === "reject"} disabled={!!busy}>
              <X className="h-3.5 w-3.5" /> Reject
            </Button>
          </>
        )}
      </div>

      <div className="mt-4 border-t border-line pt-3">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-ink-2">
          <ListTodo className="h-3.5 w-3.5" /> Spotted an obligation in the text?
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <input
            className="h-9 min-w-[16rem] flex-1 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-accent"
            value={obTitle}
            onChange={(e) => setObTitle(e.target.value)}
            placeholder="e.g. Serve renewal notice 60 days before expiry"
            aria-label="Obligation"
          />
          <input
            type="date"
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-accent"
            value={obDue}
            onChange={(e) => setObDue(e.target.value)}
            aria-label="Obligation due date"
          />
          <Button size="sm" variant="secondary" onClick={obligation}
            loading={busy === "obligation"} disabled={!obTitle.trim() || !!busy}>
            <Plus className="h-3.5 w-3.5" /> Add obligation
          </Button>
        </div>
      </div>
    </div>
  );
}

function ActivityTab({ contractId }: { contractId: string }) {
  const [items, setItems] = useState<ActivityItem[] | null>(null);
  useEffect(() => {
    api.get<ActivityItem[]>(`/contracts/${contractId}/activity`).then(setItems).catch(() => setItems([]));
  }, [contractId]);
  return (
    <Card>
      <CardBody>{items === null ? <Skeleton className="h-24" /> : <ActivityFeed items={items} />}</CardBody>
    </Card>
  );
}

function CommentsTab({ contractId }: { contractId: string }) {
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<Comment[]>(`/contracts/${contractId}/comments`).then(setComments).catch(() => setComments([]));
  }, [contractId]);
  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.post<Comment>(`/contracts/${contractId}/comments`, { body: text.trim() });
      setText("");
      load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardBody className="space-y-4">
        <form onSubmit={add} className="flex flex-col gap-2">
          <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a comment…" />
          <TextAssist value={text} onAccept={setText} />
          <div className="flex justify-end">
            <Button size="sm" type="submit" loading={busy} disabled={!text.trim()}>
              Comment
            </Button>
          </div>
        </form>
        <div className="space-y-3">
          {comments === null && <Skeleton className="h-16" />}
          {comments && comments.length === 0 && <p className="text-sm text-ink-3">No comments yet.</p>}
          {comments?.map((c) => (
            <div key={c.id} className="flex gap-3">
              <Avatar name={c.author_name} color={actorColor(c.author_name)} size={28} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium text-ink">{c.author_name}</span>
                  <span className="text-xs text-ink-3">{formatDateTime(c.created_at)}</span>
                </div>
                <p className="mt-0.5 whitespace-pre-wrap text-sm text-ink-2">{c.body}</p>
              </div>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

function FilesTab({ contractId }: { contractId: string }) {
  const [files, setFiles] = useState<FileObject[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<FileObject[]>(`/contracts/${contractId}/files`).then(setFiles).catch(() => setFiles([]));
  }, [contractId]);
  useEffect(load, [load]);

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const fo = await api.post<FileObject>(`/contracts/${contractId}/pdf`);
      setFiles((f) => [fo, ...(f ?? [])]);
      const blob = await api.blob(`/files/${fo.id}/download`);
      downloadBlob(blob, fo.original_name);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't generate the PDF.");
    } finally {
      setBusy(false);
    }
  }

  async function download(fo: FileObject) {
    try {
      const blob = await api.blob(`/files/${fo.id}/download`);
      downloadBlob(blob, fo.original_name);
    } catch {
      setError("Couldn't download that file.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <FileText className="h-4 w-4" /> Files
        </CardTitle>
        <Button size="sm" onClick={generate} loading={busy}>
          <FileDown className="h-3.5 w-3.5" /> Generate PDF
        </Button>
      </CardHeader>
      <CardBody>
        {error && <ErrorBanner message={error} className="mb-3" />}
        {files === null && <Skeleton className="h-16" />}
        {files && files.length === 0 && (
          <p className="text-sm text-ink-3">No generated files yet. Click “Generate PDF” to produce a downloadable copy of this contract.</p>
        )}
        <div className="divide-y divide-line">
          {files?.map((f) => (
            <div key={f.id} className="flex items-center gap-3 py-3 text-sm">
              <span className="grid h-9 w-9 place-items-center rounded-md bg-surface-3 text-ink-3">
                <FileText className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-ink">{f.original_name}</div>
                <div className="text-xs text-ink-3">
                  {titleCase(f.kind)} · {formatBytes(f.size)} · {formatDateTime(f.created_at)} · stored on {f.backend === "s3" ? "S3" : "local"}
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => download(f)}>
                <Download className="h-3.5 w-3.5" /> Download
              </Button>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-ink-3">
          Generated PDFs are stored in S3-compatible object storage (or a local-filesystem fallback) and are tenant-isolated. Drafts carry a “DRAFT — not executed” watermark.
        </p>
      </CardBody>
    </Card>
  );
}

function VersionsTab({ contract, onRestored, onGoToDocument }: { contract: ContractDetail; onRestored: () => void; onGoToDocument: () => void }) {
  const editable = EDITABLE_STATUSES.has(contract.status);
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [viewing, setViewing] = useState<VersionDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    api.get<Version[]>(`/contracts/${contract.id}/versions`).then(setVersions).catch(() => setVersions([]));
  }, [contract.id]);
  useEffect(load, [load]);

  async function view(v: Version) {
    if (viewing?.id === v.id) {
      setViewing(null);
      return;
    }
    try {
      setViewing(await api.get<VersionDetail>(`/contracts/${contract.id}/versions/${v.id}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load that version.");
    }
  }

  async function restore(v: Version) {
    if (!window.confirm(`Restore v${v.version_no}? The document will be reset to that version (a new version is recorded).`)) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      await api.post<ContractDetail>(`/contracts/${contract.id}/versions/${v.id}/restore`);
      setNote(`Restored v${v.version_no} — see the Document tab.`);
      onRestored();
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't restore that version.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <History className="h-4 w-4" /> Version history
        </CardTitle>
        {note && (
          <button onClick={onGoToDocument} className="text-xs text-accent hover:underline">
            {note}
          </button>
        )}
      </CardHeader>
      <CardBody>
        {error && <ErrorBanner message={error} className="mb-3" />}
        {versions === null && <Skeleton className="h-20" />}
        {versions && versions.length === 0 && <p className="text-sm text-ink-3">No versions yet.</p>}
        <div className="divide-y divide-line">
          {versions?.map((v, i) => (
            <div key={v.id} className="py-3">
              <div className="flex items-center gap-3 text-sm">
                <span className="grid h-7 w-9 place-items-center rounded-md bg-surface-3 text-xs font-semibold text-ink-2 tnum">v{v.version_no}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-ink">
                    {v.change_summary || "—"}
                    {i === 0 && <span className="ml-2 rounded-full bg-accent-subtle px-1.5 py-0.5 text-[10px] font-medium text-accent">current</span>}
                  </div>
                  <div className="text-xs text-ink-3">{formatDateTime(v.created_at)}</div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => view(v)}>
                  <Eye className="h-3.5 w-3.5" /> {viewing?.id === v.id ? "Hide" : "View"}
                </Button>
                {editable && i !== 0 && (
                  <Button size="sm" variant="outline" onClick={() => restore(v)} disabled={busy}>
                    <RotateCcw className="h-3.5 w-3.5" /> Restore
                  </Button>
                )}
              </div>
              {viewing?.id === v.id && (
                <div className="mt-2 rounded-lg border border-line bg-surface-2 p-1">
                  <BlockEditor key={`v-${v.id}`} value={viewing.body || ""} editable={false} />
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-ink-3">A new version is recorded every time the document is saved (or restored). The version sent for signature is the legal artifact.</p>
      </CardBody>
    </Card>
  );
}

const RUN_STATUS_TONE: Record<string, string> = {
  running: "text-amber-800 bg-amber-100",
  approved: "text-emerald-800 bg-emerald-100",
  rejected: "text-red-800 bg-red-100",
  changes_requested: "text-orange-800 bg-orange-100",
  cancelled: "text-slate-600 bg-slate-100",
};
const STEP_TONE: Record<string, string> = {
  active: "text-amber-800 bg-amber-100",
  approved: "text-emerald-800 bg-emerald-100",
  rejected: "text-red-800 bg-red-100",
  changes_requested: "text-orange-800 bg-orange-100",
  pending: "text-slate-600 bg-slate-100",
  skipped: "text-slate-500 bg-slate-100",
};

function ApprovalsTab({ contract, wf, onChanged }: { contract: ContractDetail; wf: ContractWorkflow | null; onChanged: () => void }) {
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [chosenWf, setChosenWf] = useState<string>("");
  const [submitBusy, setSubmitBusy] = useState(false);
  const [decideComment, setDecideComment] = useState("");
  const [decideBusy, setDecideBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<User[]>("/users").then(setUsers).catch(() => {});
  }, []);
  useEffect(() => {
    if (wf) setChosenWf(wf.default_workflow_id ?? wf.available_workflows[0]?.id ?? "");
  }, [wf]);

  function assigneeLabel(kind: string, value: string): string {
    if (kind === "user") {
      const u = users.find((x) => x.id === value);
      return u ? u.name : "a specific person";
    }
    const m: Record<string, string> = {
      approver: "Any approver (or above)",
      manager: "Any manager (or above)",
      admin: "Any admin (or above)",
      owner: "The workspace owner",
    };
    return m[value] ?? `Role: ${value}`;
  }

  async function submit() {
    setSubmitBusy(true);
    setError("");
    try {
      await api.post<ContractDetail>(`/contracts/${contract.id}/submit-for-approval`, { workflow_id: chosenWf || null });
      onChanged();
      toast.success("Submitted for approval");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't submit for approval.";
      setError(msg);
      toast.error("Couldn't submit for approval", msg);
    } finally {
      setSubmitBusy(false);
    }
  }

  async function decide(decision: "approve" | "reject" | "changes_requested") {
    setDecideBusy(decision);
    setError("");
    try {
      await api.post<ContractDetail>(`/contracts/${contract.id}/workflow/decide`, { decision, comment: decideComment.trim() });
      setDecideComment("");
      onChanged();
      const verb = decision === "approve" ? "Approved" : decision === "reject" ? "Rejected" : "Changes requested";
      toast.success(verb, "Your decision was recorded.");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't record your decision.";
      setError(msg);
      toast.error("Couldn't record your decision", msg);
    } finally {
      setDecideBusy(null);
    }
  }

  if (wf === null) {
    return (
      <Card>
        <CardBody>
          <Skeleton className="h-24" />
        </CardBody>
      </Card>
    );
  }

  if (!wf.run) {
    if (EDITABLE_STATUSES.has(contract.status)) {
      return (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <WorkflowIcon className="h-4 w-4" /> Approvals
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {error && <ErrorBanner message={error} />}
            <p className="text-sm text-ink-2">This contract hasn&rsquo;t been submitted for approval yet.</p>
            {wf.available_workflows.length > 0 ? (
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label className="mb-1 block text-[13px] font-medium text-ink-2">Workflow</label>
                  <select value={chosenWf} onChange={(e) => setChosenWf(e.target.value)} className="h-10 rounded-sm border border-line bg-white px-3 text-sm">
                    {wf.available_workflows.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                        {w.is_default ? " (default for this type)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
                <Button onClick={submit} loading={submitBusy}>
                  <Send className="h-4 w-4" /> Submit for approval
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Button onClick={submit} loading={submitBusy}>
                  <Send className="h-4 w-4" /> Submit for review
                </Button>
                <span className="text-xs text-ink-3">No active workflows &mdash; it will just go to &ldquo;in review&rdquo;. Create one under Workflows.</span>
              </div>
            )}
          </CardBody>
        </Card>
      );
    }
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-ink-3">
            {contract.status === "in_review"
              ? "This contract is in review but isn’t attached to a workflow — use the status actions in the header to approve, reject, or request changes."
              : "This contract isn’t in an approval flow."}
          </p>
        </CardBody>
      </Card>
    );
  }

  const run = wf.run;
  const activeStepName = run.steps.find((s) => s.status === "active")?.name ?? "";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <WorkflowIcon className="h-4 w-4" /> {run.definition_name || "Approval workflow"}
        </CardTitle>
        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${RUN_STATUS_TONE[run.status] ?? "text-slate-700 bg-slate-100"}`}>
          {run.status === "running" ? "In progress" : run.status.replace(/_/g, " ")}
        </span>
      </CardHeader>
      <CardBody>
        {error && <ErrorBanner message={error} className="mb-3" />}
        <div className="mb-4 text-xs text-ink-3">
          Submitted by {run.started_by_name} · {timeAgo(run.started_at)}
          {run.completed_at ? ` · finished ${timeAgo(run.completed_at)}` : ""}
        </div>
        <div className="flex flex-col">
          {run.steps.map((s, i) => (
            <div key={s.id}>
              {i > 0 && <div className="ml-3 h-4 w-px bg-line" />}
              <div className={`flex items-start gap-3 rounded-lg p-3 ${s.status === "active" ? "border border-amber-300 bg-amber-50" : ""}`}>
                <span
                  className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${
                    s.status === "approved"
                      ? "bg-emerald-500 text-white"
                      : s.status === "rejected" || s.status === "changes_requested"
                        ? "bg-red-500 text-white"
                        : s.status === "active"
                          ? "bg-amber-500 text-white"
                          : "bg-line text-ink-3"
                  }`}
                >
                  {s.status === "approved" ? <Check className="h-3.5 w-3.5" /> : s.status === "rejected" || s.status === "changes_requested" ? <X className="h-3.5 w-3.5" /> : i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{s.name}</span>
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${STEP_TONE[s.status] ?? "text-slate-600 bg-slate-100"}`}>{s.status.replace(/_/g, " ")}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-ink-3">Assignee: {assigneeLabel(s.assignee_kind, s.assignee_value)}</div>
                  {s.decided_at && (
                    <div className="mt-1 text-xs text-ink-2">
                      {s.decision === "approve" ? "Approved" : s.decision === "reject" ? "Rejected" : "Changes requested"} by {s.decided_by_name} · {formatDateTime(s.decided_at)}
                      {s.comment && <div className="mt-1 rounded-md bg-surface-2 px-2 py-1 text-ink-2">&ldquo;{s.comment}&rdquo;</div>}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        {wf.can_decide && run.status === "running" && (
          <div className="mt-4 rounded-lg border border-line bg-surface-2 p-4">
            <div className="mb-2 text-sm font-medium text-ink">Your decision on &ldquo;{activeStepName}&rdquo;</div>
            <Textarea
              rows={2}
              value={decideComment}
              onChange={(e) => setDecideComment(e.target.value)}
              placeholder="Optional note (shown on the step; recommended when rejecting or requesting changes)"
              className="mb-2"
            />
            {/* Phase 9, item 8. Stacked and full-width on a phone, side by side from `sm` up.
                Wrapped buttons on a narrow screen end up half-width and adjacent, which is how
                somebody taps Reject meaning Approve — and an approval decision is not a thing
                to make easy to mis-tap. Each is at least 44px tall (WCAG 2.5.5). */}
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Button
                onClick={() => decide("approve")}
                loading={decideBusy === "approve"}
                disabled={!!decideBusy}
                className="h-11 w-full justify-center sm:h-9 sm:w-auto"
              >
                <Check className="h-3.5 w-3.5" aria-hidden="true" /> Approve
              </Button>
              <Button
                variant="outline"
                onClick={() => decide("changes_requested")}
                loading={decideBusy === "changes_requested"}
                disabled={!!decideBusy}
                className="h-11 w-full justify-center sm:h-9 sm:w-auto"
              >
                Request changes
              </Button>
              <Button
                variant="outline"
                onClick={() => decide("reject")}
                loading={decideBusy === "reject"}
                disabled={!!decideBusy}
                className="h-11 w-full justify-center sm:h-9 sm:w-auto"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" /> Reject
              </Button>
            </div>
          </div>
        )}
        {run.status === "running" && !wf.can_decide && <p className="mt-4 text-xs text-ink-3">Waiting on the assignee of the current step.</p>}
      </CardBody>
    </Card>
  );
}

const ENV_STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  sent: "Out for signature",
  partially_signed: "Partially signed",
  completed: "Completed",
  declined: "Declined",
  voided: "Voided",
  expired: "Expired",
};
const ENV_STATUS_TONE: Record<string, string> = {
  draft: "text-slate-600 bg-slate-100",
  sent: "text-amber-800 bg-amber-100",
  partially_signed: "text-amber-800 bg-amber-100",
  completed: "text-emerald-800 bg-emerald-100",
  declined: "text-red-800 bg-red-100",
  voided: "text-slate-600 bg-slate-100",
  expired: "text-slate-600 bg-slate-100",
};
const RCPT_STATUS_TONE: Record<string, string> = {
  created: "text-slate-600 bg-slate-100",
  sent: "text-sky-800 bg-sky-100",
  viewed: "text-violet-800 bg-violet-100",
  signed: "text-emerald-800 bg-emerald-100",
  declined: "text-red-800 bg-red-100",
};
const INPUT_CLS = "h-10 rounded-sm border border-line bg-white px-3 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";

type DraftRecipient = { name: string; email: string; kind: "signer" | "cc" };

const OBL_TONE: Record<string, string> = {
  pending: "text-slate-600 bg-slate-100",
  done: "text-emerald-800 bg-emerald-100",
  skipped: "text-slate-500 bg-slate-100",
  overdue: "text-red-800 bg-red-100",
};

function ObligationsTab({ contract }: { contract: ContractDetail }) {
  const [items, setItems] = useState<Obligation[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  // add form state
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [due, setDue] = useState("");
  const [ownerId, setOwnerId] = useState<string>("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    api.get<Obligation[]>(`/contracts/${contract.id}/obligations`).then(setItems).catch(() => setItems([]));
    api.get<User[]>("/users").then(setUsers).catch(() => {});
  }, [contract.id]);
  useEffect(load, [load]);

  async function add() {
    if (!title.trim()) return;
    setError("");
    setBusyId("__add__");
    try {
      await api.post<Obligation>(`/contracts/${contract.id}/obligations`, {
        title: title.trim(),
        description: desc.trim(),
        due_date: due || null,
        owner_id: ownerId || null,
      });
      setTitle(""); setDesc(""); setDue(""); setOwnerId("");
      setAdding(false);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add the obligation.");
    } finally {
      setBusyId(null);
    }
  }

  async function update(o: Obligation, patch: Partial<Obligation>) {
    setBusyId(o.id);
    setError("");
    try {
      await api.patch<Obligation>(`/contracts/${contract.id}/obligations/${o.id}`, patch);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't update the obligation.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(o: Obligation) {
    if (!window.confirm(`Delete "${o.title}"?`)) return;
    setBusyId(o.id);
    try {
      await api.del(`/contracts/${contract.id}/obligations/${o.id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete the obligation.");
    } finally {
      setBusyId(null);
    }
  }

  const open = items?.filter((o) => o.status === "pending" || o.status === "overdue") ?? [];
  const done = items?.filter((o) => o.status === "done" || o.status === "skipped") ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <ListTodo className="h-4 w-4" /> Obligations
        </CardTitle>
        {!adding && (
          <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" /> Add
          </Button>
        )}
      </CardHeader>
      <CardBody className="space-y-3">
        {error && <ErrorBanner message={error} />}
        {adding && (
          <div className="space-y-2 rounded-lg border border-line bg-surface-2 p-3">
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What needs to happen?" autoFocus className="h-10 w-full rounded-sm border border-line bg-white px-3 text-sm" />
            <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} placeholder="Notes (optional)" className="w-full rounded-sm border border-line bg-white px-3 py-2 text-sm" />
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-xs text-ink-3">
                Due
                <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="h-9 rounded-sm border border-line bg-white px-2 text-sm" />
              </label>
              <label className="flex items-center gap-2 text-xs text-ink-3">
                Owner
                <select value={ownerId} onChange={(e) => setOwnerId(e.target.value)} className="h-9 rounded-sm border border-line bg-white px-2 text-sm">
                  <option value="">— Unassigned —</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </label>
              <div className="ml-auto flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => { setAdding(false); setTitle(""); setDesc(""); setDue(""); setOwnerId(""); }}>Cancel</Button>
                <Button size="sm" onClick={add} loading={busyId === "__add__"} disabled={!title.trim()}>
                  <Plus className="h-3.5 w-3.5" /> Add obligation
                </Button>
              </div>
            </div>
          </div>
        )}

        {items === null && <Skeleton className="h-16" />}
        {items !== null && items.length === 0 && !adding && (
          <p className="text-sm text-ink-3">No obligations yet. Add ones like "renewal notice by 60d before end" or "quarterly status report".</p>
        )}

        {open.length > 0 && (
          <div className="space-y-1">
            <div className="px-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">Open ({open.length})</div>
            {open.map((o) => <ObligationRow key={o.id} o={o} busy={busyId === o.id} onUpdate={update} onDelete={remove} />)}
          </div>
        )}
        {done.length > 0 && (
          <div className="space-y-1 pt-2">
            <div className="px-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">Completed ({done.length})</div>
            {done.map((o) => <ObligationRow key={o.id} o={o} busy={busyId === o.id} onUpdate={update} onDelete={remove} />)}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function ObligationRow({ o, busy, onUpdate, onDelete }: { o: Obligation; busy: boolean; onUpdate: (o: Obligation, patch: Partial<Obligation>) => void; onDelete: (o: Obligation) => void }) {
  const isDone = o.status === "done";
  const isSkipped = o.status === "skipped";
  const isOverdue = o.status === "overdue";
  return (
    <div className={cn(
      "flex flex-wrap items-center gap-3 rounded-md border border-line bg-white p-3",
      isOverdue && "border-red-200 bg-red-50/40",
      (isDone || isSkipped) && "opacity-70",
    )}>
      <button
        onClick={() => onUpdate(o, { status: isDone ? "pending" : "done" } as Partial<Obligation>)}
        disabled={busy}
        title={isDone ? "Mark as pending" : "Mark as done"}
        className={cn(
          "grid h-6 w-6 shrink-0 place-items-center rounded border",
          isDone ? "border-emerald-500 bg-emerald-500 text-white" : "border-line bg-white text-ink-3 hover:border-accent",
        )}
      >
        {isDone && <Check className="h-3.5 w-3.5" />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("text-sm font-medium text-ink", (isDone || isSkipped) && "line-through")}>{o.title}</span>
          <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${OBL_TONE[o.status] ?? "text-slate-600 bg-slate-100"}`}>{o.status}</span>
          {o.owner_name && <span className="text-[11px] text-ink-3">· {o.owner_name}</span>}
        </div>
        {o.description && <p className="mt-0.5 text-xs text-ink-3">{o.description}</p>}
        <div className="mt-0.5 text-[11px] text-ink-3">
          {o.due_date ? (
            <span className={cn(isOverdue && "text-red-700 font-medium")}>
              Due {formatDate(o.due_date)}
            </span>
          ) : <span>No due date</span>}
          {o.completed_at && (
            <span> · Completed {formatDateTime(o.completed_at)}{o.completed_by_name ? ` by ${o.completed_by_name}` : ""}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1">
        {!isDone && !isSkipped && (
          <Button size="sm" variant="ghost" onClick={() => onUpdate(o, { status: "skipped" } as Partial<Obligation>)} disabled={busy} title="Skip">
            Skip
          </Button>
        )}
        {(isDone || isSkipped) && (
          <Button size="sm" variant="ghost" onClick={() => onUpdate(o, { status: "pending" } as Partial<Obligation>)} disabled={busy} title="Reopen">
            Reopen
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => onDelete(o)} disabled={busy} title="Delete">
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

const TAB_KIND_LABEL: Record<string, string> = {
  signature: "Signature",
  initials: "Initials",
  date: "Date",
  text: "Text",
  checkbox: "Checkbox",
};

function TabsPanel({ env, onChanged }: { env: SignatureEnvelope; onChanged: () => void }) {
  const tabs = env.tabs;
  const recipById = useMemo(() => Object.fromEntries(env.recipients.map((r) => [r.id, r])), [env.recipients]);
  // default to the first signer
  const firstSigner = env.recipients.find((r) => r.kind === "signer");
  const [recipientId, setRecipientId] = useState<string>(firstSigner?.id ?? "");
  const [kind, setKind] = useState<"signature" | "initials" | "date" | "text" | "checkbox">("signature");
  const [page, setPage] = useState(1);
  const [x, setX] = useState(0.62);
  const [y, setY] = useState(0.85);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function addTab() {
    if (!recipientId) { setError("Pick a recipient."); return; }
    setBusy(true); setError("");
    try {
      await api.post(`/envelopes/${env.id}/tabs`, {
        recipient_id: recipientId, kind, page, x, y, width: 0.25, height: 0.05, required: true, label: label.trim(),
      });
      setLabel("");
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add tab.");
    } finally {
      setBusy(false);
    }
  }
  async function removeTab(id: string) {
    setBusy(true);
    try {
      await api.del(`/envelopes/${env.id}/tabs/${id}`);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove tab.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface-2 p-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-ink">Signature tabs <span className="text-ink-3">({tabs.length})</span></div>
        <div className="text-[11px] text-ink-3">Placed on the document — recipients see &amp; fill these</div>
      </div>
      {error && <ErrorBanner message={error} />}
      {tabs.length > 0 && (
        <div className="space-y-1">
          {tabs.map((t) => {
            const r = recipById[t.recipient_id];
            return (
              <div key={t.id} className="flex flex-wrap items-center gap-2 rounded-md bg-white px-3 py-2 text-sm">
                <span className="rounded-full bg-accent-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">{TAB_KIND_LABEL[t.kind]}</span>
                <span className="text-ink-2">{r?.name ?? "?"}</span>
                <span className="text-[11px] text-ink-3">p.{t.page} · x={t.x.toFixed(2)} y={t.y.toFixed(2)}</span>
                {t.label && <span className="text-[11px] text-ink-3">· “{t.label}”</span>}
                {!t.required && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-ink-3">optional</span>}
                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => removeTab(t.id)} disabled={busy} title="Remove">
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 rounded-md bg-white p-3 sm:grid-cols-6">
        <label className="col-span-2 text-xs text-ink-3">Recipient
          <select value={recipientId} onChange={(e) => setRecipientId(e.target.value)} className="mt-1 block h-9 w-full rounded-sm border border-line bg-white px-2 text-sm">
            {env.recipients.map((r) => (
              <option key={r.id} value={r.id}>{r.name} ({r.kind})</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-ink-3">Kind
          <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className="mt-1 block h-9 w-full rounded-sm border border-line bg-white px-2 text-sm">
            <option value="signature">Signature</option>
            <option value="initials">Initials</option>
            <option value="date">Date</option>
            <option value="text">Text</option>
            <option value="checkbox">Checkbox</option>
          </select>
        </label>
        <label className="text-xs text-ink-3">Page
          <input type="number" min={1} value={page} onChange={(e) => setPage(Math.max(1, Number(e.target.value) || 1))} className="mt-1 block h-9 w-full rounded-sm border border-line bg-white px-2 text-sm" />
        </label>
        <label className="text-xs text-ink-3">X (0–1)
          <input type="number" step={0.01} min={0} max={1} value={x} onChange={(e) => setX(Math.max(0, Math.min(1, Number(e.target.value) || 0)))} className="mt-1 block h-9 w-full rounded-sm border border-line bg-white px-2 text-sm" />
        </label>
        <label className="text-xs text-ink-3">Y (0–1)
          <input type="number" step={0.01} min={0} max={1} value={y} onChange={(e) => setY(Math.max(0, Math.min(1, Number(e.target.value) || 0)))} className="mt-1 block h-9 w-full rounded-sm border border-line bg-white px-2 text-sm" />
        </label>
        <label className="col-span-2 text-xs text-ink-3 sm:col-span-3">Label (optional)
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Signature — Buyer" className="mt-1 block h-9 w-full rounded-sm border border-line bg-white px-2 text-sm" />
        </label>
        <div className="col-span-2 flex items-end justify-end sm:col-span-3">
          <Button size="sm" onClick={addTab} loading={busy}>
            <PenLine className="h-3.5 w-3.5" /> Add tab
          </Button>
        </div>
      </div>
      <p className="text-[11px] text-ink-3">
        Pick the page and (x, y) position as fractions (0 = top-left). Tabs are stamped onto the executed PDF on completion.
      </p>
    </div>
  );
}

function SignaturesTab({ contract, env, onChanged }: { contract: ContractDetail; env: SignatureEnvelope | null; onChanged: () => void }) {
  const toast = useToast();
  // Pre-fill the first recipient with a demo address so testing the signature flow is one-click.
  // Change/clear before sending real signature requests.
  const [recips, setRecips] = useState<DraftRecipient[]>([{ name: "Shahzaib", email: "shahzaib@thiqatech.com", kind: "signer" }]);
  const [order, setOrder] = useState<"sequential" | "parallel">("sequential");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  async function prepare() {
    const clean = recips.map((r) => ({ name: r.name.trim(), email: r.email.trim(), kind: r.kind })).filter((r) => r.name && r.email);
    if (clean.length === 0) {
      setError("Add at least one recipient with a name and email.");
      return;
    }
    setBusy("prepare");
    setError("");
    try {
      await api.post(`/contracts/${contract.id}/prepare-signature`, { recipients: clean, message: message.trim(), signing_order: order });
      onChanged();
      toast.success("Signing request prepared", `${clean.length} recipient${clean.length === 1 ? "" : "s"} added — review, then send.`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't prepare the signing request.";
      setError(msg);
      toast.error("Couldn't prepare the signing request", msg);
    } finally {
      setBusy(null);
    }
  }

  async function act(key: string, fn: () => Promise<unknown>, fail: string, ok?: string) {
    setBusy(key);
    setError("");
    try {
      await fn();
      onChanged();
      if (ok) toast.success(ok);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : fail;
      setError(msg);
      toast.error(fail, msg === fail ? undefined : msg);
    } finally {
      setBusy(null);
    }
  }

  async function downloadFile(path: string, name: string) {
    try {
      const blob = await api.blob(path);
      downloadBlob(blob, name);
    } catch {
      setError("Couldn't download that file.");
    }
  }

  function copyLink(link: string, rid: string) {
    const url = `${origin}${link}`;
    const onOk = () => {
      setCopied(rid);
      setTimeout(() => setCopied(null), 1500);
      toast.success("Link copied", "Paste it wherever you need.");
    };
    const onFail = () => toast.error("Couldn't copy", "Long-press the link to copy it manually.");

    // The modern Clipboard API is only available in secure contexts (HTTPS or localhost). On
    // plain HTTP behind an IP this is undefined, so we fall back to the legacy execCommand path
    // (an off-screen textarea + select + copy) which works on HTTP too.
    if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(onOk, () => legacyCopy(url) ? onOk() : onFail());
    } else {
      legacyCopy(url) ? onOk() : onFail();
    }
  }

  // --- No envelope yet -------------------------------------------------------
  if (!env) {
    if (contract.status !== "approved") {
      return (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <PenLine className="h-4 w-4" /> Signatures
            </CardTitle>
          </CardHeader>
          <CardBody>
            <p className="text-sm text-ink-2">
              This contract needs to be <strong>approved</strong> before it can be sent for signature.
              {EDITABLE_STATUSES.has(contract.status) ? " Submit it for approval from the Approvals tab." : ""}
            </p>
          </CardBody>
        </Card>
      );
    }
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <PenLine className="h-4 w-4" /> Prepare for signature
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          {error && <ErrorBanner message={error} />}
          <div className="space-y-2">
            <div className="text-[13px] font-medium text-ink-2">Recipients</div>
            {recips.map((r, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <input
                  className={cn(INPUT_CLS, "min-w-[10rem] flex-1")}
                  placeholder="Full name"
                  value={r.name}
                  onChange={(e) => setRecips((rs) => rs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                />
                <input
                  className={cn(INPUT_CLS, "min-w-[12rem] flex-1")}
                  placeholder="email@company.com"
                  type="email"
                  value={r.email}
                  onChange={(e) => setRecips((rs) => rs.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))}
                />
                <select
                  className={INPUT_CLS}
                  value={r.kind}
                  onChange={(e) => setRecips((rs) => rs.map((x, j) => (j === i ? { ...x, kind: e.target.value as "signer" | "cc" } : x)))}
                >
                  <option value="signer">Signer</option>
                  <option value="cc">CC (gets a copy)</option>
                </select>
                {recips.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setRecips((rs) => rs.filter((_, j) => j !== i))}
                    className="grid h-9 w-9 place-items-center rounded-md text-ink-3 hover:bg-surface-3 hover:text-danger"
                    aria-label="Remove recipient"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={() => setRecips((rs) => [...rs, { name: "", email: "", kind: "signer" }])}
              className="text-sm font-medium text-accent hover:underline"
            >
              + Add recipient
            </button>
          </div>
          <div>
            <div className="mb-1 text-[13px] font-medium text-ink-2">Signing order</div>
            <div className="flex flex-wrap gap-4 text-sm text-ink-2">
              <label className="flex items-center gap-1.5">
                <input type="radio" name="order" checked={order === "sequential"} onChange={() => setOrder("sequential")} /> Sequential — one after another
              </label>
              <label className="flex items-center gap-1.5">
                <input type="radio" name="order" checked={order === "parallel"} onChange={() => setOrder("parallel")} /> Parallel — everyone at once
              </label>
            </div>
          </div>
          <div>
            <div className="mb-1 text-[13px] font-medium text-ink-2">Message to recipients (optional)</div>
            <Textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="A short note shown on the signing page." />
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={prepare} loading={busy === "prepare"}>
              <PenLine className="h-4 w-4" /> Prepare request
            </Button>
            <span className="text-xs text-ink-3">You&rsquo;ll be able to review it before anything is sent.</span>
          </div>
        </CardBody>
      </Card>
    );
  }

  // --- Envelope exists -------------------------------------------------------
  const live = env.status === "sent" || env.status === "partially_signed";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <PenLine className="h-4 w-4" /> Signature request
        </CardTitle>
        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${ENV_STATUS_TONE[env.status] ?? "text-slate-700 bg-slate-100"}`}>
          {ENV_STATUS_LABEL[env.status] ?? env.status}
        </span>
      </CardHeader>
      <CardBody className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <div className="text-xs text-ink-3">
          {env.signing_order === "sequential" ? "Signed in order" : "All sign in parallel"}
          {env.sent_at ? ` · sent ${timeAgo(env.sent_at)}` : ""}
          {env.completed_at ? ` · completed ${timeAgo(env.completed_at)}` : ""}
        </div>
        {env.message && <div className="rounded-md bg-surface-2 px-3 py-2 text-sm text-ink-2">&ldquo;{env.message}&rdquo;</div>}

        {env.status === "draft" && <TabsPanel env={env} onChanged={onChanged} />}

        <div className="divide-y divide-line overflow-hidden rounded-lg border border-line">
          {env.recipients.map((r: SignatureRecipient) => (
            <div key={r.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-3 text-xs font-semibold text-ink-2">{r.sequence}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink">{r.name}</span>
                  {r.kind === "cc" && <span className="rounded bg-slate-100 px-1.5 text-[10px] font-medium uppercase tracking-wide text-ink-3">CC</span>}
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${RCPT_STATUS_TONE[r.status] ?? "text-slate-600 bg-slate-100"}`}>{r.status}</span>
                </div>
                <div className="text-xs text-ink-3">
                  {r.email}
                  {r.signed_name && r.signed_name !== r.name ? ` · signed as “${r.signed_name}”` : ""}
                  {r.signed_at ? ` · ${formatDateTime(r.signed_at)}` : ""}
                  {r.declined_reason ? ` · declined: ${r.declined_reason}` : ""}
                </div>
                {r.signing_link && (
                  <div className="mt-1 flex items-center gap-1.5">
                    <code className="max-w-[22rem] truncate rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-3">
                      {origin}
                      {r.signing_link}
                    </code>
                    <button type="button" onClick={() => copyLink(r.signing_link!, r.id)} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                      {copied === r.id ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copied === r.id ? "copied" : "copy"}
                    </button>
                  </div>
                )}
              </div>
              {live && r.kind === "signer" && r.status !== "signed" && r.status !== "declined" && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={busy === `remind-${r.id}`}
                  onClick={() => act(`remind-${r.id}`, () => api.post(`/envelopes/${env.id}/recipients/${r.id}/remind`), "Couldn't send a reminder.", "Reminder sent")}
                >
                  <Send className="h-3.5 w-3.5" /> Remind
                </Button>
              )}
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {env.status === "draft" && (
            <>
              <Button loading={busy === "send"} onClick={() => act("send", () => api.post(`/envelopes/${env.id}/send`), "Couldn't send the request.", "Sent for signature")}>
                <Send className="h-4 w-4" /> Send for signature
              </Button>
              <Button variant="ghost" loading={busy === "void"} onClick={() => act("void", () => api.post(`/envelopes/${env.id}/void`), "Couldn't discard the draft.", "Draft discarded")}>
                <Trash2 className="h-4 w-4" /> Discard
              </Button>
            </>
          )}
          {live && (
            <>
              {env.document_file_id && (
                <Button variant="secondary" size="sm" onClick={() => downloadFile(`/envelopes/${env.id}/document`, `${contract.title}.pdf`)}>
                  <FileText className="h-3.5 w-3.5" /> View sent document
                </Button>
              )}
              <Button variant="ghost" size="sm" loading={busy === "void"} onClick={() => act("void", () => api.post(`/envelopes/${env.id}/void`), "Couldn't void the envelope.", "Envelope voided")}>
                <X className="h-3.5 w-3.5" /> Void envelope
              </Button>
            </>
          )}
          {env.status === "completed" && (
            <>
              <Button variant="secondary" size="sm" onClick={() => downloadFile(`/envelopes/${env.id}/signed-pdf`, `${contract.title} (executed).pdf`)}>
                <FileCheck2 className="h-3.5 w-3.5" /> Download executed PDF
              </Button>
              <Button variant="ghost" size="sm" onClick={() => downloadFile(`/envelopes/${env.id}/certificate`, `${contract.title} — certificate.pdf`)}>
                <FileDown className="h-3.5 w-3.5" /> Certificate of completion
              </Button>
            </>
          )}
        </div>

        {env.status === "completed" && <p className="text-sm font-medium text-emerald-700">✓ Fully executed — every signer has signed.</p>}
        {env.status === "declined" && (
          <p className="text-sm text-red-700">A signer declined this request. Return the contract to draft from the header to revise it, then start a new request.</p>
        )}
        {env.status === "voided" && <p className="text-sm text-ink-3">This signing request was voided. You can prepare a new one if the contract is still approved.</p>}
        {env.status === "draft" && (
          <p className="text-[11px] text-ink-3">
            Recipients get a unique link to review the document and adopt a typed signature — no account needed. Signers sign{" "}
            {env.signing_order === "sequential" ? "one after another" : "in any order"}; the executed PDF and a certificate of completion are produced automatically once everyone has signed.
          </p>
        )}
      </CardBody>
    </Card>
  );
}


/* ------------------------------------------------------------------- policy ---------- */

const FINDING_TONE: Record<PolicyFinding["status"], string> = {
  missing: "border-red-300/60",
  prohibited: "border-red-300/60",
  altered: "border-amber-300/60",
  present: "border-line",
};

const FINDING_LABEL: Record<PolicyFinding["status"], string> = {
  missing: "Missing",
  prohibited: "Prohibited language present",
  altered: "Wording changed",
  present: "As approved",
};

/**
 * Playbook compliance. `missing` and `altered` are shown as different problems on purpose:
 * an altered clause is still under its heading, so a reviewer skimming the document sees
 * nothing wrong — that is exactly the case worth surfacing.
 *
 * "Re-check" is a POST because acting on the result has a consequence: a blocking deviation
 * classifies the agreement non-standard, which changes who has to approve it.
 */
function PolicyTab({ contract, onChanged }: { contract: ContractDetail; onChanged: () => void }) {
  const [review, setReview] = useState<PolicyReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .get<PolicyReview>(`/contracts/${contract.id}/policy-review`)
      .catch(() => null)
      .then((r) => setReview(r));
  }, [contract.id]);
  useEffect(load, [load]);

  async function recheck() {
    setBusy(true);
    setError("");
    try {
      const result = await api.post<PolicyReview>(`/contracts/${contract.id}/policy-review`, {});
      setReview(result);
      if (result.classified_non_standard) onChanged();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "The review could not run.");
    } finally {
      setBusy(false);
    }
  }

  if (!review) return <Skeleton className="h-32" />;

  return (
    <div className="space-y-4 py-4">
      {error && <ErrorBanner message={error} />}

      {review.playbooks.length === 0 ? (
        <Card>
          <CardBody className="py-8 text-center text-sm text-ink-2">
            <Shield className="mx-auto mb-3 h-9 w-9 text-ink-3" />
            <div className="text-base font-semibold text-ink">No policy covers this agreement</div>
            <p className="mt-1">
              Playbooks are defined in the clause library. Until one applies, nothing here is
              checked.
            </p>
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardBody className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm">
                {review.ok ? (
                  <>
                    <BadgeCheck className="h-5 w-5 text-emerald-600" />
                    <span className="text-ink">
                      Within policy — {review.checked} clause{review.checked === 1 ? "" : "s"}{" "}
                      checked against {review.playbooks.map((p: { name: string }) => p.name).join(", ")}.
                    </span>
                  </>
                ) : (
                  <>
                    <AlertTriangle className="h-5 w-5 text-amber-600" />
                    <span className="text-ink">
                      {review.deviation_count} deviation
                      {review.deviation_count === 1 ? "" : "s"}
                      {review.blocker_count > 0 && (
                        <>
                          {" "}
                          — <strong>{review.blocker_count} blocking</strong>, which sends this down
                          the non-standard approval route
                        </>
                      )}
                      .
                    </span>
                  </>
                )}
              </div>
              <Button size="sm" variant="ghost" loading={busy} onClick={recheck}>
                Re-check
              </Button>
            </CardBody>
          </Card>

          <div className="space-y-2">
            {review.findings.map((f: PolicyFinding) => (
              <Card key={`${f.playbook}-${f.clause_key}-${f.kind}`} className={FINDING_TONE[f.status]}>
                <CardBody className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    {f.status === "present" ? (
                      <BadgeCheck className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <AlertTriangle
                        className={cn(
                          "h-4 w-4",
                          f.severity === "blocker" ? "text-red-600" : "text-amber-600",
                        )}
                      />
                    )}
                    <span className="text-sm font-semibold text-ink">{f.title}</span>
                    <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3">
                      {FINDING_LABEL[f.status]}
                    </span>
                    {f.status !== "present" && (
                      <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] uppercase text-ink-3">
                        {f.severity}
                      </span>
                    )}
                    <code className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] text-ink-3">
                      {f.clause_key}
                    </code>
                  </div>

                  {f.status === "altered" && f.diff.length > 0 && (
                    <pre className="overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-[11px] leading-relaxed">
                      {f.diff.map((line, i) => (
                        <div
                          key={i}
                          className={
                            line.startsWith("-")
                              ? "text-red-600"
                              : line.startsWith("+")
                                ? "text-emerald-700"
                                : "text-ink-3"
                          }
                        >
                          {line}
                        </div>
                      ))}
                    </pre>
                  )}

                  {f.status === "missing" && (
                    <p className="text-sm text-ink-2">
                      The approved wording for this clause does not appear in the document.
                    </p>
                  )}

                  {f.guidance && <p className="text-xs text-ink-3">{f.guidance}</p>}

                  <div className="text-[11px] text-ink-3">
                    {f.playbook} · {Math.round(f.ratio * 100)}% match to the approved wording
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}


/* ---------------------------------------------------------------- readiness ---------- */

/**
 * The sign-off readiness pack. Blockers lead, because the failure this prevents is a
 * signatory executing an agreement whose deviations nobody resolved — the information already
 * existed, it just was not in front of them.
 */
function ReadinessTab({ contract }: { contract: ContractDetail }) {
  const [pack, setPack] = useState<Readiness | null>(null);

  useEffect(() => {
    api
      .get<Readiness>(`/contracts/${contract.id}/readiness`)
      .catch(() => null)
      .then(setPack);
  }, [contract.id]);

  if (!pack) return <Skeleton className="h-32" />;

  return (
    <div className="space-y-4 py-4">
      <Card className={pack.ready ? "border-emerald-300/60" : "border-red-300/60"}>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {pack.ready ? (
              <BadgeCheck className="h-5 w-5 text-emerald-600" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-red-600" />
            )}
            <span className="text-sm font-semibold text-ink">
              {pack.ready
                ? "Ready for signature"
                : `Not ready — ${pack.blockers.length} blocker${pack.blockers.length === 1 ? "" : "s"}`}
            </span>
          </div>
          <a
            href={`${API_BASE}/contracts/${contract.id}/readiness.pdf`}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-line px-3 text-sm text-ink-2 transition hover:text-ink"
          >
            <FileDown className="h-4 w-4" /> Download pack
          </a>
        </CardBody>
      </Card>

      {pack.blockers.length > 0 && (
        <Card>
          <CardBody className="space-y-1">
            <div className="text-sm font-semibold text-ink">Blockers</div>
            {pack.blockers.map((b) => (
              <div key={b} className="flex items-start gap-2 text-sm text-ink-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                <span>{b}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {pack.notes.length > 0 && (
        <Card>
          <CardBody className="space-y-1">
            <div className="text-sm font-semibold text-ink">Worth knowing</div>
            {pack.notes.map((n) => (
              <p key={n} className="text-sm text-ink-2">
                {n}
              </p>
            ))}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardBody className="space-y-2">
          <div className="text-sm font-semibold text-ink">Approvals</div>
          {pack.decisions.length === 0 ? (
            <p className="text-sm text-ink-3">No approval decisions recorded.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-3">
                    <th className="py-1 pr-3">Stage</th>
                    <th className="py-1 pr-3">Step</th>
                    <th className="py-1 pr-3">Decided by</th>
                    <th className="py-1 pr-3">Decision</th>
                    <th className="py-1 pr-3">When</th>
                    <th className="py-1">SLA</th>
                  </tr>
                </thead>
                <tbody>
                  {pack.decisions.map((d: ReadinessDecision, i: number) => (
                    <tr key={i} className="border-t border-line">
                      <td className="py-1.5 pr-3 text-ink-3">{d.stage}</td>
                      <td className="py-1.5 pr-3 text-ink">{d.name}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{d.who}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{d.decision}</td>
                      <td className="py-1.5 pr-3 text-ink-3">{d.at}</td>
                      <td className="py-1.5 text-ink-3">
                        {d.on_time === null ? "—" : d.on_time ? "on time" : "late"}
                        {d.escalated && " (escalated)"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-2 text-sm">
          <div className="font-semibold text-ink">Where this wording came from</div>
          <div className="grid gap-1 text-ink-2 sm:grid-cols-2">
            <div>Source: {pack.provenance.source ?? "—"}</div>
            <div>Template: {pack.provenance.template ?? "—"}</div>
            <div>Revision: {pack.provenance.template_version ?? "—"}</div>
            {pack.provenance.edited_since_generation !== null &&
              pack.provenance.edited_since_generation !== undefined && (
                <div>
                  Edited after generation:{" "}
                  {pack.provenance.edited_since_generation ? "Yes" : "No"}
                </div>
              )}
          </div>
          {(pack.provenance.clauses ?? []).length > 0 && (
            <div className="space-y-1 pt-1">
              {(pack.provenance.clauses ?? []).map((c) => (
                <div key={c.key} className="flex flex-wrap items-center gap-2 text-xs">
                  <code className="rounded bg-surface-3 px-1.5 py-0.5">{c.key}</code>
                  <span className="text-ink-2">used v{c.used ?? "—"}</span>
                  {c.stale && (
                    <span className="text-amber-700">
                      revised since — current v{c.current}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
