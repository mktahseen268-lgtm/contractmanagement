"use client";

// Clause Library — PROTOTYPE of a reusable approved-language bank with playbook guidance.
// Categories on the left, searchable clause cards in the middle, a detail/insert panel on the
// right. In the live product, "Insert" drops the clause into the Tiptap editor and clauses are
// versioned + approval-gated. Mockup: sample data, no persistence.

import { useMemo, useState } from "react";
import { BadgeCheck, BookMarked, Check, Copy, FileInput, Plus, Search, Shield, Star } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, Input } from "@/components/ui";

type Risk = "preferred" | "acceptable" | "fallback";
type Clause = {
  id: string;
  title: string;
  category: string;
  body: string;
  tags: string[];
  approved: boolean;
  risk: Risk;
  usedCount: number;
  favorite?: boolean;
};

const CATEGORIES = [
  "Confidentiality", "Liability & Indemnity", "Termination", "Payment", "IP & Ownership",
  "Data Protection", "Governing Law", "Force Majeure",
];

const CLAUSES: Clause[] = [
  {
    id: "c1", title: "Mutual NDA — Standard", category: "Confidentiality", approved: true, risk: "preferred", usedCount: 142, favorite: true,
    tags: ["mutual", "standard", "5-year"],
    body: "Each party agrees to hold in strict confidence and not disclose to any third party any Confidential Information of the other party, and to use such Confidential Information solely for the purpose of performing its obligations under this Agreement, for a period of five (5) years from the date of disclosure.",
  },
  {
    id: "c2", title: "Limitation of Liability — Cap at Fees", category: "Liability & Indemnity", approved: true, risk: "preferred", usedCount: 98,
    tags: ["cap", "12-month fees"],
    body: "Except for breaches of confidentiality or indemnification obligations, each party's total aggregate liability arising out of or related to this Agreement shall not exceed the total fees paid or payable by Customer in the twelve (12) months preceding the event giving rise to the claim.",
  },
  {
    id: "c3", title: "Termination for Convenience — 30 Days", category: "Termination", approved: true, risk: "acceptable", usedCount: 61,
    tags: ["30-day notice"],
    body: "Either party may terminate this Agreement for convenience upon thirty (30) days' prior written notice to the other party. Customer shall remain responsible for all fees accrued through the effective date of termination.",
  },
  {
    id: "c4", title: "Net-60 Payment Terms", category: "Payment", approved: false, risk: "fallback", usedCount: 12,
    tags: ["net-60", "non-standard"],
    body: "Customer shall pay all undisputed invoices within sixty (60) (Net-60) days of the invoice date. Late payments accrue interest at 1.5% per month or the maximum rate permitted by law.",
  },
  {
    id: "c5", title: "IP Assignment — Work Product", category: "IP & Ownership", approved: true, risk: "preferred", usedCount: 77,
    tags: ["assignment", "work-for-hire"],
    body: "All deliverables, work product, and intellectual property created by Provider specifically for Customer under a Statement of Work shall be deemed work made for hire and, upon full payment, are assigned exclusively to Customer.",
  },
  {
    id: "c6", title: "GDPR Data Processing Addendum", category: "Data Protection", approved: true, risk: "preferred", usedCount: 54, favorite: true,
    tags: ["GDPR", "DPA", "EU"],
    body: "The parties shall comply with all applicable data protection laws, including the GDPR. Provider shall process Personal Data only on documented instructions from Customer, implement appropriate technical and organisational measures, and assist Customer with data-subject requests.",
  },
  {
    id: "c7", title: "Governing Law — UAE / DIFC", category: "Governing Law", approved: true, risk: "acceptable", usedCount: 33,
    tags: ["UAE", "DIFC", "arbitration"],
    body: "This Agreement shall be governed by the laws of the Dubai International Financial Centre (DIFC). Any dispute shall be referred to and finally resolved by arbitration under the DIFC-LCIA Arbitration Rules, seated in the DIFC.",
  },
  {
    id: "c8", title: "Force Majeure — Standard", category: "Force Majeure", approved: true, risk: "preferred", usedCount: 45,
    tags: ["standard"],
    body: "Neither party shall be liable for any failure or delay in performance due to causes beyond its reasonable control, including acts of God, war, terrorism, epidemic, governmental action, or failure of telecommunications, provided it uses reasonable efforts to mitigate.",
  },
];

const RISK_META: Record<Risk, { label: string; pill: string }> = {
  preferred: { label: "Preferred", pill: "bg-emerald-50 text-emerald-700" },
  acceptable: { label: "Acceptable", pill: "bg-amber-50 text-amber-700" },
  fallback: { label: "Fallback", pill: "bg-red-50 text-red-700" },
};

