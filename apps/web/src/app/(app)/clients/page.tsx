"use client";

/**
 * Clients — the counterparty register.
 *
 * The counterparty used to be a free-text box on the contract form, which means "Sadiq Traders
 * (Pvt) Ltd", "Sadiq Traders Pvt Ltd" and "SADIQ TRADERS" are three different companies as far
 * as any report is concerned. You cannot ask "what is our total exposure to Sadiq Traders?" of
 * a text column, and for a bank that is not a reporting inconvenience — it is the question
 * compliance asks.
 *
 * So a client is a record: onboarded once, with the identifiers a bank actually needs, checked
 * for duplicates before it is created, and carrying its own agreement history afterwards.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Building2,
  Check,
  Plus,
  Search,
  ShieldAlert,
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
} from "@/components/ui";
import { formatDate, formatMoney, titleCase } from "@/lib/utils";
import type { ContractListItem, DuplicateMatch, Party } from "@/lib/types";

const KYC_TONE: Record<string, "accent" | "neutral"> = {
  verified: "accent",
  pending: "neutral",
  none: "neutral",
  rejected: "neutral",
};

const ENTITY_TYPES = ["company", "sole_trader", "partnership", "government", "individual"];

export default function ClientsPage() {
  const { me } = useAuth();
  const canEdit = ["owner", "admin", "manager", "author"].includes(me?.user.role ?? "");
  const [rows, setRows] = useState<Party[] | null>(null);
  const [q, setQ] = useState("");
  const [kyc, setKyc] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Party | "new" | null>(null);
  const [selected, setSelected] = useState<Party | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (kyc) params.set("kyc_status", kyc);
    api
      .get<Party[]>(`/parties?${params.toString()}`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [q, kyc]);

  // Debounced, because this fires on every keystroke in the search box.
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Clients"
        subtitle="Counterparties the Bank contracts with"
        actions={
          canEdit ? (
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus className="h-3.5 w-3.5" /> Register a client
            </Button>
          ) : undefined
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <Field label="Search">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Name or registration number"
                  className="pl-8"
                />
              </div>
            </Field>
          </div>
          <div className="w-44">
            <Field label="KYC status">
              <Select value={kyc} onChange={(e) => setKyc(e.target.value)}>
                <option value="">Any</option>
                {["verified", "pending", "none", "rejected"].map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>

        <Card>
          <CardBody className="p-0">
            {rows === null && <Skeleton className="m-4 h-24" />}
            {rows?.length === 0 && (
              <p className="px-5 py-8 text-center text-sm text-ink-3">
                {q || kyc
                  ? "No client matches that search."
                  : "No clients yet. Register one to start contracting."}
              </p>
            )}
            {!!rows?.length && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                      <th className="px-5 py-2">Client</th>
                      <th className="py-2">Registration</th>
                      <th className="py-2">Jurisdiction</th>
                      <th className="py-2">KYC</th>
                      <th className="py-2">Risk</th>
                      <th className="py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((p) => (
                      <tr key={p.id} className="border-b border-line last:border-0">
                        <td className="px-5 py-2.5">
                          <button
                            onClick={() => setSelected(p)}
                            className="text-left font-medium text-ink hover:text-accent"
                          >
                            {p.name}
                          </button>
                          {!p.is_active && (
                            <span className="ml-2 text-xs text-ink-3">· inactive</span>
                          )}
                          {p.duplicate_override_of && (
                            <span
                              className="ml-2 inline-flex items-center gap-1 text-xs text-amber-700"
                              title={p.duplicate_override_reason}
                            >
                              <AlertTriangle className="h-3 w-3" /> onboarded over a duplicate
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 text-ink-2">{p.registration_no || "—"}</td>
                        <td className="py-2.5 text-ink-2">{p.jurisdiction || "—"}</td>
                        <td className="py-2.5">
                          <Badge tone={KYC_TONE[p.kyc_status] ?? "neutral"}>
                            {titleCase(p.kyc_status)}
                          </Badge>
                        </td>
                        <td className="py-2.5 text-ink-2">{p.risk_score}</td>
                        <td className="py-2.5 pr-5 text-right">
                          {canEdit && (
                            <Button size="sm" variant="ghost" onClick={() => setEditing(p)}>
                              Edit
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {editing && (
        <ClientForm
          initial={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
          onError={setError}
        />
      )}

      {selected && <ClientHistory party={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ onboarding ---------- */

