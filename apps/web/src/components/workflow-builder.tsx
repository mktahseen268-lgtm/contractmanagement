"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, Flag, Play, Plus, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select } from "@/components/ui";
import { CONTRACT_TYPES } from "@/lib/utils";
import type { User, WorkflowDefinitionDetail } from "@/lib/types";

interface StepRow {
  name: string;
  assignee: string; // "role:approver" | "role:manager" | "role:admin" | "role:owner" | "user:<id>"
}

const ROLE_ASSIGNEES = [
  { v: "role:approver", label: "Any approver (or above)" },
  { v: "role:manager", label: "Any manager (or above)" },
  { v: "role:admin", label: "Any admin (or above)" },
  { v: "role:owner", label: "The workspace owner" },
];

export function WorkflowBuilder({ initial }: { initial?: WorkflowDefinitionDetail }) {
  const router = useRouter();
  const isEdit = !!initial;
  const [users, setUsers] = useState<User[]>([]);
  const [name, setName] = useState(initial?.name ?? "");
  const [statusVal, setStatusVal] = useState<"draft" | "active" | "archived">(initial?.status ?? "draft");
  const [defaultTypes, setDefaultTypes] = useState<string[]>(initial?.default_for_types ?? []);
  const [steps, setSteps] = useState<StepRow[]>(
    initial?.steps?.map((s) => ({ name: s.name, assignee: `${s.assignee_kind}:${s.assignee_value}` })) ?? [
      { name: "Manager review", assignee: "role:manager" },
    ],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<User[]>("/users").then(setUsers).catch(() => {});
  }, []);

  function updateStep(i: number, patch: Partial<StepRow>) {
    setSteps((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  }
  function move(i: number, dir: -1 | 1) {
    setSteps((s) => {
      const j = i + dir;
      if (j < 0 || j >= s.length) return s;
      const c = [...s];
      [c[i], c[j]] = [c[j], c[i]];
      return c;
    });
  }
  const removeStep = (i: number) => setSteps((s) => s.filter((_, j) => j !== i));
  const addStep = () => setSteps((s) => [...s, { name: `Step ${s.length + 1}`, assignee: "role:approver" }]);
  const toggleType = (t: string) => setDefaultTypes((d) => (d.includes(t) ? d.filter((x) => x !== t) : [...d, t]));

  function toPayload() {
    return {
      name: name.trim(),
      status: statusVal,
      default_for_types: statusVal === "archived" ? [] : defaultTypes,
      steps: steps
        .filter((s) => s.name.trim())
        .map((s) => {
          const [kind, ...rest] = s.assignee.split(":");
          return { name: s.name.trim(), assignee_kind: kind === "user" ? "user" : "role", assignee_value: rest.join(":") || "approver" };
        }),
    };
  }

  async function save() {
    if (!name.trim()) {
      setError("Give the workflow a name.");
      return;
    }
    if (statusVal === "active" && !steps.some((s) => s.name.trim())) {
      setError("An active workflow needs at least one step.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const p = toPayload();
      const w = isEdit
        ? await api.patch<WorkflowDefinitionDetail>(`/workflows/${initial!.id}`, p)
        : await api.post<WorkflowDefinitionDetail>("/workflows", p);
      router.push(`/workflows/${w.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save the workflow.");
      setSaving(false);
    }
  }

  async function archive() {
    if (!initial) return;
    if (!window.confirm(`Archive "${initial.name}"? It won't be available for new submissions (in-flight runs continue).`)) return;
    setSaving(true);
    try {
      await api.del(`/workflows/${initial.id}`);
      router.push("/workflows");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't archive.");
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 px-6 py-6">
      <ErrorBanner message={error} />
      <Card>
        <CardBody className="space-y-4">
          <Field label="Workflow name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Standard approval" autoFocus />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Status" hint="Only active workflows can be assigned to contracts.">
              <Select value={statusVal} onChange={(e) => setStatusVal(e.target.value as "draft" | "active" | "archived")}>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                {isEdit && <option value="archived">Archived</option>}
              </Select>
            </Field>
          </div>
          <div>
            <div className="mb-1.5 text-[13px] font-medium text-ink-2">Default for contract types</div>
            <div className="flex flex-wrap gap-2">
              {CONTRACT_TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => toggleType(t.value)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                    defaultTypes.includes(t.value) ? "border-accent bg-accent-subtle text-accent" : "border-line text-ink-2 hover:bg-surface-3"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-ink-3">Contracts of these types use this workflow when submitted for approval (unless a different one is chosen).</p>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Approval steps</CardTitle>
          <Button size="sm" variant="ghost" onClick={addStep}>
            <Plus className="h-3.5 w-3.5" /> Add step
          </Button>
        </CardHeader>
        <CardBody>
          <div className="flex flex-col items-stretch gap-0">
            <div className="mx-auto inline-flex items-center gap-1.5 rounded-full bg-surface-3 px-3 py-1 text-xs font-medium text-ink-2">
              <Play className="h-3 w-3" /> Submitted for approval
            </div>
            {steps.map((s, i) => (
              <div key={i} className="flex flex-col items-stretch">
                <div className="mx-auto h-4 w-px bg-line" />
                <div className="flex items-start gap-3 rounded-lg border border-line bg-surface-2 p-3">
                  <span className="mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-fg">{i + 1}</span>
                  <div className="grid flex-1 gap-2 sm:grid-cols-2">
                    <Input value={s.name} onChange={(e) => updateStep(i, { name: e.target.value })} placeholder="Step name (e.g. Manager review)" />
                    <Select value={s.assignee} onChange={(e) => updateStep(i, { assignee: e.target.value })}>
                      <optgroup label="By role">
                        {ROLE_ASSIGNEES.map((r) => (
                          <option key={r.v} value={r.v}>{r.label}</option>
                        ))}
                      </optgroup>
                      {users.length > 0 && (
                        <optgroup label="A specific person">
                          {users.map((u) => (
                            <option key={u.id} value={`user:${u.id}`}>{u.name}</option>
                          ))}
                        </optgroup>
                      )}
                    </Select>
                  </div>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <button type="button" title="Move up" onClick={() => move(i, -1)} disabled={i === 0} className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-3 disabled:opacity-30">
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" title="Move down" onClick={() => move(i, 1)} disabled={i === steps.length - 1} className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-3 disabled:opacity-30">
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" title="Remove step" onClick={() => removeStep(i)} className="grid h-7 w-7 place-items-center rounded-md text-danger hover:bg-surface-3">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            <div className="mx-auto h-4 w-px bg-line" />
            <div className="mx-auto inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800">
              <Flag className="h-3 w-3" /> Approved → ready for signature
            </div>
          </div>
          {steps.length === 0 && <p className="mt-3 text-center text-sm text-ink-3">Add at least one step. (A workflow with no steps means the contract just goes to “in review”.)</p>}
        </CardBody>
      </Card>

      <div className="flex items-center justify-between">
        {isEdit ? (
          <Button variant="ghost" onClick={archive} disabled={saving}>
            Archive workflow
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => router.push("/workflows")}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving}>
            {isEdit ? "Save changes" : "Create workflow"}
          </Button>
        </div>
      </div>
    </div>
  );
}
