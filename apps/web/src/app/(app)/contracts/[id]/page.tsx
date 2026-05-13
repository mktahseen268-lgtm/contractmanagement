"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Check, Copy, Download, Eye, FileCheck2, FileDown, FileText, History, Pencil, PenLine, Repeat, RotateCcw, Send, Sparkles, Trash2, Workflow as WorkflowIcon, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Skeleton, Textarea } from "@/components/ui";

const BlockEditor = dynamic(() => import("@/components/block-editor").then((m) => m.BlockEditor), {
  ssr: false,
  loading: () => <div className="cm-doc min-h-[42vh] px-1 py-2 text-sm text-ink-3">Loading editor…</div>,
});
import { PageHeader } from "@/components/shell";
import { ActivityFeed } from "@/components/widgets";
import { LifecycleBar, RiskBadge, StatusPill } from "@/components/lifecycle";
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
import type { ActivityItem, Comment, ContractDetail, ContractWorkflow, FileObject, SignatureEnvelope, SignatureRecipient, User, Version, VersionDetail, WorkflowRunStep } from "@/lib/types";

type Tab = "overview" | "approvals" | "signatures" | "document" | "activity" | "comments" | "files" | "versions";
const EDITABLE_STATUSES = new Set(["draft", "changes_requested"]);
const TABS: Tab[] = ["overview", "approvals", "signatures", "document", "activity", "comments", "files", "versions"];
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't submit for approval.");
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't update the contract.");
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't generate the PDF.");
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
      router.push("/contracts");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete.");
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
      router.push(`/contracts/${succ.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't renew this contract.");
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

        {tab === "overview" && <OverviewTab contract={contract} />}
        {tab === "approvals" && <ApprovalsTab contract={contract} wf={wfState} onChanged={load} />}
        {tab === "signatures" && <SignaturesTab contract={contract} env={sigState} onChanged={load} />}
        {tab === "document" && <DocumentTab key={contract.id} contract={contract} />}
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

function DocumentTab({ contract }: { contract: ContractDetail }) {
  const editable = EDITABLE_STATUSES.has(contract.status);
  const [md, setMd] = useState<string>(contract.body || "");
  const [baseline, setBaseline] = useState<string>(contract.body || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const dirty = md !== baseline;

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
            <Button size="sm" variant="ghost" onClick={() => setMd(baseline)} disabled={!dirty || saving}>
              Discard
            </Button>
            <Button size="sm" onClick={save} loading={saving} disabled={!dirty}>
              Save
            </Button>
          </div>
        </CardHeader>
      )}
      <CardBody>
        {error && <ErrorBanner message={error} className="mb-3" />}
        {!editable && (
          <p className="mb-3 text-xs text-ink-3">
            This contract is “{titleCase(contract.status)}” — the document is read-only (merge variables shown resolved). Return it to draft to edit.
          </p>
        )}
        <BlockEditor
          value={editable ? baseline : resolveContractVariables(contract.body || "", contract)}
          editable={editable}
          onChange={editable ? setMd : undefined}
        />
        {editable && (
          <details className="mt-4 text-xs text-ink-3">
            <summary className="cursor-pointer select-none">Markdown source · merge variables look like <code>{"{{counterparty}}"}</code> and resolve in the PDF / read-only view</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-[11px] text-ink-2">{md || "(empty)"}</pre>
          </details>
        )}
      </CardBody>
    </Card>
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't submit for approval.");
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't record your decision.");
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
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => decide("approve")} loading={decideBusy === "approve"} disabled={!!decideBusy}>
                <Check className="h-3.5 w-3.5" /> Approve
              </Button>
              <Button variant="outline" onClick={() => decide("changes_requested")} loading={decideBusy === "changes_requested"} disabled={!!decideBusy}>
                Request changes
              </Button>
              <Button variant="outline" onClick={() => decide("reject")} loading={decideBusy === "reject"} disabled={!!decideBusy}>
                <X className="h-3.5 w-3.5" /> Reject
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

function SignaturesTab({ contract, env, onChanged }: { contract: ContractDetail; env: SignatureEnvelope | null; onChanged: () => void }) {
  const [recips, setRecips] = useState<DraftRecipient[]>([{ name: "", email: "", kind: "signer" }]);
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't prepare the signing request.");
    } finally {
      setBusy(null);
    }
  }

  async function act(key: string, fn: () => Promise<unknown>, fail: string) {
    setBusy(key);
    setError("");
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : fail);
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
    navigator.clipboard?.writeText(`${origin}${link}`).then(
      () => {
        setCopied(rid);
        setTimeout(() => setCopied(null), 1500);
      },
      () => {},
    );
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
                  onClick={() => act(`remind-${r.id}`, () => api.post(`/envelopes/${env.id}/recipients/${r.id}/remind`), "Couldn't send a reminder.")}
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
              <Button loading={busy === "send"} onClick={() => act("send", () => api.post(`/envelopes/${env.id}/send`), "Couldn't send the request.")}>
                <Send className="h-4 w-4" /> Send for signature
              </Button>
              <Button variant="ghost" loading={busy === "void"} onClick={() => act("void", () => api.post(`/envelopes/${env.id}/void`), "Couldn't discard the draft.")}>
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
              <Button variant="ghost" size="sm" loading={busy === "void"} onClick={() => act("void", () => api.post(`/envelopes/${env.id}/void`), "Couldn't void the envelope.")}>
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
