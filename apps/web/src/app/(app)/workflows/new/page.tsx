"use client";

import { PageHeader } from "@/components/shell";
import { WorkflowBuilder } from "@/components/workflow-builder";

export default function NewWorkflowPage() {
  return (
    <div>
      <PageHeader title="New workflow" subtitle="Define the approval steps, then mark it active to use it." />
      <WorkflowBuilder />
    </div>
  );
}
