"use client";

/**
 * Bulk Send — one approved template dispatched to many signers (RFP BB-09).
 *
 * Replaces the simulated-send mockup. Every recipient becomes their own contract and their own
 * single-signer envelope, so each person receives *their* agreement with their own details
 * merged into it and cannot see anybody else's.
 *
 * The CSV is parsed here in the browser rather than uploaded. Posting rows as JSON keeps a
 * user-supplied file off the server entirely — no multipart handler, no temp file, nothing for
 * the upload scanner to have an opinion about — and the validation that matters runs on the
 * rows either way.
 *
 * The two-step Check → Send is the point of the screen. Five hundred envelopes cannot be
 * unsent, so the server validates every row and refuses the whole batch if any is broken;
 * finding out on row 1 of 500 is not a recoverable position.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, CalendarClock, CheckCircle2, ListChecks, Mails, Plus, Send, Trash2, Upload,
  Users, XCircle,
} from "lucide-react";
import { PageHeader } from "@/components/shell";
import {
  Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Select,
  Spinner, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import type {
  BulkSendBatch, BulkSendBatchDetail, BulkSendProblem, BulkSendValidation, ContractTemplate,
  TemplateField, TemplateForm,
} from "@/lib/types";

type Row = { id: string; name: string; email: string; values: Record<string, string> };

/** Filled from the row's own name and email, so they are never asked for twice. */
const AUTO_KEYS = new Set(["name", "signer_name", "email", "signer_email"]);

let seq = 0;
const blank = (): Row => ({ id: `r${++seq}`, name: "", email: "", values: {} });

/**
 * A CSV reader that handles quoted fields and embedded commas.
 *
 * `split(",")` is the obvious version and it corrupts every row whose company is "Khan, Sons
 * & Co" — silently, into a column shift that produces a valid-looking sheet with everybody's
 * details one place to the left.
 */
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += c;
      continue;
    }
    if (c === '"') quoted = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (c !== "\r") cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((v) => v.trim()));
}

