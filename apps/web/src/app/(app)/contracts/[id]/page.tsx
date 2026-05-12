"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams, useRouter } from "next/navigation";
import { Download, Eye, FileDown, FileText, History, Pencil, RotateCcw, Sparkles, Trash2 } from "lucide-react";
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
  TRANSITION_LABELS,
  titleCase,
} from "@/lib/utils";
import type { ActivityItem, Comment, ContractDetail, FileObject, Version, VersionDetail } from "@/lib/types";

type Tab = "overview" | "document" | "activity" | "comments" | "files" | "versions";
const EDITABLE_STATUSES = new Set(["draft", "changes_requested"]);
const TABS: Tab[] = ["overview", "document", "activity", "comments", "files", "versions"];

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [contract, setContract] = useState<ContractDetail | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<ContractDetail>(`/contracts/${id}`).then(setContract).catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load this contract."));
  }, [id]);

  useEffect(load, [load]);

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
  const positive = contract.available_transitions.filter((t) => !NEGATIVE_TRANSITIONS.has(t));
  const negative = contract.available_transitions.filter((t) => NEGATIVE_TRANSITIONS.has(t));

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

      <div className="space-y-5 p-6">
        {error && <ErrorBanner message={error} />}

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
        {tab === "document" && <DocumentTab key={contract.id} contract={contract} />}
        {tab === "activity" && <ActivityTab contractId={contract.id} />}
        {tab === "comments" && <CommentsTab contractId={contract.id} />}
        {tab === "files" && <FilesTab contractId={contract.id} />}
        {tab === "versions" && <VersionsTab contract={contract} onRestored={load} onGoToDocument={() => setTab("document")} />}
      </div>
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
