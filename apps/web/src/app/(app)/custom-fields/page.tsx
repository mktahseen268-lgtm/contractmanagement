"use client";

/**
 * Custom fields — tenant-defined typed fields per agreement type.
 *
 *   GET/POST /custom-fields, DELETE /custom-fields/{id}
 *
 * These reuse the merge-engine field vocabulary rather than inventing a second type system:
 * the intake form and custom fields are the same idea at different points, and two
 * vocabularies would drift the first time a type was added to one of them.
 *
 * Removing a definition deactivates it. Values already captured on agreements stay — they
 * were recorded facts, and deleting a definition should not quietly rewrite history.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ListPlus, Plus, Sliders, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
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
import { contractTypeLabel, titleCase, CONTRACT_TYPES } from "@/lib/utils";
import type { CustomFieldDef } from "@/lib/types";

const FIELD_TYPES = [
  "text", "textarea", "number", "money", "date", "select", "multiselect", "boolean",
];

export default function CustomFieldsPage() {
  const { me } = useAuth();
  const role = me?.user.role;
  const canEdit = role === "owner" || role === "admin" || role === "manager";

  const [items, setItems] = useState<CustomFieldDef[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<CustomFieldDef[]>("/custom-fields").then(setItems).catch(() => setItems([]));
  }, []);
  useEffect(load, [load]);

  const grouped = useMemo(() => {
    const byType = new Map<string, CustomFieldDef[]>();
    for (const f of items ?? []) {
      byType.set(f.contract_type, [...(byType.get(f.contract_type) ?? []), f]);
    }
    return Array.from(byType.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);

  async function remove(field: CustomFieldDef) {
    if (
      !window.confirm(
        `Stop capturing "${field.label || field.key}"? Values already recorded stay put.`,
      )
    )
      return;
    setError("");
    try {
      await api.del(`/custom-fields/${field.id}`);
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that field.");
    }
  }

  return (
    <div>
      <PageHeader
        title="Custom fields"
        subtitle="Extra data your workspace captures on agreements, per type"
        actions={
          canEdit ? (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="h-3.5 w-3.5" /> New field
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {creating && (
          <FieldForm
            onCancel={() => setCreating(false)}
            onSaved={() => {
              setCreating(false);
              load();
            }}
            onError={setError}
          />
        )}

        {items === null && <Skeleton className="h-24" />}

        {items?.length === 0 && (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-2">
              <Sliders className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">No custom fields yet</div>
              <p className="mt-1">
                Add the things your workspace tracks that the standard fields do not — a cost
                centre, an SLA tier, a regulator reference.
              </p>
            </CardBody>
          </Card>
        )}

        {grouped.map(([type, fields]) => (
          <Card key={type || "_all"}>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <ListPlus className="h-4 w-4" />
                {type ? contractTypeLabel(type) : "Every agreement type"}
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {fields.map((f) => (
                <div
                  key={f.id}
                  className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2"
                >
                  <span className="text-sm font-medium text-ink">{f.label || f.key}</span>
                  <code className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] text-ink-3">
                    {f.key}
                  </code>
                  <Badge tone="neutral">{f.type}</Badge>
                  {f.required && <Badge tone="accent">required</Badge>}
                  {f.options.length > 0 && (
                    <span className="text-[11px] text-ink-3">{f.options.join(", ")}</span>
                  )}
                  {f.help && <span className="text-[11px] text-ink-3">{f.help}</span>}
                  {canEdit && (
                    <button
                      onClick={() => remove(f)}
                      className="ml-auto p-1 text-ink-3 hover:text-ink"
                      title="Stop capturing this"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}

function FieldForm({
  onCancel,
  onSaved,
  onError,
}: {
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [contractType, setContractType] = useState("");
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [type, setType] = useState("text");
  const [required, setRequired] = useState(false);
  const [options, setOptions] = useState("");
  const [help, setHelp] = useState("");
  const [busy, setBusy] = useState(false);

  const needsOptions = type === "select" || type === "multiselect";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      await api.post("/custom-fields", {
        contract_type: contractType,
        key: key.trim().toLowerCase(),
        label: label.trim(),
        type,
        required,
        options: needsOptions
          ? options.split(",").map((o) => o.trim()).filter(Boolean)
          : [],
        help: help.trim(),
      });
      onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "Couldn't create that field.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New field</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-3">
            <Field label="Applies to">
              <Select value={contractType} onChange={(e) => setContractType(e.target.value)}>
                <option value="">Every type</option>
                {CONTRACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Key" hint="How it is stored">
              <Input
                value={key}
                onChange={(e) => setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
                required
                className="font-mono text-xs"
                placeholder="cost_centre"
              />
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Label">
              <Input value={label} onChange={(e) => setLabel(e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Type">
              <Select value={type} onChange={(e) => setType(e.target.value)}>
                {FIELD_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {titleCase(t)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="flex items-end pb-2 sm:col-span-1">
            <label className="inline-flex items-center gap-1.5 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={required}
                onChange={(e) => setRequired(e.target.checked)}
              />
              req
            </label>
          </div>
          {needsOptions && (
            <div className="sm:col-span-6">
              <Field label="Permitted values" hint="Comma-separated">
                <Input
                  value={options}
                  onChange={(e) => setOptions(e.target.value)}
                  placeholder="Gold, Silver, Bronze"
                  required
                />
              </Field>
            </div>
          )}
          <div className={needsOptions ? "sm:col-span-6" : "sm:col-span-12"}>
            <Field label="Help text">
              <Input value={help} onChange={(e) => setHelp(e.target.value)} />
            </Field>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              Create
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