/** The fields a bank needs before it will contract with someone.
 *
 * Required here rather than only in the database: the API stays permissive so a bulk migration
 * of legacy counterparties can still land, but a person onboarding a client by hand is the
 * point at which the identifiers are actually knowable, and letting them skip it is how the
 * register fills with names nobody can match to a company.
 */
const REQUIRED = ["name", "registration_no", "entity_type", "jurisdiction", "contact_email"];

function ClientForm({
  initial,
  onClose,
  onSaved,
  onError,
}: {
  initial: Party | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (s: string) => void;
}) {
  const isEdit = !!initial;
  const [v, setV] = useState({
    name: initial?.name ?? "",
    registration_no: initial?.registration_no ?? "",
    entity_type: initial?.entity_type ?? "company",
    jurisdiction: initial?.jurisdiction ?? "Islamic Republic of Pakistan",
    region: initial?.region ?? "",
    kyc_status: initial?.kyc_status ?? "pending",
    contact_name: initial?.contact_name ?? "",
    contact_email: initial?.contact_email ?? "",
    contact_phone: initial?.contact_phone ?? "",
    address: initial?.address ?? "",
  });
  const [duplicates, setDuplicates] = useState<DuplicateMatch[]>([]);
  const [override, setOverride] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function set<K extends keyof typeof v>(k: K, value: string) {
    setV((s) => ({ ...s, [k]: value }));
  }

  const missing = useMemo(
    () => REQUIRED.filter((k) => !String(v[k as keyof typeof v] ?? "").trim()),
    [v],
  );

  // Warn before saving, not after. Onboarding refuses a likely duplicate, and discovering that
  // at the end of a form is how people invent a second spelling to get past it.
  useEffect(() => {
    if (!v.name.trim() && !v.registration_no.trim()) {
      setDuplicates([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .post<DuplicateMatch[]>("/parties/check-duplicates", {
          name: v.name.trim(),
          registration_no: v.registration_no.trim(),
          exclude_id: initial?.id ?? "",
        })
        .then(setDuplicates)
        .catch(() => setDuplicates([]));
    }, 350);
    return () => clearTimeout(t);
  }, [v.name, v.registration_no, initial?.id]);

  async function save() {
    if (missing.length) return;
    setBusy(true);
    setErr("");
    try {
      if (isEdit) await api.patch(`/parties/${initial!.id}`, v);
      else await api.post("/parties", { ...v, override_reason: override.trim() });
      onSaved();
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Couldn't save the client.";
      setErr(message);
      onError("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 sm:p-8">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <Building2 className="h-4 w-4" />
            {isEdit ? `Edit ${initial!.name}` : "Register a client"}
          </CardTitle>
          <button onClick={onClose} className="text-ink-3 hover:text-ink" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </CardHeader>
        <CardBody className="space-y-3">
          {err && <ErrorBanner message={err} />}

          {duplicates.length > 0 && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
              <div className="flex items-center gap-1.5 text-sm font-medium text-amber-900">
                <ShieldAlert className="h-4 w-4" /> This looks like an existing client
              </div>
              <ul className="mt-1.5 space-y-0.5 text-xs text-amber-900">
                {duplicates.map((d) => (
                  <li key={d.id}>
                    {d.name}
                    {d.registration_no ? ` · ${d.registration_no}` : ""} — matched on {d.reason}
                  </li>
                ))}
              </ul>
              {!isEdit && (
                <div className="mt-2">
                  <Field
                    label="Reason to onboard anyway"
                    hint="Recorded against the client. “We knew and did it anyway” is a different fact from “nobody noticed”."
                  >
                    <Input
                      value={override}
                      onChange={(e) => setOverride(e.target.value)}
                      placeholder="e.g. Different legal entity, same trading name"
                    />
                  </Field>
                </div>
              )}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Legal name*" hint="Exactly as registered">
              <Input value={v.name} onChange={(e) => set("name", e.target.value)} autoFocus />
            </Field>
            <Field label="Registration / NTN*">
              <Input
                value={v.registration_no}
                onChange={(e) => set("registration_no", e.target.value)}
                placeholder="NTN-1234567"
              />
            </Field>
            <Field label="Entity type*">
              <Select value={v.entity_type} onChange={(e) => set("entity_type", e.target.value)}>
                {ENTITY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {titleCase(t.replace("_", " "))}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Jurisdiction*">
              <Input
                value={v.jurisdiction}
                onChange={(e) => set("jurisdiction", e.target.value)}
              />
            </Field>
            <Field label="Region">
              <Input value={v.region} onChange={(e) => set("region", e.target.value)} placeholder="Sindh" />
            </Field>
            <Field label="KYC status">
              <Select value={v.kyc_status} onChange={(e) => set("kyc_status", e.target.value)}>
                {["none", "pending", "verified", "rejected"].map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Contact name">
              <Input value={v.contact_name} onChange={(e) => set("contact_name", e.target.value)} />
            </Field>
            <Field label="Contact email*">
              <Input
                type="email"
                value={v.contact_email}
                onChange={(e) => set("contact_email", e.target.value)}
              />
            </Field>
            <Field label="Contact phone">
              <Input
                value={v.contact_phone}
                onChange={(e) => set("contact_phone", e.target.value)}
                placeholder="+92 21 3500000"
              />
            </Field>
            <Field label="Address">
              <Input value={v.address} onChange={(e) => set("address", e.target.value)} />
            </Field>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-line pt-3">
            {missing.length > 0 && (
              <span className="mr-auto text-xs text-ink-3">
                Required: {missing.map((m) => m.replace("_", " ")).join(", ")}
              </span>
            )}
            <Button size="sm" variant="ghost" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button size="sm" onClick={save} loading={busy} disabled={!!missing.length}>
              <Check className="h-3.5 w-3.5" /> {isEdit ? "Save" : "Register"}
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ history ---------- */

function ClientHistory({ party, onClose }: { party: Party; onClose: () => void }) {
  const [rows, setRows] = useState<ContractListItem[] | null>(null);

  useEffect(() => {
    api
      .get<ContractListItem[]>(`/parties/${party.id}/contracts`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [party.id]);

  const total = (rows ?? []).reduce((sum, c) => sum + (c.value || 0), 0);
  const currency = rows?.[0]?.currency ?? "PKR";

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 sm:p-8">
      <Card className="w-full max-w-3xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            <Building2 className="h-4 w-4" /> {party.name}
          </CardTitle>
          <button onClick={onClose} className="text-ink-3 hover:text-ink" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </CardHeader>
        <CardBody className="space-y-4">
          <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-4">
            {[
              ["Registration", party.registration_no || "—"],
              ["Entity", titleCase(party.entity_type.replace("_", " "))],
              ["Jurisdiction", party.jurisdiction || "—"],
              ["KYC", titleCase(party.kyc_status)],
              ["Contact", party.contact_name || "—"],
              ["Email", party.contact_email || "—"],
              ["Phone", party.contact_phone || "—"],
              ["Risk score", String(party.risk_score)],
            ].map(([k, val]) => (
              <div key={k}>
                <dt className="text-[11px] uppercase tracking-wide text-ink-3">{k}</dt>
                <dd className="truncate text-sm text-ink">{val}</dd>
              </div>
            ))}
          </dl>

          <div>
            <div className="mb-2 flex items-baseline gap-2">
              <span className="text-sm font-medium text-ink">Agreement history</span>
              {!!rows?.length && (
                <span className="text-xs text-ink-3">
                  {rows.length} agreement{rows.length === 1 ? "" : "s"} · total exposure{" "}
                  {formatMoney(total, currency)}
                </span>
              )}
            </div>
            {rows === null && <Skeleton className="h-20" />}
            {rows?.length === 0 && (
              <p className="text-sm text-ink-3">No agreements with this client yet.</p>
            )}
            {!!rows?.length && (
              <div className="overflow-x-auto rounded-md border border-line">
                <table className="w-full text-sm">
                  <tbody>
                    {rows.map((c) => (
                      <tr key={c.id} className="border-b border-line last:border-0">
                        <td className="px-3 py-2">
                          <Link
                            href={`/contracts/${c.id}`}
                            className="font-medium text-ink hover:text-accent"
                          >
                            {c.title}
                          </Link>
                          <div className="text-xs text-ink-3">{c.reference_no}</div>
                        </td>
                        <td className="py-2 text-ink-2">{titleCase(c.status)}</td>
                        <td className="py-2 text-ink-2">
                          {c.value ? formatMoney(c.value, c.currency) : "—"}
                        </td>
                        <td className="py-2 pr-3 text-ink-3">
                          {c.end_date ? formatDate(c.end_date) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
