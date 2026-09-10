"use client";

/**
 * Executive analytics and MIS.
 *
 *   GET  /analytics/executive     cycle times, bottleneck stages, renewals, escalations, policy
 *   GET  /analytics/workload      who is carrying the review load
 *   GET  /analytics/trend         volume over time, with the same period a year earlier
 *   GET  /analytics/segmentation  by department, region, entity type, status
 *   GET  /analytics/clause-pressure  what counterparties keep pushing back on
 *   POST /analytics/export        any of it, as a spreadsheet
 *
 * Every figure shows the sample it came from. A mean cycle time over four agreements and one
 * over four hundred are different claims, and a dashboard that hides that gets quoted in a
 * board pack as though they were the same.
 *
 * Charts are inline SVG rather than a charting library: these are bars and a sparkline, and a
 * 90 kB dependency to draw a rectangle is a dependency to keep patched.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Clock,
  Download,
  Printer,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Users,
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
import { contractTypeLabel, formatDate, formatMoney, titleCase } from "@/lib/utils";
import type {
  ClausePressure,
  ExecutiveSummary,
  ReviewerLoad,
  Segmentation,
  VolumeTrend,
} from "@/lib/types";

type Tab = "overview" | "workload" | "trends" | "policy";

export default function AnalyticsPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [summary, setSummary] = useState<ExecutiveSummary | null>(null);
  const [workload, setWorkload] = useState<ReviewerLoad[] | null>(null);
  const [trend, setTrend] = useState<VolumeTrend | null>(null);
  const [segments, setSegments] = useState<Segmentation | null>(null);
  const [pressure, setPressure] = useState<ClausePressure[] | null>(null);
  const [granularity, setGranularity] = useState("month");
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api
      .get<ExecutiveSummary>("/analytics/executive")
      .then(setSummary)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Analytics could not be loaded."),
      );
    api.get<ReviewerLoad[]>("/analytics/workload").then(setWorkload).catch(() => setWorkload([]));
    api.get<Segmentation>("/analytics/segmentation").then(setSegments).catch(() => setSegments(null));
    api
      .get<ClausePressure[]>("/analytics/clause-pressure")
      .then(setPressure)
      .catch(() => setPressure([]));
  }, []);

  useEffect(() => {
    api
      .get<VolumeTrend>(`/analytics/trend?granularity=${granularity}`)
      .then(setTrend)
      .catch(() => setTrend(null));
  }, [granularity]);

  async function exportReport(kind: string) {
    setExporting(true);
    setError("");
    try {
      const job = await api.post<{ href: string }>("/analytics/export", { kind, filters: {} });
      window.location.href = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${job.href}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The export could not be generated.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Cycle times, bottlenecks, workload and policy posture across the repository"
        actions={
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="print-keep"
              onClick={() => window.print()}
            >
              <Printer className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              loading={exporting}
              onClick={() => exportReport("contracts")}
            >
              <Download className="h-3.5 w-3.5" /> Export
            </Button>
          </div>
        }
      />

      <div className="space-y-5 p-6">
        {error && <ErrorBanner message={error} />}

        <div className="flex flex-wrap gap-1 rounded-lg bg-surface-2 p-1 text-sm no-print">
          {(["overview", "workload", "trends", "policy"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
                tab === t ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
              }`}
            >
              {titleCase(t)}
            </button>
          ))}
        </div>

        {tab === "overview" && <Overview summary={summary} />}
        {tab === "workload" && <Workload rows={workload} summary={summary} />}
        {tab === "trends" && (
          <Trends
            trend={trend}
            segments={segments}
            granularity={granularity}
            onGranularity={setGranularity}
          />
        )}
        {tab === "policy" && <Policy summary={summary} pressure={pressure} />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ overview ---------- */

