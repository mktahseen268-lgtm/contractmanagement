"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { ActivityFeed, EmptyState, KpiCard, QuickCreateTiles, StatusDistribution } from "@/components/widgets";
import { StatusPill, RiskBadge } from "@/components/lifecycle";
import { contractTypeLabel, daysUntil, formatDate, formatMoney } from "@/lib/utils";
import { Sparkles } from "lucide-react";
import type { ContractListItem, Dashboard, InboxSummary } from "@/lib/types";

export default function DashboardPage() {
  const { me } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [inbox, setInbox] = useState<InboxSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Dashboard>("/dashboard").then(setData).catch((e) => setError(e.message));
    api.get<InboxSummary>("/inbox/summary").then(setInbox).catch(() => {});
  }, []);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const firstName = me?.user.name.split(" ")[0] ?? "";

  return (
    <div>
      <PageHeader title={`${greeting}, ${firstName}`} subtitle={me?.tenant.name} />
      <div className="space-y-6 p-6">
        {error && <Card><CardBody className="text-sm text-danger">{error}</CardBody></Card>}

        {/* KPI row */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {!data ? (
            Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
          ) : (
            <>
              <KpiCard
                label="On your plate"
                value={inbox?.total ?? 0}
                sub={inbox?.high_priority ? `${inbox.high_priority} high priority` : "Approvals & signatures"}
                href="/inbox"
                tone={inbox?.high_priority ? "warn" : inbox?.total ? "accent" : "default"}
              />
              <KpiCard label="Total contracts" value={data.total_contracts} href="/contracts" />
              <KpiCard label="Awaiting signature" value={data.awaiting_signature} href="/contracts?status=out_for_signature" />
              <KpiCard label="Expiring ≤30d" value={data.expiring_30d} href="/contracts?status=expiring" tone={data.expiring_30d ? "warn" : "default"} />
              <KpiCard label="Open risks" value={data.open_risks} tone={data.open_risks ? "danger" : "default"} />
              <KpiCard label="Active value" value={formatMoney(data.active_value, me?.tenant.currency)} />
            </>
          )}
        </div>

        {/* quick create */}
        <div>
          <h2 className="mb-2.5 text-sm font-semibold text-ink-2">Quick create</h2>
          <QuickCreateTiles />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* left: needs your attention + status */}
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>Needs your attention</CardTitle>
                <Link href="/contracts?mine=1" className="text-xs text-accent hover:underline">
                  My contracts
                </Link>
              </CardHeader>
              <CardBody className="space-y-2">
                {!data ? (
                  <Skeleton className="h-20" />
                ) : data.my_open.length === 0 ? (
                  <p className="py-2 text-sm text-ink-3">Nothing waiting on you. 🎉</p>
                ) : (
                  data.my_open.map((c) => <AttentionRow key={c.id} c={c} />)
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Contracts by stage</CardTitle>
              </CardHeader>
              <CardBody>{data ? <StatusDistribution counts={data.by_status} /> : <Skeleton className="h-16" />}</CardBody>
            </Card>
          </div>

          {/* right: AI recommendations + activity */}
          <div className="space-y-6">
            <Card className="ai-aurora border-ai-line/60">
              <CardHeader className="border-ai-line/40">
                <CardTitle className="flex items-center gap-1.5 text-ai">
                  <Sparkles className="h-4 w-4" /> AI recommendations
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-2.5 text-sm">
                {!data ? (
                  <Skeleton className="h-16" />
                ) : (
                  <>
                    {data.expiring_30d > 0 && (
                      <Reco>
                        {data.expiring_30d} contract{data.expiring_30d > 1 ? "s" : ""} expire within 30 days —{" "}
                        <Link href="/contracts?status=expiring" className="font-medium text-ai underline">
                          review renewals
                        </Link>
                        .
                      </Reco>
                    )}
                    {data.open_risks > 0 && (
                      <Reco>
                        {data.open_risks} contract{data.open_risks > 1 ? "s have" : " has"} high/critical risk flags —{" "}
                        <Link href="/contracts?risk=high" className="font-medium text-ai underline">
                          take a look
                        </Link>
                        .
                      </Reco>
                    )}
                    {data.pending_approvals > 0 && <Reco>{data.pending_approvals} contract(s) in review — keep them moving.</Reco>}
                    <Reco>
                      Try the{" "}
                      <Link href="/intelligence" className="font-medium text-ai underline">
                        OCR &amp; AI workspace
                      </Link>{" "}
                      — scan a document and extract its terms.
                    </Reco>
                    <p className="pt-1 text-[11px] text-ink-3">AI can be wrong — verify before relying.</p>
                  </>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Team activity</CardTitle>
              </CardHeader>
              <CardBody>{data ? <ActivityFeed items={data.recent_activity} /> : <Skeleton className="h-24" />}</CardBody>
            </Card>
          </div>
        </div>
      </div>
    </div>
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
