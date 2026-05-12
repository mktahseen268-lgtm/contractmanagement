"use client";

import { cn } from "@/lib/utils";
import { LIFECYCLE_SPINE, riskMeta, statusMeta, titleCase } from "@/lib/utils";

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const m = statusMeta(status);
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", m.pill, className)}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.dot }} />
      {m.label}
    </span>
  );
}

export function RiskBadge({ level, className }: { level: string; className?: string }) {
  const m = riskMeta(level);
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", m.pill, className)}>
      ▲ {m.label}
    </span>
  );
}

/** Compact dot-track for list rows. */
export function LifecycleDots({ status, className }: { status: string; className?: string }) {
  // terminal-ish states that aren't on the spine: show all spine done up to "active" if signed/active else just the index
  const spine = LIFECYCLE_SPINE as readonly string[];
  let activeIdx = spine.indexOf(status);
  if (activeIdx === -1) {
    if (["signed", "active", "expiring", "expired", "renewed", "terminated"].includes(status)) activeIdx = spine.length - 1;
    else if (["changes_requested"].includes(status)) activeIdx = spine.indexOf("in_review");
    else activeIdx = 0;
  }
  return (
    <span className={cn("inline-flex items-center gap-1", className)} title={titleCase(status)}>
      {spine.map((s, i) => (
        <span
          key={s}
          className="h-1.5 w-3 rounded-full"
          style={{ background: i <= activeIdx ? statusMeta(s).dot : "#E6E8EB" }}
        />
      ))}
    </span>
  );
}

/** Full labelled bar for the contract header. */
export function LifecycleBar({ status }: { status: string }) {
  const spine = LIFECYCLE_SPINE as readonly string[];
  let activeIdx = spine.indexOf(status);
  const offSpine = activeIdx === -1;
  if (offSpine) {
    if (["signed", "active", "expiring", "expired", "renewed", "terminated"].includes(status)) activeIdx = spine.length - 1;
    else if (status === "changes_requested") activeIdx = spine.indexOf("in_review");
    else activeIdx = 0;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
      {spine.map((s, i) => {
        const done = i < activeIdx;
        const current = i === activeIdx;
        const m = statusMeta(s);
        return (
          <div key={s} className="flex items-center gap-1.5">
            <div className="flex items-center gap-1.5">
              <span
                className={cn(
                  "flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-bold text-white",
                  !done && !current && "bg-line",
                )}
                style={done || current ? { background: m.dot } : undefined}
              >
                {done ? "✓" : ""}
              </span>
              <span className={cn("text-xs", current ? "font-semibold text-ink" : "text-ink-3")}>{m.label}</span>
            </div>
            {i < spine.length - 1 && <span className="mx-0.5 h-px w-5 bg-line" />}
          </div>
        );
      })}
      {offSpine && !["signed", "active", "expiring", "expired", "renewed"].includes(status) && (
        <StatusPill status={status} className="ml-2" />
      )}
    </div>
  );
}