// A local pill rather than the shared Badge, which only carries the neutral/accent/ai tones.
// Status here needs success / warning / danger, and widening the shared component for one
// screen would change every badge in the app. The status word is always shown alongside the
// colour, so the meaning survives a monochrome print or a colour-blind reader.
const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700",
  sent: "bg-emerald-50 text-emerald-700",
  completed_with_errors: "bg-amber-50 text-amber-800",
  running: "bg-amber-50 text-amber-800",
  queued: "bg-amber-50 text-amber-800",
  pending: "bg-amber-50 text-amber-800",
  failed: "bg-red-50 text-red-700",
  cancelled: "bg-surface-3 text-ink-2",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status] ?? "bg-surface-3 text-ink-2"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export default function BulkSendPage() {
  const [templates, setTemplates] = useState<ContractTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [form, setForm] = useState<TemplateForm | null>(null);
  const [rows, setRows] = useState<Row[]>([blank(), blank(), blank()]);
  const [batchName, setBatchName] = useState("");
  const [message, setMessage] = useState("");
  const [everyDays, setEveryDays] = useState(3);
  const [maxReminders, setMaxReminders] = useState(3);
  const [expiryDays, setExpiryDays] = useState(14);

  const [problems, setProblems] = useState<BulkSendProblem[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "checking" | "sending">("");
  const [batch, setBatch] = useState<BulkSendBatchDetail | null>(null);
  const [history, setHistory] = useState<BulkSendBatch[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadHistory = useCallback(() => {
    api.get<BulkSendBatch[]>("/bulk-send", { cache: false }).then(setHistory).catch(() => {});
  }, []);

  useEffect(() => {
    api.get<ContractTemplate[]>("/templates?active=true")
      .then((list) => {
        setTemplates(list);
        setTemplateId((id) => id || list[0]?.id || "");
      })
      .catch((e) => setError(e.message));
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (!templateId) { setForm(null); return; }
    api.get<TemplateForm>(`/templates/${templateId}/form`).then(setForm).catch(() => setForm(null));
  }, [templateId]);

  // Columns the operator has to fill: everything the template asks for except the two things
  // the row's own name and email already answer.
  const columns: TemplateField[] = useMemo(
    () => (form?.fields ?? []).filter((f) => !AUTO_KEYS.has(f.key)),
    [form],
  );

  const payloadRows = useMemo(
    () => rows
      .filter((r) => r.name.trim() || r.email.trim() || Object.values(r.values).some(Boolean))
      .map((r) => ({ name: r.name.trim(), email: r.email.trim(), values: r.values })),
    [rows],
  );

  const problemsByRow = useMemo(() => {
    const m = new Map<number, string[]>();
    for (const p of problems ?? []) m.set(p.row, p.errors);
    return m;
  }, [problems]);

  function update(id: string, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
    setProblems(null);
  }
  function setValue(id: string, key: string, value: string) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, values: { ...r.values, [key]: value } } : r)));
    setProblems(null);
  }

  function importCsv(file: File) {
    setError("");
    file.text().then((text) => {
      const grid = parseCsv(text);
      if (!grid.length) { setError("That file has no rows in it."); return; }
      const header = grid[0].map((h) => h.trim().toLowerCase());
      const body = grid.slice(1);
      if (!header.includes("name") || !header.includes("email")) {
        setError('The first line must be a header row including "name" and "email".');
        return;
      }
      const imported = body.map((cells) => {
        const row = blank();
        header.forEach((key, i) => {
          const cell = (cells[i] ?? "").trim();
          if (key === "name") row.name = cell;
          else if (key === "email") row.email = cell;
          else if (cell) row.values[key] = cell;
        });
        return row;
      });
      setRows(imported.length ? imported : [blank()]);
      setProblems(null);
    });
  }

  function body() {
    return {
      template_id: templateId,
      rows: payloadRows,
      name: batchName.trim(),
      message: message.trim(),
      reminder_interval_days: everyDays,
      max_reminders: maxReminders,
      expiry_days: expiryDays,
    };
  }

  async function check() {
    setBusy("checking"); setError(""); setProblems(null);
    try {
      const out = await api.post<BulkSendValidation>("/bulk-send/validate", body());
      setProblems(out.problems);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function send() {
    setBusy("sending"); setError(""); setProblems(null);
    try {
      const created = await api.post<BulkSendBatchDetail>("/bulk-send", body());
      setBatch(created);
      loadHistory();
    } catch (e) {
      // The server refuses the whole sheet and names every bad row; surface that rather than
      // a bare "400 Bad Request".
      const detail = (e as { message?: string }).message ?? "";
      try {
        const parsed = JSON.parse(detail) as { message: string; problems: BulkSendProblem[] };
        setError(parsed.message);
        setProblems(parsed.problems);
      } catch {
        setError(detail || "Could not send.");
      }
    } finally {
      setBusy("");
    }
  }

  // Poll only while there is something to watch. A finished batch stops the timer.
  useEffect(() => {
    if (!batch || !["queued", "running"].includes(batch.status)) return;
    const t = setInterval(() => {
      api.get<BulkSendBatchDetail>(`/bulk-send/${batch.id}`, { cache: false })
        .then((b) => { setBatch(b); if (!["queued", "running"].includes(b.status)) loadHistory(); })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [batch, loadHistory]);

  async function openBatch(id: string) {
    setBatch(await api.get<BulkSendBatchDetail>(`/bulk-send/${id}`, { cache: false }));
  }

  async function act(id: string, what: "cancel" | "retry") {
    try {
      setBatch(await api.post<BulkSendBatchDetail>(`/bulk-send/${id}/${what}`, {}));
      loadHistory();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const template = templates.find((t) => t.id === templateId);
  const ready = Boolean(templateId && payloadRows.length && !busy);

  if (batch) {
    return <BatchView batch={batch} onBack={() => { setBatch(null); loadHistory(); }} onAct={act} />;
  }

  return (
    <div>
      <PageHeader
        title="Bulk Send"
        subtitle="Send one approved template to many signers — each gets their own agreement, chased and expired on schedule."
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={check} disabled={!ready}>
              {busy === "checking" ? <Spinner className="h-3.5 w-3.5" /> : <ListChecks className="h-3.5 w-3.5" />}
              Check {payloadRows.length} rows
            </Button>
            <Button size="sm" onClick={send} disabled={!ready}>
              {busy === "sending" ? <Spinner className="h-3.5 w-3.5" /> : <Send className="h-3.5 w-3.5" />}
              Send to {payloadRows.length}
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_330px]">
        <div className="space-y-4">
          {error && <ErrorBanner message={error} />}

          {problems !== null && (
            problems.length === 0 ? (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                <CheckCircle2 className="h-4 w-4" /> All {payloadRows.length} rows are ready to send.
              </div>
            ) : (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <div className="flex items-center gap-2 font-medium">
                  <AlertTriangle className="h-4 w-4" />
                  {problems.length} of {payloadRows.length} rows cannot be sent. Nothing has been sent.
                </div>
                <ul className="mt-1 space-y-0.5 pl-6 text-[12px]">
                  {problems.map((p) => (
                    <li key={p.row}>Row {p.row}{p.name ? ` (${p.name})` : ""} — {p.errors.join(" ")}</li>
                  ))}
                </ul>
              </div>
            )
          )}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5"><Users className="h-4 w-4" /> Recipients</CardTitle>
              <div className="flex items-center gap-2">
                <input
                  ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) importCsv(f); e.target.value = ""; }}
                />
                <Button size="sm" variant="secondary" onClick={() => fileRef.current?.click()}>
                  <Upload className="h-3.5 w-3.5" /> Import CSV
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setRows((r) => [...r, blank()])}>
                  <Plus className="h-3.5 w-3.5" /> Add
                </Button>
              </div>
            </CardHeader>
            <CardBody className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                    <tr>
                      <th className="w-8 px-2 py-2">#</th>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2">Email</th>
                      {columns.map((c) => (
                        <th key={c.key} className="px-3 py-2">
                          {c.label}{c.required && <span className="text-danger"> *</span>}
                        </th>
                      ))}
                      <th className="w-8" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {rows.map((r, i) => {
                      const errs = problemsByRow.get(i + 1);
                      return (
                        <tr key={r.id} className={errs ? "bg-amber-50/60" : "hover:bg-surface-2"}>
                          <td className="px-2 py-1.5 text-[11px] text-ink-3">{i + 1}</td>
                          <td className="px-3 py-1.5">
                            <Input value={r.name} onChange={(e) => update(r.id, { name: e.target.value })}
                                   placeholder="Full name" className="h-8" aria-label={`Name, row ${i + 1}`} />
                          </td>
                          <td className="px-3 py-1.5">
                            <Input value={r.email} onChange={(e) => update(r.id, { email: e.target.value })}
                                   placeholder="name@company.com" className="h-8" aria-label={`Email, row ${i + 1}`} />
                          </td>
                          {columns.map((c) => (
                            <td key={c.key} className="px-3 py-1.5">
                              {c.options?.length ? (
                                <Select value={r.values[c.key] ?? ""} className="h-8"
                                        aria-label={`${c.label}, row ${i + 1}`}
                                        onChange={(e) => setValue(r.id, c.key, e.target.value)}>
                                  <option value="">—</option>
                                  {c.options.map((o) => <option key={o} value={o}>{o}</option>)}
                                </Select>
                              ) : (
                                <Input value={r.values[c.key] ?? ""} className="h-8"
                                       aria-label={`${c.label}, row ${i + 1}`}
                                       onChange={(e) => setValue(r.id, c.key, e.target.value)} />
                              )}
                            </td>
                          ))}
                          <td className="px-1">
                            <button aria-label={`Remove row ${i + 1}`}
                                    onClick={() => { setRows((rs) => rs.filter((x) => x.id !== r.id)); setProblems(null); }}
                                    className="text-ink-3 hover:text-danger">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">
                {payloadRows.length} row(s) · each becomes its own contract and its own envelope.
                CSV needs a header line with <code>name</code>, <code>email</code>
                {columns.length > 0 && <> and {columns.map((c) => <code key={c.key}> {c.key}</code>)}</>}.
              </div>
            </CardBody>
          </Card>

          {history.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Recent batches</CardTitle></CardHeader>
              <CardBody className="p-0">
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-line">
                    {history.map((b) => (
                      <tr key={b.id} className="cursor-pointer hover:bg-surface-2" onClick={() => openBatch(b.id)}>
                        <td className="px-3 py-2">{b.name}</td>
                        <td className="px-3 py-2"><StatusPill status={b.status} /></td>
                        <td className="px-3 py-2 text-right text-[12px] text-ink-2">
                          {b.succeeded} sent{b.failed ? ` · ${b.failed} failed` : ""} of {b.total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardBody>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><Mails className="h-4 w-4" /> Template</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              {templates.length === 0 ? (
                <p className="text-[12px] text-ink-2">
                  No approved templates yet. A template has to be approved before it can be sent —{" "}
                  <Link href="/templates" className="text-accent underline">approve one</Link>.
                </p>
              ) : (
                <Select value={templateId} onChange={(e) => { setTemplateId(e.target.value); setProblems(null); }}
                        aria-label="Template">
                  {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Select>
              )}
              {template && (
                <p className="text-[11px] text-ink-3">
                  {columns.length
                    ? <>Each row fills {columns.map((c) => c.label).join(", ")}. The signer&apos;s own name and email fill <code>{"{{name}}"}</code> and <code>{"{{email}}"}</code>.</>
                    : <>This template has no intake form — every recipient gets the same wording with their name merged in.</>}
                </p>
              )}
              <Field label="Batch name (optional)">
                <Input value={batchName} onChange={(e) => setBatchName(e.target.value)}
                       placeholder="e.g. Branch agents — Q3" />
              </Field>
              <Field label="Message to every signer">
                <Textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)}
                          placeholder="Please review and sign your agreement." />
              </Field>
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><CalendarClock className="h-4 w-4" /> Reminders &amp; expiry</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <Field label="Send a reminder every (days)">
                <Input type="number" min={0} value={String(everyDays)}
                       onChange={(e) => setEveryDays(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
              <Field label="Maximum reminders">
                <Input type="number" min={0} value={String(maxReminders)}
                       onChange={(e) => setMaxReminders(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
              <Field label="Envelope expires after (days)">
                <Input type="number" min={0} value={String(expiryDays)}
                       onChange={(e) => setExpiryDays(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
              <div className="rounded-lg border border-dashed border-line bg-surface-2 p-3 text-[11px] text-ink-2">
                {everyDays && maxReminders ? (
                  <>Each unsigned signer is chased up to <span className="font-semibold text-ink">{maxReminders}</span> time(s),
                    one every <span className="font-semibold text-ink">{everyDays}</span> day(s).</>
                ) : (
                  <>No automatic chasing. You can still remind a signer by hand from the contract.</>
                )}{" "}
                {expiryDays
                  ? <>Signing links stop working after <span className="font-semibold text-ink">{expiryDays}</span> day(s).</>
                  : <>Envelopes do not expire; the signing link still has its own maximum lifetime.</>}
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

function BatchView({
  batch, onBack, onAct,
}: {
  batch: BulkSendBatchDetail;
  onBack: () => void;
  onAct: (id: string, what: "cancel" | "retry") => void;
}) {
  const running = ["queued", "running"].includes(batch.status);
  return (
    <div>
      <PageHeader
        title={batch.name}
        subtitle={`${batch.template_name} · ${batch.succeeded} sent${batch.failed ? `, ${batch.failed} failed` : ""} of ${batch.total}`}
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={onBack}>Back</Button>
            {running && <Button size="sm" variant="secondary" onClick={() => onAct(batch.id, "cancel")}>Cancel remaining</Button>}
            {batch.failed > 0 && !running && <Button size="sm" onClick={() => onAct(batch.id, "retry")}>Retry {batch.failed} failed</Button>}
          </div>
        }
      />
      <div className="p-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {running && <Spinner className="h-4 w-4" />}
              <StatusPill status={batch.status} />
            </CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                <tr>
                  <th className="w-8 px-2 py-2">#</th>
                  <th className="px-3 py-2">Recipient</th>
                  <th className="px-3 py-2">Email</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Agreement</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {batch.items.map((it) => (
                  <tr key={it.id} className={it.status === "failed" ? "bg-red-50/50" : ""}>
                    <td className="px-2 py-2 text-[11px] text-ink-3">{it.sequence + 1}</td>
                    <td className="px-3 py-2">{it.name}</td>
                    <td className="px-3 py-2 text-ink-2">{it.email}</td>
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-1.5">
                        {it.status === "sent" && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />}
                        {it.status === "failed" && <XCircle className="h-3.5 w-3.5 text-danger" />}
                        <StatusPill status={it.status} />
                      </span>
                      {it.error && <div className="mt-0.5 text-[11px] text-danger">{it.error}</div>}
                    </td>
                    <td className="px-3 py-2">
                      {it.contract_id
                        ? <Link href={`/contracts/${it.contract_id}`} className="text-accent underline">Open</Link>
                        : <span className="text-[11px] text-ink-3">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
