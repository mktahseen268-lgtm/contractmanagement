"use client";

/**
 * Redline — compare two versions of an agreement and decide change by change what survives.
 *
 * Replaces the in-memory prototype. Every change here is computed server-side and every
 * decision is persisted:
 *   GET  /contracts/{id}/redline?base=&compare=   word-level diff
 *   POST /contracts/{id}/redline/apply            accepted changes → a new version
 *   POST /contracts/{id}/redline/comment          a thread anchored to one change
 *
 * Nothing is applied until "Apply" — accepting a change here only marks it, because applying
 * rewrites the agreement text and that deserves one deliberate action rather than a dozen
 * accidental ones.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  FileText,
  MessageSquare,
  Minus,
  Plus,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  ErrorBanner,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui";
import type {
  ContractListItem,
  Paginated,
  Redline,
  RedlineChange,
  Version,
} from "@/lib/types";

const LIVE = "current";

export default function RedlinePage() {
  const [contracts, setContracts] = useState<ContractListItem[] | null>(null);
  const [contractId, setContractId] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [base, setBase] = useState<string>("");
  const [compare, setCompare] = useState<string>(LIVE);
  const [redline, setRedline] = useState<Redline | null>(null);
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState("");

  useEffect(() => {
    api
      .get<Paginated<ContractListItem>>("/contracts?page_size=100")
      .then((r) => {
        setContracts(r.items);
        if (r.items.length) setContractId(r.items[0].id);
      })
      .catch(() => setContracts([]));
  }, []);

  useEffect(() => {
    if (!contractId) return;
    setRedline(null);
    setAccepted(new Set());
    setApplied("");
    api
      .get<Version[]>(`/contracts/${contractId}/versions`)
      .then((rows) => {
        setVersions(rows);
        setBase(rows.length ? String(rows[0].version_no) : "");
        setCompare(LIVE);
      })
      .catch(() => setVersions([]));
  }, [contractId]);

  const load = useCallback(async () => {
    if (!contractId || !base) return;
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("base", base);
      if (compare !== LIVE) params.set("compare", compare);
      setRedline(await api.get<Redline>(`/contracts/${contractId}/redline?${params}`));
      setAccepted(new Set());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That comparison could not be made.");
      setRedline(null);
    } finally {
      setBusy(false);
    }
  }, [contractId, base, compare]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggle(index: number) {
    setAccepted((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  async function applyChanges() {
    if (!redline) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/contracts/${contractId}/redline/apply`, {
        base_version_no: redline.base_version_no,
        compare_version_no: redline.compare_version_no,
        accept: Array.from(accepted),
      });
      setApplied(
        `Applied. ${accepted.size} of ${redline.change_count} change${
          redline.change_count === 1 ? "" : "s"
        } accepted; the previous wording is saved as a version.`,
      );
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The changes could not be applied.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Redline"
        subtitle="Compare two versions and decide, change by change, what survives"
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
              <CardBody className="grid gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink-2">Agreement</label>
                  <Select value={contractId} onChange={(e) => setContractId(e.target.value)}>
                    {contracts.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.reference_no} — {c.title}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink-2">From</label>
                  <Select value={base} onChange={(e) => setBase(e.target.value)}>
                    {versions.length === 0 && <option value="">No saved versions</option>}
                    {versions.map((v) => (
                      <option key={v.id} value={v.version_no}>
                        v{v.version_no} — {v.change_summary || "no summary"}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink-2">To</label>
                  <Select value={compare} onChange={(e) => setCompare(e.target.value)}>
                    <option value={LIVE}>Current draft</option>
                    {versions.map((v) => (
                      <option key={v.id} value={v.version_no}>
                        v{v.version_no}
                      </option>
                    ))}
                  </Select>
                </div>
              </CardBody>
            </Card>

            {applied && (
              <Card className="border-emerald-300/60">
                <CardBody className="flex items-center gap-2 py-3 text-sm text-ink">
                  <Check className="h-4 w-4 text-emerald-600" />
                  {applied}
                </CardBody>
              </Card>
            )}

            {busy && !redline && <Skeleton className="h-32" />}

            {redline && redline.identical && (
              <Card>
                <CardBody className="py-10 text-center text-sm text-ink-2">
                  <FileText className="mx-auto mb-3 h-10 w-10 text-ink-3" />
                  <div className="text-base font-semibold text-ink">No differences</div>
                  <p className="mt-1">
                    {redline.base_label} and {redline.compare_label} are word for word the same.
                  </p>
                </CardBody>
              </Card>
            )}

            {redline && !redline.identical && (
              <>
                <div className="grid gap-3 sm:grid-cols-4">
                  <Stat label="Changes" value={redline.change_count} icon={FileText} />
                  <Stat label="Words added" value={redline.added} icon={Plus} tone="text-accent" />
                  <Stat
                    label="Words removed"
                    value={redline.removed}
                    icon={Minus}
                    tone="text-red-600"
                  />
                  <Stat label="Accepted" value={accepted.size} icon={Check} />
                </div>

                <Card>
                  <CardBody className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-ink-2">
                      Comparing <strong>{redline.base_label}</strong> to{" "}
                      <strong>{redline.compare_label}</strong>. Anything not accepted keeps the
                      wording it had in {redline.base_label}.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setAccepted(new Set(redline.changes.map((c) => c.index)))
                        }
                      >
                        Accept all
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setAccepted(new Set())}>
                        Reject all
                      </Button>
                      <Button size="sm" loading={busy} onClick={applyChanges}>
                        Apply <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardBody>
                </Card>

                <div className="space-y-3">
                  {redline.changes.map((c) => (
                    <ChangeCard
                      key={c.index}
                      change={c}
                      contractId={contractId}
                      accepted={accepted.has(c.index)}
                      onToggle={() => toggle(c.index)}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ChangeCard({
  change,
  contractId,
  accepted,
  onToggle,
}: {
  change: RedlineChange;
  contractId: string;
  accepted: boolean;
  onToggle: () => void;
}) {
  const [commenting, setCommenting] = useState(false);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const label = useMemo(() => {
    if (change.kind === "insert") return "Added";
    if (change.kind === "delete") return "Removed";
    return "Reworded";
  }, [change.kind]);

  async function comment() {
    setBusy(true);
    setErr("");
    try {
      await api.post(`/contracts/${contractId}/redline/comment`, {
        body: note.trim(),
        anchor_start: change.anchor_start,
        anchor_end: change.anchor_end,
        internal_only: true,
      });
      setSaved(true);
      setCommenting(false);
      setNote("");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "The comment could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className={accepted ? "border-accent/50" : ""}>
      <CardBody className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={change.kind === "delete" ? "neutral" : "accent"}>{label}</Badge>
          {accepted ? (
            <span className="inline-flex items-center gap-1 text-xs text-accent">
              <Check className="h-3 w-3" /> will be applied
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-ink-3">
              <X className="h-3 w-3" /> keeping the earlier wording
            </span>
          )}
          {saved && (
            <span className="inline-flex items-center gap-1 text-xs text-ink-3">
              <MessageSquare className="h-3 w-3" /> comment filed
            </span>
          )}
        </div>

        {change.before_context && (
          <p className="truncate text-xs text-ink-3">…{change.before_context}</p>
        )}

        <div className="space-y-1 font-mono text-xs">
          {change.before && (
            <p className="rounded bg-red-50 px-2 py-1 text-red-700 line-through dark:bg-red-950/30">
              {change.before}
            </p>
          )}
          {change.after && (
            <p className="rounded bg-emerald-50 px-2 py-1 text-emerald-800 dark:bg-emerald-950/30">
              {change.after}
            </p>
          )}
        </div>

        {change.after_context && (
          <p className="truncate text-xs text-ink-3">{change.after_context}…</p>
        )}

        {err && <ErrorBanner message={err} />}

        {commenting ? (
          <div className="space-y-2">
            <Textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Why this needs discussion…"
            />
            <div className="flex gap-2">
              <Button size="sm" loading={busy} disabled={!note.trim()} onClick={comment}>
                File comment
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setCommenting(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={accepted ? "ghost" : "primary"} onClick={onToggle}>
              {accepted ? (
                <>
                  <X className="h-3.5 w-3.5" /> Reject
                </>
              ) : (
                <>
                  <Check className="h-3.5 w-3.5" /> Accept
                </>
              )}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCommenting(true)}>
              <MessageSquare className="h-3.5 w-3.5" /> Comment
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
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
      <div
        className={`flex items-center gap-1.5 font-display text-2xl font-semibold ${
          tone ?? "text-ink"
        }`}
      >
        <Icon className="h-4 w-4" />
        {value}
      </div>
      <div className="text-xs text-ink-2">{label}</div>
    </div>
  );
}
