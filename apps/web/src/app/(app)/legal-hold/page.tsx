"use client";

// Legal Hold / eDiscovery — PROTOTYPE. Place holds on contracts for litigation/audit so they (and
// their audit trail) are preserved from retention purge, track matters + custodians, and export a
// discovery package. Mockup: in-memory holds. Wires later to a retention-exempt flag + export job.

import { useMemo, useState } from "react";
import { Archive, Download, FileLock2, Gavel, Lock, Plus, Search, ShieldCheck, Unlock } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Input, Select } from "@/components/ui";

type Matter = { id: string; name: string; status: "active" | "released"; custodian: string; opened: string; contracts: number; scope: string };

const MATTERS: Matter[] = [
  { id: "m1", name: "Northwind v. Acme — contract dispute", status: "active", custodian: "General Counsel", opened: "2026-05-12", contracts: 6, scope: "All Northwind agreements 2024–2026" },
  { id: "m2", name: "Regulatory audit — DIFC 2026", status: "active", custodian: "Compliance", opened: "2026-04-30", contracts: 22, scope: "Vendor contracts > $50k" },
  { id: "m3", name: "Lumen IP claim", status: "released", custodian: "External Counsel", opened: "2025-11-02", contracts: 3, scope: "Lumen Labs reseller + amendments" },
];

export default function LegalHoldPage() {
  const [matters, setMatters] = useState<Matter[]>(MATTERS);
  const [q, setQ] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("");
  const [custodian, setCustodian] = useState("General Counsel");
  const [scope, setScope] = useState("");

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return matters.filter((m) => !n || m.name.toLowerCase().includes(n) || m.scope.toLowerCase().includes(n));
  }, [matters, q]);

  const activeHeld = matters.filter((m) => m.status === "active").reduce((s, m) => s + m.contracts, 0);

  function createMatter() {
    if (!name.trim()) return;
    setMatters((arr) => [
      { id: `${Date.now()}`, name: name.trim(), status: "active", custodian, opened: "Just now", contracts: 0, scope: scope.trim() || "—" },
      ...arr,
    ]);
    setName(""); setScope(""); setShowNew(false);
  }
  function toggleRelease(id: string) {
    setMatters((arr) => arr.map((m) => (m.id === id ? { ...m, status: m.status === "active" ? "released" : "active" } : m)));
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Legal Hold <Badge tone="accent">Preview</Badge></span>}
        subtitle="Preserve contracts & audit trails for litigation or audit — exempt from retention purge."
        actions={<Button size="sm" onClick={() => setShowNew((s) => !s)}><Plus className="h-3.5 w-3.5" /> Place a hold</Button>}
      />

      <div className="space-y-4 p-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Stat label="Active matters" value={matters.filter((m) => m.status === "active").length} icon={Gavel} tone="text-accent" />
          <Stat label="Contracts on hold" value={activeHeld} icon={Lock} tone="text-amber-600" />
          <Stat label="Released" value={matters.filter((m) => m.status === "released").length} icon={Unlock} tone="text-ink-3" />
        </div>

        {showNew && (
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><FileLock2 className="h-4 w-4" /> New legal hold</CardTitle></CardHeader>
            <CardBody className="grid gap-3 sm:grid-cols-2">
              <Field label="Matter name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Northwind dispute" /></Field>
              <Field label="Custodian">
                <Select value={custodian} onChange={(e) => setCustodian(e.target.value)}>
                  {["General Counsel", "Compliance", "External Counsel", "CFO"].map((c) => <option key={c}>{c}</option>)}
                </Select>
              </Field>
              <div className="sm:col-span-2">
                <Field label="Scope (which contracts the hold covers)"><Input value={scope} onChange={(e) => setScope(e.target.value)} placeholder="e.g. All Northwind agreements 2024–2026" /></Field>
              </div>
              <div className="sm:col-span-2 flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setShowNew(false)}>Cancel</Button>
                <Button size="sm" onClick={createMatter} disabled={!name.trim()}><Lock className="h-3.5 w-3.5" /> Place hold</Button>
              </div>
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Matters</CardTitle>
            <div className="relative w-56">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search matters…" className="h-8 pl-8 text-sm" />
            </div>
          </CardHeader>
          <CardBody className="space-y-2">
            {shown.map((m) => (
              <div key={m.id} className={`rounded-lg border p-3 ${m.status === "active" ? "border-amber-200 bg-amber-50/40" : "border-line"}`}>
                <div className="flex items-start gap-2">
                  <span className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg ${m.status === "active" ? "bg-amber-100 text-amber-700" : "bg-surface-2 text-ink-3"}`}>
                    {m.status === "active" ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-ink">{m.name}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${m.status === "active" ? "bg-amber-100 text-amber-800" : "bg-surface-2 text-ink-3"}`}>{m.status === "active" ? "On hold" : "Released"}</span>
                    </div>
                    <div className="mt-0.5 text-[11px] text-ink-3">{m.scope}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-ink-3">
                      <span>Custodian: <span className="text-ink-2">{m.custodian}</span></span>
                      <span>Opened {m.opened}</span>
                      <span>{m.contracts} contract{m.contracts === 1 ? "" : "s"} preserved</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <Button size="sm" variant="secondary" className="h-7"><Download className="h-3 w-3" /> Export</Button>
                    <button onClick={() => toggleRelease(m.id)} className="text-[11px] text-ink-3 hover:text-accent">
                      {m.status === "active" ? "Release hold" : "Re-apply hold"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </CardBody>
        </Card>

        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
          <ShieldCheck className="h-4 w-4 text-emerald-600" />
          Contracts under hold (and their tamper-evident audit chain) are <span className="font-medium text-ink">exempt from retention purge</span> until the matter is released.
          <Archive className="ml-auto h-4 w-4 text-ink-3" />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, icon: Icon, tone }: { label: string; value: number; icon: typeof Gavel; tone: string }) {
  return (
    <div className="rounded-xl border border-line p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
        <Icon className={`h-3.5 w-3.5 ${tone}`} /> {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-ink tnum">{value}</div>
    </div>
  );
}
