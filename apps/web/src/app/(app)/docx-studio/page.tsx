"use client";

/**
 * Word round-trip — export an agreement for a counterparty, read back what they changed.
 *
 * Replaces the simulated-conversion mockup. Both halves hit real endpoints:
 *   GET  /contracts/{id}/export.docx   the editable document, clause numbering intact
 *   POST /contracts/{id}/import.docx   the returned document, parsed for tracked changes
 *
 * The import is a two-step on purpose: applying it overwrites the contract body, files the
 * counterparty's comments, and classifies the agreement non-standard. That is a lot to happen
 * behind one button, so you see exactly what it will do first.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Download,
  FileText,
  MessageSquare,
  Minus,
  Plus,
  Upload,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorBanner,
  Select,
  Skeleton,
} from "@/components/ui";
import type { ContractListItem, DocxImportResult, Paginated } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DocxStudioPage() {
  const [contracts, setContracts] = useState<ContractListItem[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [preview, setPreview] = useState<DocxImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  useEffect(() => {
    api
      .get<Paginated<ContractListItem>>("/contracts?page_size=100")
      .then((r) => {
        setContracts(r.items);
        if (r.items.length) setSelectedId(r.items[0].id);
      })
      .catch(() => setContracts([]));
  }, []);

  const upload = useCallback(
    async (file: File, apply: boolean) => {
      if (!selectedId) return;
      setBusy(true);
      setError("");
      try {
        const form = new FormData();
        form.append("file", file);
        form.append("apply", apply ? "true" : "false");
        const result = await api.postForm<DocxImportResult>(
          `/contracts/${selectedId}/import.docx`,
          form,
        );
        setPreview(result);
        setApplied(result.applied);
        if (result.applied) setPendingFile(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "That file could not be read.");
      } finally {
        setBusy(false);
      }
    },
    [selectedId],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Word round-trip"
        subtitle="Send an editable agreement out; read back the counterparty's tracked changes and comments"
      />

      {error && <ErrorBanner message={error} />}

      {contracts === null ? (
        <Skeleton className="h-24 w-full" />
      ) : contracts.length === 0 ? (
        <Card>
          <CardBody className="py-10 text-center text-sm text-ink-2">
            No agreements yet. Create one first.
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardBody className="flex flex-wrap items-end gap-3">
              <div className="min-w-[240px] flex-1">
                <label className="mb-1 block text-xs font-medium text-ink-2">Agreement</label>
                <Select
                  value={selectedId}
                  onChange={(e) => {
                    setSelectedId(e.target.value);
                    setPreview(null);
                    setApplied(false);
                    setPendingFile(null);
                  }}
                >
                  {contracts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.reference_no} — {c.title}
                    </option>
                  ))}
                </Select>
              </div>
              <a
                href={`${API}/contracts/${selectedId}/export.docx`}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-white transition hover:opacity-90"
              >
                <Download className="h-4 w-4" /> Export .docx
              </a>
            </CardBody>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <FileText className="h-4 w-4" /> Send out
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-2 text-sm text-ink-2">
                <p>
                  The export is a real working draft. Clause numbers are Word numbering, not typed
                  digits — so if the counterparty inserts a clause, everything below it renumbers
                  correctly instead of silently going wrong.
                </p>
                <p>Headings, tables and the reference in the page header all survive the trip.</p>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Upload className="h-4 w-4" /> Read back
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-3">
                <p className="text-sm text-ink-2">
                  Upload the returned document. You will see its tracked changes and comments
                  before anything is applied.
                </p>
                <input
                  type="file"
                  accept=".docx"
                  className="block w-full text-sm text-ink-2 file:mr-3 file:rounded-md file:border-0 file:bg-surface-3 file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-surface-2"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    setPendingFile(file);
                    setApplied(false);
                    void upload(file, false);
                  }}
                />
                {busy && <p className="text-sm text-ink-3">Reading…</p>}
              </CardBody>
            </Card>
          </div>

          {preview && (
            <ImportPreview
              result={preview}
              applied={applied}
              busy={busy}
              onApply={() => pendingFile && upload(pendingFile, true)}
            />
          )}
        </>
      )}
    </div>
  );
}

function ImportPreview({
  result,
  applied,
  busy,
  onApply,
}: {
  result: DocxImportResult;
  applied: boolean;
  busy: boolean;
  onApply: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Insertions" value={result.insertions} icon={Plus} tone="text-accent" />
        <Stat label="Deletions" value={result.deletions} icon={Minus} tone="text-red-600" />
        <Stat label="Comments" value={result.comment_count} icon={MessageSquare} />
        <Stat label="Paragraphs" value={result.paragraphs} icon={FileText} />
      </div>

      {result.warnings.length > 0 && (
        <Card className="border-amber-300/60 bg-amber-50/50 dark:bg-amber-950/20">
          <CardBody className="space-y-1 py-3">
            {result.warnings.map((w) => (
              <div key={w} className="flex items-start gap-2 text-sm text-ink-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <span>{w}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {result.changes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Tracked changes</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {result.changes.map((c, i) => (
              <div key={i} className="rounded-md border border-line p-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={c.kind === "insert" ? "accent" : "neutral"}>
                    {c.kind === "insert" ? "inserted" : "deleted"}
                  </Badge>
                  <span className="text-xs text-ink-2">
                    {c.author || "Unknown"}
                    {c.at && ` · ${new Date(c.at).toLocaleDateString()}`}
                  </span>
                </div>
                <p
                  className={`mt-1 font-mono text-xs ${
                    c.kind === "insert" ? "text-accent" : "text-red-600 line-through"
                  }`}
                >
                  {c.text}
                </p>
                {c.context && <p className="mt-1 text-xs text-ink-3">in: {c.context}</p>}
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {result.comments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Comments</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {result.comments.map((c) => (
              <div key={c.comment_id} className="rounded-md border border-line p-2 text-sm">
                <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
                  <span className="font-medium text-ink">{c.author || "Unknown"}</span>
                  {c.at && <span>{new Date(c.at).toLocaleDateString()}</span>}
                </div>
                <p className="mt-1 text-ink">{c.text}</p>
                {c.anchor_text && (
                  <p className="mt-1 text-xs text-ink-3">on: “{c.anchor_text.slice(0, 160)}”</p>
                )}
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardBody className="space-y-3">
          {applied ? (
            <div className="flex items-center gap-2 text-sm text-accent">
              <Check className="h-4 w-4" />
              Imported. Version {result.version_no} saved with the previous wording
              {result.classified_non_standard && ", and the agreement is now Non-Standard"}.
            </div>
          ) : (
            <>
              <p className="text-sm text-ink-2">
                Applying this replaces the agreement text, saves the current wording as a new
                version, files the counterparty&rsquo;s comments
                {result.has_revisions && ", and classifies the agreement Non-Standard so it takes the non-standard approval route"}.
              </p>
              <Button onClick={onApply} disabled={busy}>
                {busy ? "Applying…" : "Apply to the agreement"}
                {!busy && <ArrowRight className="h-4 w-4" />}
              </Button>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: typeof FileText;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className={`flex items-center gap-1.5 font-display text-2xl font-semibold ${tone ?? "text-ink"}`}>
        <Icon className="h-4 w-4" />
        {value}
      </div>
      <div className="text-xs text-ink-2">{label}</div>
    </div>
  );
}
