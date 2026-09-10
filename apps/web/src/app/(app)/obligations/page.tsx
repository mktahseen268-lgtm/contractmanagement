"use client";

/**
 * Obligations across the whole repository.
 *
 *   GET  /obligations             every obligation, with the counts an operations view needs
 *   POST /obligations/sweep       run the reminder / escalation pass now
 *   PATCH /contracts/{c}/obligations/{o}   mark one done
 *
 * Replaces the sample-data mockup. The per-contract endpoints already existed; what was
 * missing was the cross-contract view — an obligation tracker you can only read one agreement
 * at a time is a list nobody checks.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BellRing,
  Calendar,
  CheckCircle2,
  Circle,
  ListTodo,
  UserX,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  ErrorBanner,
  Select,
  Skeleton,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import type { ObligationRollup } from "@/lib/types";

type View = "all" | "mine" | "overdue" | "week" | "unassigned";

export default function ObligationsPage() {
  const { me } = useAuth();
  const canSweep =
    me?.user.role === "owner" || me?.user.role === "admin" || me?.user.role === "manager";

  const [data, setData] = useState<ObligationRollup | null>(null);
  const [view, setView] = useState<View>("all");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [swept, setSwept] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (view === "mine") params.set("mine", "true");
    if (view === "overdue") params.set("overdue_only", "true");
    if (view === "week") params.set("due_within_days", "7");
    if (statusFilter) params.set("status_filter", statusFilter);
    api
      .get<ObligationRollup>(`/obligations?${params}`)
      .then(setData)
      .catch(() => setData(null));
  }, [view, statusFilter]);
  useEffect(load, [load]);

  async function markDone(contractId: string, obligationId: string) {
    setError("");
    try {
      await api.patch(`/contracts/${contractId}/obligations/${obligationId}`, {
        status: "done",
      });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't update that obligation.");
    }
  }

  async function sweep() {
    setBusy(true);
    setError("");
    try {
      const result = await api.post<{
        marked_overdue: number;
        reminded: number;
        escalated: number;
      }>("/obligations/sweep", {});
      setSwept(
        `${result.marked_overdue} marked overdue, ${result.reminded} reminded, ${result.escalated} escalated.`,
      );
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The sweep could not run.");
    } finally {
      setBusy(false);
    }
  }

  const items = (data?.items ?? []).filter((i) =>
    view === "unassigned" ? !i.owner_id && i.status !== "done" : true,
  );

  return (
    <div>
      <PageHeader
        title="Obligations"
        subtitle="What every agreement commits us to, and what has slipped"
        actions={
          canSweep ? (
            <Button size="sm" variant="ghost" loading={busy} onClick={sweep}>
              <BellRing className="h-3.5 w-3.5" /> Run reminders
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}
        {swept && (
          <Card className="border-emerald-300/60">
            <CardBody className="py-2 text-sm text-ink-2">{swept}</CardBody>
          </Card>
        )}

        {data === null ? (
          <Skeleton className="h-32" />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-5">
              <Stat label="Open" value={data.summary.open ?? 0} icon={Circle} />
              <Stat
                label="Overdue"
                value={data.summary.overdue ?? 0}
                icon={AlertTriangle}
                tone="text-red-600"
              />
              <Stat label="Due in 7 days" value={data.summary.due_this_week ?? 0} icon={Calendar} />
              <Stat label="Unassigned" value={data.summary.unassigned ?? 0} icon={UserX} />
              <Stat
                label="Completed"
                value={data.summary.done ?? 0}
                icon={CheckCircle2}
                tone="text-emerald-600"
              />
            </div>

            <Card>
              <CardBody className="flex flex-wrap items-center gap-2">
                {(
                  [
                    ["all", "Everything"],
                    ["mine", "Mine"],
                    ["overdue", "Overdue"],
                    ["week", "Due in 7 days"],
                    ["unassigned", "Unassigned"],
                  ] as [View, string][]
                ).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setView(key)}
                    className={`rounded-full px-3 py-1 text-xs transition ${
                      view === key
                        ? "bg-accent text-white"
                        : "bg-surface-3 text-ink-2 hover:text-ink"
                    }`}
                  >
                    {label}
                  </button>
                ))}
                <div className="ml-auto min-w-[150px]">
                  <Select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <option value="">Any status</option>
                    <option value="pending">Pending</option>
                    <option value="overdue">Overdue</option>
                    <option value="done">Done</option>
                    <option value="skipped">Skipped</option>
                  </Select>
                </div>
              </CardBody>
            </Card>

            {items.length === 0 ? (
              <Card>
                <CardBody className="py-10 text-center text-sm text-ink-2">
                  <ListTodo className="mx-auto mb-3 h-10 w-10 text-ink-3" />
                  <div className="text-base font-semibold text-ink">Nothing here</div>
                  <p className="mt-1">
                    Obligations are added on an agreement and tracked here across all of them.
                  </p>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardBody className="divide-y divide-line p-0">
                  {items.map((o) => (
                    <div key={o.id} className="flex flex-wrap items-center gap-2 px-3 py-2.5">
                      {o.status === "done" ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                      ) : o.overdue ? (
                        <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                      ) : (
                        <Circle className="h-4 w-4 shrink-0 text-ink-3" />
                      )}
                      <div className="min-w-[200px] flex-1">
                        <div className="text-sm text-ink">{o.title}</div>
                        <div className="text-[11px] text-ink-3">
                          <Link
                            href={`/contracts/${o.contract_id}`}
                            className="hover:text-ink"
                          >
                            {o.contract_reference} — {o.contract_title}
                          </Link>
                        </div>
                      </div>
                      <div className="text-xs text-ink-2">
                        {o.owner_name || <span className="text-ink-3">unassigned</span>}
                      </div>
                      <div className="min-w-[110px] text-xs">
                        {o.due_date ? (
                          <span className={o.overdue ? "text-red-600" : "text-ink-2"}>
                            {formatDate(o.due_date)}
                            {o.days_left !== null && (
                              <span className="text-ink-3">
                                {" "}
                                {o.days_left < 0
                                  ? `(${Math.abs(o.days_left)}d late)`
                                  : `(${o.days_left}d)`}
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-ink-3">no due date</span>
                        )}
                      </div>
                      <Badge tone={o.status === "done" ? "accent" : "neutral"}>{o.status}</Badge>
                      {o.status !== "done" && o.status !== "skipped" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => markDone(o.contract_id, o.id)}
                        >
                          Mark done
                        </Button>
                      )}
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: typeof Circle;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div
        className={`flex items-center gap-1.5 font-display text-2xl font-semibold ${
          tone ?? "text-ink"
        }`}
      >
        <Icon className="h-4 w-4" />
        {value}
      </div>
      <div className="text-xs text-ink-2">{label}</div>
    </div>
  );
}
