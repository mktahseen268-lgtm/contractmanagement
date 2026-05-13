"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, FileText, Inbox as InboxIcon, PenLine, Workflow as WorkflowIcon } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardBody, ErrorBanner, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { RiskBadge } from "@/components/lifecycle";
import { cn, contractTypeLabel, formatMoney, timeAgo } from "@/lib/utils";
import type { InboxItem } from "@/lib/types";

type Filter = "all" | "approval" | "signature";

export default function InboxPage() {
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(() => {
    api
      .get<InboxItem[]>("/inbox")
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your inbox."));
  }, []);
  useEffect(load, [load]);

  const filtered = useMemo(() => (items ?? []).filter((i) => filter === "all" || i.kind === filter), [items, filter]);
  const counts = useMemo(() => {
    const total = items?.length ?? 0;
    const approvals = items?.filter((i) => i.kind === "approval").length ?? 0;
    const signatures = items?.filter((i) => i.kind === "signature").length ?? 0;
    const high = items?.filter((i) => i.priority === "high").length ?? 0;
    return { total, approvals, signatures, high };
  }, [items]);

  return (
    <div>
      <PageHeader
        title="Inbox"
        subtitle={
          items === null
            ? "Loading…"
            : counts.total === 0
              ? "Nothing's waiting on you — nicely done."
              : `${counts.total} item${counts.total === 1 ? "" : "s"} waiting on you${counts.high ? ` · ${counts.high} high priority` : ""}.`
        }
      />
      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {/* tab strip */}
        <div className="flex flex-wrap items-center gap-1.5">
          <FilterPill active={filter === "all"} onClick={() => setFilter("all")} label={`All`} count={counts.total} />
          <FilterPill active={filter === "approval"} onClick={() => setFilter("approval")} label={`Approvals`} count={counts.approvals} />
          <FilterPill active={filter === "signature"} onClick={() => setFilter("signature")} label={`Signatures`} count={counts.signatures} />
        </div>

        {items === null && (
          <div className="space-y-2">
            <Skeleton className="h-20 rounded-xl" />
            <Skeleton className="h-20 rounded-xl" />
            <Skeleton className="h-20 rounded-xl" />
          </div>
        )}

        {items !== null && filtered.length === 0 && (
          <Card>
            <CardBody className="py-12 text-center">
              <InboxIcon className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">All caught up</div>
              <p className="mt-1 text-sm text-ink-2">
                {counts.total === 0
                  ? "You don't have any approvals or signatures waiting on you."
                  : filter === "approval"
                    ? "No approvals waiting — nice."
                    : "No signatures waiting on you."}
              </p>
            </CardBody>
          </Card>
        )}

        <div className="space-y-2">
          {filtered.map((item) => (
            <InboxRow key={item.id} item={item} />
          ))}
        </div>

        {items !== null && counts.total > 0 && (
          <p className="text-[11px] text-ink-3">
            High-priority items are anything waiting on you for ≥24 hours, or where the contract risk is high/critical. They float to the top.
          </p>
        )}
      </div>
    </div>
  );
}

function FilterPill({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium",
        active ? "border-accent bg-accent-subtle text-accent" : "border-line bg-white text-ink-2 hover:border-accent/40 hover:text-ink",
      )}
    >
      {label}
      <span className={cn("min-w-[1.25rem] rounded-full px-1.5 text-center text-[10px] font-semibold", active ? "bg-accent text-accent-fg" : "bg-surface-3 text-ink-3")}>
        {count}
      </span>
    </button>
  );
}

function InboxRow({ item }: { item: InboxItem }) {
  const Icon = item.kind === "approval" ? WorkflowIcon : PenLine;
  const isHigh = item.priority === "high";
  return (
    <Link href={item.href} className="block">
      <Card className={cn("p-4 transition-shadow hover:shadow-lift", isHigh && "ring-1 ring-amber-300")}>
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "grid h-10 w-10 shrink-0 place-items-center rounded-lg",
              item.kind === "approval" ? "bg-violet-100 text-violet-700" : "bg-emerald-100 text-emerald-700",
            )}
          >
            <Icon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-semibold text-ink">{item.title}</span>
              {isHigh && (
                <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">High priority</span>
              )}
              <RiskBadge level={item.risk_level} />
              <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-3">
                {contractTypeLabel(item.contract_type)}
              </span>
            </div>
            <div className="mt-0.5 text-xs text-ink-3">
              <span className="font-medium text-ink-2">{item.contract_reference}</span>
              {item.subtitle ? <> · {item.subtitle}</> : null}
              {item.value ? <> · {formatMoney(item.value, item.currency)}</> : null}
            </div>
            <div className="mt-0.5 text-[11px] text-ink-3">
              <FileText className="mr-1 inline-block h-3 w-3 align-[-2px]" />
              {item.contract_title}
              {item.since ? <span className="ml-2">· waiting {timeAgo(item.since)}</span> : null}
            </div>
          </div>
          <div className="hidden items-center gap-1 text-xs text-accent sm:flex">
            {item.kind === "approval" ? <><Check className="h-3.5 w-3.5" /> Review &amp; decide</> : <><PenLine className="h-3.5 w-3.5" /> Open &amp; sign</>}
            <ChevronRight className="h-3.5 w-3.5" />
          </div>
        </div>
      </Card>
    </Link>
  );
}
