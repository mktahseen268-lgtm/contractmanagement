"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ChevronRight, FileText, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import { Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select, Skeleton, Textarea } from "@/components/ui";
import { contractTypeLabel, formatDate, titleCase, CONTRACT_TYPES } from "@/lib/utils";
import type { ContractTemplate } from "@/lib/types";

export default function TemplatesPage() {
  const { me } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<ContractTemplate[] | null>(null);
  const [editing, setEditing] = useState<ContractTemplate | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const canEdit = me?.user.role === "owner" || me?.user.role === "admin" || me?.user.role === "manager" || me?.user.role === "author";

  const load = useCallback(() => {
    api.get<ContractTemplate[]>("/templates").then(setItems).catch(() => setItems([]));
  }, []);
  useEffect(load, [load]);

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
                  {!t.is_active && <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-ink-3">archived</span>}
                </div>
                {t.description && <p className="text-xs text-ink-3">{t.description}</p>}
                <div className="text-[11px] text-ink-3">
                  Default term {t.default_term_months}mo · {titleCase(t.default_renewal_type)} renewal · {titleCase(t.default_risk_level)} risk · {t.default_currency}
                  {" · "}used {t.usage_count}× · updated {formatDate(t.updated_at)}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Button size="sm" onClick={() => router.push(`/contracts/new?template=${t.id}`)} disabled={!t.is_active}>
                    Use template <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
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
  const [active, setActive] = useState(initial?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const payload = {
        name: name.trim(), description: description.trim(), contract_type: contractType,
        body, default_currency: currency.toUpperCase().slice(0, 3), default_term_months: Math.max(1, Number(term) || 12),
        default_renewal_type: renewal, default_risk_level: risk, default_governing_law: governing.trim(),
        default_tags: tags.split(",").map((s) => s.trim()).filter(Boolean), is_active: active,
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
          <div className="sm:col-span-3 flex items-end gap-2 pb-1"><label className="inline-flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></div>
          <div className="sm:col-span-12"><Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="When to use this template" /></Field></div>
          <div className="sm:col-span-2"><Field label="Default term (mo)"><Input type="number" min={1} value={term} onChange={(e) => setTerm(Number(e.target.value))} /></Field></div>
          <div className="sm:col-span-2"><Field label="Renewal"><Select value={renewal} onChange={(e) => setRenewal(e.target.value)}>{["none","auto","manual"].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}</Select></Field></div>
          <div className="sm:col-span-2"><Field label="Risk"><Select value={risk} onChange={(e) => setRisk(e.target.value)}>{["low","medium","high","critical"].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}</Select></Field></div>
          <div className="sm:col-span-2"><Field label="Currency"><Input value={currency} onChange={(e) => setCurrency(e.target.value)} maxLength={3} /></Field></div>
          <div className="sm:col-span-4"><Field label="Governing law"><Input value={governing} onChange={(e) => setGoverning(e.target.value)} placeholder="e.g. State of Delaware" /></Field></div>
          <div className="sm:col-span-12"><Field label="Default tags" hint="Comma-separated"><Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="msa, vendor, 2026" /></Field></div>
          <div className="sm:col-span-12">
            <Field label="Body (Markdown)" hint="Use {{counterparty}}, {{value}}, {{effective_date}}, {{end_date}} as merge variables">
              <Textarea rows={12} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-xs" />
            </Field>
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
