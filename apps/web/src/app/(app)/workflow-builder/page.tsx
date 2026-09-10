"use client";

/**
 * Workflow builder — designs the stage graph the Phase 4 engine runs.
 *
 * Replaces the drag-and-drop mockup. The thing being designed is not a flowchart, it is a
 * short list of **stages**, each holding the reviewers who work **at the same time**. That is
 * the RFI's core mechanic, so the editor makes concurrency the obvious default: adding a
 * second reviewer to a stage puts them alongside, not after.
 *
 * Everything here persists to /workflows. Nothing is sample data.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  Check,
  ChevronDown,
  Clock,
  GitBranch,
  Plus,
  Save,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorBanner,
  Field,
  Input,
  Select,
  Skeleton,
} from "@/components/ui";
import { STAGE_POLICIES } from "@/lib/types";
import type {
  StagePolicy,
  User,
  WorkflowDefinitionDetail,
  WorkflowDefinitionListItem,
  WorkflowStageDef,
  WorkflowStepDef,
} from "@/lib/types";

const ROLES = ["reviewer", "author", "approver", "manager", "admin", "owner"];
const CONTRACT_TYPES = ["nda", "msa", "lease", "employment", "vendor", "service", "other"];

function emptyStep(): WorkflowStepDef {
  return { name: "", assignee_kind: "role", assignee_value: "approver" };
}

function emptyStage(index: number): WorkflowStageDef {
  return {
    name: index === 0 ? "Review" : `Stage ${index + 1}`,
    policy: "all",
    threshold: 0,
    sla_hours: 48,
    escalate_to_user_id: null,
    steps: [emptyStep()],
  };
}

/** Promote a legacy flat definition so it can be edited here without losing anything. */
function toStages(def: WorkflowDefinitionDetail): WorkflowStageDef[] {
  if (def.stages?.length) return structuredClone(def.stages);
  return (def.steps ?? []).map((s, i) => ({
    name: s.name || `Stage ${i + 1}`,
    policy: "all" as StagePolicy,
    threshold: 0,
    sla_hours: 0,
    escalate_to_user_id: null,
    steps: [{ ...s }],
  }));
}

