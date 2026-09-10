"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { CONTRACT_TYPES } from "@/lib/utils";
import { Button, Card, CardBody, ErrorBanner, Field, Input, Select } from "@/components/ui";
import type { ContractDetail, Department } from "@/lib/types";

export interface ContractFormValues {
  title: string;
  type: string;
  counterparty: string;
  department: string;
  value: string;
  currency: string;
  effective_date: string;
  end_date: string;
  renewal_type: string;
  tags: string;
}

function emptyValues(currency = "USD"): ContractFormValues {
  return {
    title: "",
    type: "msa",
    counterparty: "",
    department: "",
    value: "",
    currency,
    effective_date: "",
    end_date: "",
    renewal_type: "none",
    tags: "",
  };
}

export function fromContract(c: ContractDetail): ContractFormValues {
  return {
    title: c.title,
    type: c.type,
    counterparty: c.counterparty,
    department: c.department,
    value: c.value ? String(c.value) : "",
    currency: c.currency,
    effective_date: c.effective_date ?? "",
    end_date: c.end_date ?? "",
    renewal_type: c.renewal_type,
    tags: c.tags.join(", "),
  };
}

function toPayload(v: ContractFormValues) {
  return {
    title: v.title.trim(),
    type: v.type,
    counterparty: v.counterparty.trim(),
    department: v.department.trim(),
    value: v.value ? Number(v.value) : 0,
    currency: v.currency,
    effective_date: v.effective_date || null,
    end_date: v.end_date || null,
    renewal_type: v.renewal_type,
    tags: v.tags.split(",").map((t) => t.trim()).filter(Boolean),
  };
}

export function ContractForm({
  mode,
  contractId,
  initial,
  currency = "USD",
}: {
  mode: "create" | "edit";
  contractId?: string;
  initial?: ContractDetail;
  currency?: string;
}) {
  const router = useRouter();
  const [v, setV] = useState<ContractFormValues>(initial ? fromContract(initial) : emptyValues(currency));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [departments, setDepartments] = useState<Department[] | null>(null);

  // Free text let three spellings of one department into the same report. The list is whatever
  // an admin has set up under Departments; null means "still loading", [] means "none configured".
  useEffect(() => {
    api.get<Department[]>("/departments")
      .then((d) => setDepartments(d.filter((x) => x.is_active)))
      .catch(() => setDepartments([]));
  }, []);

  function set<K extends keyof ContractFormValues>(k: K, val: ContractFormValues[K]) {
    setV((s) => ({ ...s, [k]: val }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!v.title.trim()) {
      setError("Please give the contract a title.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (mode === "create") {
        const c = await api.post<ContractDetail>("/contracts", toPayload(v));
        router.push(`/contracts/${c.id}`);
      } else {
        const c = await api.patch<ContractDetail>(`/contracts/${contractId}`, toPayload(v));
        router.push(`/contracts/${c.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl space-y-4 px-6 py-6">
      <ErrorBanner message={error} />
      <Card>
        <CardBody className="space-y-4">
          <Field label="Title*">
            <Input value={v.title} onChange={(e) => set("title", e.target.value)} placeholder="Master Services Agreement — Acme Corp" autoFocus />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Contract type">
              <Select value={v.type} onChange={(e) => set("type", e.target.value)}>
                {CONTRACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Department"
              hint={departments?.length === 0 ? "No departments set up yet — an admin can add them under Departments." : undefined}
            >
              <Select
                value={v.department}
                onChange={(e) => set("department", e.target.value)}
                disabled={departments === null || departments.length === 0}
              >
                <option value="">{departments === null ? "Loading…" : "Select a department"}</option>
                {/* An agreement created before a department was renamed keeps its old value; keep
                    it selectable so opening the form to edit something else cannot silently
                    reassign it. */}
                {v.department && !(departments ?? []).some((d) => d.name === v.department) && (
                  <option value={v.department}>{v.department}</option>
                )}
                {(departments ?? []).map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Counterparty">
            <Input value={v.counterparty} onChange={(e) => set("counterparty", e.target.value)} placeholder="Acme Corporation" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Value">
              <Input type="number" min="0" value={v.value} onChange={(e) => set("value", e.target.value)} placeholder="120000" />
            </Field>
            <Field label="Currency">
              <Input value={v.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} maxLength={3} />
            </Field>
            <Field label="Renewal">
              <Select value={v.renewal_type} onChange={(e) => set("renewal_type", e.target.value)}>
                <option value="none">None</option>
                <option value="auto">Auto-renew</option>
                <option value="manual">Manual</option>
              </Select>
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Effective date">
              <Input type="date" value={v.effective_date} onChange={(e) => set("effective_date", e.target.value)} />
            </Field>
            <Field label="End date">
              <Input type="date" value={v.end_date} onChange={(e) => set("end_date", e.target.value)} />
            </Field>
          </div>
          <Field label="Tags" hint="Comma-separated.">
            <Input value={v.tags} onChange={(e) => set("tags", e.target.value)} placeholder="renewal, priority" />
          </Field>
          <p className="text-xs text-ink-3">
            The contract document itself is written in the rich editor on the contract’s <span className="font-medium text-ink-2">Document</span> tab once it’s created.
          </p>
        </CardBody>
      </Card>
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button type="submit" loading={saving}>
          {mode === "create" ? "Create contract" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}