function Overview({ summary }: { summary: ExecutiveSummary | null }) {
  if (!summary) return <Skeleton className="h-64" />;

  const cycle = summary.cycle_times.overall;
  const renewals = summary.renewals.counts;
  const atRisk =
    (renewals.overdue ?? 0) + (renewals["30"] ?? 0) + (renewals["60"] ?? 0) + (renewals["90"] ?? 0);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <Kpi
          label="Median cycle time"
          value={cycle.median === null ? "—" : `${cycle.median}d`}
          sample={cycle.sample}
          icon={Clock}
          note={cycle.mean !== null ? `mean ${cycle.mean}d · p90 ${cycle.p90}d` : undefined}
        />
        <Kpi
          label="Bottleneck stage"
          value={summary.stages.bottleneck ?? "—"}
          sample={summary.stages.stages.length}
          sampleLabel="stages"
          icon={AlertTriangle}
        />
        <Kpi
          label="Expiring in 90 days"
          value={String(atRisk)}
          sample={summary.renewals.value_at_risk}
          sampleLabel="value at risk"
          formatSample={(v) => formatMoney(v, "PKR")}
          icon={RefreshCw}
        />
        <Kpi
          label="Policy deviations"
          value={String(summary.compliance.deviating)}
          sample={summary.compliance.checked}
          sampleLabel="agreements checked"
          icon={ShieldCheck}
          tone={summary.compliance.blockers > 0 ? "text-red-600" : undefined}
        />
      </div>

      {summary.cycle_times.still_in_flight > 0 && (
        <p className="text-xs text-ink-3">
          Cycle times cover {cycle.sample} executed agreement
          {cycle.sample === 1 ? "" : "s"}. {summary.cycle_times.still_in_flight} more are still
          in flight and are not counted — including them as zero would make the number improve
          every time somebody starts a draft.
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Where agreements wait</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          {summary.stages.stages.length === 0 && (
            <p className="text-sm text-ink-3">No approval stages have run yet.</p>
          )}
          {summary.stages.stages.map((s) => (
            <div key={s.stage} className="space-y-1">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="min-w-[160px] text-ink">{s.stage}</span>
                <span className="text-ink-2">
                  {s.mean_hours === null ? "—" : `${s.mean_hours}h mean`}
                </span>
                {s.p90_hours !== null && (
                  <span className="text-xs text-ink-3">p90 {s.p90_hours}h</span>
                )}
                {s.awaiting > 0 && <Badge tone="accent">{s.awaiting} waiting</Badge>}
                {s.escalations > 0 && (
                  <span className="text-xs text-red-600">{s.escalations} escalated</span>
                )}
                <span className="ml-auto text-xs text-ink-3">
                  {s.sla_adherence === null
                    ? "no SLA set"
                    : `${s.sla_adherence}% on time (${s.sla_sample})`}
                </span>
              </div>
              <Bar
                value={s.mean_hours ?? 0}
                max={Math.max(...summary.stages.stages.map((x) => x.mean_hours ?? 0), 1)}
              />
            </div>
          ))}
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Cycle time by type</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {Object.keys(summary.cycle_times.by_type).length === 0 && (
              <p className="text-sm text-ink-3">Nothing executed yet.</p>
            )}
            {Object.entries(summary.cycle_times.by_type).map(([type, m]) => (
              <div key={type} className="flex items-center gap-2 text-sm">
                <span className="min-w-[140px] text-ink">{contractTypeLabel(type)}</span>
                <span className="text-ink-2">{m.median ?? "—"}d median</span>
                <span className="ml-auto text-xs text-ink-3">n={m.sample}</span>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Renewal pipeline</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {(["overdue", "30", "60", "90", "later"] as const).map((bucket) => (
              <div key={bucket} className="flex items-center gap-2 text-sm">
                <span className="min-w-[110px] text-ink">
                  {bucket === "overdue"
                    ? "Already expired"
                    : bucket === "later"
                      ? "Beyond 90 days"
                      : `Within ${bucket} days`}
                </span>
                <span className={bucket === "overdue" ? "text-red-600" : "text-ink-2"}>
                  {summary.renewals.counts[bucket] ?? 0}
                </span>
              </div>
            ))}
            <p className="pt-1 text-xs text-ink-3">
              {formatMoney(summary.renewals.value_at_risk, "PKR")} expiring within 90 days.
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ workload ---------- */

function Workload({
  rows,
  summary,
}: {
  rows: ReviewerLoad[] | null;
  summary: ExecutiveSummary | null;
}) {
  if (!rows) return <Skeleton className="h-48" />;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <Users className="h-4 w-4" /> Reviewer load
          </CardTitle>
        </CardHeader>
        <CardBody>
          <p className="mb-2 text-xs text-ink-3">
            Ordered by what is still open, not by throughput — the point is finding who is
            about to become a bottleneck.
          </p>
          {rows.length === 0 ? (
            <p className="text-sm text-ink-3">No reviews have been assigned yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-3">
                    <th className="py-1 pr-3">Reviewer</th>
                    <th className="py-1 pr-3">Role</th>
                    <th className="py-1 pr-3">Open</th>
                    <th className="py-1 pr-3">Overdue</th>
                    <th className="py-1 pr-3">Decided</th>
                    <th className="py-1">Mean time</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.user_id} className="border-t border-line">
                      <td className="py-1.5 pr-3 text-ink">{r.name}</td>
                      <td className="py-1.5 pr-3 text-ink-3">{r.role}</td>
                      <td className="py-1.5 pr-3 text-ink">{r.open}</td>
                      <td className={`py-1.5 pr-3 ${r.overdue ? "text-red-600" : "text-ink-3"}`}>
                        {r.overdue}
                      </td>
                      <td className="py-1.5 pr-3 text-ink-2">{r.decided}</td>
                      <td className="py-1.5 text-ink-2">
                        {r.mean_hours === null ? "—" : `${r.mean_hours}h`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {summary && (
        <Card>
          <CardHeader>
            <CardTitle>Escalations</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="font-display text-2xl font-semibold text-ink">
                {summary.escalations.total}
              </span>
              <span className="text-sm text-ink-2">
                {summary.escalations.mean_resolution_hours === null
                  ? "none resolved yet"
                  : `${summary.escalations.mean_resolution_hours}h mean time to resolve (n=${summary.escalations.resolution_sample})`}
              </span>
            </div>
            <div className="flex items-end gap-1">
              {summary.escalations.series.map((p) => (
                <div key={p.month} className="flex flex-1 flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t bg-accent"
                    style={{
                      height: `${
                        8 +
                        (p.count /
                          Math.max(...summary.escalations.series.map((x) => x.count), 1)) *
                          60
                      }px`,
                    }}
                    title={`${p.month}: ${p.count}`}
                  />
                  <span className="text-[9px] text-ink-3">{p.month.slice(5)}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- trends ---------- */

function Trends({
  trend,
  segments,
  granularity,
  onGranularity,
}: {
  trend: VolumeTrend | null;
  segments: Segmentation | null;
  granularity: string;
  onGranularity: (g: string) => void;
}) {
  const max = useMemo(
    () => Math.max(...(trend?.series ?? []).map((p) => Math.max(p.raised, p.executed)), 1),
    [trend],
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <TrendingUp className="h-4 w-4" /> Volume over time
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="w-40 no-print">
            <Select value={granularity} onChange={(e) => onGranularity(e.target.value)}>
              <option value="day">Daily</option>
              <option value="week">Weekly</option>
              <option value="month">Monthly</option>
            </Select>
          </div>

          {!trend ? (
            <Skeleton className="h-32" />
          ) : trend.series.length === 0 ? (
            <p className="text-sm text-ink-3">No agreements yet.</p>
          ) : (
            <>
              <div className="flex items-end gap-1 overflow-x-auto pb-1">
                {trend.series.map((p) => (
                  <div key={p.period} className="flex min-w-[26px] flex-col items-center gap-1">
                    <div className="flex items-end gap-0.5">
                      <div
                        className="w-2.5 rounded-t bg-accent"
                        style={{ height: `${6 + (p.raised / max) * 70}px` }}
                        title={`${p.period}: ${p.raised} raised`}
                      />
                      <div
                        className="w-2.5 rounded-t bg-accent/40"
                        style={{ height: `${6 + (p.executed / max) * 70}px` }}
                        title={`${p.period}: ${p.executed} executed`}
                      />
                      {p.raised_year_ago !== null && p.raised_year_ago !== undefined && (
                        <div
                          className="w-1 rounded-t bg-ink-3/40"
                          style={{ height: `${6 + (p.raised_year_ago / max) * 70}px` }}
                          title={`A year earlier: ${p.raised_year_ago}`}
                        />
                      )}
                    </div>
                    <span className="text-[9px] text-ink-3">{p.period.slice(-5)}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap gap-3 text-[11px] text-ink-3">
                <Legend className="bg-accent" label="Raised" />
                <Legend className="bg-accent/40" label="Executed" />
                <Legend className="bg-ink-3/40" label="Raised a year earlier" />
              </div>
            </>
          )}
        </CardBody>
      </Card>

      {segments && (
        <div className="grid gap-4 lg:grid-cols-2">
          <SegmentCard title="By department" rows={segments.by_department} />
          <SegmentCard title="By region" rows={segments.by_region} />
          <SegmentCard title="By agreement type" rows={segments.by_type} />
          <SegmentCard title="By entity type" rows={segments.by_entity_type} />
        </div>
      )}
    </div>
  );
}

function SegmentCard({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; count: number; value: number }[];
}) {
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-1.5">
        {rows.length === 0 && <p className="text-sm text-ink-3">Nothing to show.</p>}
        {rows.slice(0, 8).map((r) => (
          <div key={r.label} className="space-y-0.5">
            <div className="flex items-center gap-2 text-sm">
              <span className="min-w-[130px] truncate text-ink">{r.label}</span>
              <span className="text-ink-2">{r.count}</span>
              <span className="ml-auto text-xs text-ink-3">{formatMoney(r.value, "PKR")}</span>
            </div>
            <Bar value={r.count} max={max} />
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

/* -------------------------------------------------------------------- policy ---------- */

function Policy({
  summary,
  pressure,
}: {
  summary: ExecutiveSummary | null;
  pressure: ClausePressure[] | null;
}) {
  if (!summary) return <Skeleton className="h-48" />;
  const c = summary.compliance;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <Kpi label="Checked" value={String(c.checked)} icon={ShieldCheck} />
        <Kpi
          label="Deviating"
          value={String(c.deviating)}
          icon={AlertTriangle}
          tone={c.deviating > 0 ? "text-amber-700" : undefined}
        />
        <Kpi
          label="Blocking findings"
          value={String(c.blockers)}
          icon={AlertTriangle}
          tone={c.blockers > 0 ? "text-red-600" : undefined}
        />
        <Kpi label="Overdue obligations" value={String(c.overdue_obligations)} icon={Clock} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agreements outside policy</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          {c.worst.length === 0 ? (
            <p className="text-sm text-ink-3">
              Everything checked is within policy.
            </p>
          ) : (
            c.worst.map((w) => (
              <div key={w.contract_id} className="rounded-md border border-line p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/contracts/${w.contract_id}`}
                    className="text-sm font-medium text-ink hover:text-accent"
                  >
                    {w.title}
                  </Link>
                  <span className="text-[11px] text-ink-3">{w.reference_no}</span>
                  {w.blockers > 0 && <Badge tone="accent">{w.blockers} blocking</Badge>}
                </div>
                <p className="mt-1 text-xs text-ink-2">{w.findings.join(" · ")}</p>
              </div>
            ))
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Most contested clauses</CardTitle>
        </CardHeader>
        <CardBody className="space-y-1.5">
          <p className="text-xs text-ink-3">
            Not "what do we have?" but "what do counterparties keep pushing back on?" — the
            list worth fixing.
          </p>
          {!pressure || pressure.length === 0 ? (
            <p className="text-sm text-ink-3">No clause data yet.</p>
          ) : (
            pressure.slice(0, 10).map((p) => (
              <div key={p.clause_key} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="min-w-[180px] text-ink">{p.title}</span>
                <span className="text-ink-2">used {p.used}×</span>
                {p.altered > 0 && (
                  <span className="text-amber-700">{p.altered} altered</span>
                )}
                {p.missing > 0 && <span className="text-red-600">{p.missing} missing</span>}
              </div>
            ))
          )}
        </CardBody>
      </Card>
    </div>
  );
}

/* --------------------------------------------------------------------- bits ----------- */

function Kpi({
  label,
  value,
  sample,
  sampleLabel = "sample",
  formatSample,
  icon: Icon,
  tone,
  note,
}: {
  label: string;
  value: string;
  sample?: number;
  sampleLabel?: string;
  formatSample?: (v: number) => string;
  icon: typeof Clock;
  tone?: string;
  note?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className="flex items-center gap-1.5 text-xs text-ink-2">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className={`mt-1 truncate font-display text-2xl font-semibold ${tone ?? "text-ink"}`}>
        {value}
      </div>
      {sample !== undefined && (
        <div className="text-[11px] text-ink-3">
          {formatSample ? formatSample(sample) : `${sample} ${sampleLabel}`}
        </div>
      )}
      {note && <div className="text-[11px] text-ink-3">{note}</div>}
    </div>
  );
}

function Bar({ value, max }: { value: number; max: number }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-surface-3">
      <div
        className="h-1.5 rounded-full bg-accent"
        style={{ width: `${Math.max(2, (value / max) * 100)}%` }}
      />
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-sm ${className}`} />
      {label}
    </span>
  );
}
