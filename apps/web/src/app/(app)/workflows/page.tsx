"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Workflow } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { EmptyState } from "@/components/widgets";
import { timeAgo, titleCase } from "@/lib/utils";
import type { WorkflowDefinitionListItem } from "@/lib/types";

const STATUS_TONE: Record<string, string> = {
  active: "text-emerald-800 bg-emerald-100",
  draft: "text-slate-700 bg-slate-100",
  archived: "text-slate-500 bg-slate-100",
};

export default function WorkflowsPage() {
  const [items, setItems] = useState<WorkflowDefinitionListItem[] | null>(null);

  useEffect(() => {
    api.get<WorkflowDefinitionListItem[]>("/workflows").then(setItems).catch(() => setItems([]));
  }, []);

  return (
    <div>
      <PageHeader
        title="Workflows"
        subtitle="Approval-routing — a contract submitted for approval runs through its workflow's steps in order."
        actions={
          <Link href="/workflows/new">
            <Button>
              <Plus className="h-4 w-4" /> New workflow
            </Button>
          </Link>
        }
      />
      <div className="space-y-4 p-6">
        {items === null && <Skeleton className="h-40 rounded-xl" />}
        {items && items.length === 0 && (
          <EmptyState
            icon={Workflow}
            title="No workflows yet"
            description="Create a workflow with one or more approval steps, mark it active, and set it as the default for some contract types — then contracts submitted for approval route through it."
            action={
              <Link href="/workflows/new">
                <Button>
                  <Plus className="h-4 w-4" /> New workflow
                </Button>
              </Link>
            }
          />
        )}
        {items && items.length > 0 && (
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <th className="px-4 py-2.5">Workflow</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Steps</th>
                  <th className="px-4 py-2.5">Default for</th>
                  <th className="px-4 py-2.5">Runs</th>
                  <th className="px-4 py-2.5">Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((w) => (
                  <tr key={w.id} className="border-b border-line last:border-0 hover:bg-surface-2">
                    <td className="px-4 py-3">
                      <Link href={`/workflows/${w.id}`} className="font-medium text-accent hover:underline">
                        {w.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[w.status] ?? "text-slate-700 bg-slate-100"}`}>{titleCase(w.status)}</span>
                    </td>
                    <td className="px-4 py-3 tnum text-ink-2">{w.step_count}</td>
                    <td className="px-4 py-3">
                      {w.default_for_types.length === 0 ? (
                        <span className="text-ink-3">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {w.default_for_types.map((t) => (
                            <Badge key={t} tone="neutral">{t.toUpperCase()}</Badge>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 tnum text-ink-2">{w.run_count}</td>
                    <td className="px-4 py-3 text-ink-3">{timeAgo(w.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
        <p className="text-[11px] text-ink-3">
          v1 is linear (sequential approvals); parallel groups, conditional routing, SLAs &amp; escalation are designed in <span className="font-mono">docs/10</span>.
        </p>
      </div>
    </div>
  );
}
