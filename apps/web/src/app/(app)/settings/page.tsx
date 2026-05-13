"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Key, Plug, Repeat, Settings as SettingsIcon, Trash2, UserPlus } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { SecurityPanel } from "@/components/security-panel";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select, Skeleton } from "@/components/ui";
import { titleCase } from "@/lib/utils";
import type { ApiKey, SweepResult, Tenant, User, WebhookEndpoint } from "@/lib/types";

export default function SettingsPage() {
  const { me, refreshMe } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState("");
  // invite form
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("author");
  const [password, setPassword] = useState("demo1234");
  const [inviting, setInviting] = useState(false);
  const [sweepBusy, setSweepBusy] = useState(false);
  const [sweepResult, setSweepResult] = useState<SweepResult | null>(null);

  const isAdmin = me?.user.role === "owner" || me?.user.role === "admin";

  function load() {
    api.get<User[]>("/users").then(setUsers).catch(() => setUsers([]));
  }
  useEffect(load, []);

  async function runSweep() {
    setSweepBusy(true);
    setError("");
    try {
      const r = await api.post<SweepResult>("/admin/sweep-renewals", {});
      setSweepResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't run the sweep.");
    } finally {
      setSweepBusy(false);
    }
  }

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
        <WorkspaceCard isAdmin={!!isAdmin} onSaved={refreshMe} />
        <BrandingCard isAdmin={!!isAdmin} onSaved={refreshMe} />

        <SecurityPanel />

        {isAdmin && <WebhooksCard />}
        {isAdmin && <ApiKeysCard />}

        {isAdmin && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Repeat className="h-4 w-4" /> Renewals sweep
              </CardTitle>
              <Button size="sm" variant="secondary" onClick={runSweep} loading={sweepBusy}>
                <Repeat className="h-3.5 w-3.5" /> Run now
              </Button>
            </CardHeader>
            <CardBody>
              <p className="text-sm text-ink-2">
                Walks every contract in this workspace, flips <code className="rounded bg-surface-2 px-1 text-xs">active → expiring</code> when the end
                date is within 30 days, and <code className="rounded bg-surface-2 px-1 text-xs">expiring/active → expired</code> when it&rsquo;s past — and
                posts the owner a reminder at the 30 / 7 / 1-day marks. Runs hourly in production (Celery beat); this button kicks one off now.
              </p>
              {sweepResult && (
                <div className="mt-3 grid grid-cols-3 gap-2 text-center sm:max-w-md">
                  <SweepStat label="Flagged expiring" v={sweepResult.flagged_expiring} />
                  <SweepStat label="Moved to expired" v={sweepResult.moved_to_expired} />
                  <SweepStat label="Reminders sent" v={sweepResult.reminders_sent} />
                </div>
              )}
            </CardBody>
          </Card>
        )}

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
                    <UserRow key={u.id} u={u} isMe={u.id === me?.user.id} isAdmin={!!isAdmin} myRole={me?.user.role ?? "viewer"} onChanged={load} onError={setError} />
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

