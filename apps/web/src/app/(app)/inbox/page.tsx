"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, FileText, Inbox as InboxIcon, ListTodo, PenLine, Workflow as WorkflowIcon } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardBody, ErrorBanner, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { RiskBadge } from "@/components/lifecycle";
import { cn, contractTypeLabel, formatMoney, timeAgo } from "@/lib/utils";
import type { InboxItem } from "@/lib/types";

type Filter = "all" | "approval" | "signature" | "obligation";
type Scope = "mine" | "sent";

export default function InboxPage() {
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [scope, setScope] = useState<Scope>("mine");

  const load = useCallback(() => {
    setItems(null);
    api
      .get<InboxItem[]>(scope === "sent" ? "/inbox/sent" : "/inbox")
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your inbox."));
  }, [scope]);
  useEffect(load, [load]);

  const filtered = useMemo(() => (items ?? []).filter((i) => filter === "all" || i.kind === filter), [items, filter]);
  const counts = useMemo(() => {
    const total = items?.length ?? 0;
    const approvals = items?.filter((i) => i.kind === "approval").length ?? 0;
    const signatures = items?.filter((i) => i.kind === "signature").length ?? 0;
    const obligations = items?.filter((i) => i.kind === "obligation").length ?? 0;
    const high = items?.filter((i) => i.priority === "high").length ?? 0;
    return { total, approvals, signatures, obligations, high };
  }, [items]);

  return (
    <div>
      <PageHeader
        title="Inbox"
        subtitle={
          items === null
            ? "Loading…"
            : scope === "sent"
              ? counts.total === 0
                ? "Nothing you've started is waiting on someone else."
                : `${counts.total} item${counts.total === 1 ? "" : "s"} you started, waiting on others.`
              : counts.total === 0
                ? "Nothing's waiting on you — nicely done."
                : `${counts.total} item${counts.total === 1 ? "" : "s"} waiting on you${counts.high ? ` · ${counts.high} high priority` : ""}.`
        }
        actions={
          <div className="inline-flex overflow-hidden rounded-full border border-line">
            <button onClick={() => setScope("mine")} className={cn("px-3 py-1.5 text-xs font-medium", scope === "mine" ? "bg-accent text-accent-fg" : "bg-white text-ink-2 hover:bg-surface-2")}>
              On you
            </button>
            <button onClick={() => setScope("sent")} className={cn("border-l border-line px-3 py-1.5 text-xs font-medium", scope === "sent" ? "bg-accent text-accent-fg" : "bg-white text-ink-2 hover:bg-surface-2")}>
              Sent
            </button>
          </div>
        }
      />
      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {/* tab strip */}
        <div className="flex flex-wrap items-center gap-1.5">
          <FilterPill active={filter === "all"} onClick={() => setFilter("all")} label={`All`} count={counts.total} />
          <FilterPill active={filter === "approval"} onClick={() => setFilter("approval")} label={`Approvals`} count={counts.approvals} />
          <FilterPill active={filter === "signature"} onClick={() => setFilter("signature")} label={`Signatures`} count={counts.signatures} />
          <FilterPill active={filter === "obligation"} onClick={() => setFilter("obligation")} label={`Obligations`} count={counts.obligations} />
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

        {/* prioritized queue — high-priority items grouped at the top */}
        {(() => {
          const high = filtered.filter((i) => i.priority === "high");
          const rest = filtered.filter((i) => i.priority !== "high");
          if (filtered.length === 0) return null;
          return (
            <div className="space-y-5">
              {high.length > 0 && (
                <div className="space-y-2">
                  <GroupHeader label="Needs attention now" count={high.length} tone="warn" />
                  {high.map((item) => <InboxRow key={item.id} item={item} />)}
                </div>
              )}
              {rest.length > 0 && (
                <div className="space-y-2">
                  {high.length > 0 && <GroupHeader label="Up next" count={rest.length} tone="default" />}
                  {rest.map((item) => <InboxRow key={item.id} item={item} />)}
                </div>
              )}
            </div>
          );
        })()}

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

const KIND_META = {
  approval: { Icon: WorkflowIcon, tint: "bg-violet-100 text-violet-700", stripe: "#7c3aed", action: "Review & decide", ActionIcon: Check },
  obligation: { Icon: ListTodo, tint: "bg-amber-100 text-amber-800", stripe: "#d97706", action: "Open & complete", ActionIcon: ListTodo },
  signature: { Icon: PenLine, tint: "bg-emerald-100 text-emerald-700", stripe: "#059669", action: "Open & sign", ActionIcon: PenLine },
} as const;

function GroupHeader({ label, count, tone }: { label: string; count: number; tone: "warn" | "default" }) {
  return (
    <div className="flex items-center gap-2 px-0.5">
      {tone === "warn" && <span className="pulse-dot h-2 w-2 rounded-full bg-amber-500" />}
      <span className={cn("text-[11px] font-semibold uppercase tracking-wide", tone === "warn" ? "text-amber-700" : "text-ink-3")}>{label}</span>
      <span className="rounded-full bg-surface-3 px-1.5 text-[10px] font-semibold text-ink-3">{count}</span>
    </div>
  );
}

function InboxRow({ item }: { item: InboxItem }) {
  const meta = KIND_META[item.kind as keyof typeof KIND_META] ?? KIND_META.signature;
  const { Icon, tint, action, ActionIcon } = meta;
  const isHigh = item.priority === "high";
  const stripe = isHigh ? "#f59e0b" : meta.stripe;
  return (
    <Link href={item.href} className="group block">
      <Card className={cn("card-interactive relative overflow-hidden p-4 pl-5")}>
        {/* left accent stripe — colored by kind, amber when high priority */}
        <span className="absolute inset-y-0 left-0 w-1.5" style={{ background: stripe }} aria-hidden />
        <div className="flex items-center gap-3">
          <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl", tint)}>
            <Icon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-semibold text-ink">{item.title}</span>
              {isHigh && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                  <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-amber-500" /> High priority
                </span>
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
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1.5">
            {item.since && (
              <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold tnum", isHigh ? "bg-amber-100 text-amber-800" : "bg-surface-3 text-ink-2")}>
                {timeAgo(item.since).replace(" ago", "")}
              </span>
            )}
            <span className="hidden items-center gap-1 rounded-md bg-accent-subtle px-2 py-1 text-xs font-medium text-accent transition-colors group-hover:bg-accent group-hover:text-accent-fg sm:inline-flex">
              <ActionIcon className="h-3.5 w-3.5" /> {action}
              <ChevronRight className="h-3.5 w-3.5" />
            </span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
