"use client";

// Departments — PROTOTYPE of a managed department directory. Today `department` is just a free-
// text field on contracts; this turns it into a real entity with a lead, members, and rollups so
// contracts pick from a managed list. Mockup: in-memory. Wires later to a departments table +
// contract.department_id (replacing the free-text column).

import { useState } from "react";
import { Building2, Check, FileText, Pencil, Plus, Trash2, Users, Wallet } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Input, Select } from "@/components/ui";

type Dept = { id: string; name: string; lead: string; members: number; contracts: number; value: number; color: string };

const LEADS = ["Demo Owner", "Mariam Khan", "John Doe", "Aisha Smith"];
const COLORS = ["#3E7BFA", "#8B5CF6", "#12B76A", "#F59E0B", "#EF4444", "#06B6D4"];

const INITIAL: Dept[] = [
  { id: "1", name: "Sales", lead: "Mariam Khan", members: 8, contracts: 12, value: 1080000, color: "#3E7BFA" },
  { id: "2", name: "Procurement", lead: "John Doe", members: 5, contracts: 9, value: 918000, color: "#12B76A" },
  { id: "3", name: "HR & People", lead: "Aisha Smith", members: 3, contracts: 6, value: 240000, color: "#F59E0B" },
  { id: "4", name: "Legal & Compliance", lead: "Demo Owner", members: 2, contracts: 4, value: 90000, color: "#8B5CF6" },
];

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}`;
}

let _seq = 100;

export default function DepartmentsPage() {
  const [depts, setDepts] = useState<Dept[]>(INITIAL);
  const [editing, setEditing] = useState<Dept | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [lead, setLead] = useState(LEADS[0]);

  function startNew() {
    setEditing(null); setName(""); setLead(LEADS[0]); setCreating(true);
  }
  function startEdit(d: Dept) {
    setCreating(false); setEditing(d); setName(d.name); setLead(d.lead);
  }
  function save() {
    if (!name.trim()) return;
    if (editing) {
      setDepts((arr) => arr.map((d) => (d.id === editing.id ? { ...d, name: name.trim(), lead } : d)));
    } else {
      setDepts((arr) => [...arr, { id: `${++_seq}`, name: name.trim(), lead, members: 0, contracts: 0, value: 0, color: COLORS[arr.length % COLORS.length] }]);
    }
    setCreating(false); setEditing(null); setName("");
  }
  function remove(id: string) {
    setDepts((arr) => arr.filter((d) => d.id !== id));
  }

  const totalContracts = depts.reduce((s, d) => s + d.contracts, 0);
  const totalValue = depts.reduce((s, d) => s + d.value, 0);

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Departments <Badge tone="accent">Preview</Badge></span>}
        subtitle="A managed department directory — leads, members, and contract rollups."
        actions={<Button size="sm" onClick={startNew}><Plus className="h-3.5 w-3.5" /> New department</Button>}
      />

      <div className="space-y-4 p-4">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Departments" value={String(depts.length)} icon={Building2} />
          <Stat label="Total contracts" value={String(totalContracts)} icon={FileText} />
          <Stat label="Total value" value={money(totalValue)} icon={Wallet} />
        </div>

        {(creating || editing) && (
          <Card>
            <CardHeader><CardTitle>{editing ? `Edit — ${editing.name}` : "New department"}</CardTitle></CardHeader>
            <CardBody className="flex flex-wrap items-end gap-3">
              <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Marketing" className="w-56" /></Field>
              <Field label="Department lead">
                <Select value={lead} onChange={(e) => setLead(e.target.value)}>{LEADS.map((l) => <option key={l}>{l}</option>)}</Select>
              </Field>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => { setCreating(false); setEditing(null); }}>Cancel</Button>
                <Button size="sm" onClick={save} disabled={!name.trim()}><Check className="h-3.5 w-3.5" /> {editing ? "Save" : "Create"}</Button>
              </div>
            </CardBody>
          </Card>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {depts.map((d) => (
            <Card key={d.id} className="transition hover:border-ink-3/30">
              <CardBody className="space-y-3">
                <div className="flex items-center gap-2.5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl text-white" style={{ background: d.color }}><Building2 className="h-5 w-5" /></span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold text-ink">{d.name}</div>
                    <div className="text-[11px] text-ink-3">Lead: {d.lead}</div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <Mini label="Members" value={String(d.members)} icon={Users} />
                  <Mini label="Contracts" value={String(d.contracts)} icon={FileText} />
                  <Mini label="Value" value={money(d.value)} icon={Wallet} />
                </div>
                <div className="flex justify-end gap-1">
                  <Button size="sm" variant="ghost" onClick={() => startEdit(d)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(d.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
          <Building2 className="h-4 w-4 text-ink-3" />
          When wired, contracts pick their department from this managed list (replacing the free-text field), so reports group cleanly and every department has an accountable lead.
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Building2 }) {
  return (
    <div className="rounded-xl border border-line p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3"><Icon className="h-3.5 w-3.5" /> {label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink tnum">{value}</div>
    </div>
  );
}

function Mini({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Building2 }) {
  return (
    <div className="rounded-lg bg-surface-2 py-2">
      <Icon className="mx-auto h-3.5 w-3.5 text-ink-3" />
      <div className="mt-0.5 text-sm font-semibold text-ink tnum">{value}</div>
      <div className="text-[10px] text-ink-3">{label}</div>
    </div>
  );
}
