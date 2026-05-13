"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, qs } from "@/lib/api";
import { Button, Card, Input, Select, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { EmptyState } from "@/components/widgets";
import { LifecycleDots, RiskBadge, StatusPill } from "@/components/lifecycle";
import { CONTRACT_TYPES, contractTypeLabel, daysUntil, formatDate, formatMoney, timeAgo } from "@/lib/utils";
import type { ContractListItem, Paginated } from "@/lib/types";

const STATUS_OPTIONS = [
  "draft",
  "in_review",
  "changes_requested",
  "approved",
  "out_for_signature",
  "signed",
  "active",
  "expiring",
  "expired",
  "terminated",
];

export default function ContractsPage() {
  return (
    <Suspense fallback={<div className="p-6"><Skeleton className="h-64" /></div>}>
      <ContractsList />
    </Suspense>
  );
}

function ContractsList() {
  const router = useRouter();
  const params = useSearchParams();
  const { me } = useAuth();

  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const type = params.get("type") ?? "";
  const risk = params.get("risk") ?? "";
  const mine = params.get("mine") === "1";
  const sort = params.get("sort") ?? "-updated_at";
  const page = Math.max(1, parseInt(params.get("page") ?? "1", 10) || 1);
  const pageSize = 25;

  const [data, setData] = useState<Paginated<ContractListItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(q);

  useEffect(() => setSearch(q), [q]);

  useEffect(() => {
    setLoading(true);
    api
      .get<Paginated<ContractListItem>>(
        "/contracts" +
          qs({ q, status, type, risk, mine, sort, page, page_size: pageSize }),
      )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [q, status, type, risk, mine, sort, page]);

  function update(next: Record<string, string | undefined>) {
    const sp = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v === undefined || v === "") sp.delete(k);
      else sp.set(k, v);
    }
    if (!("page" in next)) sp.delete("page"); // reset to page 1 on filter change
    router.push(`/contracts?${sp.toString()}`);
  }

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <PageHeader
        title="Contracts"
        subtitle={loading ? "…" : `${total} contract${total === 1 ? "" : "s"}`}
        actions={
          <Link href="/contracts/new">
            <Button>
              <Plus className="h-4 w-4" /> New contract
            </Button>
          </Link>
        }
      />

      <div className="space-y-4 p-6">
        {/* filter bar */}
        <Card className="flex flex-wrap items-center gap-2 p-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              update({ q: search.trim() || undefined });
            }}
            className="min-w-[200px] flex-1"
          >
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search title, ref #, counterparty…" className="h-9" />
          </form>
          <Select value={status} onChange={(e) => update({ status: e.target.value || undefined })} className="h-9 w-auto min-w-[150px]">
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          <Select value={type} onChange={(e) => update({ type: e.target.value || undefined })} className="h-9 w-auto min-w-[150px]">
            <option value="">All types</option>
            {CONTRACT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
          <Select value={risk} onChange={(e) => update({ risk: e.target.value || undefined })} className="h-9 w-auto">
            <option value="">Any risk</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </Select>
          <Button variant={mine ? "primary" : "secondary"} size="sm" onClick={() => update({ mine: mine ? undefined : "1" })}>
            {mine ? "Mine ✓" : "Mine"}
          </Button>
          <Select value={sort} onChange={(e) => update({ sort: e.target.value })} className="h-9 w-auto">
            <option value="-updated_at">Recently updated</option>
            <option value="-created_at">Newest</option>
            <option value="title">Title A→Z</option>
            <option value="end_date">End date ↑</option>
            <option value="-value">Value ↓</option>
          </Select>
          {(q || status || type || risk || mine) && (
            <Button variant="ghost" size="sm" onClick={() => router.push("/contracts")}>
              Clear
            </Button>
          )}
        </Card>

        {/* table */}
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <th className="px-4 py-2.5">Contract</th>
                  <th className="px-4 py-2.5">Stage</th>
                  <th className="px-4 py-2.5">Owner</th>
                  <th className="px-4 py-2.5">Counterparty</th>
                  <th className="px-4 py-2.5 text-right">Value</th>
                  <th className="px-4 py-2.5">End</th>
                  <th className="px-4 py-2.5">Risk</th>
                  <th className="px-4 py-2.5">Updated</th>
                </tr>
              </thead>
              <tbody>
                {loading &&
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} className="border-b border-line">
                      <td colSpan={8} className="px-4 py-3">
                        <Skeleton className="h-5" />
                      </td>
                    </tr>
                  ))}
                {!loading &&
                  data?.items.map((c) => {
                    const du = daysUntil(c.end_date);
                    return (
                      <tr key={c.id} className="cursor-pointer border-b border-line last:border-0 hover:bg-surface-2" onClick={() => router.push(`/contracts/${c.id}`)}>
                        <td className="px-4 py-3">
                          <div className="font-medium text-ink">{c.title}</div>
                          <div className="mt-1 flex items-center gap-2 text-xs text-ink-3">
                            <span className="tnum">{c.reference_no}</span>
                            <span>·</span>
                            <span>{contractTypeLabel(c.type)}</span>
                            <LifecycleDots status={c.status} className="ml-1" />
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <StatusPill status={c.status} />
                        </td>
                        <td className="px-4 py-3 text-ink-2">{c.owner_name}</td>
                        <td className="px-4 py-3 text-ink-2">{c.counterparty || "—"}</td>
                        <td className="px-4 py-3 text-right tnum text-ink-2">{formatMoney(c.value, c.currency)}</td>
                        <td className="px-4 py-3 text-ink-2">
                          {formatDate(c.end_date)}
                          {du !== null && du >= 0 && du <= 60 && <span className="ml-1 text-amber-700">({du}d)</span>}
                          {du !== null && du < 0 && <span className="ml-1 text-danger">(past)</span>}
                        </td>
                        <td className="px-4 py-3">{c.risk_level !== "low" ? <RiskBadge level={c.risk_level} /> : <span className="text-ink-3">—</span>}</td>
                        <td className="px-4 py-3 text-ink-3">{timeAgo(c.updated_at)}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          {!loading && data && data.items.length === 0 && (
            <div className="p-6">
              <EmptyState
                title={q || status || type || risk || mine ? "No contracts match these filters" : "No contracts yet"}
                description={q || status || type || risk || mine ? "Try clearing some filters." : "Create your first contract to get started."}
                action={
                  <Link href="/contracts/new">
                    <Button>
                      <Plus className="h-4 w-4" /> New contract
                    </Button>
                  </Link>
                }
              />
            </div>
          )}
        </Card>

        {/* pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between text-sm text-ink-2">
            <span>
              Page {page} of {pages}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>
                Previous
              </Button>
              <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