export default function WorkflowBuilderPage() {
  const [list, setList] = useState<WorkflowDefinitionListItem[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<WorkflowDefinitionDetail | null>(null);
  const [stages, setStages] = useState<WorkflowStageDef[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(() => {
    api
      .get<WorkflowDefinitionListItem[]>("/workflows", { cache: false })
      .then(setList)
      .catch(() => setList([]));
  }, []);

  useEffect(() => {
    loadList();
    api.get<User[]>("/users").then(setUsers).catch(() => setUsers([]));
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDraft(null);
      setStages([]);
      return;
    }
    api
      .get<WorkflowDefinitionDetail>(`/workflows/${selectedId}`, { cache: false })
      .then((d) => {
        setDraft(d);
        setStages(toStages(d));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load that workflow."));
  }, [selectedId]);

  const problems = useMemo(() => validate(stages), [stages]);

  function patchStage(index: number, patch: Partial<WorkflowStageDef>) {
    setStages((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
    setSaved(false);
  }

  function patchStep(stageIndex: number, stepIndex: number, patch: Partial<WorkflowStepDef>) {
    setStages((prev) =>
      prev.map((s, i) =>
        i === stageIndex
          ? { ...s, steps: s.steps.map((st, j) => (j === stepIndex ? { ...st, ...patch } : st)) }
          : s,
      ),
    );
    setSaved(false);
  }

  async function createWorkflow() {
    setBusy(true);
    setError("");
    try {
      const created = await api.post<WorkflowDefinitionDetail>("/workflows", {
        name: "New workflow",
        status: "draft",
        default_for_types: [],
        steps: [],
        stages: [emptyStage(0)],
      });
      loadList();
      setSelectedId(created.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the workflow.");
    } finally {
      setBusy(false);
    }
  }

  async function save(nextStatus?: string) {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.patch<WorkflowDefinitionDetail>(`/workflows/${draft.id}`, {
        name: draft.name,
        default_for_types: draft.default_for_types,
        stages,
        ...(nextStatus ? { status: nextStatus } : {}),
      });
      setDraft(updated);
      setStages(toStages(updated));
      setSaved(true);
      loadList();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the workflow.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Workflow builder"
        subtitle="Design the review stages. Reviewers in the same stage work concurrently."
        actions={
          <Button onClick={createWorkflow} disabled={busy}>
            <Plus className="h-4 w-4" /> New workflow
          </Button>
        }
      />

      {error && <ErrorBanner message={error} />}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Workflows</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            {list === null ? (
              <div className="p-3">
                <Skeleton className="h-20 w-full" />
              </div>
            ) : list.length === 0 ? (
              <p className="p-4 text-sm text-ink-2">
                No workflows yet. Create one to define how agreements are reviewed.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {list.map((w) => (
                  <li key={w.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(w.id)}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition hover:bg-surface-2 ${
                        selectedId === w.id ? "bg-accent-subtle" : ""
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-ink">{w.name}</span>
                        <span className="text-xs text-ink-3">{w.step_count} step(s)</span>
                      </span>
                      <Badge tone={w.status === "active" ? "accent" : "neutral"}>{w.status}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        {draft === null ? (
          <Card>
            <CardBody className="py-14 text-center">
              <GitBranch className="mx-auto h-9 w-9 text-ink-3" />
              <p className="mt-2 text-sm text-ink-2">
                Select a workflow to edit it, or create a new one.
              </p>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-4">
            <Card>
              <CardBody className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Workflow name">
                    <Input
                      value={draft.name}
                      onChange={(e) => {
                        setDraft({ ...draft, name: e.target.value });
                        setSaved(false);
                      }}
                    />
                  </Field>
                  <Field label="Status">
                    <div className="flex items-center gap-2">
                      <Badge tone={draft.status === "active" ? "accent" : "neutral"}>
                        {draft.status}
                      </Badge>
                      {draft.status !== "active" && (
                        <Button
                          variant="ghost"
                          className="h-8 px-2 text-xs"
                          onClick={() => save("active")}
                          disabled={busy || problems.length > 0}
                        >
                          Activate
                        </Button>
                      )}
                    </div>
                  </Field>
                </div>

                <Field
                  label="Use automatically for these contract types"
                  hint="A contract of one of these types starts this workflow by default."
                >
                  <div className="flex flex-wrap gap-1.5">
                    {CONTRACT_TYPES.map((t) => {
                      const on = draft.default_for_types.includes(t);
                      return (
                        <button
                          key={t}
                          type="button"
                          onClick={() => {
                            setDraft({
                              ...draft,
                              default_for_types: on
                                ? draft.default_for_types.filter((x) => x !== t)
                                : [...draft.default_for_types, t],
                            });
                            setSaved(false);
                          }}
                          className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                            on
                              ? "bg-accent text-white"
                              : "bg-surface-3 text-ink-2 hover:text-ink"
                          }`}
                        >
                          {t.toUpperCase()}
                        </button>
                      );
                    })}
                  </div>
                </Field>
              </CardBody>
            </Card>

            {problems.length > 0 && (
              <Card className="border-amber-300/60 bg-amber-50/50 dark:bg-amber-950/20">
                <CardBody className="space-y-1 py-3">
                  {problems.map((p) => (
                    <div key={p} className="flex items-start gap-2 text-sm text-ink-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                      <span>{p}</span>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}

            <div className="space-y-3">
              {stages.map((stage, stageIndex) => (
                <div key={stageIndex}>
                  <StageEditor
                    stage={stage}
                    index={stageIndex}
                    users={users}
                    onPatch={(patch) => patchStage(stageIndex, patch)}
                    onPatchStep={(stepIndex, patch) => patchStep(stageIndex, stepIndex, patch)}
                    onAddStep={() => {
                      patchStage(stageIndex, { steps: [...stage.steps, emptyStep()] });
                    }}
                    onRemoveStep={(stepIndex) => {
                      patchStage(stageIndex, {
                        steps: stage.steps.filter((_, j) => j !== stepIndex),
                      });
                    }}
                    onRemove={() => {
                      setStages((prev) => prev.filter((_, i) => i !== stageIndex));
                      setSaved(false);
                    }}
                    canRemove={stages.length > 1}
                  />
                  {stageIndex < stages.length - 1 && (
                    <div className="flex items-center justify-center gap-2 py-2 text-xs text-ink-3">
                      <ArrowDown className="h-3.5 w-3.5" />
                      then
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setStages((prev) => [...prev, emptyStage(prev.length)]);
                  setSaved(false);
                }}
              >
                <Plus className="h-4 w-4" /> Add a stage
              </Button>
              <div className="flex-1" />
              {saved && (
                <span className="flex items-center gap-1 text-sm text-accent">
                  <Check className="h-4 w-4" /> Saved
                </span>
              )}
              <Button onClick={() => save()} disabled={busy || problems.length > 0}>
                <Save className="h-4 w-4" /> {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Problems that would make the engine reject the graph — shown before saving, not after. */
function validate(stages: WorkflowStageDef[]): string[] {
  const problems: string[] = [];
  stages.forEach((stage, i) => {
    const label = stage.name || `Stage ${i + 1}`;
    if (stage.steps.length === 0) {
      problems.push(`${label} has no reviewers. A stage with nobody in it can never complete.`);
    }
    if (stage.policy === "quorum") {
      if (stage.threshold < 1 || stage.threshold > stage.steps.length) {
        problems.push(
          `${label}: a quorum of ${stage.threshold} is impossible with ${stage.steps.length} reviewer(s).`,
        );
      }
    }
    if (stage.policy === "percentage" && (stage.threshold < 1 || stage.threshold > 100)) {
      problems.push(`${label}: the percentage must be between 1 and 100.`);
    }
    stage.steps.forEach((step, j) => {
      if (!step.assignee_value) {
        problems.push(`${label}, reviewer ${j + 1}: choose who reviews.`);
      }
    });
  });
  return problems;
}

function StageEditor({
  stage,
  index,
  users,
  onPatch,
  onPatchStep,
  onAddStep,
  onRemoveStep,
  onRemove,
  canRemove,
}: {
  stage: WorkflowStageDef;
  index: number;
  users: User[];
  onPatch: (patch: Partial<WorkflowStageDef>) => void;
  onPatchStep: (stepIndex: number, patch: Partial<WorkflowStepDef>) => void;
  onAddStep: () => void;
  onRemoveStep: (stepIndex: number) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const [open, setOpen] = useState(true);
  const policy = STAGE_POLICIES.find((p) => p.value === stage.policy);

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-3 text-[11px] font-semibold text-ink-2">
            {index + 1}
          </span>
          <Input
            value={stage.name}
            onChange={(e) => onPatch({ name: e.target.value })}
            className="h-8 max-w-xs"
            placeholder="Stage name"
          />
          <Badge tone="neutral">
            <Users className="h-3 w-3" /> {stage.steps.length} concurrent
          </Badge>
          {stage.sla_hours > 0 && (
            <Badge tone="neutral">
              <Clock className="h-3 w-3" /> {stage.sla_hours}h SLA
            </Badge>
          )}
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="rounded p-1 text-ink-3 hover:text-ink"
            aria-label={open ? "Collapse stage" : "Expand stage"}
          >
            <ChevronDown className={`h-4 w-4 transition ${open ? "" : "-rotate-90"}`} />
          </button>
          {canRemove && (
            <button
              type="button"
              onClick={onRemove}
              className="rounded p-1 text-ink-3 hover:text-red-600"
              aria-label="Remove stage"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>

        {open && (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Completion">
                <Select
                  value={stage.policy}
                  onChange={(e) => onPatch({ policy: e.target.value as StagePolicy })}
                >
                  {STAGE_POLICIES.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </Field>
              {(stage.policy === "quorum" || stage.policy === "percentage") && (
                <Field label={stage.policy === "quorum" ? "How many" : "Percentage"}>
                  <Input
                    type="number"
                    min={1}
                    max={stage.policy === "quorum" ? stage.steps.length : 100}
                    value={stage.threshold || ""}
                    onChange={(e) => onPatch({ threshold: Number(e.target.value) || 0 })}
                  />
                </Field>
              )}
              <Field label="SLA (working hours)" hint="0 = no deadline">
                <Input
                  type="number"
                  min={0}
                  value={stage.sla_hours || 0}
                  onChange={(e) => onPatch({ sla_hours: Number(e.target.value) || 0 })}
                />
              </Field>
            </div>

            {policy && <p className="text-xs text-ink-3">{policy.hint}</p>}

            {stage.sla_hours > 0 && (
              <Field label="Escalate to" hint="Who picks it up if the deadline passes.">
                <Select
                  value={stage.escalate_to_user_id ?? ""}
                  onChange={(e) => onPatch({ escalate_to_user_id: e.target.value || null })}
                >
                  <option value="">Notify only — do not reassign</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}

            <div className="space-y-2 border-t border-line pt-3">
              <p className="text-xs font-medium text-ink-2">
                Reviewers in this stage — they review at the same time
              </p>
              {stage.steps.map((step, stepIndex) => (
                <div key={stepIndex} className="flex flex-wrap items-end gap-2">
                  <div className="min-w-[140px] flex-1">
                    <Input
                      value={step.name}
                      onChange={(e) => onPatchStep(stepIndex, { name: e.target.value })}
                      placeholder="Label (e.g. Legal)"
                      className="h-9"
                    />
                  </div>
                  <Select
                    value={step.assignee_kind}
                    onChange={(e) =>
                      onPatchStep(stepIndex, {
                        assignee_kind: e.target.value as "role" | "user",
                        assignee_value: e.target.value === "role" ? "approver" : "",
                      })
                    }
                    className="h-9 w-28"
                  >
                    <option value="role">Any role</option>
                    <option value="user">Person</option>
                  </Select>
                  <Select
                    value={step.assignee_value}
                    onChange={(e) => onPatchStep(stepIndex, { assignee_value: e.target.value })}
                    className="h-9 w-44"
                  >
                    {step.assignee_kind === "role" ? (
                      ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r} or above
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="">Choose a person…</option>
                        {users.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.name}
                          </option>
                        ))}
                      </>
                    )}
                  </Select>
                  {stage.steps.length > 1 && (
                    <button
                      type="button"
                      onClick={() => onRemoveStep(stepIndex)}
                      className="rounded p-2 text-ink-3 hover:text-red-600"
                      aria-label="Remove reviewer"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
              <Button variant="ghost" className="h-8 px-2 text-xs" onClick={onAddStep}>
                <Plus className="h-3.5 w-3.5" /> Add a concurrent reviewer
              </Button>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
