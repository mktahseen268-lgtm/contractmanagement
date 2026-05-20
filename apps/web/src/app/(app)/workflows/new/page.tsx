"use client";

import dynamic from "next/dynamic";
import { PageHeader } from "@/components/shell";
import { Skeleton } from "@/components/ui";

// The builder is the heaviest non-editor component (drag state, node graph). Lazy-load it so it
// doesn't ship in the initial /workflows/new route JS; show a skeleton while the chunk loads.
const WorkflowBuilder = dynamic(() => import("@/components/workflow-builder").then((m) => m.WorkflowBuilder), {
  ssr: false,
  loading: () => <div className="mx-auto max-w-2xl p-6"><Skeleton className="h-96 rounded-xl" /></div>,
});

export default function NewWorkflowPage() {
  return (
    <div>
      <PageHeader title="New workflow" subtitle="Define the approval steps, then mark it active to use it." />
      <WorkflowBuilder />
    </div>
  );
}
