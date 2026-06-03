"use client";

// Temporary External Access — PROTOTYPE. Grant a vendor/counterparty scoped, time-limited access
// to a SINGLE contract (view / view+comment / view+sign), with an expiry and instant revoke. The
// vendor lands on an unauthenticated guest portal scoped to just that contract. Reuses the same
// hashed + expiring token model as signing links. Mockup: in-memory; "Vendor view" previews the
// guest experience. Wires later to a /share endpoint minting a /portal/{token} link.

import { useState } from "react";
import {
  CalendarClock, Check, Clock, Copy, Eye, FileText, Link2, Lock, MessageSquare, PenLine,
  Shield, Trash2, UserPlus,
} from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Input, Select } from "@/components/ui";

type Access = "view" | "comment" | "sign";
type Grant = {
  id: string; email: string; access: Access; expiresDays: number; otp: boolean;
  status: "active" | "revoked"; opened: boolean; token: string;
};

const ACCESS_META: Record<Access, { label: string; icon: typeof Eye; pill: string }> = {
  view: { label: "View only", icon: Eye, pill: "bg-slate-100 text-slate-700" },
  comment: { label: "View + comment", icon: MessageSquare, pill: "bg-blue-50 text-blue-700" },
  sign: { label: "View + sign", icon: PenLine, pill: "bg-violet-50 text-violet-700" },
};

const CONTRACT = { ref: "C-2026-0012", title: "Northwind Master Services Agreement", value: "$120,000", term: "24 months" };

function fakeToken() {
  // deterministic-ish demo token (no Math.random in this env-friendly way needed for a mockup)
  return "tmp_" + Math.abs(Date.now()).toString(36) + "x7f2a9";
}

const INITIAL: Grant[] = [
  { id: "1", email: "vendor@northwind.io", access: "sign", expiresDays: 7, otp: true, status: "active", opened: true, token: "tmp_a1b2c3" },
  { id: "2", email: "legal@northwind.io", access: "comment", expiresDays: 5, otp: false, status: "active", opened: false, token: "tmp_d4e5f6" },
];

