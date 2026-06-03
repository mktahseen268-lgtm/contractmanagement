"use client";

// AI Risk & Clause Analysis — PROTOTYPE. Runs an LLM review of a contract: overall risk score,
// flagged clauses by severity, missing-clause warnings, and extracted obligations. Mockup:
// canned analysis + a simulated "Analyze" run. Wires later to the OCR/AI provider seam (Claude).

import { useState } from "react";
import { AlertTriangle, CheckCircle2, FileSearch, Loader2, ShieldAlert, Sparkles, TriangleAlert } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";

type Sev = "high" | "medium" | "low";
type Finding = { id: string; clause: string; severity: Sev; issue: string; suggestion: string };

const SEV: Record<Sev, { label: string; pill: string; dot: string }> = {
  high: { label: "High", pill: "bg-red-50 text-red-700", dot: "#EF4444" },
  medium: { label: "Medium", pill: "bg-amber-50 text-amber-700", dot: "#F59E0B" },
  low: { label: "Low", pill: "bg-emerald-50 text-emerald-700", dot: "#12B76A" },
};

const FINDINGS: Finding[] = [
  { id: "f1", clause: "§7 Limitation of Liability", severity: "high", issue: "Liability is uncapped for data-breach events — unlimited exposure.", suggestion: "Add a super-cap (e.g. 2× annual fees) for data-breach claims rather than unlimited." },
  { id: "f2", clause: "§3 Payment Terms", severity: "medium", issue: "Net-60 payment terms exceed your standard Net-30 policy.", suggestion: "Negotiate to Net-30, or add late-payment interest at 1.5%/month." },
  { id: "f3", clause: "§11 Auto-Renewal", severity: "medium", issue: "Auto-renews for successive 12-month terms with 90-day notice — long lock-in.", suggestion: "Shorten the non-renewal notice window to 30 days." },
  { id: "f4", clause: "§9 Governing Law", severity: "low", issue: "Governing law is DIFC — acceptable, matches your preferred jurisdiction.", suggestion: "No change needed." },
];

const MISSING = [
  "Force Majeure clause not found",
  "Data Processing Addendum (GDPR) not referenced",
  "Assignment / change-of-control clause missing",
];

const OBLIGATIONS = [
  { who: "You", what: "Pay first invoice", due: "Within 30 days of effective date" },
  { who: "Provider", what: "Deliver onboarding plan", due: "10 business days after signing" },
  { who: "You", what: "Renewal decision", due: "90 days before term end (2027-03-31)" },
];

export default function AiAnalysisPage() {
  const [state, setState] = useState<"idle" | "running" | "done">("done");

  function run() {
    setState("running");
    setTimeout(() => setState("done"), 1600);
  }

  const score = 62; // /100 — higher = riskier
  const highN = FINDINGS.filter((f) => f.severity === "high").length;

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">AI Risk Analysis <Badge tone="accent">Preview</Badge></span>}
        subtitle="LLM review of a contract — risk score, flagged clauses, missing terms, extracted obligations."
        actions={<Button size="sm" onClick={run} disabled={state === "running"}><Sparkles className="h-3.5 w-3.5" /> {state === "running" ? "Analyzing…" : "Re-analyze"}</Button>}
      />

      <div className="p-4">
        <div className="mb-3 flex items-center gap-2 text-sm text-ink-3">
          <FileSearch className="h-4 w-4" /> Analyzing <span className="font-medium text-ink-2">Northwind Master Services Agreement (C-2026-0012)</span>
        </div>

        {state === "running" ? (
          <Card><CardBody className="grid place-items-center gap-2 py-16">
            <Loader2 className="h-8 w-8 animate-spin text-accent" />
            <div className="text-sm font-medium text-ink">Reading the document &amp; assessing risk…</div>
          </CardBody></Card>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
            {/* score + summary */}
            <div className="space-y-4">
              <Card>
                <CardBody className="text-center">
                  <RiskGauge score={score} />
                  <div className="mt-2 text-sm font-medium text-ink">Moderate–High risk</div>
                  <div className="text-[11px] text-ink-3">{highN} high-severity finding{highN === 1 ? "" : "s"} · review before signing</div>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle className="flex items-center gap-1.5"><TriangleAlert className="h-4 w-4" /> Missing clauses</CardTitle></CardHeader>
                <CardBody className="space-y-1.5">
                  {MISSING.map((m) => (
                    <div key={m} className="flex items-start gap-2 text-sm text-ink-2">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" /> {m}
                    </div>
                  ))}
                </CardBody>
              </Card>
            </div>

            {/* findings + obligations */}
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-1.5"><ShieldAlert className="h-4 w-4" /> Flagged clauses</CardTitle>
                  <span className="text-xs text-ink-3">{FINDINGS.length} findings</span>
                </CardHeader>
                <CardBody className="space-y-2.5">
                  {FINDINGS.map((f) => (
                    <div key={f.id} className="rounded-lg border border-line p-3">
                      <div className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: SEV[f.severity].dot }} />
                        <span className="text-sm font-semibold text-ink">{f.clause}</span>
                        <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold ${SEV[f.severity].pill}`}>{SEV[f.severity].label}</span>
                      </div>
                      <p className="mt-1.5 text-sm text-ink-2">{f.issue}</p>
                      <div className="mt-1.5 flex items-start gap-1.5 rounded-md bg-accent/5 px-2.5 py-1.5 text-[13px] text-ink-2">
                        <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                        <span><span className="font-medium text-ink">Suggestion:</span> {f.suggestion}</span>
                      </div>
                    </div>
                  ))}
                </CardBody>
              </Card>

              <Card>
                <CardHeader><CardTitle className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" /> Extracted obligations</CardTitle></CardHeader>
                <CardBody className="p-0">
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-line">
                      {OBLIGATIONS.map((o, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2"><span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-ink-2">{o.who}</span></td>
                          <td className="px-3 py-2 font-medium text-ink">{o.what}</td>
                          <td className="px-3 py-2 text-right text-[12px] text-ink-3">{o.due}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">These can be added to the contract's Obligations tab with one click.</div>
                </CardBody>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function RiskGauge({ score }: { score: number }) {
  // semicircular gauge, green→amber→red. score 0..100.
  const r = 52;
  const c = Math.PI * r; // half-circumference
  const dash = (score / 100) * c;
  const color = score >= 66 ? "#EF4444" : score >= 40 ? "#F59E0B" : "#12B76A";
  return (
    <div className="relative mx-auto h-[80px] w-[140px]">
      <svg viewBox="0 0 140 80" className="h-full w-full">
        <path d="M14 74 A52 52 0 0 1 126 74" fill="none" stroke="#E6E8EB" strokeWidth="12" strokeLinecap="round" />
        <path d="M14 74 A52 52 0 0 1 126 74" fill="none" stroke={color} strokeWidth="12" strokeLinecap="round" strokeDasharray={`${dash} ${c}`} />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="text-2xl font-bold tnum" style={{ color }}>{score}</div>
        <div className="-mt-1 text-[10px] uppercase tracking-wide text-ink-3">risk / 100</div>
      </div>
    </div>
  );
}