function WorkspaceCard({ isAdmin, onSaved }: { isAdmin: boolean; onSaved: () => void }) {
  const [t, setT] = useState<Tenant | null>(null);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("");
  const [locale, setLocale] = useState("");
  const [tz, setTz] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    api.get<Tenant>("/tenant").then((tt) => {
      setT(tt); setName(tt.name); setCurrency(tt.currency); setLocale(tt.locale); setTz(tt.timezone);
    }).catch(() => {});
  }, []);

  async function save() {
    setBusy(true); setErr("");
    try {
      const tt = await api.patch<Tenant>("/tenant", { name: name || null, currency: currency || null, locale: locale || null, timezone: tz || null });
      setT(tt); setSavedAt(Date.now());
      onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  if (!t) return <Card><CardBody><Skeleton className="h-24" /></CardBody></Card>;
  return (
    <Card>
      <CardHeader><CardTitle>Workspace</CardTitle></CardHeader>
      <CardBody className="space-y-3">
        {err && <ErrorBanner message={err} />}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} disabled={!isAdmin} />
          </Field>
          <Field label="Subdomain" hint="Read-only">
            <Input value={`${t.slug}.app`} disabled readOnly />
          </Field>
          <Field label="Default currency">
            <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} disabled={!isAdmin} />
          </Field>
          <Field label="Locale" hint="Arabic / Hebrew / Persian / Urdu switch the UI to RTL">
            <Select value={locale} onChange={(e) => setLocale(e.target.value)} disabled={!isAdmin}>
              {[
                ["en", "English"], ["en-GB", "English (UK)"], ["en-US", "English (US)"],
                ["ar", "العربية (Arabic, RTL)"], ["he", "עברית (Hebrew, RTL)"],
                ["fa", "فارسی (Persian, RTL)"], ["ur", "اردو (Urdu, RTL)"],
                ["fr", "Français"], ["de", "Deutsch"], ["es", "Español"], ["pt", "Português"],
                ["zh", "中文"], ["ja", "日本語"], ["hi", "हिन्दी"],
              ].map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </Select>
          </Field>
          <Field label="Timezone" hint="e.g. UTC, Europe/London, Asia/Dubai">
            <Input value={tz} onChange={(e) => setTz(e.target.value)} disabled={!isAdmin} />
          </Field>
          <Field label="Plan" hint="Read-only">
            <Input value={titleCase(t.plan)} disabled readOnly />
          </Field>
        </div>
        {isAdmin && (
          <div className="flex items-center justify-end gap-3">
            {savedAt && <span className="text-xs text-emerald-700">Saved.</span>}
            <Button size="sm" onClick={save} loading={busy}>Save workspace</Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

const PRESET_ACCENTS = ["#3E7BFA", "#8B7BF5", "#2BC0D4", "#F6B83C", "#F5736B", "#3FBF7F", "#111827"];

function BrandingCard({ isAdmin, onSaved }: { isAdmin: boolean; onSaved: () => void }) {
  const [t, setT] = useState<Tenant | null>(null);
  const [color, setColor] = useState("#3E7BFA");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get<Tenant>("/tenant").then((tt) => { setT(tt); setColor(tt.accent_color); }).catch(() => {});
  }, []);

  function preview(c: string) {
    setColor(c);
    if (typeof document !== "undefined") document.documentElement.style.setProperty("--color-accent", c);
  }

  async function save() {
    setBusy(true); setErr("");
    try {
      await api.patch("/tenant", { accent_color: color });
      onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  if (!t) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Branding</CardTitle>
        <span className="text-xs text-ink-3">Accent color · used throughout the app</span>
      </CardHeader>
      <CardBody className="space-y-3">
        {err && <ErrorBanner message={err} />}
        <div className="flex flex-wrap items-center gap-2">
          {PRESET_ACCENTS.map((c) => (
            <button
              key={c}
              onClick={() => isAdmin && preview(c)}
              disabled={!isAdmin}
              className={`grid h-9 w-9 place-items-center rounded-full ring-offset-2 ${color.toLowerCase() === c.toLowerCase() ? "ring-2 ring-ink/70" : ""}`}
              style={{ backgroundColor: c }}
              title={c}
            />
          ))}
          <input
            type="color"
            value={color}
            onChange={(e) => preview(e.target.value)}
            disabled={!isAdmin}
            className="h-9 w-12 rounded-md border border-line bg-white"
            title="Custom"
          />
          <span className="ml-2 font-mono text-xs text-ink-3">{color}</span>
          {isAdmin && (
            <Button size="sm" className="ml-auto" loading={busy} onClick={save}>
              Save branding
            </Button>
          )}
        </div>
        <div className="rounded-md border border-line bg-surface-2 p-3 text-sm">
          <span className="text-ink-3">Preview: </span>
          <span className="font-medium text-accent">A button or active link</span> uses this colour.
        </div>
      </CardBody>
    </Card>
  );
}

const ALL_ROLES = ["owner", "admin", "manager", "author", "approver", "reviewer", "viewer", "auditor"];

function UserRow({ u, isMe, isAdmin, myRole, onChanged, onError }: { u: User; isMe: boolean; isAdmin: boolean; myRole: string; onChanged: () => void; onError: (e: string) => void }) {
  const [busy, setBusy] = useState(false);
  // admins can't touch owners
  const canEdit = isAdmin && (u.role !== "owner" || myRole === "owner");
  const canDeactivate = canEdit && !isMe;

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
          <Avatar name={u.name} color={u.avatar_color} size={24} />
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
            disabled={busy}
            className="h-8 rounded-sm border border-line bg-white px-2 text-sm"
          >
            {ALL_ROLES.map((r) => (
              <option key={r} value={r}>{titleCase(r)}</option>
            ))}
          </select>
        ) : (
          <span className="text-ink-2">{titleCase(u.role)}</span>
        )}
      </td>
      <td className="py-2.5">
        <div className="flex items-center gap-2">
          <Badge tone="neutral">{u.is_active ? "Active" : "Deactivated"}</Badge>
          {canDeactivate && (
            <Button size="sm" variant="ghost" loading={busy} onClick={() => patch({ is_active: !u.is_active })}>
              {u.is_active ? "Deactivate" : "Reactivate"}
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------- Webhooks card

function WebhooksCard() {
  const [rows, setRows] = useState<WebhookEndpoint[] | null>(null);
  const [url, setUrl] = useState("");
  const [desc, setDesc] = useState("");
  const [events, setEvents] = useState("*");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [newSecret, setNewSecret] = useState<{ id: string; secret: string } | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  function load() {
    api.get<WebhookEndpoint[]>("/webhooks").then(setRows).catch(() => setRows([]));
  }
  useEffect(load, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api.post<WebhookEndpoint & { secret: string }>("/webhooks", {
        url: url.trim(), description: desc.trim(),
        events: events.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setNewSecret({ id: r.id, secret: r.secret });
      setUrl(""); setDesc(""); setEvents("*");
      load();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : "Couldn't create the webhook.");
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (!window.confirm("Delete this webhook? Past delivery history is also removed.")) return;
    await api.del(`/webhooks/${id}`); load();
  }
  async function toggle(ep: WebhookEndpoint) {
    await api.patch(`/webhooks/${ep.id}`, { is_active: !ep.is_active }); load();
  }
  async function fire(ep: WebhookEndpoint) {
    setTestResult((m) => ({ ...m, [ep.id]: "…" }));
    try {
      const d = await api.post<{ status: string; response_code: number }>(`/webhooks/${ep.id}/test`, {});
      setTestResult((m) => ({ ...m, [ep.id]: d.status === "ok" ? `OK (${d.response_code})` : `Failed (${d.response_code})` }));
      load();
    } catch (e: unknown) {
      setTestResult((m) => ({ ...m, [ep.id]: e instanceof ApiError ? e.message : "Failed" }));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5"><Plug className="h-4 w-4" /> Webhooks</CardTitle>
        <span className="text-xs text-ink-3">Outbound HTTPS callbacks · HMAC-SHA256 signed</span>
      </CardHeader>
      <CardBody className="space-y-3">
        {err && <ErrorBanner message={err} />}
        {newSecret && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Check className="h-4 w-4 text-emerald-700" />
              <span className="font-medium text-ink">Endpoint created.</span> Copy the signing secret now — it&rsquo;s shown only once.
            </div>
            <div className="mt-2 flex items-center gap-2">
              <code className="rounded bg-white px-2 py-1 font-mono text-xs text-ink">{newSecret.secret}</code>
              <button onClick={() => navigator.clipboard?.writeText(newSecret.secret)} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                <Copy className="h-3 w-3" /> copy
              </button>
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setNewSecret(null)}>Dismiss</Button>
            </div>
          </div>
        )}
        <form onSubmit={create} className="grid gap-2 sm:grid-cols-12">
          <div className="sm:col-span-5"><Field label="URL"><Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-app.example/webhook" required /></Field></div>
          <div className="sm:col-span-4"><Field label="Description"><Input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="What is this for?" /></Field></div>
          <div className="sm:col-span-3"><Field label="Events" hint="Comma-list, or *"><Input value={events} onChange={(e) => setEvents(e.target.value)} placeholder="contract.signed, contract.expired" /></Field></div>
          <div className="flex items-end justify-end sm:col-span-12"><Button type="submit" size="sm" loading={busy}><Plug className="h-3.5 w-3.5" /> Add endpoint</Button></div>
        </form>
        {rows === null && <Skeleton className="h-16" />}
        {rows !== null && rows.length === 0 && <p className="text-sm text-ink-3">No webhooks yet. Add one to receive HTTP callbacks on contract events.</p>}
        {rows && rows.length > 0 && (
          <div className="divide-y divide-line rounded-md border border-line">
            {rows.map((ep) => (
              <div key={ep.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="truncate text-ink">{ep.url}</code>
                    <Badge tone="neutral">{ep.is_active ? "active" : "paused"}</Badge>
                    {ep.last_status && <Badge tone={ep.last_status === "ok" ? "accent" : "neutral"}>last: {ep.last_status}</Badge>}
                  </div>
                  <div className="text-xs text-ink-3">
                    Events: {(ep.events || []).join(", ") || "*"}{ep.description ? ` · ${ep.description}` : ""}
                    {testResult[ep.id] && <span className="ml-2 text-ink-2">Test → {testResult[ep.id]}</span>}
                  </div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => fire(ep)}>Test fire</Button>
                <Button size="sm" variant="ghost" onClick={() => toggle(ep)}>{ep.is_active ? "Pause" : "Activate"}</Button>
                <Button size="sm" variant="ghost" onClick={() => remove(ep.id)} title="Delete"><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            ))}
          </div>
        )}
        <p className="text-[11px] text-ink-3">
          Each POST carries header <code className="rounded bg-surface-2 px-1">X-CM-Signature: t=&lt;unix&gt;,v1=&lt;hex&gt;</code> — verify with HMAC-SHA256(secret, &quot;&lt;unix&gt;.&lt;raw-body&gt;&quot;). Events include: <code className="rounded bg-surface-2 px-1">contract.status_changed</code>, <code className="rounded bg-surface-2 px-1">contract.signed</code>, <code className="rounded bg-surface-2 px-1">contract.expired</code>, <code className="rounded bg-surface-2 px-1">contract.renewed</code>, <code className="rounded bg-surface-2 px-1">contract.voided</code>, <code className="rounded bg-surface-2 px-1">contract.terminated</code>, <code className="rounded bg-surface-2 px-1">envelope.signed</code>, <code className="rounded bg-surface-2 px-1">envelope.completed</code>.
        </p>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- API Keys card

function ApiKeysCard() {
  const [rows, setRows] = useState<ApiKey[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [shown, setShown] = useState<{ id: string; token: string } | null>(null);

  function load() {
    api.get<ApiKey[]>("/api-keys").then(setRows).catch(() => setRows([]));
  }
  useEffect(load, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api.post<ApiKey & { token: string }>("/api-keys", { name: name.trim() });
      setShown({ id: r.id, token: r.token });
      setName("");
      load();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : "Couldn't create the API key.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(k: ApiKey) {
    if (!window.confirm(`Revoke "${k.name}"? Requests using this key will start to fail immediately.`)) return;
    await api.del(`/api-keys/${k.id}`);
    load();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5"><Key className="h-4 w-4" /> API keys</CardTitle>
        <span className="text-xs text-ink-3">Bearer tokens for headless integrations · inherit your role</span>
      </CardHeader>
      <CardBody className="space-y-3">
        {err && <ErrorBanner message={err} />}
        {shown && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Check className="h-4 w-4 text-emerald-700" />
              <span className="font-medium text-ink">API key created — copy it now, it&rsquo;s shown only once.</span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <code className="break-all rounded bg-white px-2 py-1 font-mono text-xs text-ink">{shown.token}</code>
              <button onClick={() => navigator.clipboard?.writeText(shown.token)} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                <Copy className="h-3 w-3" /> copy
              </button>
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setShown(null)}>Dismiss</Button>
            </div>
            <div className="mt-2 text-[11px] text-ink-3">Use it with <code className="rounded bg-white px-1">Authorization: Bearer {shown.token.slice(0, 12)}…</code></div>
          </div>
        )}
        <form onSubmit={create} className="flex flex-wrap items-end gap-2">
          <div className="flex-1"><Field label="Name" hint="e.g. CI pipeline / Zapier"><Input value={name} onChange={(e) => setName(e.target.value)} required /></Field></div>
          <Button type="submit" size="sm" loading={busy}><Key className="h-3.5 w-3.5" /> Create key</Button>
        </form>
        {rows === null && <Skeleton className="h-16" />}
        {rows !== null && rows.length === 0 && <p className="text-sm text-ink-3">No API keys yet.</p>}
        {rows && rows.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                <th className="py-2">Name</th>
                <th className="py-2">Prefix</th>
                <th className="py-2">Last used</th>
                <th className="py-2">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((k) => (
                <tr key={k.id} className="border-b border-line last:border-0">
                  <td className="py-2 text-ink">{k.name}</td>
                  <td className="py-2 font-mono text-xs text-ink-2">{k.prefix}…</td>
                  <td className="py-2 text-ink-3">{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "never"}</td>
                  <td className="py-2"><Badge tone="neutral">{k.revoked_at ? "revoked" : "active"}</Badge></td>
                  <td className="py-2 text-right">
                    {!k.revoked_at && <Button size="sm" variant="ghost" onClick={() => revoke(k)}><Trash2 className="h-3.5 w-3.5" /></Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

function SweepStat({ label, v }: { label: string; v: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink tnum">{v}</div>
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