export default function TemporaryAccessPage() {
  const [mode, setMode] = useState<"manage" | "vendor">("manage");
  const [grants, setGrants] = useState<Grant[]>(INITIAL);
  const [email, setEmail] = useState("");
  const [access, setAccess] = useState<Access>("view");
  const [expiry, setExpiry] = useState(7);
  const [otp, setOtp] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [justAdded, setJustAdded] = useState<string | null>(null);

  function grant() {
    if (!email.includes("@")) return;
    const g: Grant = { id: `${Date.now()}`, email: email.trim(), access, expiresDays: expiry, otp, status: "active", opened: false, token: fakeToken() };
    setGrants((arr) => [g, ...arr]);
    setJustAdded(g.id);
    setEmail("");
    setTimeout(() => setJustAdded(null), 4000);
  }
  function revoke(id: string) {
    setGrants((arr) => arr.map((x) => (x.id === id ? { ...x, status: "revoked" } : x)));
  }
  function copyLink(g: Grant) {
    try { navigator.clipboard?.writeText(`https://acme-cm.io/portal/${g.token}`); } catch { /* noop */ }
    setCopied(g.id);
    setTimeout(() => setCopied(null), 1400);
  }

  // the grant we preview in "Vendor view"
  const previewGrant = grants.find((g) => g.status === "active") ?? INITIAL[0];

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Temporary Access <Badge tone="accent">Preview</Badge></span>}
        subtitle="Give a vendor scoped, time-limited access to a single contract — then it auto-expires."
        actions={
          <div className="flex items-center gap-1 rounded-lg border border-line bg-surface-2 p-0.5 text-sm">
            <button onClick={() => setMode("manage")} className={`rounded-md px-3 py-1.5 font-medium ${mode === "manage" ? "bg-white text-ink shadow-sm" : "text-ink-3"}`}>Manage grants</button>
            <button onClick={() => setMode("vendor")} className={`rounded-md px-3 py-1.5 font-medium ${mode === "vendor" ? "bg-white text-ink shadow-sm" : "text-ink-3"}`}>Vendor view</button>
          </div>
        }
      />

      {mode === "manage" ? (
        <div className="grid gap-4 p-4 lg:grid-cols-[360px_1fr]">
          {/* grant form */}
          <Card className="h-max">
            <CardHeader><CardTitle className="flex items-center gap-1.5"><UserPlus className="h-4 w-4" /> Grant access</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <div className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm">
                <div className="flex items-center gap-1.5 text-ink"><FileText className="h-3.5 w-3.5 text-ink-3" /> <span className="font-medium">{CONTRACT.title}</span></div>
                <div className="text-[11px] text-ink-3">{CONTRACT.ref} · {CONTRACT.value} · {CONTRACT.term}</div>
              </div>
              <Field label="Vendor email"><Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="vendor@company.com" /></Field>
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">Access level</label>
                <div className="space-y-1.5">
                  {(Object.keys(ACCESS_META) as Access[]).map((a) => {
                    const M = ACCESS_META[a]; const Icon = M.icon; const on = access === a;
                    return (
                      <button key={a} onClick={() => setAccess(a)} className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition ${on ? "border-accent bg-accent/5 font-medium text-ink" : "border-line text-ink-2 hover:bg-surface-2"}`}>
                        <Icon className={`h-4 w-4 ${on ? "text-accent" : "text-ink-3"}`} /> {M.label}
                        {on && <Check className="ml-auto h-4 w-4 text-accent" />}
                      </button>
                    );
                  })}
                </div>
              </div>
              <Field label="Expires after">
                <Select value={String(expiry)} onChange={(e) => setExpiry(Number(e.target.value))}>
                  {[3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} days</option>)}
                </Select>
              </Field>
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={otp} onChange={(e) => setOtp(e.target.checked)} />
                <Shield className="h-3.5 w-3.5 text-ink-3" /> Require email OTP before access
              </label>
              <Button className="w-full" onClick={grant} disabled={!email.includes("@")}><Link2 className="h-4 w-4" /> Create access link</Button>
              <p className="text-[11px] text-ink-3">A unique, hashed link is emailed to the vendor — scoped to this contract only, never your whole workspace.</p>
            </CardBody>
          </Card>

          {/* active grants */}
          <Card>
            <CardHeader>
              <CardTitle>Active &amp; past grants</CardTitle>
              <span className="text-xs text-ink-3">{grants.filter((g) => g.status === "active").length} active</span>
            </CardHeader>
            <CardBody className="space-y-2">
              {grants.map((g) => {
                const M = ACCESS_META[g.access];
                const revoked = g.status === "revoked";
                return (
                  <div key={g.id} className={`rounded-lg border p-3 ${justAdded === g.id ? "border-accent ring-1 ring-accent" : "border-line"} ${revoked ? "opacity-60" : ""}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-ink">{g.email}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${M.pill}`}>{M.label}</span>
                      {g.otp && <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-ink-3"><Shield className="h-2.5 w-2.5" /> OTP</span>}
                      {revoked ? (
                        <span className="rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-medium text-red-700">Revoked</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700"><Clock className="h-2.5 w-2.5" /> {g.expiresDays}d left</span>
                      )}
                      <span className="ml-auto text-[11px] text-ink-3">{g.opened ? "Opened" : "Not opened yet"}</span>
                    </div>
                    {!revoked && (
                      <div className="mt-2 flex items-center gap-2">
                        <code className="truncate rounded bg-surface-2 px-2 py-1 text-[11px] text-ink-2">acme-cm.io/portal/{g.token}</code>
                        <Button size="sm" variant="secondary" className="h-7 shrink-0" onClick={() => copyLink(g)}>
                          {copied === g.id ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                        </Button>
                        <button onClick={() => revoke(g.id)} className="shrink-0 text-[11px] text-ink-3 hover:text-danger"><Trash2 className="mr-0.5 inline h-3 w-3" />Revoke</button>
                      </div>
                    )}
                  </div>
                );
              })}
            </CardBody>
          </Card>
        </div>
      ) : (
        /* ---------- Vendor (guest) view preview ---------- */
        <div className="p-4">
          <p className="mx-auto mb-3 max-w-3xl text-center text-xs text-ink-3">Preview of what <span className="font-medium text-ink-2">{previewGrant.email}</span> sees at their access link — scoped to one contract.</p>
          <div className="mx-auto max-w-3xl overflow-hidden rounded-2xl border border-line bg-white shadow-card">
            <div className="flex items-center justify-between border-b border-line bg-gradient-to-r from-accent/10 to-transparent px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-sm font-bold text-white">A</div>
                <div>
                  <div className="text-sm font-semibold text-ink">Acme Holdings shared a contract with you</div>
                  <div className="text-[11px] text-ink-3">{previewGrant.email}</div>
                </div>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${ACCESS_META[previewGrant.access].pill}`}>{ACCESS_META[previewGrant.access].label}</span>
            </div>

            {/* expiry banner */}
            <div className="flex items-center gap-2 border-b border-line bg-amber-50 px-6 py-2 text-[12px] text-amber-800">
              <CalendarClock className="h-4 w-4" /> Your access expires in <span className="font-semibold">{previewGrant.expiresDays} days</span> · this link is unique to you, please don&rsquo;t forward it.
            </div>

            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-line px-6 py-3 text-sm">
              <span className="font-semibold text-ink">{CONTRACT.title}</span>
              <span className="text-ink-3">{CONTRACT.ref}</span>
              <span className="ml-auto text-[11px] text-ink-3">{CONTRACT.value} · {CONTRACT.term}</span>
            </div>

            <div className="grid gap-4 p-6 md:grid-cols-[1fr_200px]">
              <div className="rounded-lg border border-line bg-surface-2 p-5 text-sm leading-relaxed text-ink-2">
                <div className="mb-2 text-center text-[10px] uppercase tracking-[0.3em] text-ink-3">Master Services Agreement</div>
                <p className="mb-3"><span className="font-semibold text-ink">1. Scope.</span> Provider will deliver the services described in each Statement of Work…</p>
                <p className="mb-3"><span className="font-semibold text-ink">7. Limitation of Liability.</span> Each party&rsquo;s aggregate liability shall not exceed the fees paid in the preceding twelve months…</p>
                <p><span className="font-semibold text-ink">12. Governing Law.</span> Governed by the laws of the DIFC…</p>
              </div>
              <div className="space-y-2">
                <Button variant="secondary" className="w-full"><FileText className="h-4 w-4" /> Download PDF</Button>
                {previewGrant.access === "comment" && <Button variant="secondary" className="w-full"><MessageSquare className="h-4 w-4" /> Add a comment</Button>}
                {previewGrant.access === "sign" && <Button className="w-full"><PenLine className="h-4 w-4" /> Review &amp; sign</Button>}
                {previewGrant.access === "view" && (
                  <div className="flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-2 text-[11px] text-ink-3"><Lock className="h-3.5 w-3.5" /> View-only access</div>
                )}
                {previewGrant.otp && (
                  <div className="flex items-center gap-1.5 rounded-lg border border-dashed border-line px-3 py-2 text-[11px] text-ink-2"><Shield className="h-3.5 w-3.5 text-emerald-600" /> Verified via email OTP</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
