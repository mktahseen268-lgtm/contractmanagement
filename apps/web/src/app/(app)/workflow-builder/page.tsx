"use client";

// Visual Workflow Builder — PROTOTYPE of the advanced approval-flow canvas: parallel approver
// groups, conditional routing, and SLA timers with auto-escalation. The current product ships a
// linear step-list; this is the upgrade designed in docs/10. Mockup: sample data + a config
// panel; "Activate" is simulated. Wires later to the workflow_service engine.

import { useState } from "react";
import { ArrowDown, Clock, GitBranch, Plus, Settings2, Users, Zap } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, Field, Input, Select } from "@/components/ui";

type Mode = "single" | "any" | "all";
type Approver = { id: string; name: string; color: string };
type Stage = {
  id: string;
  name: string;
  mode: Mode;
  approvers: Approver[];
  slaHours: number;
  escalateTo: string;
  condition?: string; // routing condition that gates entry to this stage
};

const PEOPLE: Approver[] = [
  { id: "p1", name: "Line Manager", color: "#3E7BFA" },
  { id: "p2", name: "Finance", color: "#12B76A" },
  { id: "p3", name: "Legal", color: "#8B5CF6" },
  { id: "p4", name: "CFO", color: "#F59E0B" },
  { id: "p5", name: "CEO", color: "#EF4444" },
];

const MODE_LABEL: Record<Mode, string> = {
  single: "One approver",
  any: "Any one of (parallel)",
  all: "All must approve (parallel group)",
};

const INITIAL: Stage[] = [
  { id: "s1", name: "Manager review", mode: "single", approvers: [PEOPLE[0]], slaHours: 24, escalateTo: "Skip-level manager" },
  { id: "s2", name: "Finance & Legal", mode: "all", approvers: [PEOPLE[1], PEOPLE[2]], slaHours: 48, escalateTo: "Department head", condition: "Always" },
  { id: "s3", name: "Executive sign-off", mode: "any", approvers: [PEOPLE[3], PEOPLE[4]], slaHours: 72, escalateTo: "Board secretary", condition: "If value > $50,000" },
];

let _seq = 100;
const nextId = () => `s${++_seq}`;