function RiskPill({ risk }: { risk: Risk }) {
  return (
    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${RISK_META[risk].pill}`}>
      {RISK_META[risk].label}
    </span>
  );
}

export default function ClauseLibraryPage() {
  const [cat, setCat] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string>(CLAUSES[0].id);
  const [copied, setCopied] = useState<string | null>(null);
  const [inserted, setInserted] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return CLAUSES.filter((c) => {
      if (cat && c.category !== cat) return false;
      if (!needle) return true;
      return (
        c.title.toLowerCase().includes(needle) ||
        c.body.toLowerCase().includes(needle) ||
        c.tags.some((t) => t.toLowerCase().includes(needle))
      );
    });
  }, [cat, q]);

  const current = CLAUSES.find((c) => c.id === selected) ?? null;

  function copyBody(c: Clause) {
    try { navigator.clipboard?.writeText(c.body); } catch { /* noop */ }
    setCopied(c.id);
    setTimeout(() => setCopied(null), 1500);
  }
  function insert(c: Clause) {
    setInserted(c.id);
    setTimeout(() => setInserted(null), 1800);
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Clause Library <Badge tone="accent">Preview</Badge></span>}
        subtitle="Reusable, approved language with playbook guidance — insert straight into the contract editor."
        actions={<Button size="sm"><Plus className="h-3.5 w-3.5" /> New clause</Button>}
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[210px_1fr_340px]">
        {/* categories */}
        <Card className="h-max">
          <CardBody className="space-y-0.5">
            <button
              onClick={() => setCat(null)}
              className={`flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm ${!cat ? "bg-accent/10 font-medium text-accent" : "text-ink-2 hover:bg-surface-2"}`}
            >
              <BookMarked className="h-4 w-4" /> All clauses
              <span className="ml-auto text-[11px] text-ink-3">{CLAUSES.length}</span>
            </button>
            {CATEGORIES.map((c) => {
              const n = CLAUSES.filter((x) => x.category === c).length;
              const on = cat === c;
              return (
                <button
                  key={c}
                  onClick={() => setCat(on ? null : c)}
                  className={`flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm ${on ? "bg-accent/10 font-medium text-accent" : "text-ink-2 hover:bg-surface-2"}`}
                >
                  <span className="truncate">{c}</span>
                  <span className="ml-auto text-[11px] text-ink-3">{n}</span>
                </button>
              );
            })}
          </CardBody>
        </Card>

        {/* clause list */}
        <div className="space-y-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search clauses, tags, or text…" className="pl-9" />
          </div>
          {filtered.length === 0 ? (
            <Card><CardBody><p className="text-sm text-ink-3">No clauses match.</p></CardBody></Card>
          ) : (
            filtered.map((c) => {
              const on = selected === c.id;
              return (
                <Card key={c.id} className={`cursor-pointer transition ${on ? "ring-1 ring-accent" : "hover:border-ink-3/30"}`}>
                  <CardBody onClick={() => setSelected(c.id)} className="space-y-2">
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-sm font-semibold text-ink">{c.title}</span>
                          {c.favorite && <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />}
                        </div>
                        <div className="text-[11px] text-ink-3">{c.category}</div>
                      </div>
                      <RiskPill risk={c.risk} />
                    </div>
                    <p className="line-clamp-2 text-xs leading-relaxed text-ink-2">{c.body}</p>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {c.approved ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
                          <BadgeCheck className="h-3 w-3" /> Approved
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                          <Shield className="h-3 w-3" /> Needs review
                        </span>
                      )}
                      {c.tags.map((t) => (
                        <span key={t} className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-ink-3">{t}</span>
                      ))}
                      <span className="ml-auto text-[10px] text-ink-3">used {c.usedCount}×</span>
                    </div>
                  </CardBody>
                </Card>
              );
            })
          )}
        </div>

        {/* detail / insert */}
        <div className="space-y-3">
          {current && (
            <Card className="lg:sticky lg:top-20">
              <CardBody className="space-y-3">
                <div>
                  <div className="flex items-center gap-1.5">
                    <h3 className="text-sm font-semibold text-ink">{current.title}</h3>
                    {current.favorite && <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-3">
                    <span>{current.category}</span>·<span>used {current.usedCount}×</span>
                    <RiskPill risk={current.risk} />
                  </div>
                </div>
                <div className="rounded-lg border border-line bg-surface-2 p-3 text-xs leading-relaxed text-ink">
                  {current.body}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" className="flex-1" onClick={() => insert(current)}>
                    {inserted === current.id ? <><Check className="h-3.5 w-3.5" /> Inserted</> : <><FileInput className="h-3.5 w-3.5" /> Insert into editor</>}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => copyBody(current)}>
                    {copied === current.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  </Button>
                </div>
                <div className="rounded-lg border border-dashed border-line p-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Playbook guidance</div>
                  <p className="mt-1 text-xs text-ink-2">
                    {current.risk === "preferred"
                      ? "This is our preferred position — use as-is. No approval needed."
                      : current.risk === "acceptable"
                        ? "Acceptable fallback. Flag to Legal if the counterparty pushes further."
                        : "Non-standard / fallback language. Requires Legal sign-off before sending."}
                  </p>
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      </div>

      {inserted && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-full bg-ink px-4 py-2 text-sm text-white shadow-lg">
          Clause inserted into the contract editor (preview)
        </div>
      )}
    </div>
  );
}
