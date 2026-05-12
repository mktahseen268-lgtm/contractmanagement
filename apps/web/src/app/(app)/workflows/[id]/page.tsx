"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Card, CardBody, CardHeader, CardTitle, ErrorBanner, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { WorkflowBuilder } from "@/components/workflow-builder";
import { timeAgo } from "@/lib/utils";
import type { WorkflowDefinitionDetail, WorkflowRunListItem } from "@/lib/types";

const RUN_TONE: Record<string, string> = {
  running: "text-amber-800 bg-amber-100",
  approved: "text-emerald-800 bg-emerald-100",
  rejected: "text-red-800 bg-red-100",
  changes_requested: "text-orange-800 bg-orange-100",
  cancelled: "text-slate-600 bg-slate-100",
};

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [wf, setWf] = useState<WorkflowDefinitionDetail | null>(null);
  const [runs, setRuns] = useState<WorkflowRunListItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<WorkflowDefinitionDetail>(`/workflows/${id}`).then(setWf).catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load this workflow."));
    api.get<WorkflowRunListItem[]>(`/workflows/${id}/runs`).then(setRuns).catch(() => setRuns([]));
  }, [id]);

  if (error && !wf) {
    return (
      <div className="p-6">
        <ErrorBanner message={error} />
        <Link href="/workflows" className="mt-3 inline-block text-sm text-accent hover:underline">← Back to workflows</Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={wf ? `Edit: ${wf.name}` : "Workflow"}
        subtitle={
          <span className="flex items-center gap-2">
            <Link href="/workflows" className="text-accent hover:underline">Workflows</Link>
            <span>›</span>
            <span>{wf?.name ?? "…"}</span>
          </span>
        }
      />
      {!wf ? (
        <div className="mx-auto max-w-2xl p-6">
          <Skeleton className="h-96 rounded-xl" />
        </div>
      ) : (
        <>
          <WorkflowBuilder initial={wf} />
          <div className="mx-auto max-w-2xl px-6 pb-8">
            <Card>
              <CardHeader>
                <CardTitle>Runs</CardTitle>
                <span className="text-xs text-ink-3">{runs?.length ?? 0} run(s)</span>
              </CardHeader>
              <CardBody>
                {runs === null && <Skeleton className="h-16" />}
                {runs && runs.length === 0 && <p className="text-sm text-ink-3">No contracts have gone through this workflow yet.</p>}
                <div className="divide-y divide-line">
                  {runs?.map((r) => (
                    <div key={r.id} className="flex items-center gap-3 py-2.5 text-sm">
                      <span className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${RUN_TONE[r.status] ?? "text-slate-700 bg-slate-100"}`}>
                        {r.status === "running" ? `Step: ${r.current_step_name}` : r.status.replace(/_/g, " ")}
                      </span>
                      <Link href={`/contracts/${r.contract_id}`} className="min-w-0 flex-1 truncate font-medium text-accent hover:underline">
                        {r.contract_title}
                      </Link>
                      <span className="hidden text-xs text-ink-3 sm:inline">by {r.started_by_name}</span>
                      <span className="text-xs text-ink-3">{timeAgo(r.started_at)}</span>
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
