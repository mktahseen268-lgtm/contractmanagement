"use client";

import Link from "next/link";
import { FileText, FileUp, FilePlus2, Upload, PenLine, Inbox } from "lucide-react";
import { Card } from "@/components/ui";
import { activityVerb, actorColor, cn, statusMeta, timeAgo, titleCase } from "@/lib/utils";
import { Avatar } from "@/components/ui";
import type { ActivityItem, StatusCount } from "@/lib/types";

export function KpiCard({
  label,
  value,
  sub,
  href,
  tone = "default",
}: {
  label: string;
  value: string | number;
  sub?: string;
  href?: string;
  tone?: "default" | "accent" | "warn" | "danger";
}) {
  const toneCls = {
    default: "",
    accent: "text-accent",
    warn: "text-amber-700",
    danger: "text-danger",
  }[tone];
  const inner = (
    <Card className={cn("p-4 transition-shadow", href && "hover:shadow-lift")}>
      <div className="text-[13px] font-medium text-ink-3">{label}</div>
      <div className={cn("mt-1 text-2xl font-semibold tnum text-ink", toneCls)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-3">{sub}</div>}
    </Card>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
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
            className="group flex flex-col items-center gap-2.5 rounded-2xl border border-line bg-white p-4 shadow-card transition-shadow hover:shadow-lift"
          >
            <span className="grid h-11 w-11 place-items-center rounded-xl" style={{ background: t.bg }}>
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
