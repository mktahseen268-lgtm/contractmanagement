"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CalendarClock, FileText, Inbox, PenLine, RefreshCw, ShieldAlert, Sparkles, TrendingUp, Wallet } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { ErrorBoundary } from "@/components/error-boundary";
import { AreaChart, type TrendPoint } from "@/components/charts";
import { ActivityFeed, KpiCard, QuickCreateTiles, StatusDistribution } from "@/components/widgets";
import { StatusPill, RiskBadge } from "@/components/lifecycle";
import { cn, contractTypeLabel, daysUntil, formatDate, formatMoney } from "@/lib/utils";
import type { ContractListItem, Dashboard, InboxSummary } from "@/lib/types";

type Kpis = Pick<Dashboard, "total_contracts" | "pending_approvals" | "awaiting_signature" | "expiring_30d" | "active_value" | "open_risks">;
type Distribution = Pick<Dashboard, "by_status" | "by_type">;
type Trends = { points: TrendPoint[]; total_contracts: number; delta_pct: number };

// Each widget fetches its own slice independently, so the fast KPI row paints without waiting on
// the heavier activity / attention queries. A shared `refreshKey` re-runs every widget's effect
// (after busting the GET cache) when the user hits Refresh. The request de-dupe in lib/api means
// the two widgets that both read /dashboard/kpis share a single network call.

export default function DashboardPage() {
  const { me } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const refreshAll = useCallback(() => {
    api.invalidate();
    setRefreshing(true);
    setRefreshKey((k) => k + 1);
    setTimeout(() => setRefreshing(false), 600);
  }, []);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const firstName = me?.user.name.split(" ")[0] ?? "";

  return (
    <div>
      <PageHeader
        title={<span className="font-display">{`${greeting}, ${firstName}`}</span>}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span>{me?.tenant.name}</span>
            <span className="inline-flex items-center gap-1.5 text-[12px] text-ok">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-ok" /> All systems operational
            </span>
            <span className="text-ink-3">· synced just now</span>
          </span>
        }
        actions={
          <Button variant="secondary" size="sm" onClick={refreshAll} title="Refresh all widgets">
            <RefreshCw className={refreshing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} /> Refresh
          </Button>
        }
      />
      <div className="space-y-6 p-6">
        <ErrorBoundary label="key metrics">
          <KpiRow refreshKey={refreshKey} currency={me?.tenant.currency} />
        </ErrorBoundary>

        <ErrorBoundary label="the trend chart">
          <TrendCard refreshKey={refreshKey} currency={me?.tenant.currency} />
        </ErrorBoundary>

        <div>
          <h2 className="mb-2.5 text-sm font-semibold text-ink-2">Quick create</h2>
          <QuickCreateTiles />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <ErrorBoundary label="your contracts">
              <AttentionWidget refreshKey={refreshKey} />
            </ErrorBoundary>
            <ErrorBoundary label="the status breakdown">
              <DistributionWidget refreshKey={refreshKey} />
            </ErrorBoundary>
          </div>
          <div className="space-y-6">
            <ErrorBoundary label="recommendations">
              <RecommendationsWidget refreshKey={refreshKey} />
            </ErrorBoundary>
            <ErrorBoundary label="team activity">
              <ActivityWidget refreshKey={refreshKey} />
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- per-widget data hook: fetch on mount + whenever refreshKey changes ----

function useWidget<T>(path: string, refreshKey: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    api
      .get<T>(path)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : "Couldn't load this widget."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, refreshKey]);

  return { data, error, loading };
}

function WidgetError({ message }: { message: string }) {
  return <div className="rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-xs text-danger">{message}</div>;
}

// ---- widgets ----

