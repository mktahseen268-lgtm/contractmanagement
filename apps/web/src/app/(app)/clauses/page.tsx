"use client";

/**
 * Clause library — approved language, versioned and approval-gated, plus the playbooks that
 * say which of it is compulsory.
 *
 * Replaces the sample-data prototype. Everything here is persisted:
 *   GET/POST/PATCH /clauses          the library, alternatives nested under their parent
 *   POST /clauses/{id}/submit|approve|reject|retire
 *   GET/POST/PATCH /playbooks        the policy a draft is measured against
 *
 * A clause is used from a template by reference — `[[clause:key]]` — not by copying its text,
 * which is why "Copy reference" is the primary action rather than "Copy text". Copying the
 * words is how ten templates end up with nine slightly different indemnities.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  BookMarked,
  Check,
  ChevronRight,
  Copy,
  Plus,
  Search,
  Send,
  Shield,
  X,
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
  Textarea,
} from "@/components/ui";
import { titleCase, CONTRACT_TYPES } from "@/lib/utils";
import type { Clause, ClausePosition, ClauseStatus, Playbook, PlaybookRule } from "@/lib/types";

const STATUS_TONE: Record<ClauseStatus, string> = {
  draft: "bg-surface-3 text-ink-3",
  pending_approval: "bg-amber-100 text-amber-800",
  active: "bg-emerald-100 text-emerald-800",
  retired: "bg-slate-200 text-ink-3",
};

const STATUS_LABEL: Record<ClauseStatus, string> = {
  draft: "draft",
  pending_approval: "awaiting approval",
  active: "approved",
  retired: "retired",
};

const POSITIONS: ClausePosition[] = ["preferred", "acceptable", "fallback"];
const RISKS = ["low", "medium", "high", "critical"];

export default function ClausesPage() {
  const [tab, setTab] = useState<"library" | "playbooks">("library");

  return (
    <div>
      <PageHeader
        title="Clause library"
        subtitle="Approved language templates compose by reference, and the policy drafts are measured against"
      />
      <div className="space-y-5 p-6">
        <div className="flex gap-1 rounded-lg bg-surface-2 p-1 text-sm">
          {(["library", "playbooks"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
                tab === t ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
              }`}
            >
              {t === "library" ? "Clauses" : "Playbooks"}
            </button>
          ))}
        </div>
        {tab === "library" ? <Library /> : <Playbooks />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ library ---------- */

