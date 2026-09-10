"use client";

/**
 * Departments — a record rather than a free-text string on the contract.
 *
 *   GET/POST/PATCH /departments
 *
 * The free-text `Contract.department` is still written alongside `department_id` so existing
 * reports and exports keep working; the record is what you can assign a lead to and report on.
 */

import { useCallback, useEffect, useState } from "react";
import { Building2, Pencil, Plus, Users } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import {
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
import type { Department, User } from "@/lib/types";

export default function DepartmentsPage() {
  const { me } = useAuth();
  const role = me?.user.role;
  const canEdit = role === "owner" || role === "admin" || role === "manager";

  const [items, setItems] = useState<Department[] | null>(null);
  const [people, setPeople] = useState<User[]>([]);
  const [editing, setEditing] = useState<Department | "new" | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<Department[]>("/departments").then(setItems).catch(() => setItems([]));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    api.get<User[]>("/users").then(setPeople).catch(() => setPeople([]));
  }, []);

  return (
    <div>
      <PageHeader
        title="Departments"
        subtitle={
          items === null
            ? "Loading…"
            : `${items.length} department${items.length === 1 ? "" : "s"} · owners, cost centres, regions`
        }
        actions={
          canEdit ? (
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus className="h-3.5 w-3.5" /> New department
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {editing && (
          <DepartmentForm
            initial={editing === "new" ? undefined : editing}
            people={people}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              load();
            }}
            onError={setError}
          />
        )}

        {items === null && <Skeleton className="h-24" />}

        {items?.length === 0 && (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-2">
              <Building2 className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">No departments yet</div>
              <p className="mt-1">
                A department record is what an agreement can be assigned to, reported on, and
                given an owner — a typed name in a text box is none of those.
              </p>
            </CardBody>
          </Card>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items?.map((d) => (
            <Card key={d.id}>
              <CardBody className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Building2 className="h-3.5 w-3.5 text-accent" />
                  <span className="text-sm font-semibold text-ink">{d.name}</span>
                  {!d.is_active && (
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-ink-3">
                      inactive
                    </span>
                  )}
                </div>
                <div className="text-xs text-ink-2">
                  {d.lead_name ? (
                    <span className="inline-flex items-center gap-1">
                      <Users className="h-3 w-3" /> {d.lead_name}
                    </span>
                  ) : (
                    <span className="text-ink-3">No lead assigned</span>
                  )}
                </div>
                <div className="text-[11px] text-ink-3">
                  {d.cost_centre && `${d.cost_centre} · `}
                  {d.region && `${d.region} · `}
                  {d.contract_count} agreement{d.contract_count === 1 ? "" : "s"}
                </div>
                {canEdit && (
                  <Button size="sm" variant="ghost" onClick={() => setEditing(d)}>
                    <Pencil className="h-3.5 w-3.5" /> Edit
                  </Button>
                )}
              </CardBody>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function DepartmentForm({
  initial,
  people,
  onCancel,
  onSaved,
  onError,
}: {
  initial?: Department;
  people: User[];
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? "");
  const [lead, setLead] = useState(initial?.lead_user_id ?? "");
  const [costCentre, setCostCentre] = useState(initial?.cost_centre ?? "");
  const [region, setRegion] = useState(initial?.region ?? "");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      const payload = {
        name: name.trim(),
        lead_user_id: lead || null,
        cost_centre: costCentre.trim(),
        region: region.trim(),
      };
      if (isEdit) await api.patch(`/departments/${initial!.id}`, payload);
      else await api.post("/departments", payload);
      onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "Couldn't save the department.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEdit ? `Edit — ${initial?.name}` : "New department"}</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-4">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Lead">
              <Select value={lead} onChange={(e) => setLead(e.target.value)}>
                <option value="">No lead</option>
                {people.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Cost centre">
              <Input value={costCentre} onChange={(e) => setCostCentre(e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Region">
              <Input value={region} onChange={(e) => setRegion(e.target.value)} />
            </Field>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              {isEdit ? "Save changes" : "Create"}
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
