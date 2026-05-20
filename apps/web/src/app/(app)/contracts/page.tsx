"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Bookmark, BookmarkPlus, Download, Eye, Plus, Trash2, X } from "lucide-react";
import { api, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, Input, Select, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { useToast } from "@/components/toast";
import { Drawer, DrawerRow } from "@/components/drawer";
import { EmptyState } from "@/components/widgets";
import { LifecycleDots, RiskBadge, StatusPill } from "@/components/lifecycle";
import { CONTRACT_TYPES, contractTypeLabel, daysUntil, formatDate, formatMoney, statusMeta, timeAgo } from "@/lib/utils";
import { loadViews, newViewId, normalizeQuery, saveViews, type SavedView } from "@/lib/saved-views";
import type { ContractDetail, ContractListItem, Paginated } from "@/lib/types";

type BulkResult = { requested: number; succeeded: number; deleted_ids: string[]; skipped: { id: string; reason: string }[] };

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
  const toast = useToast();
  const { me } = useAuth();
  const canDelete = ["owner", "admin", "manager"].includes(me?.user.role ?? "");

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
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [quickView, setQuickView] = useState<ContractListItem | null>(null);
  const [views, setViews] = useState<SavedView[]>([]);

  const tenantId = me?.tenant.id;
  // load this workspace's saved views once we know the tenant
  useEffect(() => {
    setViews(loadViews(tenantId));
  }, [tenantId]);

  useEffect(() => setSearch(q), [q]);

  // Live, debounced search — update the URL 300ms after the user stops typing (URL stays the
  // source of truth, so results are shareable + back-button friendly). Skips when unchanged.
  useEffect(() => {
    const term = search.trim();
    if (term === q) return;
    const t = setTimeout(() => update({ q: term || undefined }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    setLoading(true);
    setSelected(new Set()); // clear selection when the result set changes
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

  // ---- saved views ----
  const currentQuery = normalizeQuery(params.toString());
  const activeViewId = views.find((v) => normalizeQuery(v.query) === currentQuery)?.id ?? null;
  const hasActiveFilters = currentQuery.length > 0;

  function applyView(v: SavedView) {
    router.push(`/contracts?${v.query}`);
  }
  function saveCurrentView() {
    if (!hasActiveFilters) {
      toast.info("Nothing to save", "Apply some filters first, then save them as a view.");
      return;
    }
    const name = window.prompt("Name this view (e.g. “High-risk renewals”):", "")?.trim();
    if (!name) return;
    const view: SavedView = { id: newViewId(), name: name.slice(0, 40), query: currentQuery };
    const next = [...views.filter((v) => v.name !== name), view];
    setViews(next);
    saveViews(tenantId, next);
    toast.success("View saved", `“${view.name}” is now in your saved views.`);
  }
  function deleteView(id: string) {
    const next = views.filter((v) => v.id !== id);
    setViews(next);
    saveViews(tenantId, next);
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  // ---- selection ----
  const allOnPageSelected = items.length > 0 && items.every((c) => selected.has(c.id));
  const someSelected = selected.size > 0;
  function toggleOne(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleAll() {
    setSelected((s) => {
      if (items.every((c) => s.has(c.id))) return new Set();
      return new Set(items.map((c) => c.id));
    });
  }
  const selectedItems = useMemo(() => items.filter((c) => selected.has(c.id)), [items, selected]);

  function exportCsv() {
    const rows = selectedItems.length ? selectedItems : items;
    if (!rows.length) return;
    const headers = ["Reference", "Title", "Type", "Status", "Owner", "Counterparty", "Value", "Currency", "End date", "Risk", "Updated"];
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [
      headers.join(","),
      ...rows.map((c) =>
        [c.reference_no, c.title, contractTypeLabel(c.type), c.status, c.owner_name, c.counterparty, c.value, c.currency, c.end_date ?? "", c.risk_level, c.updated_at]
          .map(esc)
          .join(","),
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `contracts-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${rows.length} contract${rows.length === 1 ? "" : "s"}`, "CSV downloaded.");
  }

  const [bulkBusy, setBulkBusy] = useState(false);
  async function bulkDelete() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    if (!window.confirm(`Delete ${ids.length} contract${ids.length === 1 ? "" : "s"}? Live agreements (active/signed/out-for-signature) will be skipped. This can't be undone.`)) return;
    setBulkBusy(true);
    try {
      const res = await api.post<BulkResult>("/contracts/bulk", { ids, action: "delete" });
      // optimistic: drop the deleted rows from the current view + adjust the total
      const deleted = new Set(res.deleted_ids);
      setData((d) => (d ? { ...d, items: d.items.filter((c) => !deleted.has(c.id)), total: Math.max(0, d.total - res.succeeded) } : d));
      setSelected(new Set());
      if (res.succeeded && res.skipped.length) {
        toast.warning(`Deleted ${res.succeeded}, skipped ${res.skipped.length}`, "Live agreements were left untouched.");
      } else if (res.succeeded) {
        toast.success(`Deleted ${res.succeeded} contract${res.succeeded === 1 ? "" : "s"}`);
      } else {
        toast.warning("Nothing deleted", `${res.skipped.length} item(s) are protected — delete them individually.`);
      }
    } catch (e) {
      toast.error("Bulk delete failed", e instanceof Error ? e.message : "Please try again.");
    } finally {
      setBulkBusy(false);
    }
  }

  const hasFilters = !!(q || status || type || risk || mine);

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
          <Button variant="ghost" size="sm" onClick={exportCsv} title="Export current page (or selection) to CSV" disabled={loading || items.length === 0}>
            <Download className="h-3.5 w-3.5" /> Export
          </Button>
          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={() => router.push("/contracts")}>
              Clear
            </Button>
          )}
        </Card>

        {/* saved views — apply a stored filter combo in one click, or save the current one */}
        {(views.length > 0 || hasActiveFilters) && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
              <Bookmark className="h-3.5 w-3.5" /> Views
            </span>
            <button
              onClick={() => router.push("/contracts")}
              className={cnChip(!hasActiveFilters)}
            >
              All
            </button>
            {views.map((v) => (
              <span key={v.id} className={cnChip(activeViewId === v.id)}>
                <button onClick={() => applyView(v)} className="max-w-[180px] truncate">
                  {v.name}
                </button>
                <button
                  onClick={() => deleteView(v.id)}
                  className="grid h-4 w-4 place-items-center rounded-full text-ink-3 hover:bg-surface-3 hover:text-danger"
                  aria-label={`Delete view ${v.name}`}
                  title="Delete view"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <button
              onClick={saveCurrentView}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-line px-2.5 py-1 text-xs text-ink-2 hover:border-accent hover:text-accent"
              title="Save the current filters as a view"
            >
              <BookmarkPlus className="h-3.5 w-3.5" /> Save view
            </button>
          </div>
        )}

        {/* table */}
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <th className="w-10 px-3 py-2.5">
                    <input
                      type="checkbox"
                      aria-label="Select all on this page"
                      className="h-3.5 w-3.5 cursor-pointer accent-[var(--color-accent)]"
                      checked={allOnPageSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected && !allOnPageSelected;
                      }}
                      onChange={toggleAll}
                    />
                  </th>
                  <th className="px-4 py-2.5">Contract</th>
                  <th className="px-4 py-2.5">Stage</th>
                  <th className="px-4 py-2.5">Owner</th>
                  <th className="px-4 py-2.5">Counterparty</th>
                  <th className="px-4 py-2.5 text-right">Value</th>
                  <th className="px-4 py-2.5">End</th>
                  <th className="px-4 py-2.5">Risk</th>
                  <th className="px-4 py-2.5">Updated</th>
                  <th className="w-12 px-2 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {loading &&
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} className="border-b border-line">
                      <td colSpan={10} className="px-4 py-3">
                        <Skeleton className="h-5" />
                      </td>
                    </tr>
                  ))}
                {!loading &&
                  items.map((c) => {
                    const du = daysUntil(c.end_date);
                    const isSel = selected.has(c.id);
                    return (
                      <tr
                        key={c.id}
                        className={cnRow(isSel)}
                        onClick={() => router.push(`/contracts/${c.id}`)}
                      >
                        <td
                          className="px-3 py-3"
                          onClick={(e) => e.stopPropagation()}
                          style={{ boxShadow: `inset 3px 0 0 0 ${statusMeta(c.status).dot}` }}
                        >
                          <input
                            type="checkbox"
                            aria-label={`Select ${c.title}`}
                            className="h-3.5 w-3.5 cursor-pointer accent-[var(--color-accent)]"
                            checked={isSel}
                            onChange={() => toggleOne(c.id)}
                          />
                        </td>
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
                        <td className="px-2 py-3" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => setQuickView(c)}
                            title="Quick view"
                            aria-label={`Quick view ${c.title}`}
                            className="grid h-8 w-8 place-items-center rounded-md text-ink-3 hover:bg-surface-3 hover:text-ink"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          {!loading && data && items.length === 0 && (
            <div className="p-6">
              <EmptyState
                title={hasFilters ? "No contracts match these filters" : "No contracts yet"}
                description={hasFilters ? "Try clearing some filters." : "Create your first contract to get started."}
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

      {/* bulk action bar — floats above content when ≥1 row is selected */}
      {someSelected && (
        <div className="pointer-events-none fixed inset-x-0 bottom-5 z-40 flex justify-center px-4">
          <div className="pointer-events-auto flex items-center gap-3 rounded-full border border-line bg-white px-3 py-2 shadow-pop">
            <span className="pl-1 text-sm font-medium text-ink">{selected.size} selected</span>
            <span className="h-4 w-px bg-line" />
            <Button size="sm" variant="secondary" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" /> Export CSV
            </Button>
            {canDelete && (
              <Button size="sm" variant="danger" onClick={bulkDelete} loading={bulkBusy}>
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            )}
            <button
              onClick={() => setSelected(new Set())}
              className="grid h-8 w-8 place-items-center rounded-full text-ink-3 hover:bg-surface-3 hover:text-ink"
              aria-label="Clear selection"
              title="Clear selection"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* quick-view slide-over */}
      <ContractQuickView item={quickView} onClose={() => setQuickView(null)} />
    </div>
  );
}

function cnRow(selected: boolean): string {
  return [
    "cursor-pointer border-b border-line last:border-0 hover:bg-surface-2",
    selected ? "bg-accent-subtle/50" : "",
  ].join(" ");
}

function cnChip(active: boolean): string {
  return [
    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
    active ? "border-accent bg-accent-subtle text-accent" : "border-line bg-white text-ink-2 hover:bg-surface-3",
  ].join(" ");
}

// ---- quick view drawer: instant summary from the list row + progressive detail fetch ----

function ContractQuickView({ item, onClose }: { item: ContractListItem | null; onClose: () => void }) {
  const [detail, setDetail] = useState<ContractDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    setDetail(null);
    if (!item) return;
    setDetailLoading(true);
    api
      .get<ContractDetail>(`/contracts/${item.id}`)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [item]);

  if (!item) return null;
  const du = daysUntil(item.end_date);

  return (
    <Drawer
      open={!!item}
      onClose={onClose}
      title={item.title}
      subtitle={`${item.reference_no} · ${contractTypeLabel(item.type)}`}
      footer={
        <div className="flex items-center gap-2">
          <Link href={`/contracts/${item.id}`} className="flex-1" onClick={onClose}>
            <Button className="w-full" size="sm">Open full contract</Button>
          </Link>
        </div>
      }
    >
      <div className="space-y-1">
        <div className="mb-3 flex items-center gap-2">
          <StatusPill status={item.status} />
          {item.risk_level !== "low" && <RiskBadge level={item.risk_level} />}
        </div>
        <DrawerRow label="Owner">{item.owner_name}</DrawerRow>
        <DrawerRow label="Counterparty">{item.counterparty || "—"}</DrawerRow>
        <DrawerRow label="Value">{formatMoney(item.value, item.currency)}</DrawerRow>
        <DrawerRow label="End date">
          {formatDate(item.end_date)}
          {du !== null && du >= 0 && du <= 60 && <span className="ml-1 text-amber-700">({du}d)</span>}
          {du !== null && du < 0 && <span className="ml-1 text-danger">(past)</span>}
        </DrawerRow>
        <DrawerRow label="Last updated">{timeAgo(item.updated_at)}</DrawerRow>

        {/* progressively-loaded richer detail */}
        <div className="mt-4 border-t border-line pt-3">
          {detailLoading && !detail && <Skeleton className="h-20" />}
          {detail && (
            <>
              {detail.governing_law && <DrawerRow label="Governing law">{detail.governing_law}</DrawerRow>}
              {detail.effective_date && <DrawerRow label="Effective">{formatDate(detail.effective_date)}</DrawerRow>}
              {detail.department && <DrawerRow label="Department">{detail.department}</DrawerRow>}
              {detail.tags?.length > 0 && (
                <div className="py-2 text-sm">
                  <div className="mb-1 text-ink-3">Tags</div>
                  <div className="flex flex-wrap justify-end gap-1">
                    {detail.tags.map((t) => (
                      <span key={t} className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] text-ink-2">{t}</span>
                    ))}
                  </div>
                </div>
              )}
              {detail.ai_summary && (
                <div className="mt-2 rounded-md bg-surface-2 p-3 text-[13px] leading-relaxed text-ink-2">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">Summary</div>
                  {detail.ai_summary}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </Drawer>
  );
}
