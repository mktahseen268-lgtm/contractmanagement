"use client";

// Obligations Dashboard — PROTOTYPE of a portfolio-wide view of every contract obligation, with
// status, owner, due dates, and reminder cadence. Today obligations are per-contract; this is the
// cross-contract rollup + email reminders. Mockup: sample data + simulated reminder toggle.

import { useMemo, useState } from "react";
import { AlarmClock, CalendarClock, CheckCircle2, Circle, Clock, ListChecks } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/shell";
import { Badge, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";

type Status = "overdue" | "due_soon" | "upcoming" | "done";
type Obligation = {
  id: string; title: string; contract: string; contractId: string; owner: string;
  due: string; daysOut: number; status: Status; category: string; reminder: boolean;
};

const DATA: Obligation[] = [
  { id: "1", title: "Submit Q3 deliverables report", contract: "Northwind MSA", contractId: "a", owner: "You", due: "2026-06-01", daysOut: -2, status: "overdue", category: "Deliverable", reminder: true },
  { id: "2", title: "Pay Q2 invoice", contract: "Lumen Reseller", contractId: "b", owner: "Finance", due: "2026-06-05", daysOut: 2, status: "due_soon", category: "Payment", reminder: true },
  { id: "3", title: "Renewal go/no-go decision", contract: "Platform DPA", contractId: "c", owner: "You", due: "2026-06-09", daysOut: 6, status: "due_soon", category: "Renewal", reminder: true },
  { id: "4", title: "Security review sign-off", contract: "ThiqaTech NDA", contractId: "d", owner: "Legal", due: "2026-06-20", daysOut: 17, status: "upcoming", category: "Compliance", reminder: false },
  { id: "5", title: "Deliver onboarding plan", contract: "Trial Co Order", contractId: "e", owner: "Provider", due: "2026-06-28", daysOut: 25, status: "upcoming", category: "Deliverable", reminder: false },
  { id: "6", title: "Insurance certificate renewal", contract: "Northwind MSA", contractId: "a", owner: "You", due: "2026-05-20", daysOut: 0, status: "done", category: "Compliance", reminder: false },
];

const STATUS_META: Record<Status, { label: string; pill: string; dot: string }> = {
  overdue: { label: "Overdue", pill: "bg-red-50 text-red-700", dot: "#EF4444" },
  due_soon: { label: "Due soon", pill: "bg-amber-50 text-amber-700", dot: "#F59E0B" },
  upcoming: { label: "Upcoming", pill: "bg-blue-50 text-blue-700", dot: "#3E7BFA" },
  done: { label: "Done", pill: "bg-emerald-50 text-emerald-700", dot: "#12B76A" },
};

export default function ObligationsDashboardPage() {
  const [filter, setFilter] = useState<Status | "all">("all");
  const [items, setItems] = useState<Obligation[]>(DATA);

  const counts = useMemo(() => ({
    overdue: items.filter((i) => i.status === "overdue").length,
    due_soon: items.filter((i) => i.status === "due_soon").length,
    upcoming: items.filter((i) => i.status === "upcoming").length,
    done: items.filter((i) => i.status === "done").length,
  }), [items]);

  const shown = filter === "all" ? items : items.filter((i) => i.status === filter);

  function toggleReminder(id: string) {
    setItems((arr) => arr.map((i) => (i.id === id ? { ...i, reminder: !i.reminder } : i)));
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Obligations</span>}
        subtitle="Every obligation across the portfolio — due dates, owners, and email reminders."
      />

      <div className="space-y-4 p-4">
        {/* KPI tiles double as filters */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {([
            ["overdue", AlarmClock], ["due_soon", Clock], ["upcoming", CalendarClock], ["done", CheckCircle2],
          ] as const).map(([k, Icon]) => {
            const on = filter === k;
            return (
              <button
                key={k}
                onClick={() => setFilter(on ? "all" : k)}
                className={`rounded-xl border p-3 text-left transition ${on ? "border-accent ring-1 ring-accent" : "border-line hover:border-ink-3/40"}`}
              >
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <Icon className="h-3.5 w-3.5" style={{ color: STATUS_META[k].dot }} /> {STATUS_META[k].label}
                </div>
                <div className="mt-1 text-2xl font-semibold text-ink tnum">{counts[k]}</div>
              </button>
            );
          })}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5"><ListChecks className="h-4 w-4" /> {filter === "all" ? "All obligations" : STATUS_META[filter].label}</CardTitle>
            <span className="text-xs text-ink-3">{shown.length} item{shown.length === 1 ? "" : "s"}</span>
          </CardHeader>
          <CardBody className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <tr>
                    <th className="px-3 py-2">Obligation</th>
                    <th className="px-3 py-2">Contract</th>
                    <th className="px-3 py-2">Owner</th>
                    <th className="px-3 py-2">Due</th>
                    <th className="px-3 py-2 text-center">Reminder</th>
                    <th className="px-3 py-2 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {shown.map((o) => (
                    <tr key={o.id} className="hover:bg-surface-2">
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          {o.status === "done" ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <Circle className="h-4 w-4 text-ink-3" />}
                          <div>
                            <div className="font-medium text-ink">{o.title}</div>
                            <div className="text-[11px] text-ink-3">{o.category}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <Link href={`/contracts/${o.contractId}`} className="text-ink-2 hover:text-accent">{o.contract}</Link>
                      </td>
                      <td className="px-3 py-2.5"><span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-ink-2">{o.owner}</span></td>
                      <td className="px-3 py-2.5">
                        <div className="text-ink-2">{o.due}</div>
                        {o.status !== "done" && (
                          <div className={`text-[11px] ${o.daysOut < 0 ? "text-red-600" : o.daysOut <= 7 ? "text-amber-600" : "text-ink-3"}`}>
                            {o.daysOut < 0 ? `${-o.daysOut}d overdue` : o.daysOut === 0 ? "today" : `in ${o.daysOut}d`}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <button
                          onClick={() => toggleReminder(o.id)}
                          className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${o.reminder ? "bg-accent" : "bg-surface-3"}`}
                          aria-label="Toggle reminder"
                        >
                          <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${o.reminder ? "translate-x-4" : "translate-x-0.5"}`} />
                        </button>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_META[o.status].pill}`}>{STATUS_META[o.status].label}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">
              Reminder-enabled obligations email their owner at 7 / 3 / 1 days before the due date, and on the day it goes overdue.
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
