"use client";

/**
 * AI assist — clause suggestions and document data capture.
 *
 * Replaces the simulated-analysis mockup. Two halves, and they work differently on purpose:
 *
 *   GET  /contracts/{id}/ai/suggestions   clause suggestions — deterministic, grounded in the
 *                                         library and the playbook, every entry cites why
 *   POST /contracts/{id}/ai/capture       extract metadata from a document, FOR CONFIRMATION
 *   POST /contracts/{id}/ai/captures/{r}/apply   writes only the fields a person ticked
 *
 * Nothing extracted is ever written automatically. A confidence score is not a fact; it is a
 * reason to look. The provider is shown because `stub` means the document was not read at all.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  FileSearch,
  Lightbulb,
  Sparkles,
  Upload,
  X,
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
import type {
  ClauseSuggestion,
  ContractListItem,
  ExtractionReview,
  Paginated,
} from "@/lib/types";

const RISK_TONE: Record<string, string> = {
  low: "text-emerald-700",
  medium: "text-amber-700",
  high: "text-orange-700",
  critical: "text-red-700",
};

const BASIS_LABEL: Record<string, string> = {
  policy: "Required by policy",
  peers: "Used by comparable agreements",
  risk: "High-risk clause not present",
};

export default function AiAnalysisPage() {
  const [contracts, setContracts] = useState<ContractListItem[] | null>(null);
  const [contractId, setContractId] = useState("");
  const [suggestions, setSuggestions] = useState<ClauseSuggestion[] | null>(null);
  const [captures, setCaptures] = useState<ExtractionReview[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<Paginated<ContractListItem>>("/contracts?page_size=100")
      .then((r) => {
        setContracts(r.items);
        if (r.items.length) setContractId(r.items[0].id);
      })
      .catch(() => setContracts([]));
  }, []);

  const load = useCallback(() => {
    if (!contractId) return;
    setSuggestions(null);
    api
      .get<ClauseSuggestion[]>(`/contracts/${contractId}/ai/suggestions`)
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
    api
      .get<ExtractionReview[]>(`/contracts/${contractId}/ai/captures`)
      .then(setCaptures)
      .catch(() => setCaptures([]));
  }, [contractId]);
  useEffect(load, [load]);

  async function upload(file: File) {
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      await api.postForm<ExtractionReview>(`/contracts/${contractId}/ai/capture`, form);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That document could not be read.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="AI assist"
        subtitle="Clause suggestions from your own library, and document capture you confirm before anything is written"
      />

      <div className="space-y-5 p-6">
        {error && <ErrorBanner message={error} />}

        {contracts === null ? (
          <Skeleton className="h-24" />
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
                <div className="min-w-[260px] flex-1">
                  <label className="mb-1 block text-xs font-medium text-ink-2">Agreement</label>
                  <Select value={contractId} onChange={(e) => setContractId(e.target.value)}>
                    {contracts.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.reference_no} — {c.title}
                      </option>
                    ))}
                  </Select>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Lightbulb className="h-4 w-4 text-accent" /> Clause suggestions
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-2">
                <p className="text-xs text-ink-3">
                  Grounded in your clause library and playbooks, not generated — every
                  suggestion says what it is based on, and the same draft always gives the same
                  list.
                </p>
                {suggestions === null && <Skeleton className="h-20" />}
                {suggestions?.length === 0 && (
                  <p className="py-4 text-sm text-ink-2">
                    Nothing to suggest — this draft already carries the clauses your library and
                    policy would add.
                  </p>
                )}
                {suggestions?.map((s) => (
                  <div key={s.key} className="rounded-md border border-line p-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-ink">{s.title}</span>
                      <Badge tone={s.basis === "policy" ? "accent" : "neutral"}>
                        {BASIS_LABEL[s.basis] ?? s.basis}
                      </Badge>
                      <span className={`text-xs font-medium ${RISK_TONE[s.risk_level] ?? "text-ink-3"}`}>
                        {s.risk_level} risk
                      </span>
                      {s.severity === "blocker" && (
                        <span className="inline-flex items-center gap-1 text-xs text-red-700">
                          <AlertTriangle className="h-3 w-3" /> blocking
                        </span>
                      )}
                      <code className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] text-ink-3">
                        [[clause:{s.key}]]
                      </code>
                    </div>
                    <p className="mt-1 text-xs text-ink-2">{s.reason}</p>
                    {s.body && <p className="mt-1 line-clamp-2 text-xs text-ink-3">{s.body}</p>}
                  </div>
                ))}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <FileSearch className="h-4 w-4" /> Capture from a document
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-3">
                <p className="text-sm text-ink-2">
                  Upload a signed or scanned agreement. Fields are extracted{" "}
                  <strong>for your confirmation</strong> — nothing is written to the agreement
                  until you tick it.
                </p>
                <input
                  type="file"
                  className="block w-full text-sm text-ink-2 file:mr-3 file:rounded-md file:border-0 file:bg-surface-3 file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-surface-2"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                  }}
                />
                {busy && (
                  <p className="flex items-center gap-1.5 text-sm text-ink-3">
                    <Upload className="h-4 w-4" /> Reading…
                  </p>
                )}
              </CardBody>
            </Card>

            {captures.map((c) => (
              <CaptureCard
                key={c.id}
                capture={c}
                contractId={contractId}
                onChanged={load}
                onError={setError}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function CaptureCard({
  capture,
  contractId,
  onChanged,
  onError,
}: {
  capture: ExtractionReview;
  contractId: string;
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const [accepted, setAccepted] = useState<Set<string>>(
    () => new Set(capture.fields.filter((f) => f.suggested).map((f) => f.field)),
  );
  const [busy, setBusy] = useState(false);
  const pending = capture.status === "pending";

  async function act(path: string, body?: unknown) {
    setBusy(true);
    onError("");
    try {
      await api.post(`/contracts/${contractId}/ai/captures/${capture.id}/${path}`, body ?? {});
      onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" />
          {capture.file_name}
          <Badge tone={pending ? "accent" : "neutral"}>{capture.status}</Badge>
          {capture.provider === "stub" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-800">
              <AlertTriangle className="h-3 w-3" /> demo provider — the document was not read
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        {capture.summary && <p className="text-sm text-ink-2">{capture.summary}</p>}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-3">
                <th className="py-1 pr-3">Accept</th>
                <th className="py-1 pr-3">Field</th>
                <th className="py-1 pr-3">Found</th>
                <th className="py-1 pr-3">Currently</th>
                <th className="py-1">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {capture.fields.map((f) => (
                <tr key={f.field} className="border-t border-line">
                  <td className="py-1.5 pr-3">
                    <input
                      type="checkbox"
                      disabled={!pending || !f.changes}
                      checked={accepted.has(f.field)}
                      onChange={() =>
                        setAccepted((prev) => {
                          const next = new Set(prev);
                          if (next.has(f.field)) next.delete(f.field);
                          else next.add(f.field);
                          return next;
                        })
                      }
                    />
                  </td>
                  <td className="py-1.5 pr-3 text-ink">{f.field.replace(/_/g, " ")}</td>
                  <td className="py-1.5 pr-3 text-ink">{f.value || "—"}</td>
                  <td className="py-1.5 pr-3 text-ink-3">
                    {f.changes ? f.current || "(empty)" : "same"}
                  </td>
                  <td className="py-1.5 text-ink-3">{Math.round(f.confidence * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {pending ? (
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              loading={busy}
              onClick={() => act("apply", { accept: Array.from(accepted) })}
            >
              <Check className="h-3.5 w-3.5" /> Apply {accepted.size} field
              {accepted.size === 1 ? "" : "s"}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("discard")}>
              <X className="h-3.5 w-3.5" /> Discard
            </Button>
          </div>
        ) : (
          <p className="text-xs text-ink-3">
            {capture.applied_fields.length > 0
              ? `Applied: ${capture.applied_fields.join(", ")}.`
              : "Discarded — nothing was written."}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
