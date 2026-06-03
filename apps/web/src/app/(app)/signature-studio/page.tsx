"use client";

// Signature Studio — interactive PROTOTYPE of the drag-and-drop signing-ceremony DocViewer.
// The sender picks a recipient, then drops signature / initials / date / text / checkbox fields
// onto the document at exact coordinates. This mirrors the real `signature_tabs` data model
// (page + x/y/w/h as 0..1 fractions) so it can be wired to POST /envelopes/{id}/tabs later.
// Mockup: nothing persists; "Send" is simulated.

import { useRef, useState } from "react";
import { CheckSquare, Calendar, Hash, PenLine, Plus, Send, Trash2, Type as TypeIcon, X } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";

type FieldKind = "signature" | "initials" | "date" | "text" | "checkbox";

type Recipient = { id: string; name: string; email: string; color: string };

type PlacedField = {
  id: string;
  kind: FieldKind;
  recipientId: string;
  page: number;
  x: number; // 0..1 fraction of page width (left)
  y: number; // 0..1 fraction of page height (top)
  w: number;
  h: number;
};

const RECIPIENTS: Recipient[] = [
  { id: "r1", name: "Shahzaib Memon", email: "shahzaib@thiqatech.com", color: "#3E7BFA" },
  { id: "r2", name: "Aisha Al Abri", email: "aisha@trialco.io", color: "#8B5CF6" },
  { id: "r3", name: "Counsel (CC)", email: "legal@acme.io", color: "#12B76A" },
];

const FIELD_TYPES: { kind: FieldKind; label: string; icon: typeof PenLine; w: number; h: number }[] = [
  { kind: "signature", label: "Signature", icon: PenLine, w: 0.26, h: 0.05 },
  { kind: "initials", label: "Initials", icon: Hash, w: 0.1, h: 0.045 },
  { kind: "date", label: "Date signed", icon: Calendar, w: 0.16, h: 0.04 },
  { kind: "text", label: "Text", icon: TypeIcon, w: 0.22, h: 0.04 },
  { kind: "checkbox", label: "Checkbox", icon: CheckSquare, w: 0.04, h: 0.035 },
];

const PAGES = [1, 2];

let _seq = 0;
const nextId = () => `f${++_seq}`;

