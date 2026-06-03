"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarClock, Calendar, FileCheck2, FilePlus2, FileText, FileSpreadsheet, Filter, Gauge, ListChecks, PenLine, TrendingUp, Wallet, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Input, Select, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { AreaChart } from "@/components/charts";
import { KpiCard } from "@/components/widgets";
import { CONTRACT_TYPES, RISK_META, STATUS_META, contractTypeLabel, downloadBlob, formatDate, formatMoney, statusMeta, titleCase } from "@/lib/utils";
import type { ReportSummary, StuckItem, User } from "@/lib/types";

type ReportFilters = {
  type: string; status: string; risk: string; department: string;
  owner: string; counterparty: string; value_min: string; value_max: string;
  q: string; renewal_type: string; currency: string; tag: string;
  effective_from: string; effective_to: string; end_from: string; end_to: string;
};
const EMPTY_FILTERS: ReportFilters = {
  type: "", status: "", risk: "", department: "", owner: "", counterparty: "", value_min: "", value_max: "",
  q: "", renewal_type: "", currency: "", tag: "", effective_from: "", effective_to: "", end_from: "", end_to: "",
};
function filterQuery(f: ReportFilters): string {
  const p = new URLSearchParams();
  (Object.keys(f) as (keyof ReportFilters)[]).forEach((k) => {
    const v = f[k].trim();
    if (v) p.set(k, v);
  });
  const s = p.toString();
  return s ? `&${s}` : "";
}
function activeFilterCount(f: ReportFilters): number {
  return (Object.keys(f) as (keyof ReportFilters)[]).filter((k) => f[k].trim()).length;
}

type Preset = { label: string; days: number };
const PRESETS: Preset[] = [
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "6 months", days: 180 },
  { label: "12 months", days: 365 },
];

function toIso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function defaultRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date(to);
  from.setDate(from.getDate() - 90);
  return { from: toIso(from), to: toIso(to) };
}

