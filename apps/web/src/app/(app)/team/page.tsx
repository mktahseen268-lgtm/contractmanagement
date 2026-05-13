"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, Mail, Shield, UserPlus, Users as UsersIcon } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select, Skeleton } from "@/components/ui";
import { titleCase } from "@/lib/utils";
import type { User } from "@/lib/types";

// Permissions matrix — derived from the actual code's role gates. Update here if backend
// _EDIT_ROLES / _ADMIN_ROLES / workflow_service._OVERRIDE_ROLES change.
type RoleKey = "owner" | "admin" | "manager" | "author" | "approver" | "reviewer" | "viewer" | "auditor";
const ROLES: RoleKey[] = ["owner", "admin", "manager", "author", "approver", "reviewer", "viewer", "auditor"];

const PERMS: { label: string; allow: Set<RoleKey>; note?: string }[] = [
  { label: "See contracts, dashboard, reports", allow: new Set<RoleKey>(ROLES) },
  { label: "Create + edit contracts", allow: new Set<RoleKey>(["owner", "admin", "manager", "author"]) },
  { label: "Delete contracts", allow: new Set<RoleKey>(["owner", "admin", "manager"]) },
  { label: "Submit for approval", allow: new Set<RoleKey>(["owner", "admin", "manager", "author"]) },
  { label: "Approve / reject / request changes", allow: new Set<RoleKey>(["owner", "admin", "approver", "manager"]), note: "Role hierarchy — anyone at or above the step's role can decide." },
  { label: "Manage approval workflows", allow: new Set<RoleKey>(["owner", "admin", "manager"]) },
  { label: "Prepare & send for signature", allow: new Set<RoleKey>(["owner", "admin", "manager", "author"]) },
  { label: "Void / recall an envelope", allow: new Set<RoleKey>(["owner", "admin", "manager", "author"]) },
  { label: "Manage obligations", allow: new Set<RoleKey>(["owner", "admin", "manager", "author"]), note: "An obligation's owner can also update it." },
  { label: "Run renewals sweep", allow: new Set<RoleKey>(["owner", "admin"]) },
  { label: "Edit workspace + branding", allow: new Set<RoleKey>(["owner", "admin"]) },
  { label: "Invite / role-change / deactivate users", allow: new Set<RoleKey>(["owner", "admin"]), note: "Admins can't change another owner. The last active owner can't be demoted or deactivated." },
  { label: "See workspace-wide audit log", allow: new Set<RoleKey>(["owner", "admin", "auditor"]), note: "Others see their own actions only." },
];

type InviteResult = User & { generated_password: string | null };