function KpiRow({ refreshKey, currency }: { refreshKey: number; currency?: string }) {
  const kpis = useWidget<Kpis>("/dashboard/kpis", refreshKey);
  const inbox = useWidget<InboxSummary>("/inbox/summary", refreshKey);
  const trends = useWidget<Trends>("/dashboard/trends", refreshKey); // de-duped with TrendCard
  const k = kpis.data;
  const inboxTotal = inbox.data?.total ?? 0;
  const inboxHigh = inbox.data?.high_priority ?? 0;
  const spark = trends.data?.points.map((p) => p.contracts);
  // real $-value-created-per-week sparkline + WoW delta for the hero card
  const valueSpark = trends.data?.points.map((p) => p.value);
  const vp = trends.data?.points ?? [];
  const valueDelta =
    vp.length >= 2 && vp[vp.length - 2].value > 0
      ? ((vp[vp.length - 1].value - vp[vp.length - 2].value) / vp[vp.length - 2].value) * 100
      : null;

  if (kpis.loading && !k) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  }
  if (kpis.error && !k) return <WidgetError message={kpis.error} />;
  if (!k) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <KpiCard
        label="On your plate"
        value={inboxTotal}
        sub={inboxHigh ? `${inboxHigh} high priority` : "Approvals & signatures"}
        href="/inbox"
        icon={Inbox}
        tone={inboxHigh ? "warn" : inboxTotal ? "accent" : "default"}
      />
      <KpiCard label="Total contracts" value={k.total_contracts} href="/contracts" icon={FileText} sparkline={spark} delta={trends.data?.delta_pct} />
      <KpiCard label="Awaiting signature" value={k.awaiting_signature} href="/contracts?status=out_for_signature" icon={PenLine} />
      <KpiCard label="Expiring ≤30d" value={k.expiring_30d} href="/contracts?status=expiring" icon={CalendarClock} tone={k.expiring_30d ? "warn" : "default"} />
      <KpiCard label="Open risks" value={k.open_risks} icon={ShieldAlert} tone={k.open_risks ? "danger" : "default"} />
      <KpiCard label="Active value" value={formatMoney(k.active_value, currency)} icon={Wallet} hero sparkline={valueSpark} delta={valueDelta} />
    </div>
  );
}

const TREND_RANGES = [
  { label: "4w", weeks: 4 },
  { label: "8w", weeks: 8 },
  { label: "12w", weeks: 12 },
  { label: "26w", weeks: 26 },
];