export default function ReportsPage() {
  const { me } = useAuth();
  const currency = me?.tenant.currency;
  const [range, setRange] = useState<{ from: string; to: string }>(defaultRange);
  const [data, setData] = useState<ReportSummary | null>(null);
  const [stuck, setStuck] = useState<StuckItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [csvBusy, setCsvBusy] = useState(false);
  const [error, setError] = useState("");
  // Detail filters. `filters` is the applied set the report reads; `draft` is what the bar edits
  // until you hit Apply, so changing a dropdown doesn't refetch on every keystroke.
  const [filters, setFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<ReportFilters>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [owners, setOwners] = useState<User[]>([]);
  const [deptOptions, setDeptOptions] = useState<string[]>([]);
  const activeCount = activeFilterCount(filters);

  // owner options for the filter dropdown (best-effort; non-admins may get 403 → ignore)
  useEffect(() => {
    api.get<User[]>("/users").then(setOwners).catch(() => setOwners([]));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    const fq = filterQuery(filters);
    api
      .get<ReportSummary>(`/reports/summary?from=${range.from}&to=${range.to}${fq}`)
      .then((d) => {
        setData(d);
        // capture department options from an unfiltered load so the dropdown stays complete
        if (activeFilterCount(filters) === 0) {
          setDeptOptions(d.by_department.map((b) => b.label).filter((x) => x && x !== "Unassigned"));
        }
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load the report."))
      .finally(() => setLoading(false));
    api.get<StuckItem[]>("/reports/stuck?limit=10").then(setStuck).catch(() => setStuck([]));
  }, [range.from, range.to, filters]);
  useEffect(load, [load]);

  function applyPreset(days: number) {
    const to = new Date();
    const from = new Date(to);
    from.setDate(from.getDate() - days);
    setRange({ from: toIso(from), to: toIso(to) });
  }

  function applyFilters() {
    setFilters(draft);
  }
  function clearFilters() {
    setDraft(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
  }

  async function exportCsv() {
    setCsvBusy(true);
    try {
      const blob = await api.blob(`/reports/contracts.csv?from=${range.from}&to=${range.to}${filterQuery(filters)}`);
      downloadBlob(blob, `contracts_${range.from}_to_${range.to}.csv`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't export the CSV.");
    } finally {
      setCsvBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Portfolio analytics — distributions, cycle time, expiring & renewal pipeline, approver throughput."
        actions={
          <div className="flex items-center gap-2">
            <Button variant={showFilters || activeCount ? "primary" : "secondary"} size="sm" onClick={() => setShowFilters((s) => !s)}>
              <Filter className="h-3.5 w-3.5" /> Filters{activeCount ? ` · ${activeCount}` : ""}
            </Button>
            <Button variant="secondary" size="sm" onClick={exportCsv} loading={csvBusy}>
              <FileSpreadsheet className="h-3.5 w-3.5" /> Export CSV
            </Button>
          </div>
        }
      />

      <div className="space-y-6 p-6">
        {/* Range picker */}
        <Card>
          <CardBody className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">From</label>
              <input
                type="date"
                value={range.from}
                onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))}
                className="h-10 rounded-sm border border-line bg-white px-3 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">To</label>
              <input
                type="date"
                value={range.to}
                onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))}
                className="h-10 rounded-sm border border-line bg-white px-3 text-sm"
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.days}
                  onClick={() => applyPreset(p.days)}
                  className="rounded-full border border-line bg-white px-3 py-1.5 text-xs font-medium text-ink-2 hover:border-accent hover:text-accent"
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-1.5 text-xs text-ink-3">
              <Calendar className="h-3.5 w-3.5" />
              {data ? `${formatDate(data.range_from)} → ${formatDate(data.range_to)}` : ""}
            </div>
          </CardBody>
        </Card>

        {/* Detail filters */}
        {showFilters && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Filter className="h-4 w-4" /> Filter the report
              </CardTitle>
              {activeCount > 0 && (
                <button onClick={clearFilters} className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-danger">
                  <X className="h-3 w-3" /> Clear all
                </button>
              )}
            </CardHeader>
            <CardBody className="space-y-3">
              <FilterField label="Search (title or reference)">
                <Input value={draft.q} onChange={(e) => setDraft((d) => ({ ...d, q: e.target.value }))} placeholder="e.g. Northwind or C-2026-0012" />
              </FilterField>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <FilterField label="Type">
                  <Select value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))}>
                    <option value="">Any type</option>
                    {CONTRACT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </Select>
                </FilterField>
                <FilterField label="Status">
                  <Select value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}>
                    <option value="">Any status</option>
                    {Object.keys(STATUS_META).map((s) => <option key={s} value={s}>{statusMeta(s).label}</option>)}
                  </Select>
                </FilterField>
                <FilterField label="Risk">
                  <Select value={draft.risk} onChange={(e) => setDraft((d) => ({ ...d, risk: e.target.value }))}>
                    <option value="">Any risk</option>
                    {Object.keys(RISK_META).map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
                  </Select>
                </FilterField>
                <FilterField label="Department">
                  <Select value={draft.department} onChange={(e) => setDraft((d) => ({ ...d, department: e.target.value }))}>
                    <option value="">Any department</option>
                    {deptOptions.map((dp) => <option key={dp} value={dp}>{dp}</option>)}
                  </Select>
                </FilterField>
                <FilterField label="Owner">
                  <Select value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))}>
                    <option value="">Any owner</option>
                    {owners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </Select>
                </FilterField>
                <FilterField label="Counterparty">
                  <Input value={draft.counterparty} onChange={(e) => setDraft((d) => ({ ...d, counterparty: e.target.value }))} placeholder="contains…" />
                </FilterField>
                <FilterField label="Min value">
                  <Input type="number" inputMode="decimal" value={draft.value_min} onChange={(e) => setDraft((d) => ({ ...d, value_min: e.target.value }))} placeholder="0" />
                </FilterField>
                <FilterField label="Max value">
                  <Input type="number" inputMode="decimal" value={draft.value_max} onChange={(e) => setDraft((d) => ({ ...d, value_max: e.target.value }))} placeholder="—" />
                </FilterField>
                <FilterField label="Renewal type">
                  <Select value={draft.renewal_type} onChange={(e) => setDraft((d) => ({ ...d, renewal_type: e.target.value }))}>
                    <option value="">Any renewal</option>
                    <option value="none">None</option>
                    <option value="auto">Auto-renew</option>
                    <option value="manual">Manual</option>
                  </Select>
                </FilterField>
                <FilterField label="Currency">
                  <Input value={draft.currency} onChange={(e) => setDraft((d) => ({ ...d, currency: e.target.value.toUpperCase() }))} maxLength={3} placeholder="Any (e.g. USD)" />
                </FilterField>
                <FilterField label="Tag">
                  <Input value={draft.tag} onChange={(e) => setDraft((d) => ({ ...d, tag: e.target.value }))} placeholder="contains…" />
                </FilterField>
              </div>

              {/* date windows */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <FilterField label="Effective from">
                  <Input type="date" value={draft.effective_from} onChange={(e) => setDraft((d) => ({ ...d, effective_from: e.target.value }))} />
                </FilterField>
                <FilterField label="Effective to">
                  <Input type="date" value={draft.effective_to} onChange={(e) => setDraft((d) => ({ ...d, effective_to: e.target.value }))} />
                </FilterField>
                <FilterField label="Expiry (end) from">
                  <Input type="date" value={draft.end_from} onChange={(e) => setDraft((d) => ({ ...d, end_from: e.target.value }))} />
                </FilterField>
                <FilterField label="Expiry (end) to">
                  <Input type="date" value={draft.end_to} onChange={(e) => setDraft((d) => ({ ...d, end_to: e.target.value }))} />
                </FilterField>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setDraft(filters)}>Reset</Button>
                <Button size="sm" onClick={applyFilters}>Apply filters</Button>
              </div>
              <p className="text-[11px] text-ink-3">Filters apply across the whole report — KPIs, distributions, pipeline, cycle time, throughput, approvers, and the CSV export.</p>
            </CardBody>
          </Card>
        )}

        {error && <ErrorBanner message={error} />}

        {/* KPI strip */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {loading || !data ? (
            Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
          ) : (
            <>
              <KpiCard label="Total contracts" value={data.total_contracts} href="/contracts" icon={FileText} />
              <KpiCard label="Created in range" value={data.created_in_range} sub={`Last ${daysBetween(data.range_from, data.range_to)} days`} icon={FilePlus2} />
              <KpiCard label="Signed in range" value={data.signed_in_range} sub="Envelopes completed" icon={FileCheck2} tone="accent" />
              <KpiCard label="Active" value={data.active_count} sub={formatMoney(data.active_value, currency)} href="/contracts?status=active" icon={Wallet} />
              <KpiCard label="Expiring ≤30d" value={data.expiring_30d} tone={data.expiring_30d ? "warn" : "default"} href="/contracts?status=expiring" icon={CalendarClock} />
              <KpiCard label="Expiring ≤90d" value={data.expiring_90d} tone={data.expiring_90d ? "warn" : "default"} icon={CalendarClock} />
            </>
          )}
        </div>

        {/* Distributions row */}
        <div className="grid gap-6 lg:grid-cols-2">
          <DistributionCard
            title="By status"
            icon={<ListChecks className="h-4 w-4" />}
            buckets={data?.by_status ?? []}
            labelOf={(b) => statusMeta(b.label).label}
            href={(b) => `/contracts?status=${b.label}`}
            loading={loading}
          />
          <DistributionCard
            title="By type"
            icon={<ListChecks className="h-4 w-4" />}
            buckets={data?.by_type ?? []}
            labelOf={(b) => contractTypeLabel(b.label)}
            showValue
            currency={currency}
            href={(b) => `/contracts?type=${b.label}`}
            loading={loading}
          />
          <DistributionCard
            title="Risk (open contracts)"
            icon={<Gauge className="h-4 w-4" />}
            buckets={data?.by_risk ?? []}
            labelOf={(b) => titleCase(b.label)}
            colorOf={(b) =>
              ({ low: "bg-emerald-500", medium: "bg-amber-500", high: "bg-orange-500", critical: "bg-red-500" })[b.label] ?? "bg-accent"
            }
            loading={loading}
          />
          <DistributionCard
            title="Active value by department"
            icon={<ListChecks className="h-4 w-4" />}
            buckets={data?.by_department ?? []}
            labelOf={(b) => b.label}
            sortBy="value"
            showValue
            currency={currency}
            loading={loading}
          />
        </div>

        {/* New per month */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4" /> Contracts created over time
            </CardTitle>
            <span className="text-xs text-ink-3">{data?.new_per_month.length ?? 0} months</span>
          </CardHeader>
          <CardBody>
            {loading ? (
              <Skeleton className="h-40" />
            ) : !data || data.new_per_month.length === 0 ? (
              <p className="text-sm text-ink-3">No contracts created in this range.</p>
            ) : (
              <MonthlySeries points={data.new_per_month} currency={currency} />
            )}
          </CardBody>
        </Card>

        {/* Cycle time + throughput */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Gauge className="h-4 w-4" /> Cycle time
              </CardTitle>
              <span className="text-xs text-ink-3">In range</span>
            </CardHeader>
            <CardBody>
              {loading || !data ? (
                <Skeleton className="h-36" />
              ) : (
                <div className="grid grid-cols-3 gap-3 text-center">
                  <CycleCell title="Approval" days={data.cycle_time.approval_avg_days} median={data.cycle_time.approval_median_days} n={data.cycle_time.approval_n} />
                  <CycleCell title="Signature" days={data.cycle_time.signature_avg_days} median={data.cycle_time.signature_median_days} n={data.cycle_time.signature_n} />
                  <CycleCell title="End-to-end" days={data.cycle_time.end_to_end_avg_days} n={data.cycle_time.end_to_end_n} sub="created → signed" />
                </div>
              )}
              <p className="mt-3 text-[11px] text-ink-3">Approval = workflow-run completion (started → approved). Signature = envelope sent → completed. End-to-end = contract creation → signed.</p>
            </CardBody>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <PenLine className="h-4 w-4" /> Throughput
              </CardTitle>
              <span className="text-xs text-ink-3">In range</span>
            </CardHeader>
            <CardBody>
              {loading || !data ? (
                <Skeleton className="h-36" />
              ) : (
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                  <ThroughputRow label="Workflows started" v={data.throughput.workflow_runs_started} />
                  <ThroughputRow label="Envelopes sent" v={data.throughput.envelopes_sent} />
                  <ThroughputRow label="Workflows approved" v={data.throughput.workflow_runs_approved} tone="ok" />
                  <ThroughputRow label="Envelopes completed" v={data.throughput.envelopes_completed} tone="ok" />
                  <ThroughputRow label="Changes requested" v={data.throughput.workflow_runs_changes_requested} tone="warn" />
                  <ThroughputRow label="Envelopes declined" v={data.throughput.envelopes_declined} tone="bad" />
                  <ThroughputRow label="Workflows rejected" v={data.throughput.workflow_runs_rejected} tone="bad" />
                  <ThroughputRow label="Envelopes voided" v={data.throughput.envelopes_voided} />
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Expiring pipeline */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Renewal pipeline</CardTitle>
              <Link href="/contracts?status=expiring" className="text-xs text-accent hover:underline">
                See all
              </Link>
            </CardHeader>
            <CardBody>
              {loading || !data ? (
                <Skeleton className="h-40" />
              ) : (
                <div className="grid grid-cols-4 gap-3 text-center">
                  {data.expiring_buckets.map((b) => (
                    <div key={b.label} className="rounded-lg border border-line bg-surface-2 p-3">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">{b.label}</div>
                      <div className="mt-1 text-2xl font-semibold text-ink tnum">{b.count}</div>
                      <div className="mt-0.5 text-[11px] text-ink-3">{formatMoney(b.value, currency)}</div>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-3 text-[11px] text-ink-3">Active / expiring contracts with an end date in the next 180 days, bucketed.</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Expiring soonest</CardTitle>
              <span className="text-xs text-ink-3">{data?.expiring_top.length ?? 0} contracts</span>
            </CardHeader>
            <CardBody>
              {loading || !data ? (
                <Skeleton className="h-40" />
              ) : data.expiring_top.length === 0 ? (
                <p className="text-sm text-ink-3">Nothing expiring in the next 180 days.</p>
              ) : (
                <div className="divide-y divide-line">
                  {data.expiring_top.map((c) => (
                    <Link key={c.id} href={`/contracts/${c.id}`} className="flex items-center gap-3 py-2.5 hover:bg-surface-2">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-ink">{c.title}</div>
                        <div className="truncate text-xs text-ink-3">
                          {c.reference_no}
                          {c.counterparty ? ` · ${c.counterparty}` : ""}
                          {c.value ? ` · ${formatMoney(c.value, c.currency)}` : ""}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-sm font-medium ${c.days_to_end <= 30 ? "text-danger" : c.days_to_end <= 60 ? "text-amber-700" : "text-ink-2"}`}>
                          {c.days_to_end === 0 ? "today" : c.days_to_end < 0 ? `${-c.days_to_end}d overdue` : `${c.days_to_end}d`}
                        </div>
                        <div className="text-xs text-ink-3">{c.end_date ? formatDate(c.end_date) : ""}</div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Where contracts are stuck */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <ListChecks className="h-4 w-4" /> Where contracts are stuck
            </CardTitle>
            <span className="text-xs text-ink-3">{stuck?.length ?? 0} blocking · oldest first</span>
          </CardHeader>
          <CardBody>
            {stuck === null ? (
              <Skeleton className="h-32" />
            ) : stuck.length === 0 ? (
              <p className="text-sm text-ink-3">Nothing is blocking right now. 🎉</p>
            ) : (
              <div className="divide-y divide-line">
                {stuck.map((s, i) => (
                  <Link key={`${s.kind}-${s.contract_id}-${i}`} href={s.href} className="flex flex-wrap items-center gap-3 py-2.5 hover:bg-surface-2">
                    <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-md ${s.kind === "approval_step" ? "bg-violet-100 text-violet-700" : "bg-emerald-100 text-emerald-700"}`}>
                      {s.kind === "approval_step" ? "A" : "S"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-ink">{s.contract_title}</div>
                      <div className="truncate text-xs text-ink-3">
                        <span className="font-medium text-ink-2">{s.contract_reference}</span> · {s.detail}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-sm font-semibold tnum ${s.waiting_hours > 168 ? "text-danger" : s.waiting_hours > 24 ? "text-amber-700" : "text-ink-2"}`}>
                        {formatWait(s.waiting_hours)}
                      </div>
                      <div className="text-[11px] text-ink-3">waiting</div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Top approvers */}
        <Card>
          <CardHeader>
            <CardTitle>Top approvers</CardTitle>
            <span className="text-xs text-ink-3">Decisions in range</span>
          </CardHeader>
          <CardBody>
            {loading || !data ? (
              <Skeleton className="h-32" />
            ) : data.top_approvers.length === 0 ? (
              <p className="text-sm text-ink-3">No workflow decisions have been recorded in this range.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                    <tr>
                      <th className="py-2 pr-3">Person</th>
                      <th className="py-2 pr-3 text-right">Approved</th>
                      <th className="py-2 pr-3 text-right">Changes</th>
                      <th className="py-2 pr-3 text-right">Rejected</th>
                      <th className="py-2 pr-3 text-right">Total</th>
                      <th className="py-2 pr-3 text-right">Avg response</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.top_approvers.map((a) => (
                      <tr key={a.user_id}>
                        <td className="py-2 pr-3 font-medium text-ink">{a.name || "—"}</td>
                        <td className="py-2 pr-3 text-right text-emerald-700 tnum">{a.approved}</td>
                        <td className="py-2 pr-3 text-right text-amber-700 tnum">{a.changes_requested}</td>
                        <td className="py-2 pr-3 text-right text-red-700 tnum">{a.rejected}</td>
                        <td className="py-2 pr-3 text-right font-semibold text-ink tnum">{a.total}</td>
                        <td className="py-2 pr-3 text-right text-ink-2 tnum">{formatHours(a.avg_response_hours)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</label>
      {children}
    </div>
  );
}

function daysBetween(from: string, to: string): number {
  const a = new Date(from).getTime();
  const b = new Date(to).getTime();
  return Math.max(Math.round((b - a) / 86400000), 0);
}

function formatWait(h: number): string {
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${Math.round(h / 24)}d`;
}

function formatHours(h: number): string {
  if (!h) return "—";
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function DistributionCard({
  title,
  icon,
  buckets,
  labelOf,
  colorOf,
  href,
  showValue = false,
  currency,
  loading,
  sortBy = "count",
}: {
  title: string;
  icon?: React.ReactNode;
  buckets: { label: string; count: number; value: number }[];
  labelOf: (b: { label: string; count: number; value: number }) => string;
  colorOf?: (b: { label: string; count: number; value: number }) => string;
  href?: (b: { label: string; count: number; value: number }) => string;
  showValue?: boolean;
  currency?: string;
  loading?: boolean;
  sortBy?: "count" | "value";
}) {
  const ordered = useMemo(() => [...buckets].sort((a, b) => (sortBy === "value" ? b.value - a.value : b.count - a.count)), [buckets, sortBy]);
  const max = useMemo(() => Math.max(1, ...ordered.map((b) => (sortBy === "value" ? b.value : b.count))), [ordered, sortBy]);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          {icon} {title}
        </CardTitle>
        <span className="text-xs text-ink-3">{ordered.length}</span>
      </CardHeader>
      <CardBody>
        {loading ? (
          <Skeleton className="h-36" />
        ) : ordered.length === 0 ? (
          <p className="text-sm text-ink-3">No data.</p>
        ) : (
          <div className="space-y-2">
            {ordered.map((b) => {
              const pct = ((sortBy === "value" ? b.value : b.count) / max) * 100;
              const color = colorOf ? colorOf(b) : "bg-accent";
              const row = (
                <div className="group">
                  <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate text-ink-2">{labelOf(b)}</span>
                    <span className="shrink-0 text-ink tabular-nums">
                      {b.count}
                      {showValue ? <span className="ml-1 text-xs text-ink-3">· {formatMoney(b.value, currency)}</span> : null}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-surface-3">
                    <div className={`bar-grow h-full rounded-full ${color}`} style={{ width: `${Math.max(pct, 2)}%` }} />
                  </div>
                </div>
              );
              return href ? (
                <Link key={b.label} href={href(b)} className="block rounded-md p-1 hover:bg-surface-2">
                  {row}
                </Link>
              ) : (
                <div key={b.label} className="p-1">{row}</div>
              );
            })}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function MonthlySeries({ points, currency }: { points: { label: string; count: number; value: number }[]; currency?: string }) {
  // Reuse the interactive area chart (hover tooltip + animated draw). Map month labels to a
  // compact MM/YY and the report's {count} to the chart's {contracts} field.
  const chartPoints = points.map((p) => ({
    label: `${p.label.slice(5)}/${p.label.slice(2, 4)}`,
    contracts: p.count,
    value: p.value,
  }));
  return <AreaChart points={chartPoints} formatValue={(v) => formatMoney(v, currency)} />;
}

function CycleCell({ title, days, median, n, sub }: { title: string; days: number; median?: number; n: number; sub?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">{title}</div>
      <div className="mt-1 text-2xl font-semibold text-ink tnum">{days ? `${days.toFixed(1)}d` : "—"}</div>
      <div className="mt-0.5 text-[11px] text-ink-3">
        {n ? (
          <>
            {median !== undefined ? `median ${median.toFixed(1)}d · ` : ""}
            n={n}
          </>
        ) : (
          "no completed runs"
        )}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-ink-3">{sub}</div>}
    </div>
  );
}

function ThroughputRow({ label, v, tone = "default" }: { label: string; v: number; tone?: "default" | "ok" | "warn" | "bad" }) {
  const cls = {
    default: "text-ink",
    ok: "text-emerald-700",
    warn: "text-amber-700",
    bad: "text-red-700",
  }[tone];
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1.5 last:border-0">
      <span className="text-ink-2">{label}</span>
      <span className={`text-base font-semibold tabular-nums ${cls}`}>{v}</span>
    </div>
  );
}