export default function TeamPage() {
  const { me } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState("");
  const isAdmin = me?.user.role === "owner" || me?.user.role === "admin";
  const myRole = me?.user.role ?? "viewer";

  const load = useCallback(() => {
    api.get<User[]>("/users").then(setUsers).catch(() => setUsers([]));
  }, []);
  useEffect(load, [load]);

  // gate: non-admins see a friendly message + a link back to dashboard
  if (me && !isAdmin) {
    return (
      <div>
        <PageHeader title="Team" subtitle="Manage employees & roles" />
        <div className="p-6">
          <Card>
            <CardBody className="py-10 text-center">
              <Shield className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">Owners &amp; admins only</div>
              <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">
                Your current role (<strong>{titleCase(myRole)}</strong>) can&rsquo;t invite or manage other users. Ask an admin or the workspace owner to bump your role, or to add a new teammate for you.
              </p>
              <Button variant="secondary" size="sm" className="mt-4" onClick={() => router.push("/dashboard")}>
                Back to dashboard
              </Button>
            </CardBody>
          </Card>
        </div>
      </div>
    );
  }

  const ownerCount = users?.filter((u) => u.role === "owner" && u.is_active).length ?? 0;

  return (
    <div>
      <PageHeader
        title="Team"
        subtitle={users === null ? "Loading…" : `${users.length} member${users.length === 1 ? "" : "s"} · ${ownerCount} owner${ownerCount === 1 ? "" : "s"} · workspace: ${me?.tenant.name}`}
      />

      <div className="space-y-6 p-6">
        {error && <ErrorBanner message={error} />}

        {/* Invite */}
        <InviteCard onInvited={() => { setError(""); load(); }} onError={setError} />

        {/* Members */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <UsersIcon className="h-4 w-4" /> Members
            </CardTitle>
            <span className="text-xs text-ink-3">Click a role to change it · deactivated users can&rsquo;t sign in</span>
          </CardHeader>
          <CardBody>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                    <th className="py-2">Member</th>
                    <th className="py-2">Email</th>
                    <th className="py-2">Role</th>
                    <th className="py-2">Status</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users === null && (
                    <tr><td colSpan={5} className="py-3"><Skeleton className="h-4" /></td></tr>
                  )}
                  {users?.map((u) => (
                    <MemberRow
                      key={u.id}
                      u={u}
                      isMe={u.id === me?.user.id}
                      myRole={myRole}
                      ownerCount={ownerCount}
                      onChanged={load}
                      onError={setError}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        {/* Permissions matrix */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Shield className="h-4 w-4" /> What each role can do
            </CardTitle>
            <span className="text-xs text-ink-3">Hierarchy: viewer &lt; reviewer &lt; author &lt; approver &lt; manager &lt; admin &lt; owner</span>
          </CardHeader>
          <CardBody className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                  <th className="py-2 pr-3">Action</th>
                  {ROLES.map((r) => (
                    <th key={r} className="px-2 py-2 text-center">{titleCase(r)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PERMS.map((p) => (
                  <tr key={p.label} className="border-b border-line last:border-0">
                    <td className="py-2.5 pr-3 align-top">
                      <div className="text-ink">{p.label}</div>
                      {p.note && <div className="mt-0.5 text-[11px] text-ink-3">{p.note}</div>}
                    </td>
                    {ROLES.map((r) => (
                      <td key={r} className="px-2 py-2.5 text-center align-top">
                        {p.allow.has(r) ? (
                          <Check className="mx-auto h-3.5 w-3.5 text-emerald-600" />
                        ) : (
                          <span className="text-ink-3">—</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[11px] text-ink-3">
              Permissions are enforced server-side in every router (role gates + RLS); the table is for reference. Full design in docs/19 §3.
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- invite form

function InviteCard({ onInvited, onError }: { onInvited: () => void; onError: (s: string) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<RoleKey>("author");
  const [welcome, setWelcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastInvite, setLastInvite] = useState<InviteResult | null>(null);
  const [copied, setCopied] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    setLastInvite(null);
    try {
      const r = await api.post<InviteResult>("/users", {
        name: name.trim(),
        email: email.trim(),
        role,
        welcome_message: welcome.trim() || undefined,
      });
      setLastInvite(r);
      setName(""); setEmail(""); setWelcome("");
      onInvited();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Couldn't invite that user.");
    } finally {
      setBusy(false);
    }
  }

  function copyTemp() {
    if (!lastInvite?.generated_password) return;
    navigator.clipboard?.writeText(lastInvite.generated_password).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), 1500); },
      () => {},
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <UserPlus className="h-4 w-4" /> Invite an employee
        </CardTitle>
        <span className="text-xs text-ink-3">A welcome email with their temp password is sent automatically</span>
      </CardHeader>
      <CardBody>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-3">
            <Field label="Full name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Asha Kapoor" />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Work email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="asha@yourcompany.com" />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Role" hint="Drives every permission">
              <Select value={role} onChange={(e) => setRole(e.target.value as RoleKey)}>
                {(["admin", "manager", "author", "approver", "reviewer", "viewer", "auditor"] as RoleKey[]).map((r) => (
                  <option key={r} value={r}>{titleCase(r)}</option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Welcome note (optional)">
              <Input value={welcome} onChange={(e) => setWelcome(e.target.value)} placeholder="Welcome aboard!" />
            </Field>
          </div>
          <div className="flex items-end justify-end sm:col-span-12">
            <Button type="submit" loading={busy} disabled={!email.trim() || !name.trim()}>
              <Mail className="h-3.5 w-3.5" /> Send invite
            </Button>
          </div>
        </form>

        {lastInvite && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Check className="h-4 w-4 text-emerald-700" />
              <span className="font-medium text-ink">
                Invited <strong>{lastInvite.name}</strong> as <strong>{titleCase(lastInvite.role)}</strong>.
              </span>
              <Badge tone="neutral">{lastInvite.email}</Badge>
            </div>
            {lastInvite.generated_password ? (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-2">
                Temporary password (also emailed):
                <code className="rounded bg-white px-2 py-1 font-mono text-ink">{lastInvite.generated_password}</code>
                <button onClick={copyTemp} className="inline-flex items-center gap-1 text-accent hover:underline">
                  {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                  {copied ? "copied" : "copy"}
                </button>
              </div>
            ) : (
              <div className="mt-1 text-xs text-ink-2">Welcome email queued through the Outbox.</div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------- one row

function MemberRow({
  u, isMe, myRole, ownerCount, onChanged, onError,
}: {
  u: User; isMe: boolean; myRole: string; ownerCount: number; onChanged: () => void; onError: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  // admins can't touch owners; only owner can change another owner
  const canEdit = (myRole === "owner") || (myRole === "admin" && u.role !== "owner");
  const lastOwner = u.role === "owner" && ownerCount <= 1;

  async function patch(payload: Partial<{ role: string; is_active: boolean }>) {
    setBusy(true);
    try {
      await api.patch<User>(`/users/${u.id}`, payload);
      onError("");
      onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Couldn't update the user.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-b border-line last:border-0">
      <td className="py-2.5">
        <span className="inline-flex items-center gap-2">
          <Avatar name={u.name} color={u.avatar_color} size={26} />
          <span className="font-medium text-ink">{u.name}</span>
          {isMe && <Badge tone="accent">you</Badge>}
        </span>
      </td>
      <td className="py-2.5 text-ink-2">{u.email}</td>
      <td className="py-2.5">
        {canEdit && !isMe ? (
          <select
            value={u.role}
            onChange={(e) => patch({ role: e.target.value })}
            disabled={busy || lastOwner}
            title={lastOwner ? "The last active owner can't be demoted" : ""}
            className="h-8 rounded-sm border border-line bg-white px-2 text-sm disabled:opacity-50"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>{titleCase(r)}</option>
            ))}
          </select>
        ) : (
          <span className="text-ink-2">{titleCase(u.role)}</span>
        )}
      </td>
      <td className="py-2.5">
        <Badge tone={u.is_active ? "neutral" : "neutral"}>{u.is_active ? "Active" : "Deactivated"}</Badge>
      </td>
      <td className="py-2.5 text-right">
        {canEdit && !isMe && !lastOwner && (
          <Button size="sm" variant="ghost" loading={busy} onClick={() => patch({ is_active: !u.is_active })}>
            {u.is_active ? "Deactivate" : "Reactivate"}
          </Button>
        )}
      </td>
    </tr>
  );
}
