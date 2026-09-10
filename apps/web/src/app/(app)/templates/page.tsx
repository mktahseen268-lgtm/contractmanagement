"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Check, ChevronRight, FileText, Pencil, Plus, Send, Sparkles, Trash2, Wand2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import { Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select, Skeleton, Textarea } from "@/components/ui";
import { contractTypeLabel, formatDate, titleCase, CONTRACT_TYPES } from "@/lib/utils";
import type { ContractTemplate, TemplateField, TemplateFieldType, TemplateStatus } from "@/lib/types";

const STATUS_TONE: Record<TemplateStatus, string> = {
  draft: "bg-surface-3 text-ink-3",
  pending_approval: "bg-amber-100 text-amber-800",
  active: "bg-emerald-100 text-emerald-800",
  retired: "bg-slate-200 text-ink-3",
};

const STATUS_LABEL: Record<TemplateStatus, string> = {
  draft: "draft",
  pending_approval: "awaiting approval",
  active: "approved",
  retired: "retired",
};

const FIELD_TYPES: TemplateFieldType[] = [
  "text", "textarea", "number", "money", "date", "select", "multiselect", "boolean",
];

function blankField(): TemplateField {
  return {
    key: "", label: "", type: "text", required: false, options: [], default: null,
    help: "", group: "", entity_kind: "", minimum: null, maximum: null,
  };
}

