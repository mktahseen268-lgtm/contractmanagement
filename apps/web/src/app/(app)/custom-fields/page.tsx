"use client";

// Custom Fields — PROTOTYPE of tenant-defined contract metadata. Admins add fields (text, number,
// date, select, checkbox), mark required, scope to contract types, and preview how they render on
// a contract. Mockup: in-memory schema. Wires later to a per-tenant field definitions table +
// a JSONB values column on contracts.

import { useState } from "react";
import { Calendar, CheckSquare, GripVertical, Hash, List, Plus, Trash2, Type as TypeIcon } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field as FormField, Input, Select } from "@/components/ui";

type FieldType = "text" | "number" | "date" | "select" | "checkbox";
type CustomField = {
  id: string; label: string; type: FieldType; required: boolean; appliesTo: string; options?: string[];
};

const TYPE_META: Record<FieldType, { label: string; icon: typeof TypeIcon }> = {
  text: { label: "Text", icon: TypeIcon },
  number: { label: "Number", icon: Hash },
  date: { label: "Date", icon: Calendar },
  select: { label: "Dropdown", icon: List },
  checkbox: { label: "Checkbox", icon: CheckSquare },
};

const INITIAL: CustomField[] = [
  { id: "1", label: "Cost Center", type: "text", required: true, appliesTo: "All types" },
  { id: "2", label: "Annual Contract Value", type: "number", required: false, appliesTo: "MSA, Vendor" },
  { id: "3", label: "Region", type: "select", required: true, appliesTo: "All types", options: ["EMEA", "APAC", "Americas"] },
  { id: "4", label: "Auto-renew", type: "checkbox", required: false, appliesTo: "All types" },
];

export default function CustomFieldsPage() {
  const [fields, setFields] = useState<CustomField[]>(INITIAL);
  const [label, setLabel] = useState("");
  const [type, setType] = useState<FieldType>("text");
  const [required, setRequired] = useState(false);
  const [options, setOptions] = useState("");

  function add() {
    if (!label.trim()) return;
    setFields((f) => [
      ...f,
      {
        id: `${Date.now()}`, label: label.trim(), type, required, appliesTo: "All types",
        options: type === "select" ? options.split(",").map((o) => o.trim()).filter(Boolean) : undefined,
      },
    ]);
    setLabel(""); setRequired(false); setOptions("");
  }
  function remove(id: string) {
    setFields((f) => f.filter((x) => x.id !== id));
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Custom Fields <Badge tone="accent">Preview</Badge></span>}
        subtitle="Define your own contract metadata fields — they appear on every contract form."
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_320px]">
        {/* field list */}
        <Card>
          <CardHeader>
            <CardTitle>Fields</CardTitle>
            <span className="text-xs text-ink-3">{fields.length}</span>
          </CardHeader>
          <CardBody className="space-y-1.5">
            {fields.map((f) => {
              const M = TYPE_META[f.type];
              const Icon = M.icon;
              return (
                <div key={f.id} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-2">
                  <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-ink-3" />
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-ink-2"><Icon className="h-4 w-4" /></span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-medium text-ink">{f.label}</span>
                      {f.required && <span className="rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700">required</span>}
                    </div>
                    <div className="text-[11px] text-ink-3">
                      {M.label} · {f.appliesTo}{f.options ? ` · ${f.options.join(", ")}` : ""}
                    </div>
                  </div>
                  <button onClick={() => remove(f.id)} className="shrink-0 text-ink-3 hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              );
            })}
            {fields.length === 0 && <p className="py-4 text-center text-sm text-ink-3">No custom fields yet.</p>}
          </CardBody>
        </Card>

        {/* add + preview */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><Plus className="h-4 w-4" /> Add a field</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <FormField label="Field label"><Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Cost Center" /></FormField>
              <FormField label="Type">
                <Select value={type} onChange={(e) => setType(e.target.value as FieldType)}>
                  {(Object.keys(TYPE_META) as FieldType[]).map((t) => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
                </Select>
              </FormField>
              {type === "select" && (
                <FormField label="Options (comma-separated)"><Input value={options} onChange={(e) => setOptions(e.target.value)} placeholder="EMEA, APAC, Americas" /></FormField>
              )}
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} /> Required field
              </label>
              <Button className="w-full" onClick={add} disabled={!label.trim()}><Plus className="h-4 w-4" /> Add field</Button>
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>How it looks on a contract</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              {fields.slice(0, 5).map((f) => (
                <div key={f.id}>
                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                    {f.label} {f.required && <span className="text-red-500">*</span>}
                  </label>
                  {f.type === "checkbox" ? (
                    <label className="flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" disabled /> Yes</label>
                  ) : f.type === "select" ? (
                    <Select disabled><option>{f.options?.[0] ?? "Choose…"}</option></Select>
                  ) : (
                    <Input disabled placeholder={f.type === "date" ? "YYYY-MM-DD" : f.type === "number" ? "0" : "—"} />
                  )}
                </div>
              ))}
              {fields.length === 0 && <p className="text-sm text-ink-3">Add a field to preview it here.</p>}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
