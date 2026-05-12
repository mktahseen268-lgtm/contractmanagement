"use client";

import Link from "next/link";
import { Workflow } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { EmptyState } from "@/components/widgets";
import { Button } from "@/components/ui";

export default function WorkflowsPage() {
  return (
    <div>
      <PageHeader title="Workflows" subtitle="Visual approval-routing builder" />
      <div className="p-6">
        <EmptyState
          icon={Workflow}
          title="Workflow builder — in the blueprint"
          description="The visual, drag-and-drop approval-routing canvas (sequential / parallel / conditional steps, SLAs, escalation) is fully specced in docs/10-workflow-builder.md. This scaffold ships the contract lifecycle state machine you can drive from a contract's detail page — the workflow engine sits on top of it."
          action={
            <Link href="/contracts">
              <Button variant="secondary">Go to contracts</Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}
