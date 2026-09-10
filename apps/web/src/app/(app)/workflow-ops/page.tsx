"use client";

/**
 * Workflow operations — the running side of the Phase 4 engine.
 *
 *   Escalations   what has breached its SLA, and how long breaches take to clear
 *   Approval matrix  the rules that add reviewers based on value, risk or jurisdiction
 *   Delegations   who is covering for whom
 *   Calendar      the working days and holidays the SLA clock runs on
 *
 * All four are backed by real endpoints under /workflow.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clock,
  Plus,
  RefreshCw,
  Scale,
  Trash2,
  UserCheck,
} from "lucide-react";
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
import type { ApprovalRule, Delegation, Escalation, Holiday, User } from "@/lib/types";

type Tab = "escalations" | "rules" | "delegations" | "calendar";

const TABS: { key: Tab; label: string; icon: typeof Clock }[] = [
  { key: "escalations", label: "Escalations", icon: AlertTriangle },
  { key: "rules", label: "Approval matrix", icon: Scale },
  { key: "delegations", label: "Delegations", icon: UserCheck },
  { key: "calendar", label: "Working calendar", icon: CalendarDays },
];

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function WorkflowOpsPage() {
  const { me } = useAuth();
  const isAdmin = me?.user.role === "owner" || me?.user.role === "admin";
  const [tab, setTab] = useState<Tab>("escalations");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Workflow operations"
        subtitle="SLA breaches, the approval matrix, delegations and the working calendar"
      />
      <nav className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition ${
              tab === key ? "border-accent text-accent" : "border-transparent text-ink-2 hover:text-ink"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      {tab === "escalations" && <Escalations isAdmin={isAdmin} />}
      {tab === "rules" && <Rules isAdmin={isAdmin} />}
      {tab === "delegations" && <Delegations />}
      {tab === "calendar" && <Calendar isAdmin={isAdmin} />}
    </div>
  );
}

// ---------------------------------------------------------------------------- escalations

function Escalations({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<Escalation[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<Escalation[]>("/workflow/escalations", { cache: false })
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  useEffect(load, [load]);

  async function sweep() {
    setBusy(true);
    setError("");
    try {
      const result = await api.post<{ reminded: number; escalated: number; breached: number }>(
        "/workflow/sla-sweep",
      );
      setError(
        `Sweep complete — ${result.reminded} reminded, ${result.escalated} escalated, ${result.breached} past due.`,
      );
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not run the sweep.");
    } finally {
      setBusy(false);
    }
  }

  const open = (rows ?? []).filter((r) => !r.resolved_at);
  const resolved = (rows ?? []).filter((r) => r.resolved_at && r.hours_to_resolve !== null);
  const meanResolve =
    resolved.length > 0
      ? resolved.reduce((sum, r) => sum + (r.hours_to_resolve ?? 0), 0) / resolved.length
      : null;

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Open escalations" value={open.length} tone={open.length ? "text-red-600" : undefined} />
        <Stat label="Escalations (90 days)" value={rows?.length ?? 0} />
        <Stat
          label="Mean time to resolve"
          value={meanResolve === null ? "—" : `${meanResolve.toFixed(1)}h`}
        />
      </div>

      <div className="flex items-center gap-2">
        <Button variant="ghost" onClick={load}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
        {isAdmin && (
          <Button variant="ghost" onClick={sweep} disabled={busy}>
            {busy ? "Running…" : "Run SLA sweep now"}
          </Button>
        )}
      </div>

      {rows === null ? (
        <Skeleton className="h-32 w-full" />
      ) : rows.length === 0 ? (
        <Card>
          <CardBody className="space-y-2 py-10 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-accent" />
            <p className="text-sm text-ink-2">No reviews have breached their SLA. </p>
          </CardBody>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs text-ink-2">
                <tr>
                  <th className="px-3 py-2 font-medium">Agreement</th>
                  <th className="px-3 py-2 font-medium">Step</th>
                  <th className="px-3 py-2 font-medium">Due</th>
                  <th className="px-3 py-2 font-medium">Escalated</th>
                  <th className="px-3 py-2 font-medium">To</th>
                  <th className="px-3 py-2 font-medium">Resolved</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.step_id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">
                      <div className="font-medium text-ink">{r.contract_title}</div>
                      <div className="text-xs text-ink-3">{r.contract_reference}</div>
                    </td>
                    <td className="px-3 py-2 text-ink-2">
                      {r.step_name}
                      <div className="text-xs text-ink-3">Stage {r.stage_index + 1}</div>
                    </td>
                    <td className="px-3 py-2 text-ink-2">{fmt(r.due_at)}</td>
                    <td className="px-3 py-2 text-ink-2">{fmt(r.escalated_at)}</td>
                    <td className="px-3 py-2 text-ink-2">{r.escalated_to_name || "—"}</td>
                    <td className="px-3 py-2">
                      {r.resolved_at ? (
                        <span className="text-ink-2">
                          {fmt(r.resolved_at)}
                          {r.hours_to_resolve !== null && (
                            <span className="block text-xs text-ink-3">
                              {r.hours_to_resolve.toFixed(1)} working hours
                            </span>
                          )}
                        </span>
                      ) : (
                        <Badge tone="neutral">still open</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className={`font-display text-2xl font-semibold ${tone ?? "text-ink"}`}>{value}</div>
      <div className="text-xs text-ink-2">{label}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------- rules

function Rules({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<ApprovalRule[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    contract_type: "",
    min_value: 0,
    max_value: "",
    risk_level: "",
    non_standard_only: false,
    stage_name: "",
    required_role: "approver",
    sla_hours: 48,
  });

  const load = useCallback(() => {
    api.get<ApprovalRule[]>("/workflow/rules", { cache: false }).then(setRows).catch(() => setRows([]));
  }, []);

  useEffect(() => {
    load();
    api.get<User[]>("/users").then(setUsers).catch(() => setUsers([]));
  }, [load]);

  async function create() {
    setError("");
    try {
      await api.post("/workflow/rules", {
        name: form.name,
        contract_type: form.contract_type,
        min_value: Number(form.min_value) || 0,
        max_value: form.max_value === "" ? null : Number(form.max_value),
        risk_level: form.risk_level,
        non_standard_only: form.non_standard_only,
        stage_name: form.stage_name || form.name,
        stage_policy: "all",
        stage_steps: [
          { name: form.stage_name || form.name, assignee_kind: "role", assignee_value: form.required_role },
        ],
        sla_hours: Number(form.sla_hours) || 0,
        insert_after_stage: -1,
        is_active: true,
      });
      setForm({ ...form, name: "", stage_name: "" });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the rule.");
    }
  }

  async function remove(id: string) {
    try {
      await api.del(`/workflow/rules/${id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not deactivate the rule.");
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}
      <Card>
        <CardHeader>
          <CardTitle>Approval matrix</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-ink-2">
            Rules <strong>add</strong> a review stage when an agreement matches — they do not replace
            the workflow. So &ldquo;anything over 10 million also needs the CFO&rdquo; is one rule,
            not a second copy of every workflow.
          </p>
          {rows === null ? (
            <Skeleton className="h-20 w-full" />
          ) : rows.length === 0 ? (
            <p className="text-sm text-ink-3">No rules yet — every agreement follows its workflow as written.</p>
          ) : (
            <ul className="divide-y divide-line">
              {rows.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink">{r.name}</div>
                    <div className="text-xs text-ink-2">
                      {describeRule(r)} → adds <strong>{r.stage_name || "a stage"}</strong>
                      {r.sla_hours > 0 && ` (${r.sla_hours}h SLA)`}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={r.is_active ? "accent" : "neutral"}>
                      {r.is_active ? "active" : "inactive"}
                    </Badge>
                    {isAdmin && r.is_active && (
                      <button
                        type="button"
                        onClick={() => remove(r.id)}
                        className="rounded p-1 text-ink-3 hover:text-red-600"
                        aria-label="Deactivate rule"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>Add a rule</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Rule name">
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Over 10M needs the CFO"
                />
              </Field>
              <Field label="Stage this adds">
                <Input
                  value={form.stage_name}
                  onChange={(e) => setForm({ ...form, stage_name: e.target.value })}
                  placeholder="CFO sign-off"
                />
              </Field>
              <Field label="Minimum value">
                <Input
                  type="number"
                  value={form.min_value}
                  onChange={(e) => setForm({ ...form, min_value: Number(e.target.value) })}
                />
              </Field>
              <Field label="Maximum value" hint="Blank = no upper limit">
                <Input
                  type="number"
                  value={form.max_value}
                  onChange={(e) => setForm({ ...form, max_value: e.target.value })}
                />
              </Field>
              <Field label="Who must review">
                <Select
                  value={form.required_role}
                  onChange={(e) => setForm({ ...form, required_role: e.target.value })}
                >
                  {["approver", "manager", "admin", "owner"].map((r) => (
                    <option key={r} value={r}>
                      {r} or above
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="SLA (working hours)">
                <Input
                  type="number"
                  value={form.sla_hours}
                  onChange={(e) => setForm({ ...form, sla_hours: Number(e.target.value) })}
                />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={form.non_standard_only}
                onChange={(e) => setForm({ ...form, non_standard_only: e.target.checked })}
              />
              Only when the agreement is classified non-standard
            </label>
            <Button onClick={create} disabled={!form.name.trim()}>
              <Plus className="h-4 w-4" /> Add rule
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function describeRule(r: ApprovalRule): string {
  const parts: string[] = [];
  if (r.contract_type) parts.push(r.contract_type.toUpperCase());
  if (r.department) parts.push(r.department);
  if (r.risk_level) parts.push(`${r.risk_level} risk`);
  if (r.non_standard_only) parts.push("non-standard");
  if (r.min_value > 0 || r.max_value !== null) {
    const lo = r.min_value ? r.min_value.toLocaleString() : "0";
    const hi = r.max_value === null ? "∞" : r.max_value.toLocaleString();
    parts.push(`${lo}–${hi}`);
  }
  return parts.length ? parts.join(" · ") : "Any agreement";
}

// ---------------------------------------------------------------------------- delegations

function Delegations() {
  const [rows, setRows] = useState<Delegation[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ to_user_id: "", starts_at: "", ends_at: "", reason: "" });

  const load = useCallback(() => {
    api.get<Delegation[]>("/workflow/delegations", { cache: false }).then(setRows).catch(() => setRows([]));
  }, []);

  useEffect(() => {
    load();
    api.get<User[]>("/users").then(setUsers).catch(() => setUsers([]));
  }, [load]);

  async function create() {
    setError("");
    try {
      await api.post("/workflow/delegations", {
        to_user_id: form.to_user_id,
        scope: "all",
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        reason: form.reason,
      });
      setForm({ to_user_id: "", starts_at: "", ends_at: "", reason: "" });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the delegation.");
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}
      <Card>
        <CardHeader>
          <CardTitle>Out-of-office cover</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-ink-2">
            Reviews assigned to you route to your proxy for the window. Both names stay in the audit
            trail — an approval given under delegation is never recorded as though you gave it.
          </p>
          {rows === null ? (
            <Skeleton className="h-16 w-full" />
          ) : rows.length === 0 ? (
            <p className="text-sm text-ink-3">No delegations.</p>
          ) : (
            <ul className="divide-y divide-line">
              {rows.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="text-ink">
                    <strong>{d.from_user_name}</strong> → {d.to_user_name}
                    <span className="ml-2 text-xs text-ink-2">
                      {fmt(d.starts_at)} – {fmt(d.ends_at)}
                    </span>
                  </span>
                  <Badge tone={d.is_active ? "accent" : "neutral"}>
                    {d.is_active ? "active" : "revoked"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Delegate my approvals</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Cover">
              <Select
                value={form.to_user_id}
                onChange={(e) => setForm({ ...form, to_user_id: e.target.value })}
              >
                <option value="">Choose a colleague…</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Reason">
              <Input
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                placeholder="Annual leave"
              />
            </Field>
            <Field label="From">
              <Input
                type="datetime-local"
                value={form.starts_at}
                onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
              />
            </Field>
            <Field label="Until">
              <Input
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => setForm({ ...form, ends_at: e.target.value })}
              />
            </Field>
          </div>
          <Button
            onClick={create}
            disabled={!form.to_user_id || !form.starts_at || !form.ends_at}
          >
            <Plus className="h-4 w-4" /> Delegate
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------- calendar

function Calendar({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<Holiday[] | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ day: "", name: "" });

  const load = useCallback(() => {
    api.get<Holiday[]>("/workflow/holidays", { cache: false }).then(setRows).catch(() => setRows([]));
  }, []);

  useEffect(load, [load]);

  async function add() {
    setError("");
    try {
      await api.post("/workflow/holidays", { day: form.day, name: form.name });
      setForm({ day: "", name: "" });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add the holiday.");
    }
  }

  async function remove(id: string) {
    try {
      await api.del(`/workflow/holidays/${id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove the holiday.");
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}
      <Card>
        <CardHeader>
          <CardTitle>Public holidays</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-ink-2">
            Review deadlines are measured in <strong>working</strong> hours. A review raised at 16:00
            on a Friday before Eid is not overdue on Saturday — these dates are what makes that true.
          </p>
          {rows === null ? (
            <Skeleton className="h-16 w-full" />
          ) : rows.length === 0 ? (
            <p className="text-sm text-ink-3">
              No holidays entered. Only weekends are excluded from SLA calculations.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {rows.map((h) => (
                <li key={h.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="text-ink">
                    {new Date(h.day).toLocaleDateString(undefined, {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                    <span className="ml-2 text-ink-2">{h.name}</span>
                  </span>
                  {isAdmin && (
                    <button
                      type="button"
                      onClick={() => remove(h.id)}
                      className="rounded p-1 text-ink-3 hover:text-red-600"
                      aria-label="Remove holiday"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {isAdmin && (
            <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
              <Field label="Date">
                <Input
                  type="date"
                  value={form.day}
                  onChange={(e) => setForm({ ...form, day: e.target.value })}
                />
              </Field>
              <div className="min-w-[180px] flex-1">
                <Field label="Name">
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Eid al-Fitr"
                  />
                </Field>
              </div>
              <Button onClick={add} disabled={!form.day}>
                <Plus className="h-4 w-4" /> Add
              </Button>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