export default function TemplatesPage() {
  const { me } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<ContractTemplate[] | null>(null);
  const [editing, setEditing] = useState<ContractTemplate | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const role = me?.user.role;
  const canEdit = role === "owner" || role === "admin" || role === "manager" || role === "author";
  // Approving is deliberately narrower than authoring: signing off your own template is the
  // thing this control exists to prevent.
  const canApprove = role === "owner" || role === "admin" || role === "manager";

  const load = useCallback(() => {
    api.get<ContractTemplate[]>("/templates").then(setItems).catch(() => setItems([]));
  }, []);
  useEffect(load, [load]);

  async function act(t: ContractTemplate, path: string, body?: unknown) {
    setError("");
    try {
      await api.post(`/templates/${t.id}/${path}`, body ?? {});
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "That didn't work.");
    }
  }

  async function reject(t: ContractTemplate) {
    const reason = window.prompt(`Send "${t.name}" back to its author. Why?`);
    if (!reason?.trim()) return;
    await act(t, "reject", { reason: reason.trim() });
  }

  async function remove(t: ContractTemplate) {
    if (!window.confirm(`Delete template "${t.name}"?`)) return;
    try {
      await api.del(`/templates/${t.id}`);
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete the template.");
    }
  }

  return (
    <div>
      <PageHeader
        title="Templates"
        subtitle={items === null ? "Loading…" : `${items.length} template${items.length === 1 ? "" : "s"} · spawn a contract in one click`}
        actions={canEdit ? <Button size="sm" onClick={() => { setEditing(null); setCreating(true); }}><Plus className="h-3.5 w-3.5" /> New template</Button> : null}
      />
      <div className="space-y-5 p-6">
        {error && <ErrorBanner message={error} />}

        {(creating || editing) && (
          <TemplateForm
            initial={editing ?? undefined}
            onCancel={() => { setCreating(false); setEditing(null); }}
            onSaved={() => { setCreating(false); setEditing(null); load(); }}
          />
        )}

        {items === null && <Skeleton className="h-24" />}
        {items !== null && items.length === 0 && !creating && (
          <Card>
            <CardBody className="py-10 text-center">
              <FileText className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">No templates yet</div>
              <p className="mt-1 text-sm text-ink-2">Templates let you spawn a fresh contract draft in one click — same body, same metadata defaults.</p>
              {canEdit && <Button size="sm" className="mt-4" onClick={() => setCreating(true)}><Plus className="h-3.5 w-3.5" /> Create your first</Button>}
            </CardBody>
          </Card>
        )}

        <div className="grid gap-3 lg:grid-cols-2">
          {items?.map((t) => (
            <Card key={t.id}>
              <CardBody className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Sparkles className="h-3.5 w-3.5 text-accent" />
                  <span className="text-sm font-semibold text-ink">{t.name}</span>
                  <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] uppercase text-ink-3">{contractTypeLabel(t.contract_type)}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${STATUS_TONE[t.status] ?? STATUS_TONE.draft}`}>
                    {STATUS_LABEL[t.status] ?? t.status}{t.status === "active" ? ` v${t.version_no}` : ""}
                  </span>
                  {t.fields.length > 0 && (
                    <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3">
                      {t.fields.length} merge field{t.fields.length === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                {t.description && <p className="text-xs text-ink-3">{t.description}</p>}
                <div className="text-[11px] text-ink-3">
                  Default term {t.default_term_months}mo · {titleCase(t.default_renewal_type)} renewal · {titleCase(t.default_risk_level)} risk · {t.default_currency}
                  {" · "}used {t.usage_count}× · updated {formatDate(t.updated_at)}
                </div>
                {t.status === "draft" && t.approval_note && (
                  <p className="rounded-md border border-amber-300/60 p-2 text-xs text-ink-2">
                    Sent back: {t.approval_note}
                  </p>
                )}
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => router.push(t.fields.length ? `/templates/${t.id}/intake` : `/contracts/new?template=${t.id}`)}
                    disabled={t.status !== "active"}
                  >
                    {t.fields.length ? "Raise an agreement" : "Use template"} <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                  {canEdit && t.status === "draft" && (
                    <Button size="sm" variant="ghost" onClick={() => act(t, "submit")}>
                      <Send className="h-3.5 w-3.5" /> Send for approval
                    </Button>
                  )}
                  {canApprove && t.status === "pending_approval" && (
                    <>
                      <Button size="sm" onClick={() => act(t, "approve")}>
                        <Check className="h-3.5 w-3.5" /> Approve
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => reject(t)}>
                        <X className="h-3.5 w-3.5" /> Send back
                      </Button>
                    </>
                  )}
                  {canApprove && t.status === "active" && (
                    <Button size="sm" variant="ghost" onClick={() => act(t, "retire")}>
                      Retire
                    </Button>
                  )}
                  {canEdit && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => { setCreating(false); setEditing(t); }}>
                        <Pencil className="h-3.5 w-3.5" /> Edit
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(t)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function TemplateForm({ initial, onCancel, onSaved }: { initial?: ContractTemplate; onCancel: () => void; onSaved: () => void }) {
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [contractType, setContractType] = useState(initial?.contract_type ?? "other");
  const [body, setBody] = useState(initial?.body ?? "## Agreement\n\nThis Agreement is made between {{counterparty}} and ...");
  const [term, setTerm] = useState(initial?.default_term_months ?? 12);
  const [renewal, setRenewal] = useState(initial?.default_renewal_type ?? "none");
  const [risk, setRisk] = useState(initial?.default_risk_level ?? "low");
  const [currency, setCurrency] = useState(initial?.default_currency ?? "USD");
  const [governing, setGoverning] = useState(initial?.default_governing_law ?? "");
  const [tags, setTags] = useState((initial?.default_tags ?? []).join(", "));
  const [fields, setFields] = useState<TemplateField[]>(initial?.fields ?? []);
  const [busy, setBusy] = useState(false);
  const [scaffolding, setScaffolding] = useState(false);
  const [err, setErr] = useState("");

  /** Scaffold field definitions from the placeholders the body already uses, rather than
   *  making the author transcribe every one by hand. */
  async function scaffold() {
    setScaffolding(true);
    setErr("");
    try {
      const known = new Set(fields.map((f) => f.key));
      const { fields: suggested } = await api.post<{ fields: TemplateField[] }>(
        "/templates/suggest-fields", { body },
      );
      setFields([...fields, ...suggested.filter((f) => !known.has(f.key))]);
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : "Couldn't read the body.");
    } finally {
      setScaffolding(false);
    }
  }

  function patchField(index: number, patch: Partial<TemplateField>) {
    setFields(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const payload = {
        name: name.trim(), description: description.trim(), contract_type: contractType,
        body, default_currency: currency.toUpperCase().slice(0, 3), default_term_months: Math.max(1, Number(term) || 12),
        default_renewal_type: renewal, default_risk_level: risk, default_governing_law: governing.trim(),
        default_tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
        fields: fields.filter((f) => f.key.trim()),
      };
      if (isEdit) await api.patch(`/templates/${initial!.id}`, payload);
      else await api.post("/templates", payload);
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : "Couldn't save the template.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEdit ? `Edit template — ${initial?.name}` : "New template"}</CardTitle>
      </CardHeader>
      <CardBody>
        {err && <ErrorBanner message={err} className="mb-3" />}
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-6"><Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} required /></Field></div>
          <div className="sm:col-span-3"><Field label="Type"><Select value={contractType} onChange={(e) => setContractType(e.target.value)}>{CONTRACT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select></Field></div>
          <div className="sm:col-span-3 flex items-end pb-2 text-xs text-ink-3">Saved as a draft \u2014 send it for approval to put it into use.</div>
          <div className="sm:col-span-12"><Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="When to use this template" /></Field></div>
          <div className="sm:col-span-2"><Field label="Default term (mo)"><Input type="number" min={1} value={term} onChange={(e) => setTerm(Number(e.target.value))} /></Field></div>
          <div className="sm:col-span-2"><Field label="Renewal"><Select value={renewal} onChange={(e) => setRenewal(e.target.value)}>{["none","auto","manual"].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}</Select></Field></div>
          <div className="sm:col-span-2"><Field label="Risk"><Select value={risk} onChange={(e) => setRisk(e.target.value)}>{["low","medium","high","critical"].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}</Select></Field></div>
          <div className="sm:col-span-2"><Field label="Currency"><Input value={currency} onChange={(e) => setCurrency(e.target.value)} maxLength={3} /></Field></div>
          <div className="sm:col-span-4"><Field label="Governing law"><Input value={governing} onChange={(e) => setGoverning(e.target.value)} placeholder="e.g. State of Delaware" /></Field></div>
          <div className="sm:col-span-12"><Field label="Default tags" hint="Comma-separated"><Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="msa, vendor, 2026" /></Field></div>
          <div className="sm:col-span-12">
            <Field label="Body (Markdown)" hint="Use {{field_key}} wherever an answer belongs. {{counterparty}}, {{our_entity}}, {{value}}, {{effective_date}} and {{end_date}} come from the agreement itself.">
              <Textarea rows={12} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-xs" />
            </Field>
          </div>

          <div className="sm:col-span-12 space-y-2 rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-ink">Intake form</div>
                <p className="text-xs text-ink-3">
                  What the requester is asked. Every {"{{placeholder}}"} in the body needs a field
                  here, or the template can&rsquo;t be approved.
                </p>
              </div>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="ghost" loading={scaffolding} onClick={scaffold}>
                  <Wand2 className="h-3.5 w-3.5" /> Scaffold from body
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setFields([...fields, blankField()])}>
                  <Plus className="h-3.5 w-3.5" /> Add field
                </Button>
              </div>
            </div>

            {fields.length === 0 && (
              <p className="py-2 text-xs text-ink-3">
                No fields yet. Without them the body is copied as-is and whoever raises the
                agreement edits it by hand.
              </p>
            )}

            {fields.map((f, i) => (
              <div key={i} className="grid gap-2 rounded-md bg-surface-2 p-2 sm:grid-cols-12">
                <div className="sm:col-span-3">
                  <Input
                    value={f.key}
                    onChange={(e) => patchField(i, { key: e.target.value.trim().toLowerCase() })}
                    placeholder="field_key"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="sm:col-span-3">
                  <Input value={f.label} onChange={(e) => patchField(i, { label: e.target.value })} placeholder="Label" />
                </div>
                <div className="sm:col-span-2">
                  <Select value={f.type} onChange={(e) => patchField(i, { type: e.target.value as TemplateFieldType })}>
                    {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </Select>
                </div>
                <div className="sm:col-span-3">
                  {(f.type === "select" || f.type === "multiselect") ? (
                    <Input
                      value={f.options.join(", ")}
                      onChange={(e) => patchField(i, { options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })}
                      placeholder="Permitted values, comma-separated"
                    />
                  ) : (
                    <Input value={f.help} onChange={(e) => patchField(i, { help: e.target.value })} placeholder="Help text (optional)" />
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 sm:col-span-1">
                  <label className="inline-flex items-center gap-1 text-[11px] text-ink-2" title="Required">
                    <input type="checkbox" checked={f.required} onChange={(e) => patchField(i, { required: e.target.checked })} />
                    req
                  </label>
                  <button type="button" onClick={() => setFields(fields.filter((_, j) => j !== i))} className="text-ink-3 hover:text-ink">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
            <Button type="submit" size="sm" loading={busy}>{isEdit ? "Save changes" : "Create template"}</Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