export default function SignatureStudioPage() {
  const [recipientId, setRecipientId] = useState(RECIPIENTS[0].id);
  const [armed, setArmed] = useState<FieldKind | null>("signature");
  const [fields, setFields] = useState<PlacedField[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const dragRef = useRef<{ id: string; dx: number; dy: number; pageEl: HTMLElement } | null>(null);

  const recip = (id: string) => RECIPIENTS.find((r) => r.id === id)!;

  function placeOnPage(e: React.MouseEvent<HTMLDivElement>, page: number) {
    if (!armed) return;
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const ft = FIELD_TYPES.find((f) => f.kind === armed)!;
    const nf: PlacedField = {
      id: nextId(), kind: armed, recipientId, page,
      x: Math.max(0, Math.min(1 - ft.w, x - ft.w / 2)),
      y: Math.max(0, Math.min(1 - ft.h, y - ft.h / 2)),
      w: ft.w, h: ft.h,
    };
    setFields((f) => [...f, nf]);
    setSelected(nf.id);
  }

  function startMove(e: React.PointerEvent, f: PlacedField) {
    e.stopPropagation();
    const pageEl = (e.currentTarget as HTMLElement).parentElement as HTMLElement;
    const rect = pageEl.getBoundingClientRect();
    dragRef.current = {
      id: f.id,
      dx: (e.clientX - rect.left) / rect.width - f.x,
      dy: (e.clientY - rect.top) / rect.height - f.y,
      pageEl,
    };
    setSelected(f.id);
    try { (e.target as Element).setPointerCapture(e.pointerId); } catch { /* noop */ }
  }
  function moving(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    const rect = d.pageEl.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width - d.dx;
    const ny = (e.clientY - rect.top) / rect.height - d.dy;
    setFields((arr) => arr.map((f) => (f.id === d.id ? { ...f, x: Math.max(0, Math.min(1 - f.w, nx)), y: Math.max(0, Math.min(1 - f.h, ny)) } : f)));
  }
  function endMove() {
    dragRef.current = null;
  }

  function removeField(id: string) {
    setFields((f) => f.filter((x) => x.id !== id));
    if (selected === id) setSelected(null);
  }

  const fieldsForRecipient = (id: string) => fields.filter((f) => f.recipientId === id).length;

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Signature Studio</span>}
        subtitle="Drag-and-drop signing fields onto the document — the visual placement experience."
        actions={
          <Button size="sm" onClick={() => setSent(true)} disabled={fields.length === 0}>
            <Send className="h-3.5 w-3.5" /> Send for signature
          </Button>
        }
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[260px_1fr_240px]">
        {/* Left: recipients + field palette */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Recipients</CardTitle></CardHeader>
            <CardBody className="space-y-1.5">
              {RECIPIENTS.map((r) => {
                const active = r.id === recipientId;
                return (
                  <button
                    key={r.id}
                    onClick={() => setRecipientId(r.id)}
                    className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition ${active ? "border-accent bg-accent/5" : "border-line hover:bg-surface-2"}`}
                  >
                    <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: r.color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-ink">{r.name}</span>
                      <span className="block truncate text-[11px] text-ink-3">{r.email}</span>
                    </span>
                    <span className="shrink-0 rounded-full bg-surface-2 px-1.5 text-[11px] font-semibold text-ink-2">{fieldsForRecipient(r.id)}</span>
                  </button>
                );
              })}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>Fields</CardTitle></CardHeader>
            <CardBody className="space-y-1.5">
              <p className="mb-1 text-[11px] text-ink-3">Pick a field, then click on the document to drop it. Drag any placed field to move it.</p>
              {FIELD_TYPES.map((ft) => {
                const Icon = ft.icon;
                const on = armed === ft.kind;
                return (
                  <button
                    key={ft.kind}
                    onClick={() => setArmed(on ? null : ft.kind)}
                    className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition ${on ? "border-accent bg-accent text-white" : "border-line text-ink-2 hover:bg-surface-2"}`}
                  >
                    <Icon className="h-4 w-4" /> {ft.label}
                    {on && <span className="ml-auto text-[10px] uppercase tracking-wide opacity-80">armed</span>}
                  </button>
                );
              })}
            </CardBody>
          </Card>
        </div>

        {/* Center: the document */}
        <div className="space-y-6">
          {armed && (
            <div className="rounded-lg border border-dashed border-accent bg-accent/5 px-3 py-2 text-sm text-ink-2">
              Placing <span className="font-semibold text-ink">{FIELD_TYPES.find((f) => f.kind === armed)!.label}</span> for{" "}
              <span className="font-semibold" style={{ color: recip(recipientId).color }}>{recip(recipientId).name}</span> — click on the page.
            </div>
          )}
          {PAGES.map((page) => (
            <div
              key={page}
              onClick={(e) => placeOnPage(e, page)}
              onPointerMove={moving}
              onPointerUp={endMove}
              className={`relative mx-auto aspect-[1/1.414] w-full max-w-2xl overflow-hidden rounded-lg border border-line bg-white shadow-card ${armed ? "cursor-crosshair" : ""}`}
            >
              <DocumentMockBody page={page} />
              {fields.filter((f) => f.page === page).map((f) => {
                const r = recip(f.recipientId);
                const Icon = FIELD_TYPES.find((t) => t.kind === f.kind)!.icon;
                const isSel = selected === f.id;
                return (
                  <div
                    key={f.id}
                    onPointerDown={(e) => startMove(e, f)}
                    onClick={(e) => e.stopPropagation()}
                    className={`group absolute flex cursor-move items-center justify-center rounded-[3px] border-2 text-[10px] font-semibold ${isSel ? "z-10 ring-2 ring-offset-1" : ""}`}
                    style={{
                      left: `${f.x * 100}%`, top: `${f.y * 100}%`,
                      width: `${f.w * 100}%`, height: `${f.h * 100}%`,
                      borderColor: r.color, background: `${r.color}1a`, color: r.color,
                    }}
                  >
                    <Icon className="h-3 w-3 shrink-0" />
                    <span className="ml-1 truncate">{FIELD_TYPES.find((t) => t.kind === f.kind)!.label}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeField(f.id); }}
                      className="absolute -right-2 -top-2 hidden h-4 w-4 place-items-center rounded-full bg-danger text-white group-hover:grid"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                );
              })}
              <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-ink-3">Page {page} of {PAGES.length}</div>
            </div>
          ))}
        </div>

        {/* Right: placed fields summary */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Placed fields</CardTitle>
              <span className="text-xs text-ink-3">{fields.length}</span>
            </CardHeader>
            <CardBody className="space-y-1.5">
              {fields.length === 0 ? (
                <p className="text-sm text-ink-3">No fields yet. Pick a field on the left and click the document.</p>
              ) : (
                fields.map((f) => {
                  const r = recip(f.recipientId);
                  return (
                    <button
                      key={f.id}
                      onClick={() => setSelected(f.id)}
                      className={`flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs ${selected === f.id ? "border-accent bg-accent/5" : "border-line hover:bg-surface-2"}`}
                    >
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: r.color }} />
                      <span className="flex-1 truncate font-medium text-ink">{FIELD_TYPES.find((t) => t.kind === f.kind)!.label}</span>
                      <span className="shrink-0 text-ink-3">p{f.page}</span>
                      <Trash2 className="h-3 w-3 shrink-0 text-ink-3 hover:text-danger" onClick={(e) => { e.stopPropagation(); removeField(f.id); }} />
                    </button>
                  );
                })
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>Signing order</CardTitle></CardHeader>
            <CardBody className="space-y-2 text-sm">
              {RECIPIENTS.map((r, i) => (
                <div key={r.id} className="flex items-center gap-2">
                  <span className="grid h-5 w-5 place-items-center rounded-full bg-surface-2 text-[11px] font-semibold text-ink-2">{i + 1}</span>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: r.color }} />
                  <span className="flex-1 truncate text-ink-2">{r.name}</span>
                  <span className="text-[11px] text-ink-3">{fieldsForRecipient(r.id)} fields</span>
                </div>
              ))}
              <p className="pt-1 text-[11px] text-ink-3">Sequential — each signer is emailed when it's their turn.</p>
            </CardBody>
          </Card>
        </div>
      </div>

      {sent && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setSent(false)}>
          <Card className="w-full max-w-sm" >
            <CardBody className="space-y-3 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                <Send className="h-6 w-6" />
              </div>
              <div className="text-base font-semibold text-ink">Envelope ready to send</div>
              <p className="text-sm text-ink-2">
                {fields.length} field{fields.length === 1 ? "" : "s"} placed across {RECIPIENTS.filter((r) => fieldsForRecipient(r.id) > 0).length} recipient(s).
                The fields are saved to each recipient and the envelope is sent for signature.
              </p>
              <Button className="w-full" onClick={() => setSent(false)}>Got it</Button>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}

