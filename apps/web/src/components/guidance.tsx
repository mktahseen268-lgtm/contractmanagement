"use client";

/**
 * Guided actions and the stage tracker (Phase 9, item 4).
 *
 *   GET /contracts/{id}/guidance   — where it is, and what to do next
 *   GET /guidance/next             — across the workspace, for the dashboard
 *
 * Everything is derived server-side from current state, so nothing here caches a suggestion:
 * a stale "send for signature" on an agreement somebody already sent is how a helper panel
 * loses its audience.
 */

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Check, CircleAlert, Info } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";

export type Suggestion = {
  key: string;
  title: string;
  detail: string;
  action: string;
  permission: string;
  severity: "critical" | "warning" | "info";
  href: string;
};

export type StageProgress = {
  stage: string;
  label: string;
  index: number;
  total: number;
  stages: { key: string; label: string; state: "done" | "current" | "todo" }[];
  is_closed: boolean;
};

const SEVERITY = {
  critical: {
    icon: CircleAlert,
    // Colour is not the only signal — the icon differs too. A palette that carries meaning by
    // hue alone fails WCAG 1.4.1 and fails anyone with a colour-vision deficiency.
    tone: "border-red-200 bg-red-50 text-red-900",
    iconTone: "text-red-600",
    label: "Needs attention",
  },
  warning: {
    icon: AlertTriangle,
    tone: "border-amber-200 bg-amber-50 text-amber-900",
    iconTone: "text-amber-600",
    label: "Worth doing",
  },
  info: {
    icon: Info,
    tone: "border-line bg-surface-2 text-ink",
    iconTone: "text-accent",
    label: "Suggestion",
  },
} as const;

/** Intake → Drafting → Review → Approval → Signature → Active. */
export function StageTracker({ progress }: { progress: StageProgress }) {
  return (
    <ol
      className="flex flex-wrap items-center gap-1.5"
      aria-label={`Stage: ${progress.label}${progress.is_closed ? " (closed)" : ""}`}
    >
      {progress.stages.map((stage) => (
        <li key={stage.key} className="flex items-center gap-1.5">
          <span
            // `aria-current` is what tells a screen reader which stage this is. Without it the
            // list reads as six equal items and the whole tracker conveys nothing.
            aria-current={stage.state === "current" ? "step" : undefined}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium",
              stage.state === "done" && "bg-accent-subtle text-accent",
              stage.state === "current" && "bg-accent text-white",
              stage.state === "todo" && "bg-surface-3 text-ink-3",
            )}
          >
            {stage.state === "done" && <Check className="h-3 w-3" aria-hidden="true" />}
            {stage.label}
            {stage.state === "current" && <span className="sr-only"> (current stage)</span>}
          </span>
          {stage.key !== progress.stages[progress.stages.length - 1].key && (
            <ArrowRight className="h-3 w-3 text-ink-3 rtl:rotate-180" aria-hidden="true" />
          )}
        </li>
      ))}
    </ol>
  );
}

export function SuggestionList({
  actions,
  permissions,
}: {
  actions: Suggestion[];
  permissions?: string[];
}) {
  if (!actions.length) return null;

  return (
    <ul className="space-y-2">
      {actions.map((a) => {
        const meta = SEVERITY[a.severity] ?? SEVERITY.info;
        const Icon = meta.icon;
        // A suggestion the reader cannot carry out is shown as information, not as an offer —
        // an action button that always refuses is worse than a sentence explaining the state.
        const actionable =
          !a.permission || !permissions || permissions.includes(a.permission);

        return (
          <li key={a.key} className={cn("rounded-lg border p-3", meta.tone)}>
            <div className="flex items-start gap-2">
              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", meta.iconTone)} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">
                  <span className="sr-only">{meta.label}: </span>
                  {a.title}
                </div>
                {a.detail && <p className="mt-0.5 text-xs opacity-90">{a.detail}</p>}
                {a.href && actionable && (
                  <Link
                    href={a.href}
                    className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium underline underline-offset-2"
                  >
                    Go there <ArrowRight className="h-3 w-3 rtl:rotate-180" aria-hidden="true" />
                  </Link>
                )}
                {!actionable && (
                  <p className="mt-1 text-[11px] opacity-75">
                    Someone with the right permission needs to do this.
                  </p>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** The panel on an agreement: where it is, and what to do next. */
export function ContractGuidance({
  contractId,
  permissions,
}: {
  contractId: string;
  permissions?: string[];
}) {
  const [data, setData] = useState<{ progress: StageProgress; actions: Suggestion[] } | null>(
    null,
  );
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .get<{ progress: StageProgress; actions: Suggestion[] }>(
        `/contracts/${contractId}/guidance`,
      )
      .then((d) => alive && setData(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [contractId]);

  // Guidance is an aid. If it cannot load, the agreement page still works — showing an error
  // banner for a failed hint would make a helper feel like a fault.
  if (failed) return null;
  if (!data) return <Skeleton className="h-24" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Where this is, and what is next</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <StageTracker progress={data.progress} />
        {data.actions.length > 0 ? (
          <SuggestionList actions={data.actions} permissions={permissions} />
        ) : (
          <p className="text-sm text-ink-2">
            {data.progress.is_closed
              ? "This agreement is closed. Nothing further is needed."
              : "Nothing needs doing right now."}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

/** The dashboard panel: what is waiting on this person across the workspace. */
export function WorkspaceGuidance() {
  const [actions, setActions] = useState<Suggestion[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .get<Suggestion[]>("/guidance/next")
      .then((d) => alive && setActions(d))
      .catch(() => alive && setActions([]));
    return () => {
      alive = false;
    };
  }, []);

  if (actions === null) return <Skeleton className="h-24" />;
  if (!actions.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>What needs you</CardTitle>
      </CardHeader>
      <CardBody>
        <SuggestionList actions={actions} />
      </CardBody>
    </Card>
  );
}
