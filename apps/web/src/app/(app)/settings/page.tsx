"use client";

import { useEffect, useState } from "react";
import { Settings as SettingsIcon, UserPlus } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select, Skeleton } from "@/components/ui";
import { titleCase } from "@/lib/utils";
import type { User } from "@/lib/types";

export default function SettingsPage() {
  const { me } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState("");
  // invite form
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("author");
  const [password, setPassword] = useState("demo1234");
  const [inviting, setInviting] = useState(false);

  const isAdmin = me?.user.role === "owner" || me?.user.role === "admin";

  function load() {
    api.get<User[]>("/users").then(setUsers).catch(() => setUsers([]));
  }
  useEffect(load, []);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setError("");
    try {
      await api.post<User>("/users", { name: name.trim(), email: email.trim(), role, password });
      setName("");
      setEmail("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add the user.");
    } finally {
      setInviting(false);
    }
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle={me?.tenant.name} />
      <div className="space-y-5 p-6">
        <Card>
          <CardHeader>
            <CardTitle>Workspace</CardTitle>
          </CardHeader>
          <CardBody>
            <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 text-sm">
              <Row k="Name" v={me?.tenant.name} />
              <Row k="Subdomain" v={`${me?.tenant.slug}.app`} />
              <Row k="Plan" v={titleCase(me?.tenant.plan ?? "")} />
              <Row k="Default currency" v={me?.tenant.currency} />
              <Row k="Locale" v={me?.tenant.locale} />
              <Row k="Your role" v={titleCase(me?.user.role ?? "")} />
            </dl>
            <p className="mt-4 text-xs text-ink-3">
              Branding, security/SSO, custom fields, billing, retention &amp; the rest are specced in docs/08 &amp; docs/19.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <SettingsIcon className="h-4 w-4" /> Users &amp; roles
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            <ErrorBanner message={error} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                    <th className="py-2">User</th>
                    <th className="py-2">Email</th>
                    <th className="py-2">Role</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {users === null && (
                    <tr>
                      <td colSpan={4} className="py-3">
                        <Skeleton className="h-4" />
                      </td>
                    </tr>
                  )}
                  {users?.map((u) => (
                    <tr key={u.id} className="border-b border-line last:border-0">
                      <td className="py-2.5">
                        <span className="inline-flex items-center gap-2">
                          <Avatar name={u.name} color={u.avatar_color} size={24} />
                          <span className="font-medium text-ink">{u.name}</span>
                          {u.id === me?.user.id && <Badge tone="accent">you</Badge>}
                        </span>
                      </td>
                      <td className="py-2.5 text-ink-2">{u.email}</td>
                      <td className="py-2.5 text-ink-2">{titleCase(u.role)}</td>
                      <td className="py-2.5">
                        <Badge tone={u.is_active ? "neutral" : "neutral"}>{u.is_active ? "Active" : "Deactivated"}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {isAdmin && (
              <form onSubmit={invite} className="rounded-lg border border-line bg-surface-2 p-4">
                <div className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-ink">
                  <UserPlus className="h-4 w-4" /> Add a user
                </div>
                <div className="grid gap-3 sm:grid-cols-4">
                  <Field label="Name">
                    <Input value={name} onChange={(e) => setName(e.target.value)} required />
                  </Field>
                  <Field label="Email">
                    <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                  </Field>
                  <Field label="Role">
                    <Select value={role} onChange={(e) => setRole(e.target.value)}>
                      {["admin", "manager", "author", "approver", "reviewer", "viewer", "auditor"].map((r) => (
                        <option key={r} value={r}>
                          {titleCase(r)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Temp password" hint="≥ 8 chars">
                    <Input value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required />
                  </Field>
                </div>
                <div className="mt-3 flex justify-end">
                  <Button type="submit" size="sm" loading={inviting}>
                    Add user
                  </Button>
                </div>
              </form>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line/60 pb-2 last:border-0">
      <dt className="text-ink-3">{k}</dt>
      <dd className="text-right font-medium text-ink">{v ?? "—"}</dd>
    </div>
  );
}