function DocumentMockBody({ page }: { page: number }) {
  // A faux contract page so placement has realistic context. Pointer-events disabled so clicks
  // fall through to the page (for placing fields).
  return (
    <div className="pointer-events-none absolute inset-0 p-8 text-ink">
      {page === 1 ? (
        <>
          <div className="text-center">
            <div className="text-[10px] uppercase tracking-[0.3em] text-ink-3">Master Services Agreement</div>
            <div className="mt-2 text-lg font-bold">Acme Holdings &amp; ThiqaTech</div>
            <div className="mt-1 text-[11px] text-ink-3">Reference C-2026-0031 · effective 2026-06-01</div>
          </div>
          <div className="mt-6 space-y-2">
            {["1. Scope of Services", "2. Term and Termination", "3. Fees and Payment", "4. Confidentiality"].map((h) => (
              <div key={h}>
                <div className="text-[11px] font-semibold">{h}</div>
                <FauxLines n={3} />
              </div>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="text-[11px] font-semibold">5. Signatures</div>
          <FauxLines n={2} />
          <div className="mt-10 grid grid-cols-2 gap-8">
            {["For Acme Holdings", "For ThiqaTech"].map((s) => (
              <div key={s}>
                <div className="h-10 border-b border-ink/30" />
                <div className="mt-1 text-[10px] text-ink-3">{s}</div>
                <div className="mt-4 h-6 border-b border-ink/30" />
                <div className="mt-1 text-[10px] text-ink-3">Date</div>
              </div>
            ))}
          </div>
          <div className="mt-8 text-[11px] font-semibold">6. General Provisions</div>
          <FauxLines n={4} />
        </>
      )}
    </div>
  );
}

function FauxLines({ n }: { n: number }) {
  return (
    <div className="mt-1 space-y-1.5">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="h-1.5 rounded bg-surface-3" style={{ width: `${92 - (i % 3) * 12}%` }} />
      ))}
    </div>
  );
}