export default function WorkflowBuilderPage() {
  const [stages, setStages] = useState<Stage[]>(INITIAL);
  const [selected, setSelected] = useState<string | null>("s2");
  const [activated, setActivated] = useState(false);

  const sel = stages.find((s) => s.id === selected) ?? null;

  function update(id: string, patch: Partial<Stage>) {
    setStages((arr) => arr.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }
  function addStage() {
    const ns: Stage = { id: nextId(), name: "New stage", mode: "single", approvers: [PEOPLE[0]], slaHours: 24, escalateTo: "Manager" };
    setStages((a) => [...a, ns]);
    setSelected(ns.id);
  }
  function removeStage(id: string) {
    setStages((a) => a.filter((s) => s.id !== id));
    if (selected === id) setSelected(null);
  }
  function toggleApprover(stageId: string, p: Approver) {
    setStages((arr) =>
      arr.map((s) => {
        if (s.id !== stageId) return s;
        const has = s.approvers.some((a) => a.id === p.id);
        const approvers = has ? s.approvers.filter((a) => a.id !== p.id) : [...s.approvers, p];
        return { ...s, approvers: approvers.length ? approvers : s.approvers };
      })
    );
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Workflow Builder</span>}
        subtitle="Parallel approval groups, conditional routing, and SLA auto-escalation."
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={addStage}><Plus className="h-3.5 w-3.5" /> Add stage</Button>
            <Button size="sm" onClick={() => setActivated(true)}><Zap className="h-3.5 w-3.5" /> Activate</Button>
          </div>
        }
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_340px]">
        {/* canvas */}
        <div className="rounded-xl border border-line bg-surface-2/40 p-6">
          <div className="mx-auto flex max-w-md flex-col items-center">
            <TerminalNode label="Submitted for approval" tone="start" />
            {stages.map((s, i) => (
              <div key={s.id} className="flex w-full flex-col items-center">
                <Connector condition={s.condition} />
                <StageNode
                  stage={s}
                  index={i}
                  selected={selected === s.id}
                  onSelect={() => setSelected(s.id)}
                  onRemove={() => removeStage(s.id)}
                />
              </div>
            ))}
            <Connector />
            <TerminalNode label="Approved → out for signature" tone="end" />
          </div>
        </div>

        {/* config panel */}
        <div>
          {sel ? (
            <Card className="lg:sticky lg:top-20">
              <CardBody className="space-y-3">
                <div className="flex items-center gap-2">
                  <Settings2 className="h-4 w-4 text-accent" />
                  <h3 className="text-sm font-semibold text-ink">Stage settings</h3>
                </div>

                <Field label="Stage name">
                  <Input value={sel.name} onChange={(e) => update(sel.id, { name: e.target.value })} />
                </Field>

                <Field label="Approval mode">
                  <Select value={sel.mode} onChange={(e) => update(sel.id, { mode: e.target.value as Mode })}>
                    {(Object.keys(MODE_LABEL) as Mode[]).map((m) => (
                      <option key={m} value={m}>{MODE_LABEL[m]}</option>
                    ))}
                  </Select>
                </Field>

                <div>
                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">Approvers</label>
                  <div className="flex flex-wrap gap-1.5">
                    {PEOPLE.map((p) => {
                      const on = sel.approvers.some((a) => a.id === p.id);
                      return (
                        <button
                          key={p.id}
                          onClick={() => toggleApprover(sel.id, p)}
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition ${on ? "border-transparent text-white" : "border-line text-ink-2 hover:bg-surface-2"}`}
                          style={on ? { background: p.color } : undefined}
                        >
                          <span className="h-2 w-2 rounded-full" style={{ background: on ? "#fff" : p.color }} />
                          {p.name}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <Field label="SLA — escalate after (hours)">
                  <Input
                    type="number"
                    value={String(sel.slaHours)}
                    onChange={(e) => update(sel.id, { slaHours: Math.max(1, Number(e.target.value) || 1) })}
                  />
                </Field>

                <Field label="Escalate to">
                  <Input value={sel.escalateTo} onChange={(e) => update(sel.id, { escalateTo: e.target.value })} />
                </Field>

                <Field label="Entry condition (routing)">
                  <Input
                    value={sel.condition ?? ""}
                    onChange={(e) => update(sel.id, { condition: e.target.value })}
                    placeholder="e.g. If value > $50,000"
                  />
                </Field>

                <div className="rounded-lg border border-dashed border-line bg-surface-2 p-3 text-[11px] text-ink-2">
                  <span className="font-semibold text-ink">Summary:</span> {summarize(sel)}
                </div>
              </CardBody>
            </Card>
          ) : (
            <Card><CardBody><p className="text-sm text-ink-3">Select a stage on the canvas to configure it, or add a new stage.</p></CardBody></Card>
          )}
        </div>
      </div>

      {activated && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setActivated(false)}>
          <Card className="w-full max-w-sm">
            <CardBody className="space-y-3 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-accent/10 text-accent"><Zap className="h-6 w-6" /></div>
              <div className="text-base font-semibold text-ink">Workflow activated</div>
              <p className="text-sm text-ink-2">
                {stages.length} stages · {stages.filter((s) => s.mode === "all").length} parallel group(s) ·{" "}
                {stages.filter((s) => s.condition && s.condition !== "Always").length} conditional route(s).
                The workflow is versioned and applied to new approval runs.
              </p>
              <Button className="w-full" onClick={() => setActivated(false)}>Done</Button>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}

function summarize(s: Stage): string {
  const who = s.approvers.map((a) => a.name).join(", ");
  const mode = s.mode === "all" ? "all of" : s.mode === "any" ? "any of" : "";
  const cond = s.condition && s.condition !== "Always" ? `${s.condition}, then ` : "";
  return `${cond}${mode ? `${mode} ` : ""}${who} must approve within ${s.slaHours}h, else escalate to ${s.escalateTo}.`;
}

function Connector({ condition }: { condition?: string }) {
  return (
    <div className="flex flex-col items-center py-1">
      {condition && condition !== "Always" && (
        <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-700">
          <GitBranch className="h-3 w-3" /> {condition}
        </span>
      )}
      <ArrowDown className="h-4 w-4 text-ink-3" />
    </div>
  );
}

function TerminalNode({ label, tone }: { label: string; tone: "start" | "end" }) {
  return (
    <div className={`rounded-full px-4 py-1.5 text-xs font-semibold ${tone === "start" ? "bg-ink text-white" : "bg-emerald-600 text-white"}`}>
      {label}
    </div>
  );
}

function StageNode({
  stage, index, selected, onSelect, onRemove,
}: {
  stage: Stage; index: number; selected: boolean; onSelect: () => void; onRemove: () => void;
}) {
  const parallel = stage.mode === "all" || stage.mode === "any";
  return (
    <button
      onClick={onSelect}
      className={`w-full rounded-xl border bg-white p-3 text-left shadow-sm transition ${selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-ink-3/40"}`}
    >
      <div className="flex items-center gap-2">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface-2 text-[11px] font-semibold text-ink-2">{index + 1}</span>
        <span className="flex-1 truncate text-sm font-semibold text-ink">{stage.name}</span>
        <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-2">
          <Clock className="h-3 w-3" /> {stage.slaHours}h
        </span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${parallel ? "bg-accent/10 text-accent" : "bg-surface-2 text-ink-3"}`}>
          <Users className="h-3 w-3" /> {MODE_LABEL[stage.mode]}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        {stage.approvers.map((a) => (
          <span key={a.id} className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-ink-2">
            <span className="h-2 w-2 rounded-full" style={{ background: a.color }} /> {a.name}
          </span>
        ))}
        <span
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="ml-auto cursor-pointer text-[10px] text-ink-3 hover:text-danger"
        >
          remove
        </span>
      </div>
    </button>
  );
}
