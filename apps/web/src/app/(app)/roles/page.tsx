"use client";

// Roles & Permissions — PROTOTYPE of an editable RBAC matrix + custom roles. Today roles are a
// fixed hierarchy gated in code and the Team page shows a read-only matrix; this makes the matrix
// editable and lets admins define custom roles. Mockup: in-memory. Wires later to a per-tenant
// role/permission table replacing the hardcoded gates.

import { Fragment, useState } from "react";
import { Check, Plus, Shield, Users } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Input } from "@/components/ui";
import { titleCase } from "@/lib/utils";

type Role = { key: string; label: string; builtin: boolean; members: number };
type Perm = { id: string; label: string; group: string };

const PERMS: Perm[] = [
  { id: "view", label: "View contracts, dashboard, reports", group: "Read" },
  { id: "create", label: "Create & edit contracts", group: "Contracts" },
  { id: "delete", label: "Delete contracts", group: "Contracts" },
  { id: "submit", label: "Submit for approval", group: "Workflow" },
  { id: "decide", label: "Approve / reject in workflows", group: "Workflow" },
  { id: "manage_wf", label: "Manage workflow definitions", group: "Workflow" },
  { id: "send_sig", label: "Send for signature & void", group: "Signing" },
  { id: "manage_users", label: "Manage users & roles", group: "Admin" },
  { id: "manage_ws", label: "Manage workspace settings", group: "Admin" },
  { id: "api_keys", label: "Mint API keys & webhooks", group: "Admin" },
];

const INITIAL_ROLES: Role[] = [
  { key: "owner", label: "Owner", builtin: true, members: 1 },
  { key: "admin", label: "Admin", builtin: true, members: 2 },
  { key: "manager", label: "Manager", builtin: true, members: 3 },
  { key: "author", label: "Author", builtin: true, members: 5 },
  { key: "approver", label: "Approver", builtin: true, members: 2 },
  { key: "reviewer", label: "Reviewer", builtin: true, members: 1 },
  { key: "viewer", label: "Viewer", builtin: true, members: 4 },
];

// default grants per role (mirrors the real code gates as a starting point)
const DEFAULTS: Record<string, string[]> = {
  owner: PERMS.map((p) => p.id),
  admin: ["view", "create", "delete", "submit", "decide", "manage_wf", "send_sig", "manage_users", "manage_ws", "api_keys"],
  manager: ["view", "create", "delete", "submit", "decide", "manage_wf", "send_sig"],
  author: ["view", "create", "submit"],
  approver: ["view", "decide"],
  reviewer: ["view"],
  viewer: ["view"],
};

function initialGrants(): Record<string, Set<string>> {
  const g: Record<string, Set<string>> = {};
  INITIAL_ROLES.forEach((r) => (g[r.key] = new Set(DEFAULTS[r.key] ?? ["view"])));
  return g;
}

export default function RolesPage() {
  const [roles, setRoles] = useState<Role[]>(INITIAL_ROLES);
  const [grants, setGrants] = useState<Record<string, Set<string>>>(initialGrants);
  const [newRole, setNewRole] = useState("");
  const [savedAt, setSavedAt] = useState(false);

  function toggle(roleKey: string, permId: string) {
    if (roleKey === "owner") return; // owner always all
    setGrants((g) => {
      const next = new Set(g[roleKey]);
      next.has(permId) ? next.delete(permId) : next.add(permId);
      return { ...g, [roleKey]: next };
    });
  }
  function addRole() {
    const label = newRole.trim();
    if (!label) return;
    const key = label.toLowerCase().replace(/\s+/g, "_");
    if (roles.some((r) => r.key === key)) return;
    setRoles((r) => [...r, { key, label, builtin: false, members: 0 }]);
    setGrants((g) => ({ ...g, [key]: new Set(["view"]) }));
    setNewRole("");
  }

  const groups = Array.from(new Set(PERMS.map((p) => p.group)));

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Roles &amp; Permissions</span>}
        subtitle="Define what each role can do — and add custom roles beyond the built-in hierarchy."
        actions={
          <Button size="sm" onClick={() => { setSavedAt(true); setTimeout(() => setSavedAt(false), 1600); }}>
            {savedAt ? <><Check className="h-3.5 w-3.5" /> Saved</> : "Save changes"}
          </Button>
        }
      />

      <div className="space-y-4 p-4">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Add a custom role">
            <Input value={newRole} onChange={(e) => setNewRole(e.target.value)} placeholder="e.g. Legal Reviewer" className="w-56" />
          </Field>
          <Button size="sm" variant="secondary" onClick={addRole} disabled={!newRole.trim()}><Plus className="h-3.5 w-3.5" /> Add role</Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5"><Shield className="h-4 w-4" /> Permission matrix</CardTitle>
            <span className="text-xs text-ink-3">{roles.length} roles · {PERMS.length} permissions</span>
          </CardHeader>
          <CardBody className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line">
                    <th className="sticky left-0 z-10 bg-white px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">Permission</th>
                    {roles.map((r) => (
                      <th key={r.key} className="px-2 py-2 text-center">
                        <div className="text-xs font-semibold text-ink">{r.label}</div>
                        <div className="mt-0.5 inline-flex items-center gap-0.5 text-[10px] text-ink-3"><Users className="h-2.5 w-2.5" />{r.members}</div>
                        {!r.builtin && <div className="text-[9px] uppercase tracking-wide text-accent">custom</div>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {groups.map((grp) => (
                    <Fragment key={grp}>
                      <tr className="bg-surface-2">
                        <td colSpan={roles.length + 1} className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-3">{grp}</td>
                      </tr>
                      {PERMS.filter((p) => p.group === grp).map((p) => (
                        <tr key={p.id} className="border-b border-line last:border-0 hover:bg-surface-2/50">
                          <td className="sticky left-0 z-10 bg-white px-3 py-2 text-ink-2">{p.label}</td>
                          {roles.map((r) => {
                            const on = grants[r.key]?.has(p.id);
                            const locked = r.key === "owner";
                            return (
                              <td key={r.key} className="px-2 py-2 text-center">
                                <button
                                  onClick={() => toggle(r.key, p.id)}
                                  disabled={locked}
                                  className={`grid h-5 w-5 place-items-center rounded transition ${on ? "bg-accent text-white" : "bg-surface-3 text-transparent hover:bg-surface-2"} ${locked ? "cursor-not-allowed opacity-80" : ""}`}
                                  aria-label={`${r.label}: ${p.label}`}
                                >
                                  <Check className="h-3 w-3" />
                                </button>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">
              Owner always has every permission. Assign roles to people in <span className="font-medium text-ink-2">Settings → Users &amp; roles</span>.
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
