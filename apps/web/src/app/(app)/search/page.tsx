"use client";

/**
 * Repository search — full text across title, counterparty, body and summary, plus the
 * structured filters a contract manager actually reaches for.
 *
 *   POST /search   free text + filters; returns hits with snippets and facet counts
 *
 * POST rather than GET because the filter set is a nested object (date ranges, value bands,
 * tag lists). Facets are counted over the whole result set, not the page on screen.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Download, Filter, Printer, Search as SearchIcon, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  ErrorBanner,
  Field,
  Input,
  Select,
  Skeleton,
} from "@/components/ui";
import { contractTypeLabel, formatDate, formatMoney, titleCase, CONTRACT_TYPES } from "@/lib/utils";
import type { Department, Folder, SearchResult } from "@/lib/types";

const STATUSES = [
  "draft", "in_review", "approved", "out_for_signature", "signed", "active",
  "expiring", "expired", "terminated", "renewed",
];
const RISKS = ["low", "medium", "high", "critical"];

type Filters = {
  status: string[];
  type: string[];
  risk_level: string[];
  department_id: string;
  folder_path: string;
  counterparty: string;
  effective_from: string;
  effective_to: string;
  end_from: string;
  end_to: string;
  value_min: string;
  value_max: string;
  include_archived: boolean;
};

const EMPTY: Filters = {
  status: [], type: [], risk_level: [], department_id: "", folder_path: "",
  counterparty: "", effective_from: "", effective_to: "", end_from: "", end_to: "",
  value_min: "", value_max: "", include_archived: false,
};

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [page, setPage] = useState(1);
  const [showFilters, setShowFilters] = useState(false);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Department[]>("/departments").then(setDepartments).catch(() => setDepartments([]));
    api.get<Folder[]>("/folders").then(setFolders).catch(() => setFolders([]));
  }, []);

  const run = useCallback(
    async (targetPage = 1) => {
      setBusy(true);
      setError("");
      try {
        setResult(
          await api.post<SearchResult>("/search", {
            q,
            ...filters,
            value_min: filters.value_min ? Number(filters.value_min) : null,
            value_max: filters.value_max ? Number(filters.value_max) : null,
            effective_from: filters.effective_from || null,
            effective_to: filters.effective_to || null,
            end_from: filters.end_from || null,
            end_to: filters.end_to || null,
            page: targetPage,
            page_size: 25,
          }),
        );
        setPage(targetPage);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "That search could not be run.");
      } finally {
        setBusy(false);
      }
    },
    [q, filters],
  );

  useEffect(() => {
    void run(1);
    // Runs once on mount to show the repository; subsequent searches are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Export exactly what is on screen: the same filters, as a spreadsheet. */
  async function exportResults() {
    setExporting(true);
    setError("");
    try {
      const job = await api.post<{ id: string; href: string }>("/exports", {
        kind: "contracts",
        filters: { q, ...filters },
      });
      window.location.href = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${job.href}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The export could not be generated.");
    } finally {
      setExporting(false);
    }
  }

  function toggle(key: "status" | "type" | "risk_level", value: string) {
    setFilters((f) => ({
      ...f,
      [key]: f[key].includes(value) ? f[key].filter((v) => v !== value) : [...f[key], value],
    }));
  }

  const activeCount =
    filters.status.length +
    filters.type.length +
    filters.risk_level.length +
    (filters.department_id ? 1 : 0) +
    (filters.folder_path ? 1 : 0) +
    (filters.counterparty ? 1 : 0) +
    (filters.effective_from || filters.effective_to ? 1 : 0) +
    (filters.end_from || filters.end_to ? 1 : 0) +
    (filters.value_min || filters.value_max ? 1 : 0);

  return (
    <div>
      <PageHeader
        title="Search"
        subtitle="Everything in the repository — text, parties, dates, values, folders"
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        <Card>
          <CardBody className="space-y-3">
            <form
              className="flex flex-wrap gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void run(1);
              }}
            >
              <div className="relative min-w-[240px] flex-1">
                <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Words in the agreement, a party, a reference number…"
                  className="pl-8"
                />
              </div>
              <Button type="submit" loading={busy}>
                Search
              </Button>
              <Button
                type="button"
                variant="ghost"
                loading={exporting}
                disabled={!result || result.total === 0}
                onClick={exportResults}
                title="Download these results as a spreadsheet"
              >
                <Download className="h-3.5 w-3.5" /> Export
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="print-keep"
                onClick={() => window.print()}
                title="Print these results"
              >
                <Printer className="h-3.5 w-3.5" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowFilters((v) => !v)}
              >
                <Filter className="h-3.5 w-3.5" /> Filters
                {activeCount > 0 && <Badge tone="accent">{activeCount}</Badge>}
              </Button>
              {activeCount > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setFilters(EMPTY);
                    void run(1);
                  }}
                >
                  <X className="h-3.5 w-3.5" /> Clear
                </Button>
              )}
            </form>

            {showFilters && (
              <div className="space-y-3 border-t border-line pt-3">
                <ChipRow
                  label="Status"
                  values={STATUSES}
                  selected={filters.status}
                  counts={result?.facets?.status}
                  onToggle={(v) => toggle("status", v)}
                />
                <ChipRow
                  label="Type"
                  values={CONTRACT_TYPES.map((t) => t.value)}
                  labels={Object.fromEntries(CONTRACT_TYPES.map((t) => [t.value, t.label]))}
                  selected={filters.type}
                  counts={result?.facets?.type}
                  onToggle={(v) => toggle("type", v)}
                />
                <ChipRow
                  label="Risk"
                  values={RISKS}
                  selected={filters.risk_level}
                  counts={result?.facets?.risk_level}
                  onToggle={(v) => toggle("risk_level", v)}
                />

                <div className="grid gap-3 sm:grid-cols-4">
                  <Field label="Counterparty">
                    <Input
                      value={filters.counterparty}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, counterparty: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Department">
                    <Select
                      value={filters.department_id}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, department_id: e.target.value }))
                      }
                    >
                      <option value="">Any</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Folder" hint="Includes everything beneath it">
                    <Select
                      value={filters.folder_path}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, folder_path: e.target.value }))
                      }
                    >
                      <option value="">Anywhere</option>
                      {folders.map((f) => (
                        <option key={f.id} value={f.path}>
                          {f.path}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <div className="flex items-end pb-2">
                    <label className="inline-flex items-center gap-2 text-sm text-ink-2">
                      <input
                        type="checkbox"
                        checked={filters.include_archived}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, include_archived: e.target.checked }))
                        }
                      />
                      Include archived
                    </label>
                  </div>

                  <Field label="Effective from">
                    <Input
                      type="date"
                      value={filters.effective_from}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, effective_from: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Effective to">
                    <Input
                      type="date"
                      value={filters.effective_to}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, effective_to: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Expires from">
                    <Input
                      type="date"
                      value={filters.end_from}
                      onChange={(e) => setFilters((f) => ({ ...f, end_from: e.target.value }))}
                    />
                  </Field>
                  <Field label="Expires to">
                    <Input
                      type="date"
                      value={filters.end_to}
                      onChange={(e) => setFilters((f) => ({ ...f, end_to: e.target.value }))}
                    />
                  </Field>

                  <Field label="Value at least">
                    <Input
                      type="number"
                      min={0}
                      value={filters.value_min}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, value_min: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Value at most">
                    <Input
                      type="number"
                      min={0}
                      value={filters.value_max}
                      onChange={(e) =>
                        setFilters((f) => ({ ...f, value_max: e.target.value }))
                      }
                    />
                  </Field>
                </div>

                <Button size="sm" onClick={() => run(1)} loading={busy}>
                  Apply filters
                </Button>
              </div>
            )}
          </CardBody>
        </Card>

        {result === null && busy && <Skeleton className="h-40" />}

        {result && (
          <>
            <p className="text-sm text-ink-2">
              {result.total === 0
                ? "Nothing matches."
                : `${result.total} agreement${result.total === 1 ? "" : "s"}`}
            </p>

            <div className="space-y-2">
              {result.items.map((hit) => (
                <Card key={hit.id}>
                  <CardBody className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/contracts/${hit.id}`}
                        className="text-sm font-semibold text-ink hover:text-accent"
                      >
                        {hit.title}
                      </Link>
                      <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3">
                        {hit.reference_no}
                      </span>
                      <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] uppercase text-ink-3">
                        {contractTypeLabel(hit.type)}
                      </span>
                      <Badge tone={hit.status === "active" ? "accent" : "neutral"}>
                        {titleCase(hit.status.replace(/_/g, " "))}
                      </Badge>
                    </div>
                    {hit.snippet && <Snippet text={hit.snippet} />}
                    <div className="text-[11px] text-ink-3">
                      {hit.counterparty || "no counterparty"} ·{" "}
                      {formatMoney(hit.value, hit.currency)} ·{" "}
                      {hit.effective_date ? formatDate(hit.effective_date) : "no start date"}
                      {hit.end_date && ` → ${formatDate(hit.end_date)}`}
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>

            {result.total > result.page_size && (
              <div className="flex items-center justify-between">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={page <= 1 || busy}
                  onClick={() => run(page - 1)}
                >
                  Previous
                </Button>
                <span className="text-xs text-ink-3">
                  Page {page} of {Math.ceil(result.total / result.page_size)}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={page * result.page_size >= result.total || busy}
                  onClick={() => run(page + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Renders the `**term**` markers the server puts around query hits. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <p className="text-xs text-ink-2">
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <mark key={i} className="rounded bg-accent-subtle px-0.5 text-accent">
            {part.slice(2, -2)}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  );
}

function ChipRow({
  label,
  values,
  labels,
  selected,
  counts,
  onToggle,
}: {
  label: string;
  values: string[];
  labels?: Record<string, string>;
  selected: string[];
  counts?: Record<string, number>;
  onToggle: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-16 text-xs font-medium text-ink-2">{label}</span>
      {values.map((v) => {
        const count = counts?.[v];
        return (
          <button
            key={v}
            type="button"
            onClick={() => onToggle(v)}
            className={`rounded-full px-2 py-0.5 text-[11px] transition ${
              selected.includes(v)
                ? "bg-accent text-white"
                : "bg-surface-3 text-ink-2 hover:text-ink"
            }`}
          >
            {labels?.[v] ?? titleCase(v.replace(/_/g, " "))}
            {count !== undefined && count > 0 && ` ${count}`}
          </button>
        );
      })}
    </div>
  );
}
