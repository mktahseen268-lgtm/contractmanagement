"use client";

/**
 * Pick the client an agreement is with, or register one without leaving the form.
 *
 * This replaced a free-text box. That box is why "Sadiq Traders (Pvt) Ltd", "Sadiq Traders Pvt
 * Ltd" and "SADIQ TRADERS" were three different companies to every report, and why "what is our
 * total exposure to this client?" had no answer.
 *
 * The register-inline path matters as much as the search. A drafter with the counterparty in
 * front of them and no matching record will find a way to proceed — and the way a text box
 * allows is to type the name slightly differently. Making onboarding a two-field step inside
 * the flow is what stops that.
 */

import { useEffect, useRef, useState } from "react";
import { Building2, Check, Plus, Search, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Field, Input, Select } from "@/components/ui";
import type { Party } from "@/lib/types";

const ENTITY_TYPES = ["company", "sole_trader", "partnership", "government", "individual"];

export function ClientPicker({
  value,
  partyId,
  onPick,
}: {
  /** The stored counterparty name — kept, because every report and PDF still reads it. */
  value: string;
  partyId: string | null;
  onPick: (name: string, id: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Party[] | null>(null);
  const [registering, setRegistering] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      api
        .get<Party[]>(`/parties?${params.toString()}`)
        .then((r) => setRows(r.filter((p) => p.is_active)))
        .catch(() => setRows([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, open]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-full items-center gap-2 rounded-md border border-line bg-surface px-3 text-left text-sm text-ink outline-none focus:border-accent"
      >
        <Building2 className="h-3.5 w-3.5 shrink-0 text-ink-3" />
        <span className={value ? "truncate text-ink" : "truncate text-ink-3"}>
          {value || "Search for a client…"}
        </span>
        {value && !partyId && (
          // A name with no record behind it is exactly the state this control exists to end.
          <span className="ml-auto shrink-0 text-xs text-amber-700">unlinked</span>
        )}
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-line bg-surface shadow-lg">
          {registering ? (
            <QuickRegister
              initialName={q}
              onCancel={() => setRegistering(false)}
              onCreated={(p) => {
                onPick(p.name, p.id);
                setRegistering(false);
                setOpen(false);
              }}
            />
          ) : (
            <>
              <div className="relative border-b border-line p-2">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" />
                <input
                  autoFocus
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Name or registration number"
                  className="h-8 w-full rounded-md border border-line bg-surface pl-7 pr-2 text-sm text-ink outline-none focus:border-accent"
                />
              </div>
              <div className="max-h-60 overflow-y-auto">
                {rows === null && <p className="px-3 py-3 text-xs text-ink-3">Searching…</p>}
                {rows?.length === 0 && (
                  <p className="px-3 py-3 text-xs text-ink-3">
                    No client matches “{q}”.
                  </p>
                )}
                {rows?.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      onPick(p.name, p.id);
                      setOpen(false);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-surface-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-ink">{p.name}</div>
                      <div className="truncate text-xs text-ink-3">
                        {p.registration_no || "no registration"} · {p.jurisdiction || "—"}
                      </div>
                    </div>
                    {p.kyc_status === "verified" && (
                      <Check className="h-3.5 w-3.5 shrink-0 text-ok" />
                    )}
                    {p.id === partyId && <span className="text-xs text-accent">selected</span>}
                  </button>
                ))}
              </div>
              <div className="border-t border-line p-2">
                <Button
                  size="sm"
                  variant="ghost"
                  className="w-full justify-start"
                  onClick={() => setRegistering(true)}
                >
                  <Plus className="h-3.5 w-3.5" /> Register a new client
                  {q.trim() ? ` — “${q.trim()}”` : ""}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** The smallest onboarding that still produces a usable record.
 *
 * Fewer fields than the Clients screen on purpose: a drafter mid-agreement has the name and the
 * registration number to hand and rarely the rest, and a nine-field form at this moment is what
 * sends them back to typing a name. The record can be completed under Clients afterwards, and
 * its KYC status starts at pending to say so.
 */
function QuickRegister({
  initialName,
  onCancel,
  onCreated,
}: {
  initialName: string;
  onCancel: () => void;
  onCreated: (p: Party) => void;
}) {
  const [name, setName] = useState(initialName);
  const [registration, setRegistration] = useState("");
  const [entity, setEntity] = useState("company");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function create() {
    if (!name.trim() || !registration.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const p = await api.post<Party>("/parties", {
        name: name.trim(),
        registration_no: registration.trim(),
        entity_type: entity,
        jurisdiction: "Islamic Republic of Pakistan",
        kyc_status: "pending",
      });
      onCreated(p);
    } catch (e) {
      // Onboarding refuses a likely duplicate. Surfacing that verbatim is the point: the
      // reader should go and find the existing record, not invent a spelling to get past it.
      setErr(e instanceof ApiError ? e.message : "Couldn't register that client.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink-3">
        Register a client
      </div>
      {err && <p className="text-xs text-danger">{err}</p>}
      <Field label="Legal name*">
        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </Field>
      <Field label="Registration / NTN*">
        <Input
          value={registration}
          onChange={(e) => setRegistration(e.target.value)}
          placeholder="NTN-1234567"
        />
      </Field>
      <Field label="Entity type">
        <Select value={entity} onChange={(e) => setEntity(e.target.value)}>
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace("_", " ")}
            </option>
          ))}
        </Select>
      </Field>
      <p className="text-[11px] text-ink-3">
        Starts as KYC pending. Complete the record under Clients.
      </p>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={create} loading={busy} disabled={!name.trim() || !registration.trim()}>
          <Check className="h-3.5 w-3.5" /> Register &amp; use
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          <X className="h-3.5 w-3.5" /> Back to search
        </Button>
      </div>
    </div>
  );
}
