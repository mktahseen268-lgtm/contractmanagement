"use client";

// Bulk Send — PROTOTYPE of template-driven mass dispatch with scheduled reminders + expiry.
// Send one template to many recipients at once; configure auto-reminders and envelope expiry.
// Mockup: sample recipients + simulated send. Wires later to a /bulk-send batch endpoint that
// fans out one envelope per recipient.

import { useState } from "react";
import { CalendarClock, Mails, Plus, Send, Trash2, Upload, Users } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Input, Select } from "@/components/ui";

type Row = { id: string; name: string; email: string; company: string };

const TEMPLATES = [
  { id: "t1", name: "NDA — Mutual (Standard)" },
  { id: "t2", name: "Vendor Onboarding Agreement" },
  { id: "t3", name: "Employee Offer Letter" },
  { id: "t4", name: "Reseller Agreement 2026" },
];

const SAMPLE: Row[] = [
  { id: "1", name: "Shahzaib Memon", email: "shahzaib@thiqatech.com", company: "ThiqaTech" },
  { id: "2", name: "Aisha Al Abri", email: "aisha@trialco.io", company: "Trial Co" },
  { id: "3", name: "John Carter", email: "john@northwind.io", company: "Northwind" },
  { id: "4", name: "Mei Lin", email: "mei@lumen.io", company: "Lumen Labs" },
  { id: "5", name: "Omar Khalid", email: "omar@platform.io", company: "Platform Inc" },
];

let _seq = 100;
const nextId = () => `${++_seq}`;

export default function BulkSendPage() {
  const [template, setTemplate] = useState(TEMPLATES[0].id);
  const [rows, setRows] = useState<Row[]>(SAMPLE);
  const [everyDays, setEveryDays] = useState(3);
  const [maxReminders, setMaxReminders] = useState(3);
  const [expiryDays, setExpiryDays] = useState(14);
  const [sent, setSent] = useState(false);

  function addRow() {
    setRows((r) => [...r, { id: nextId(), name: "", email: "", company: "" }]);
  }
  function update(id: string, patch: Partial<Row>) {
    setRows((r) => r.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  }
  function remove(id: string) {
    setRows((r) => r.filter((x) => x.id !== id));
  }

  const valid = rows.filter((r) => r.email.includes("@") && r.name.trim());

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Bulk Send <Badge tone="accent">Preview</Badge></span>}
        subtitle="Send one template to many signers at once, with scheduled reminders and expiry."
        actions={
          <Button size="sm" onClick={() => setSent(true)} disabled={valid.length === 0}>
            <Send className="h-3.5 w-3.5" /> Send to {valid.length}
          </Button>
        }
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_320px]">
        {/* recipients */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5"><Users className="h-4 w-4" /> Recipients</CardTitle>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary"><Upload className="h-3.5 w-3.5" /> Import CSV</Button>
              <Button size="sm" variant="secondary" onClick={addRow}><Plus className="h-3.5 w-3.5" /> Add</Button>
            </div>
          </CardHeader>
          <CardBody className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <tr>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">Email</th>
                    <th className="px-3 py-2">Company</th>
                    <th className="px-3 py-2 text-right">Status</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((r) => {
                    const ok = r.email.includes("@") && r.name.trim();
                    return (
                      <tr key={r.id} className="hover:bg-surface-2">
                        <td className="px-3 py-1.5">
                          <Input value={r.name} onChange={(e) => update(r.id, { name: e.target.value })} placeholder="Full name" className="h-8" />
                        </td>
                        <td className="px-3 py-1.5">
                          <Input value={r.email} onChange={(e) => update(r.id, { email: e.target.value })} placeholder="name@company.com" className="h-8" />
                        </td>
                        <td className="px-3 py-1.5">
                          <Input value={r.company} onChange={(e) => update(r.id, { company: e.target.value })} placeholder="Company" className="h-8" />
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${ok ? "bg-emerald-50 text-emerald-700" : "bg-surface-2 text-ink-3"}`}>
                            {ok ? "Ready" : "Incomplete"}
                          </span>
                        </td>
                        <td className="px-1">
                          <button onClick={() => remove(r.id)} className="text-ink-3 hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">
              {valid.length} of {rows.length} rows ready · each becomes its own envelope from the template below.
            </div>
          </CardBody>
        </Card>

        {/* config */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><Mails className="h-4 w-4" /> Template</CardTitle></CardHeader>
            <CardBody>
              <Select value={template} onChange={(e) => setTemplate(e.target.value)}>
                {TEMPLATES.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
              <p className="mt-2 text-[11px] text-ink-3">Merge fields ({"{{name}}"}, {"{{company}}"}) auto-fill per recipient.</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><CalendarClock className="h-4 w-4" /> Reminders &amp; expiry</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <Field label="Send a reminder every (days)">
                <Input type="number" value={String(everyDays)} onChange={(e) => setEveryDays(Math.max(1, Number(e.target.value) || 1))} />
              </Field>
              <Field label="Maximum reminders">
                <Input type="number" value={String(maxReminders)} onChange={(e) => setMaxReminders(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
              <Field label="Envelope expires after (days)">
                <Input type="number" value={String(expiryDays)} onChange={(e) => setExpiryDays(Math.max(1, Number(e.target.value) || 1))} />
              </Field>
              <div className="rounded-lg border border-dashed border-line bg-surface-2 p-3 text-[11px] text-ink-2">
                Each unsigned signer gets up to <span className="font-semibold text-ink">{maxReminders}</span> reminders, one every{" "}
                <span className="font-semibold text-ink">{everyDays}</span> day(s). Links auto-expire after{" "}
                <span className="font-semibold text-ink">{expiryDays}</span> days.
              </div>
            </CardBody>
          </Card>
        </div>
      </div>

      {sent && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setSent(false)}>
          <Card className="w-full max-w-sm">
            <CardBody className="space-y-3 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700"><Send className="h-6 w-6" /></div>
              <div className="text-base font-semibold text-ink">{valid.length} envelopes queued</div>
              <p className="text-sm text-ink-2">
                One envelope per recipient from <span className="font-medium text-ink">{TEMPLATES.find((t) => t.id === template)?.name}</span>,
                with reminders every {everyDays}d (max {maxReminders}) and {expiryDays}-day expiry. In the live product each fans out through the signing engine.
              </p>
              <Button className="w-full" onClick={() => setSent(false)}>Done</Button>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
