"use client";

// Client / Counterparty Portal — PROTOTYPE of the external negotiation + signing surface a
// counterparty sees when a contract is shared with them. Branded, no internal chrome: review the
// document, comment / propose redlines, then accept & sign. Mockup: sample thread + simulated
// actions. The real version is an unauthenticated (portal)-group route per shared-link token.

import { useState } from "react";
import { Check, CheckCircle2, FileText, MessageSquarePlus, PenLine, Send, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, Textarea } from "@/components/ui";

type Tab = "review" | "negotiate" | "sign";
type Comment = { id: string; author: string; side: "you" | "them"; clause: string; body: string; at: string };

const THREAD: Comment[] = [
  { id: "1", author: "Acme Legal", side: "them", clause: "§7 Limitation of Liability", body: "We've capped liability at 12 months' fees. This is our standard position.", at: "2 days ago" },
  { id: "2", author: "You (Northwind)", side: "you", clause: "§7 Limitation of Liability", body: "Can we raise the cap to 24 months for data-breach events specifically?", at: "1 day ago" },
  { id: "3", author: "Acme Legal", side: "them", clause: "§7 Limitation of Liability", body: "Agreed for data-breach only. We'll send a revised draft.", at: "4 hours ago" },
];

export default function ClientPortalPage() {
  const [tab, setTab] = useState<Tab>("review");
  const [thread, setThread] = useState<Comment[]>(THREAD);
  const [draft, setDraft] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [signedName, setSignedName] = useState("");
  const [done, setDone] = useState(false);

  function postComment() {
    if (!draft.trim()) return;
    setThread((t) => [...t, { id: `${t.length + 1}`, author: "You (Northwind)", side: "you", clause: "General", body: draft.trim(), at: "just now" }]);
    setDraft("");
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Client Portal <Badge tone="accent">Preview</Badge></span>}
        subtitle="What an external counterparty sees — review, negotiate, and sign a shared contract."
      />

      <div className="p-4">
        {/* Branded portal frame */}
        <div className="mx-auto max-w-4xl overflow-hidden rounded-2xl border border-line bg-white shadow-card">
          {/* portal header (branded, no app chrome) */}
          <div className="flex items-center justify-between border-b border-line bg-gradient-to-r from-accent/10 to-transparent px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-sm font-bold text-white">A</div>
              <div>
                <div className="text-sm font-semibold text-ink">Acme Holdings</div>
                <div className="text-[11px] text-ink-3">shared a contract with Northwind Ltd</div>
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-ink-3">
              <ShieldCheck className="h-3.5 w-3.5" /> Secure portal
            </div>
          </div>

          {/* contract summary */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-line px-6 py-3 text-sm">
            <span className="font-semibold text-ink">Master Services Agreement</span>
            <span className="text-ink-3">C-2026-0012</span>
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-medium text-violet-800">Awaiting your review</span>
            <span className="ml-auto text-[11px] text-ink-3">Value $120,000 · term 24 months</span>
          </div>

          {/* tabs */}
          <div className="flex gap-1 border-b border-line px-4">
            {([
              { key: "review", label: "Review document", icon: FileText },
              { key: "negotiate", label: `Negotiate (${thread.length})`, icon: MessageSquarePlus },
              { key: "sign", label: "Accept & sign", icon: PenLine },
            ] as const).map((t) => {
              const on = tab === t.key;
              const Icon = t.icon;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition ${on ? "border-accent text-accent" : "border-transparent text-ink-3 hover:text-ink"}`}
                >
                  <Icon className="h-4 w-4" /> {t.label}
                </button>
              );
            })}
          </div>

          <div className="p-6">
            {tab === "review" && (
              <div className="grid gap-4 md:grid-cols-[1fr_200px]">
                <div className="rounded-lg border border-line bg-surface-2 p-5 text-sm leading-relaxed text-ink-2">
                  <div className="mb-2 text-center text-[10px] uppercase tracking-[0.3em] text-ink-3">Master Services Agreement</div>
                  <p className="mb-3"><span className="font-semibold text-ink">1. Scope.</span> Provider will deliver the services described in each Statement of Work executed under this Agreement…</p>
                  <p className="mb-3"><span className="font-semibold text-ink">7. Limitation of Liability.</span> Except for breaches of confidentiality, each party's aggregate liability shall not exceed the fees paid in the preceding twelve (12) months <mark className="rounded bg-amber-100 px-0.5">— revised to 24 months for data-breach events</mark>…</p>
                  <p><span className="font-semibold text-ink">12. Governing Law.</span> This Agreement is governed by the laws of the DIFC…</p>
                </div>
                <div className="space-y-2">
                  <Button variant="secondary" className="w-full"><FileText className="h-4 w-4" /> Download PDF</Button>
                  <div className="rounded-lg border border-dashed border-line p-3 text-[11px] text-ink-3">
                    Latest revision incorporates the 24-month data-breach cap agreed in negotiation.
                  </div>
                </div>
              </div>
            )}

            {tab === "negotiate" && (
              <div className="space-y-4">
                <div className="space-y-3">
                  {thread.map((c) => (
                    <div key={c.id} className={`flex ${c.side === "you" ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 text-sm ${c.side === "you" ? "bg-accent text-white" : "bg-surface-2 text-ink"}`}>
                        <div className={`mb-0.5 text-[10px] font-semibold uppercase tracking-wide ${c.side === "you" ? "text-white/80" : "text-ink-3"}`}>{c.clause}</div>
                        <p>{c.body}</p>
                        <div className={`mt-1 text-[10px] ${c.side === "you" ? "text-white/70" : "text-ink-3"}`}>{c.author} · {c.at}</div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex items-end gap-2">
                  <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Propose a change or ask a question…" rows={2} className="flex-1" />
                  <Button onClick={postComment} disabled={!draft.trim()}><Send className="h-4 w-4" /></Button>
                </div>
              </div>
            )}

            {tab === "sign" && (
              <div className="mx-auto max-w-md space-y-4">
                {done ? (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center">
                    <CheckCircle2 className="mx-auto mb-2 h-10 w-10 text-emerald-600" />
                    <div className="text-base font-semibold text-ink">Signed &amp; returned</div>
                    <p className="mt-1 text-sm text-ink-2">Acme Holdings has been notified. You'll receive the fully-executed PDF by email.</p>
                  </div>
                ) : (
                  <>
                    <label className="flex items-start gap-2 text-sm text-ink-2">
                      <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-0.5" />
                      <span>I agree to use electronic records and signatures, and I accept the terms of this agreement.</span>
                    </label>
                    <div>
                      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">Type your full name to sign</label>
                      <input
                        value={signedName}
                        onChange={(e) => setSignedName(e.target.value)}
                        placeholder="Jane Doe"
                        className="h-10 w-full rounded-md border border-line bg-white px-3 text-sm"
                      />
                      <div className="mt-2 rounded-md bg-surface-2 px-3 py-2 text-2xl font-bold italic text-ink">/s/ {signedName.trim() || "—"}</div>
                    </div>
                    <Button className="w-full" disabled={!agreed || !signedName.trim()} onClick={() => setDone(true)}>
                      <Check className="h-4 w-4" /> Accept &amp; sign
                    </Button>
                    <p className="text-center text-[11px] text-ink-3">Your IP address and the time of signing are recorded as evidence.</p>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
