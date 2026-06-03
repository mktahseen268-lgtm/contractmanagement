"use client";

// Full-text Search — PROTOTYPE of search across the contract *body* (not just metadata).
// Today's product matches with ILIKE on title/ref; this previews tsvector-style ranked results
// with highlighted snippets from inside the document text + clauses. Mockup: sample corpus +
// client-side matching. Wires later to a Postgres tsvector / FTS index.

import { useMemo, useState } from "react";
import { FileText, Filter, Search as SearchIcon, Sparkles } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/shell";
import { Badge, Card, CardBody, Input } from "@/components/ui";
import { statusMeta } from "@/lib/utils";

type Hit = {
  id: string;
  ref: string;
  title: string;
  type: string;
  status: string;
  counterparty: string;
  matchedIn: "Document body" | "Clause" | "Title" | "Metadata";
  snippet: string; // contains <<...>> around the term to highlight
};

const CORPUS: Hit[] = [
  {
    id: "a", ref: "C-2026-0012", title: "Northwind Master Services Agreement", type: "MSA", status: "active", counterparty: "Northwind Ltd",
    matchedIn: "Document body",
    snippet: "…each party's total aggregate <<liability>> arising out of this Agreement shall not exceed the fees paid in the preceding twelve months…",
  },
  {
    id: "b", ref: "C-2026-0033", title: "Lumen Labs Reseller Agreement", type: "Vendor", status: "out_for_signature", counterparty: "Lumen Labs",
    matchedIn: "Clause",
    snippet: "…Limitation of <<Liability>>: neither party shall be liable for indirect, incidental, or consequential damages…",
  },
  {
    id: "c", ref: "C-2025-0119", title: "Platform Inc Data Processing Addendum", type: "Service", status: "signed", counterparty: "Platform Inc",
    matchedIn: "Document body",
    snippet: "…Provider shall <<indemnify>> Customer against third-party claims arising from a breach of its data-protection obligations…",
  },
  {
    id: "d", ref: "C-2026-0007", title: "Acme ↔ ThiqaTech NDA", type: "NDA", status: "active", counterparty: "ThiqaTech",
    matchedIn: "Document body",
    snippet: "…the <<confidentiality>> obligations shall survive termination of this Agreement for a period of five (5) years…",
  },
  {
    id: "e", ref: "C-2026-0041", title: "Trial Co Subscription Order", type: "Service", status: "draft", counterparty: "Trial Co",
    matchedIn: "Clause",
    snippet: "…governed by the laws of the <<DIFC>>; disputes resolved by arbitration under the DIFC-LCIA Rules…",
  },
];

const SUGGESTED = ["liability cap", "indemnify", "confidentiality", "auto-renewal", "governing law DIFC", "termination for convenience"];

function highlight(snippet: string) {
  // split on <<...>> markers and wrap the inner text in a styled mark
  const parts = snippet.split(/<<(.+?)>>/g);
  return parts.map((p, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded bg-amber-100 px-0.5 font-medium text-amber-900">{p}</mark>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

export default function SearchPage() {
  const [q, setQ] = useState("liability");
  const [inBody, setInBody] = useState(true);

  const results = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n) return [];
    return CORPUS.filter((h) => {
      if (!inBody && (h.matchedIn === "Document body" || h.matchedIn === "Clause")) return false;
      return (
        h.snippet.toLowerCase().includes(n) ||
        h.title.toLowerCase().includes(n) ||
        h.counterparty.toLowerCase().includes(n) ||
        // loose match so the demo always shows something for the suggested terms
        n.split(" ").some((w) => h.snippet.toLowerCase().includes(w))
      );
    });
  }, [q, inBody]);

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Search <Badge tone="accent">Preview</Badge></span>}
        subtitle="Ranked full-text search across contract bodies and clauses — not just titles."
      />

      <div className="mx-auto max-w-3xl space-y-4 p-4">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-3" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search inside contracts — clauses, terms, parties…"
            className="h-12 pl-11 text-base"
            autoFocus
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1.5 text-sm text-ink-2">
            <input type="checkbox" checked={inBody} onChange={(e) => setInBody(e.target.checked)} />
            <Sparkles className="h-3.5 w-3.5 text-accent" /> Search inside document text
          </label>
          <span className="text-ink-3">·</span>
          <span className="text-xs text-ink-3">Try:</span>
          {SUGGESTED.map((s) => (
            <button key={s} onClick={() => setQ(s)} className="rounded-full border border-line bg-white px-2.5 py-1 text-xs text-ink-2 hover:border-accent hover:text-accent">
              {s}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between text-xs text-ink-3">
          <span>{results.length} result{results.length === 1 ? "" : "s"} for &ldquo;{q}&rdquo;</span>
          <span className="inline-flex items-center gap-1"><Filter className="h-3 w-3" /> Ranked by relevance</span>
        </div>

        <div className="space-y-3">
          {results.length === 0 ? (
            <Card><CardBody><p className="text-sm text-ink-3">No matches. Try a clause term like &ldquo;indemnify&rdquo; or &ldquo;confidentiality&rdquo;.</p></CardBody></Card>
          ) : (
            results.map((h) => (
              <Card key={h.id} className="transition hover:border-ink-3/30">
                <CardBody className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0 text-ink-3" />
                    <Link href={`/contracts/${h.id}`} className="truncate text-sm font-semibold text-ink hover:text-accent">{h.title}</Link>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusMeta(h.status).pill}`}>{statusMeta(h.status).label}</span>
                  </div>
                  <div className="text-[11px] text-ink-3">
                    {h.ref} · {h.type} · {h.counterparty}
                    <span className="ml-2 rounded bg-surface-2 px-1.5 py-0.5 font-medium text-ink-2">matched in {h.matchedIn}</span>
                  </div>
                  <p className="text-sm leading-relaxed text-ink-2">{highlight(h.snippet)}</p>
                </CardBody>
              </Card>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
