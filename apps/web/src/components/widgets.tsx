"use client";

import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, FileText, FileUp, FilePlus2, Upload, PenLine, Inbox } from "lucide-react";
import { Card } from "@/components/ui";
import { activityVerb, actorColor, cn, statusMeta, timeAgo, titleCase } from "@/lib/utils";
import { Avatar } from "@/components/ui";
import { Sparkline, useCountUp } from "@/components/charts";
import type { ActivityItem, StatusCount } from "@/lib/types";

const TONE_TEXT = {
  default: "",
  accent: "text-accent",
  warn: "text-amber-700",
  danger: "text-danger",
} as const;

const TONE_CHIP = {
  default: "bg-surface-3 text-ink-2",
  accent: "bg-accent-subtle text-accent",
  warn: "bg-warn-bg text-warn",
  danger: "bg-danger-bg text-danger",
} as const;

const TONE_SPARK = {
  default: "var(--color-accent)",
  accent: "var(--color-accent)",
  warn: "#B54708",
  danger: "#B42318",
} as const;

export function KpiCard({
  label,
  value,
  sub,
  href,
  tone = "default",
  icon: Icon,
  sparkline,
  delta,
  hero = false,
}: {
  label: string;
  value: string | number;
  sub?: string;
  href?: string;
  tone?: "default" | "accent" | "warn" | "danger";
  icon?: typeof Inbox;
  sparkline?: number[];
  delta?: number | null;
  /** gradient "hero" treatment for a featured/primary metric (command-center style) */
  hero?: boolean;
}) {
  const isNum = typeof value === "number";
  const counted = useCountUp(isNum ? value : 0);
  const display = isNum ? Math.round(counted).toLocaleString() : value;

  // ---- hero: accent→ai gradient, white text (the spotlight metric) ----
  if (hero) {
    const inner = (
      <Card className={cn("relative overflow-hidden border-0 bg-gradient-to-br from-accent to-ai p-4 text-white shadow-glow", href && "card-interactive cursor-pointer")}>
        <div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-white/10 blur-2xl" />
        <div className="relative flex items-center justify-between gap-2">
          {Icon && (
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/20">
              <Icon className="h-4 w-4" />
            </span>
          )}
          {delta != null && <DeltaChip delta={delta} onDark />}
        </div>
        <div className="relative mt-3 font-display text-[26px] font-bold leading-none tnum">{display}</div>
        <div className="relative mt-1.5 text-[13px] font-medium text-white/80">{label}</div>
        {sub && <div className="relative mt-0.5 text-xs text-white/70">{sub}</div>}
        {sparkline && sparkline.length > 1 && (
          <div className="relative mt-2 -mb-1 opacity-90">
            <Sparkline data={sparkline} stroke="#ffffff" />
          </div>
        )}
      </Card>
    );
    return href ? <Link href={href}>{inner}</Link> : inner;
  }

  // ---- standard: icon (rounded chip) top-left, delta top-right, big number, label ----
  const inner = (
    <Card className={cn("relative overflow-hidden p-4", href && "card-interactive cursor-pointer")}>
      <div className="flex items-center justify-between gap-2">
        {Icon ? (
          <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg", TONE_CHIP[tone])}>
            <Icon className="h-4 w-4" />
          </span>
        ) : <span />}
        {delta != null && <DeltaChip delta={delta} />}
      </div>
      <div className={cn("mt-3 font-display text-2xl font-bold tnum text-ink", TONE_TEXT[tone])}>{display}</div>
      <div className="mt-0.5 text-[13px] font-medium text-ink-3">{label}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-3">{sub}</div>}
      {sparkline && sparkline.length > 1 && (
        <div className="mt-2 -mb-1">
          <Sparkline data={sparkline} stroke={TONE_SPARK[tone]} />
        </div>
      )}
    </Card>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

function DeltaChip({ delta, onDark = false }: { delta: number; onDark?: boolean }) {
  const flat = Math.abs(delta) < 0.5;
  const up = delta > 0;
  const cls = onDark
    ? "bg-white/20 text-white"
    : flat
      ? "text-ink-3 bg-surface-3"
      : up
        ? "text-ok bg-ok-bg"
        : "text-danger bg-danger-bg";
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold leading-none", cls)}>
      {!flat && <Icon className="h-3 w-3" />}
      {flat ? "—" : `${Math.abs(delta).toFixed(0)}%`}
    </span>
  );
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: typeof Inbox;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface-2 px-6 py-12 text-center">
      <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-accent-subtle text-accent">
        <Icon className="h-6 w-6" />
      </div>
      <div className="text-base font-semibold text-ink">{title}</div>
      {description && <div className="mt-1 max-w-sm text-sm text-ink-2">{description}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

const TILES: { label: string; href: string; icon: typeof FileText; hue: string; bg: string }[] = [
  { label: "New from template", href: "/contracts/new?from=template", icon: FileText, hue: "#5B8DEF", bg: "#EAF1FE" },
  { label: "Upload & scan", href: "/intelligence", icon: FileUp, hue: "#8B7BF5", bg: "#F1EEFD" },
  { label: "Blank contract", href: "/contracts/new", icon: FilePlus2, hue: "#2BC0D4", bg: "#E6F8FB" },
  { label: "Import bulk", href: "/intelligence?mode=bulk", icon: Upload, hue: "#F6B83C", bg: "#FEF5E4" },
  { label: "Request signature", href: "/contracts?status=approved", icon: PenLine, hue: "#F5736B", bg: "#FDECEB" },
];

export function QuickCreateTiles() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {TILES.map((t) => {
        const Icon = t.icon;
        return (
          <Link
            key={t.label}
            href={t.href}
            className="card-interactive group flex flex-col items-center gap-2.5 rounded-2xl border border-line bg-white p-4 shadow-card"
          >
            <span className="grid h-11 w-11 place-items-center rounded-xl transition-transform duration-150 group-hover:scale-110" style={{ background: t.bg }}>
              <Icon className="h-5 w-5" style={{ color: t.hue }} />
            </span>
            <span className="text-center text-[13px] font-medium text-ink">{t.label}</span>
          </Link>
        );
      })}
    </div>
  );
}

export function ActivityFeed({ items }: { items: ActivityItem[] }) {
  if (!items.length) return <div className="px-1 py-6 text-center text-sm text-ink-3">No activity yet.</div>;
  return (
    <ul className="space-y-3">
      {items.map((a) => (
        <li key={a.id} className="flex items-start gap-3 text-sm">
          <Avatar name={a.actor_name} color={actorColor(a.actor_name)} size={26} />
          <div className="min-w-0 flex-1">
            <div className="leading-snug text-ink-2">
              <span className="font-medium text-ink">{a.actor_name}</span> {activityVerb(a.action)}{" "}
              {a.object_id && a.object_type === "contract" ? (
                <Link href={`/contracts/${a.object_id}`} className="font-medium text-accent hover:underline">
                  {a.object_label || "a contract"}
                </Link>
              ) : (
                <span className="font-medium text-ink">{a.object_label}</span>
              )}
            </div>
            <div className="text-xs text-ink-3">{timeAgo(a.at)}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function StatusDistribution({ counts }: { counts: StatusCount[] }) {
  const total = counts.reduce((s, c) => s + c.count, 0) || 1;
  const sorted = [...counts].sort((a, b) => b.count - a.count);
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-3">
        {sorted.map((c) => (
          <div key={c.status} style={{ width: `${(c.count / total) * 100}%`, background: statusMeta(c.status).dot }} title={`${titleCase(c.status)}: ${c.count}`} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {sorted.map((c) => (
          <span key={c.status} className="inline-flex items-center gap-1.5 text-xs text-ink-2">
            <span className="h-2 w-2 rounded-full" style={{ background: statusMeta(c.status).dot }} />
            {statusMeta(c.status).label} <span className="font-medium text-ink tnum">{c.count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