function Library() {
  const { me } = useAuth();
  const role = me?.user.role;
  const canEdit = role === "owner" || role === "admin" || role === "manager" || role === "author";
  const canApprove = role === "owner" || role === "admin" || role === "manager";

  const [items, setItems] = useState<Clause[] | null>(null);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<Clause | null>(null);
  const [editing, setEditing] = useState<Clause | "new" | null>(null);
  const [parentForNew, setParentForNew] = useState<Clause | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  const load = useCallback(() => {
    api
      .get<Clause[]>("/clauses?include_alternatives=true")
      .then((rows) => {
        setItems(rows);
        setSelected((s) => (s ? rows.find((r) => r.id === s.id) ?? null : null));
      })
      .catch(() => setItems([]));
  }, []);
  useEffect(load, [load]);

  const categories = useMemo(
    () => Array.from(new Set((items ?? []).map((c) => c.category).filter(Boolean))).sort(),
    [items],
  );

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (items ?? []).filter(
      (c) =>
        (!category || c.category === category) &&
        (!needle ||
          c.title.toLowerCase().includes(needle) ||
          c.key.includes(needle) ||
          c.body.toLowerCase().includes(needle)),
    );
  }, [items, q, category]);

  async function act(c: Clause, path: string, body?: unknown) {
    setError("");
    try {
      await api.post(`/clauses/${c.id}/${path}`, body ?? {});
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "That didn't work.");
    }
  }

  async function reject(c: Clause) {
    const reason = window.prompt(`Send "${c.title}" back to its author. Why?`);
    if (!reason?.trim()) return;
    await act(c, "reject", { reason: reason.trim() });
  }

  function copyReference(c: Clause) {
    void navigator.clipboard?.writeText(`[[clause:${c.key}]]`);
    setCopied(c.id);
    window.setTimeout(() => setCopied(""), 1500);
  }

  if (editing) {
    return (
      <ClauseForm
        initial={editing === "new" ? undefined : editing}
        parent={parentForNew}
        onCancel={() => {
          setEditing(null);
          setParentForNew(null);
        }}
        onSaved={() => {
          setEditing(null);
          setParentForNew(null);
          load();
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      <Card>
        <CardBody className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs font-medium text-ink-2">Search</label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Title, key or wording"
                className="pl-8"
              />
            </div>
          </div>
          <div className="min-w-[160px]">
            <label className="mb-1 block text-xs font-medium text-ink-2">Category</label>
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          {canEdit && (
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus className="h-3.5 w-3.5" /> New clause
            </Button>
          )}
        </CardBody>
      </Card>

      {items === null && <Skeleton className="h-32" />}

      {items !== null && shown.length === 0 && (
        <Card>
          <CardBody className="py-10 text-center text-sm text-ink-2">
            <BookMarked className="mx-auto mb-3 h-10 w-10 text-ink-3" />
            <div className="text-base font-semibold text-ink">
              {items.length === 0 ? "No clauses yet" : "Nothing matches"}
            </div>
            <p className="mt-1">
              {items.length === 0
                ? "A clause is written once, approved once, and referenced from every template that needs it."
                : "Try a different search."}
            </p>
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          {shown.map((c) => (
            <Card
              key={c.id}
              className={`cursor-pointer transition ${selected?.id === c.id ? "ring-1 ring-accent" : ""}`}
            >
              <CardBody className="space-y-2" onClick={() => setSelected(c)}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-ink">{c.title}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${STATUS_TONE[c.status]}`}>
                    {STATUS_LABEL[c.status]}
                    {c.status === "active" ? ` v${c.version_no}` : ""}
                  </span>
                  {c.risk_level !== "low" && (
                    <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] uppercase text-ink-3">
                      {c.risk_level} risk
                    </span>
                  )}
                  {c.alternatives.length > 0 && (
                    <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3">
                      {c.alternatives.length} fallback
                      {c.alternatives.length === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                <p className="line-clamp-2 text-xs text-ink-2">{c.body}</p>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-3">
                  <code className="rounded bg-surface-3 px-1.5 py-0.5">[[clause:{c.key}]]</code>
                  {c.category && <span>{c.category}</span>}
                  <span>used {c.usage_count}×</span>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>

        {selected && (
          <ClauseDetail
            clause={selected}
            canEdit={canEdit}
            canApprove={canApprove}
            copied={copied === selected.id}
            onCopy={() => copyReference(selected)}
            onEdit={() => setEditing(selected)}
            onAddAlternative={() => {
              setParentForNew(selected);
              setEditing("new");
            }}
            onAct={act}
            onReject={reject}
          />
        )}
      </div>
    </div>
  );
}

function ClauseDetail({
  clause,
  canEdit,
  canApprove,
  copied,
  onCopy,
  onEdit,
  onAddAlternative,
  onAct,
  onReject,
}: {
  clause: Clause;
  canEdit: boolean;
  canApprove: boolean;
  copied: boolean;
  onCopy: () => void;
  onEdit: () => void;
  onAddAlternative: () => void;
  onAct: (c: Clause, path: string) => void;
  onReject: (c: Clause) => void;
}) {
  return (
    <Card className="lg:sticky lg:top-4 lg:self-start">
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          {clause.status === "active" ? (
            <BadgeCheck className="h-4 w-4 text-emerald-600" />
          ) : (
            <Shield className="h-4 w-4 text-ink-3" />
          )}
          {clause.title}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={onCopy}>
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy reference"}
          </Button>
          {canEdit && clause.status === "draft" && (
            <Button size="sm" variant="ghost" onClick={() => onAct(clause, "submit")}>
              <Send className="h-3.5 w-3.5" /> Send for approval
            </Button>
          )}
          {canApprove && clause.status === "pending_approval" && (
            <>
              <Button size="sm" onClick={() => onAct(clause, "approve")}>
                <Check className="h-3.5 w-3.5" /> Approve
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onReject(clause)}>
                <X className="h-3.5 w-3.5" /> Send back
              </Button>
            </>
          )}
          {canEdit && <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>}
          {canApprove && clause.status === "active" && (
            <Button size="sm" variant="ghost" onClick={() => onAct(clause, "retire")}>
              Retire
            </Button>
          )}
        </div>

        {clause.status === "draft" && clause.approval_note && (
          <p className="rounded-md border border-amber-300/60 p-2 text-xs text-ink-2">
            Sent back: {clause.approval_note}
          </p>
        )}

        <p className="whitespace-pre-wrap rounded-md bg-surface-2 p-3 text-sm text-ink">
          {clause.body}
        </p>

        {clause.guidance && (
          <div className="rounded-md border border-line p-2 text-xs text-ink-2">
            <div className="mb-0.5 font-medium text-ink">When to use this</div>
            {clause.guidance}
          </div>
        )}

        {clause.alternatives.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-ink">Fallback positions</div>
            {clause.alternatives.map((a) => (
              <div key={a.id} className="rounded-md border border-line p-2">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <ChevronRight className="h-3 w-3 text-ink-3" />
                  <span className="font-medium text-ink">{a.title}</span>
                  <Badge tone={a.position === "acceptable" ? "accent" : "neutral"}>
                    {a.position}
                  </Badge>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${STATUS_TONE[a.status]}`}>
                    {STATUS_LABEL[a.status]}
                  </span>
                </div>
                <p className="mt-1 text-xs text-ink-2">{a.body}</p>
                {a.guidance && <p className="mt-1 text-[11px] text-ink-3">{a.guidance}</p>}
              </div>
            ))}
          </div>
        )}

        {canEdit && !clause.parent_id && (
          <Button size="sm" variant="ghost" onClick={onAddAlternative}>
            <Plus className="h-3.5 w-3.5" /> Add a fallback position
          </Button>
        )}
      </CardBody>
    </Card>
  );
}

function ClauseForm({
  initial,
  parent,
  onCancel,
  onSaved,
}: {
  initial?: Clause;
  parent: Clause | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!initial;
  const [key, setKey] = useState(initial?.key ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [category, setCategory] = useState(initial?.category ?? parent?.category ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [position, setPosition] = useState<ClausePosition>(
    initial?.position ?? (parent ? "fallback" : "preferred"),
  );
  const [risk, setRisk] = useState(initial?.risk_level ?? "low");
  const [guidance, setGuidance] = useState(initial?.guidance ?? "");
  const [rank, setRank] = useState(initial?.fallback_rank ?? 1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const payload = {
        key: key.trim().toLowerCase(),
        title: title.trim(),
        category: category.trim(),
        body,
        position,
        risk_level: risk,
        guidance,
        fallback_rank: parent || initial?.parent_id ? Number(rank) || 1 : 0,
        ...(parent ? { parent_id: parent.id } : {}),
      };
      if (isEdit) await api.patch(`/clauses/${initial!.id}`, payload);
      else await api.post("/clauses", payload);
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : "Couldn't save the clause.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {isEdit
            ? `Edit — ${initial?.title}`
            : parent
              ? `Fallback position for “${parent.title}”`
              : "New clause"}
        </CardTitle>
      </CardHeader>
      <CardBody>
        {err && <ErrorBanner message={err} className="mb-3" />}
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-4">
            <Field label="Key" hint="How templates refer to it. Cannot change once approved.">
              <Input
                value={key}
                onChange={(e) => setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
                required
                disabled={isEdit && initial?.status === "active"}
                className="font-mono text-xs"
                placeholder="limitation_of_liability"
              />
            </Field>
          </div>
          <div className="sm:col-span-5">
            <Field label="Title">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Category">
              <Input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Liability & Indemnity"
              />
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Position">
              <Select
                value={position}
                onChange={(e) => setPosition(e.target.value as ClausePosition)}
              >
                {POSITIONS.map((p) => (
                  <option key={p} value={p}>
                    {titleCase(p)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Risk">
              <Select value={risk} onChange={(e) => setRisk(e.target.value)}>
                {RISKS.map((r) => (
                  <option key={r} value={r}>
                    {titleCase(r)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {(parent || initial?.parent_id) && (
            <div className="sm:col-span-3">
              <Field label="Fallback rank" hint="1 is the first to reach for">
                <Input
                  type="number"
                  min={1}
                  value={rank}
                  onChange={(e) => setRank(Number(e.target.value))}
                />
              </Field>
            </div>
          )}
          <div className="sm:col-span-12">
            <Field
              label="Wording"
              hint="May contain {{merge_fields}} — they are filled when the draft is generated."
            >
              <Textarea
                rows={8}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                required
                className="text-sm"
              />
            </Field>
          </div>
          <div className="sm:col-span-12">
            <Field label="Guidance" hint="When a negotiator should reach for this wording.">
              <Textarea rows={2} value={guidance} onChange={(e) => setGuidance(e.target.value)} />
            </Field>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              {isEdit ? "Save changes" : "Create as draft"}
            </Button>
          </div>
        </form>
        {!isEdit && (
          <p className="mt-2 text-xs text-ink-3">
            Saved as a draft. It has to be approved by someone else before a template can use it.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

/* ---------------------------------------------------------------- playbooks ---------- */

function Playbooks() {
  const { me } = useAuth();
  const role = me?.user.role;
  const canEdit = role === "owner" || role === "admin" || role === "manager";

  const [items, setItems] = useState<Playbook[] | null>(null);
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [editing, setEditing] = useState<Playbook | "new" | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.get<Playbook[]>("/playbooks").then(setItems).catch(() => setItems([]));
    api.get<Clause[]>("/clauses").then(setClauses).catch(() => setClauses([]));
  }, []);
  useEffect(load, [load]);

  if (editing) {
    return (
      <PlaybookForm
        initial={editing === "new" ? undefined : editing}
        clauses={clauses}
        onCancel={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          load();
        }}
      />
    );
  }

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}

      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-2">
            A playbook says which clauses an agreement must contain and which it must never.
            A <strong>blocking</strong> deviation classifies the agreement non-standard, which
            sends it down the non-standard approval route.
          </p>
          {canEdit && (
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus className="h-3.5 w-3.5" /> New playbook
            </Button>
          )}
        </CardBody>
      </Card>

      {items === null && <Skeleton className="h-24" />}
      {items?.length === 0 && (
        <Card>
          <CardBody className="py-10 text-center text-sm text-ink-2">
            <Shield className="mx-auto mb-3 h-10 w-10 text-ink-3" />
            <div className="text-base font-semibold text-ink">No policy yet</div>
            <p className="mt-1">
              Without a playbook the library is a text store. With one, every draft is checked.
            </p>
          </CardBody>
        </Card>
      )}

      {items?.map((p) => (
        <Card key={p.id}>
          <CardBody className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-ink">{p.name}</span>
              <Badge tone={p.status === "active" ? "accent" : "neutral"}>{p.status}</Badge>
              <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] uppercase text-ink-3">
                {p.contract_type || "all types"}
              </span>
              {p.applies_when?.min_value ? (
                <span className="text-[11px] text-ink-3">
                  above {p.applies_when.min_value.toLocaleString()}
                </span>
              ) : null}
            </div>
            {p.description && <p className="text-xs text-ink-3">{p.description}</p>}
            <div className="space-y-1">
              {p.rules.map((r) => (
                <div key={r.clause_key} className="flex flex-wrap items-center gap-2 text-xs">
                  {r.severity === "blocker" ? (
                    <AlertTriangle className="h-3 w-3 text-red-600" />
                  ) : (
                    <Shield className="h-3 w-3 text-ink-3" />
                  )}
                  <span className="text-ink-2">{titleCase(r.kind)}</span>
                  <code className="rounded bg-surface-3 px-1.5 py-0.5">{r.clause_key}</code>
                  <span className="text-ink-3">{r.severity}</span>
                </div>
              ))}
            </div>
            {canEdit && (
              <Button size="sm" variant="ghost" onClick={() => setEditing(p)}>
                Edit
              </Button>
            )}
          </CardBody>
        </Card>
      ))}
    </div>
  );
}

function PlaybookForm({
  initial,
  clauses,
  onCancel,
  onSaved,
}: {
  initial?: Playbook;
  clauses: Clause[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [contractType, setContractType] = useState(initial?.contract_type ?? "");
  const [minValue, setMinValue] = useState(String(initial?.applies_when?.min_value ?? ""));
  const [status, setStatus] = useState(initial?.status ?? "draft");
  const [rules, setRules] = useState<PlaybookRule[]>(initial?.rules ?? []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function patchRule(index: number, patch: Partial<PlaybookRule>) {
    setRules(rules.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        contract_type: contractType,
        applies_when: minValue ? { min_value: Number(minValue) } : {},
        rules: rules.filter((r) => r.clause_key),
        status,
      };
      if (isEdit) await api.patch(`/playbooks/${initial!.id}`, payload);
      else await api.post("/playbooks", payload);
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : "Couldn't save the playbook.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEdit ? `Edit — ${initial?.name}` : "New playbook"}</CardTitle>
      </CardHeader>
      <CardBody>
        {err && <ErrorBanner message={err} className="mb-3" />}
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-6">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
          </div>
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
            <Field label="Status">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-8">
            <Field label="Description">
              <Input value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Only above value" hint="Leave blank to always apply">
              <Input
                type="number"
                min={0}
                value={minValue}
                onChange={(e) => setMinValue(e.target.value)}
              />
            </Field>
          </div>

          <div className="sm:col-span-12 space-y-2 rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-semibold text-ink">Rules</div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  setRules([
                    ...rules,
                    { clause_key: "", kind: "required", severity: "warning", guidance: "" },
                  ])
                }
              >
                <Plus className="h-3.5 w-3.5" /> Add rule
              </Button>
            </div>
            {rules.length === 0 && (
              <p className="py-2 text-xs text-ink-3">
                No rules yet. A playbook with no rules checks nothing.
              </p>
            )}
            {rules.map((r, i) => (
              <div key={i} className="grid gap-2 rounded-md bg-surface-2 p-2 sm:grid-cols-12">
                <div className="sm:col-span-5">
                  <Select
                    value={r.clause_key}
                    onChange={(e) => patchRule(i, { clause_key: e.target.value })}
                  >
                    <option value="">Select a clause…</option>
                    {clauses.map((c) => (
                      <option key={c.id} value={c.key}>
                        {c.title} ({c.key})
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="sm:col-span-3">
                  <Select
                    value={r.kind}
                    onChange={(e) => patchRule(i, { kind: e.target.value as PlaybookRule["kind"] })}
                  >
                    <option value="required">must appear</option>
                    <option value="prohibited">must not appear</option>
                    <option value="preferred">preferred</option>
                  </Select>
                </div>
                <div className="sm:col-span-3">
                  <Select
                    value={r.severity}
                    onChange={(e) =>
                      patchRule(i, { severity: e.target.value as PlaybookRule["severity"] })
                    }
                  >
                    <option value="warning">warning</option>
                    <option value="blocker">blocker — makes it non-standard</option>
                  </Select>
                </div>
                <div className="flex items-center sm:col-span-1">
                  <button
                    type="button"
                    onClick={() => setRules(rules.filter((_, j) => j !== i))}
                    className="text-ink-3 hover:text-ink"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              {isEdit ? "Save changes" : "Create playbook"}
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
