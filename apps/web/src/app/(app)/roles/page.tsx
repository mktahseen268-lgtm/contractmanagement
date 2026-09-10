"use client";

/**
 * Roles and permissions.
 *
 *   GET  /roles          built-in roles, custom roles, and every permission the app checks
 *   POST/PATCH /roles    define a role
 *   GET  /permissions/me what the signed-in user can do
 *
 * Replaces the mockup. A custom role always names a built-in as its base and adds or removes
 * individual permissions — so an unrecognised role degrades to a known baseline rather than
 * to no access, which would lock an administrator out of the system they administer.
 *
 * A revoke is applied after grants and always wins. That is shown in the editor, because a
 * rule whose precedence you have to guess is a rule nobody trusts.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Lock, Plus, Shield, ShieldCheck, X } from "lucide-react";
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
import { titleCase } from "@/lib/utils";
import type { CustomRole, MyPermissions, RolesResponse } from "@/lib/types";

export default function RolesPage() {
  const [data, setData] = useState<RolesResponse | null>(null);
  const [mine, setMine] = useState<MyPermissions | null>(null);
  const [editing, setEditing] = useState<CustomRole | "new" | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .get<RolesResponse>("/roles")
      .then(setData)
      .catch((e) => {
        setData(null);
        setError(
          e instanceof ApiError ? e.message : "Roles could not be loaded.",
        );
      });
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    api.get<MyPermissions>("/permissions/me").then(setMine).catch(() => setMine(null));
  }, []);

  return (
    <div>
      <PageHeader
        title="Roles and permissions"
        subtitle="What each role may do, and how to define one of your own"
        actions={
          data ? (
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus className="h-3.5 w-3.5" /> New role
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {mine && (
          <Card>
            <CardBody className="flex flex-wrap items-center gap-2 py-3 text-sm">
              <ShieldCheck className="h-4 w-4 text-accent" />
              <span className="text-ink">
                You are <strong>{mine.role}</strong>
              </span>
              <span className="text-ink-3">
                — {mine.permissions.length} permission
                {mine.permissions.length === 1 ? "" : "s"}
              </span>
            </CardBody>
          </Card>
        )}

        {data === null ? (
          <Skeleton className="h-48" />
        ) : (
          <>
            {editing && (
              <RoleForm
                initial={editing === "new" ? undefined : editing}
                permissions={data.permissions}
                baseRoles={data.builtin.map((b) => b.key)}
                onCancel={() => setEditing(null)}
                onSaved={() => {
                  setEditing(null);
                  load();
                }}
                onError={setError}
              />
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Lock className="h-4 w-4" /> Built-in roles
                </CardTitle>
              </CardHeader>
              <CardBody>
                <p className="mb-2 text-xs text-ink-3">
                  These cannot be edited. A custom role starts from one of them.
                </p>
                <PermissionMatrix
                  rows={data.builtin.map((b) => ({
                    key: b.key,
                    label: titleCase(b.key),
                    permissions: b.permissions,
                  }))}
                  permissions={data.permissions}
                />
              </CardBody>
            </Card>

            {data.custom.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-1.5">
                    <Shield className="h-4 w-4" /> Custom roles
                  </CardTitle>
                </CardHeader>
                <CardBody className="space-y-2">
                  {data.custom.map((role) => (
                    <div key={role.id} className="rounded-md border border-line p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-ink">{role.name}</span>
                        <code className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px]">
                          {role.key}
                        </code>
                        <Badge tone="neutral">based on {role.base_role}</Badge>
                        {!role.is_active && <Badge tone="neutral">inactive</Badge>}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto"
                          onClick={() => setEditing(role)}
                        >
                          Edit
                        </Button>
                      </div>
                      {role.description && (
                        <p className="mt-1 text-xs text-ink-2">{role.description}</p>
                      )}
                      <div className="mt-1 flex flex-wrap gap-1">
                        {role.grants.map((p) => (
                          <span
                            key={p}
                            className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800"
                          >
                            + {p}
                          </span>
                        ))}
                        {role.revokes.map((p) => (
                          <span
                            key={p}
                            className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] text-red-800"
                          >
                            − {p}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function PermissionMatrix({
  rows,
  permissions,
}: {
  rows: { key: string; label: string; permissions: string[] }[];
  permissions: string[];
}) {
  const groups = useMemo(() => {
    const byPrefix = new Map<string, string[]>();
    for (const p of permissions) {
      const prefix = p.split(".")[0];
      byPrefix.set(prefix, [...(byPrefix.get(prefix) ?? []), p]);
    }
    return Array.from(byPrefix.entries());
  }, [permissions]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-ink-3">
            <th className="py-1 pr-3">Permission</th>
            {rows.map((r) => (
              <th key={r.key} className="px-2 py-1 text-center">
                {r.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map(([prefix, items]) => (
            <>
              <tr key={prefix} className="border-t border-line">
                <td colSpan={rows.length + 1} className="pt-2 font-medium text-ink-2">
                  {titleCase(prefix)}
                </td>
              </tr>
              {items.map((permission) => (
                <tr key={permission} className="border-t border-line/50">
                  <td className="py-1 pr-3 text-ink">{permission}</td>
                  {rows.map((r) => (
                    <td key={r.key} className="px-2 py-1 text-center">
                      {r.permissions.includes(permission) ? (
                        <Check className="mx-auto h-3.5 w-3.5 text-emerald-600" />
                      ) : (
                        <X className="mx-auto h-3.5 w-3.5 text-ink-3/40" />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RoleForm({
  initial,
  permissions,
  baseRoles,
  onCancel,
  onSaved,
  onError,
}: {
  initial?: CustomRole;
  permissions: string[];
  baseRoles: string[];
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const isEdit = !!initial;
  const [key, setKey] = useState(initial?.key ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [baseRole, setBaseRole] = useState(initial?.base_role ?? "viewer");
  const [grants, setGrants] = useState<string[]>(initial?.grants ?? []);
  const [revokes, setRevokes] = useState<string[]>(initial?.revokes ?? []);
  const [busy, setBusy] = useState(false);

  function toggle(list: string[], set: (v: string[]) => void, permission: string) {
    set(list.includes(permission) ? list.filter((p) => p !== permission) : [...list, permission]);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      const payload = {
        key: key.trim().toLowerCase(),
        name: name.trim(),
        description: description.trim(),
        base_role: baseRole,
        grants,
        revokes,
      };
      if (isEdit) await api.patch(`/roles/${initial!.id}`, payload);
      else await api.post("/roles", payload);
      onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "That role could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEdit ? `Edit — ${initial?.name}` : "New role"}</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-3">
            <Field label="Key">
              <Input
                value={key}
                onChange={(e) =>
                  setKey(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))
                }
                required
                disabled={isEdit}
                className="font-mono text-xs"
                placeholder="legal-reviewer"
              />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Based on" hint="An unknown role falls back to this">
              <Select value={baseRole} onChange={(e) => setBaseRole(e.target.value)}>
                {baseRoles.map((r) => (
                  <option key={r} value={r}>
                    {titleCase(r)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-12">
            <Field label="Description">
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </Field>
          </div>

          <div className="sm:col-span-12 space-y-2 rounded-md border border-line p-3">
            <p className="text-xs text-ink-3">
              Tick to <strong className="text-emerald-700">add</strong> a permission on top of{" "}
              {baseRole}, or to <strong className="text-red-700">remove</strong> one from it. A
              removal is applied last and always wins.
            </p>
            <div className="grid gap-1 sm:grid-cols-2">
              {permissions.map((permission) => (
                <div
                  key={permission}
                  className="flex items-center gap-2 text-xs text-ink-2"
                >
                  <span className="flex-1 font-mono">{permission}</span>
                  <label className="inline-flex items-center gap-1 text-emerald-700">
                    <input
                      type="checkbox"
                      checked={grants.includes(permission)}
                      onChange={() => toggle(grants, setGrants, permission)}
                    />
                    add
                  </label>
                  <label className="inline-flex items-center gap-1 text-red-700">
                    <input
                      type="checkbox"
                      checked={revokes.includes(permission)}
                      onChange={() => toggle(revokes, setRevokes, permission)}
                    />
                    remove
                  </label>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              {isEdit ? "Save changes" : "Create role"}
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