function TrendCard({ refreshKey, currency }: { refreshKey: number; currency?: string }) {
  const [weeks, setWeeks] = useState(8);
  const { data, error, loading } = useWidget<Trends>(`/dashboard/trends?weeks=${weeks}`, refreshKey);
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent-subtle text-accent">
            <TrendingUp className="h-4 w-4" />
          </span>
          Contracts created
          <span className="text-xs font-normal text-ink-3">· last {weeks} weeks</span>
        </CardTitle>
        <div className="flex items-center gap-3">
          {/* time-range toggle */}
          <div className="inline-flex overflow-hidden rounded-lg border border-line">
            {TREND_RANGES.map((r) => (
              <button
                key={r.weeks}
                onClick={() => setWeeks(r.weeks)}
                className={cn(
                  "px-2.5 py-1 text-[11px] font-medium transition-colors",
                  weeks === r.weeks ? "bg-accent text-accent-fg" : "bg-white text-ink-2 hover:bg-surface-2",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
          {data && (
            <div className="text-right">
              <div className="font-display text-lg font-bold tnum text-ink">{data.total_contracts}</div>
              <div className="text-[11px] text-ink-3">in window</div>
            </div>
          )}
        </div>
      </CardHeader>
      <CardBody>
        {loading && !data && <Skeleton className="h-44" />}
        {error && !data && <WidgetError message={error} />}
        {data && (data.points.some((p) => p.contracts > 0) ? (
          <AreaChart points={data.points} formatValue={(v) => formatMoney(v, currency)} />
        ) : (
          <div className="grid h-44 place-items-center text-sm text-ink-3">No contracts created in this window yet.</div>
        ))}
      </CardBody>
    </Card>
  );
}

function AttentionWidget({ refreshKey }: { refreshKey: number }) {
  const { data, error, loading } = useWidget<ContractListItem[]>("/dashboard/attention", refreshKey);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Needs your attention</CardTitle>
        <Link href="/contracts?mine=1" className="text-xs text-accent hover:underline">My contracts</Link>
      </CardHeader>
      <CardBody className="space-y-2">
        {loading && !data && <Skeleton className="h-20" />}
        {error && !data && <WidgetError message={error} />}
        {data && data.length === 0 && <p className="py-2 text-sm text-ink-3">Nothing waiting on you. 🎉</p>}
        {data && data.map((c) => <AttentionRow key={c.id} c={c} />)}
      </CardBody>
    </Card>
  );
}

function DistributionWidget({ refreshKey }: { refreshKey: number }) {
  const { data, error, loading } = useWidget<Distribution>("/dashboard/distribution", refreshKey);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Contracts by stage</CardTitle>
      </CardHeader>
      <CardBody>
        {loading && !data && <Skeleton className="h-16" />}
        {error && !data && <WidgetError message={error} />}
        {data && <StatusDistribution counts={data.by_status} />}
      </CardBody>
    </Card>
  );
}

function ActivityWidget({ refreshKey }: { refreshKey: number }) {
  const { data, error, loading } = useWidget<Dashboard["recent_activity"]>("/dashboard/activity", refreshKey);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Team activity</CardTitle>
      </CardHeader>
      <CardBody>
        {loading && !data && <Skeleton className="h-24" />}
        {error && !data && <WidgetError message={error} />}
        {data && <ActivityFeed items={data} />}
      </CardBody>
    </Card>
  );
}

function RecommendationsWidget({ refreshKey }: { refreshKey: number }) {
  // Reads /dashboard/kpis too — de-duped with KpiRow's call by the api-client micro-cache.
  const { data, loading } = useWidget<Kpis>("/dashboard/kpis", refreshKey);
  return (
    <Card className="ai-aurora border-ai-line/60">
      <CardHeader className="border-ai-line/40">
        <CardTitle className="flex items-center gap-1.5 text-ai">
          <Sparkles className="h-4 w-4" /> AI recommendations
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-2.5 text-sm">
        {loading && !data ? (
          <Skeleton className="h-16" />
        ) : data ? (
          <>
            {data.expiring_30d > 0 && (
              <Reco>
                {data.expiring_30d} contract{data.expiring_30d > 1 ? "s" : ""} expire within 30 days —{" "}
                <Link href="/contracts?status=expiring" className="font-medium text-ai underline">review renewals</Link>.
              </Reco>
            )}
            {data.open_risks > 0 && (
              <Reco>
                {data.open_risks} contract{data.open_risks > 1 ? "s have" : " has"} high/critical risk flags —{" "}
                <Link href="/contracts?risk=high" className="font-medium text-ai underline">take a look</Link>.
              </Reco>
            )}
            {data.pending_approvals > 0 && <Reco>{data.pending_approvals} contract(s) in review — keep them moving.</Reco>}
            <Reco>
              Try the{" "}
              <Link href="/intelligence" className="font-medium text-ai underline">OCR &amp; AI workspace</Link>{" "}
              — scan a document and extract its terms.
            </Reco>
            <p className="pt-1 text-[11px] text-ink-3">AI can be wrong — verify before relying.</p>
          </>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Reco({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-white/70 px-3 py-2 text-ink-2">
      <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ai" />
      <span>{children}</span>
    </div>
  );
}

function AttentionRow({ c }: { c: ContractListItem }) {
  const du = daysUntil(c.end_date);
  return (
    <Link href={`/contracts/${c.id}`} className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-surface-3">
      <StatusPill status={c.status} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-ink">{c.title}</div>
        <div className="truncate text-xs text-ink-3">
          {c.reference_no} · {contractTypeLabel(c.type)}
          {c.end_date && ` · ends ${formatDate(c.end_date)}${du !== null && du >= 0 ? ` (${du}d)` : ""}`}
        </div>
      </div>
      {(c.risk_level === "high" || c.risk_level === "critical") && <RiskBadge level={c.risk_level} />}
    </Link>
  );
}
