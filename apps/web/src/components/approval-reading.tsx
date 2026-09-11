"use client";

/**
 * The two things an approver needs around the document itself.
 *
 * Someone arriving to approve has one question first — *what am I agreeing to?* — and the
 * answer was spread across the Overview tab, the header and the body text. They then have to
 * find the clause they care about in a twenty-section agreement by scrolling.
 *
 * So: the deal points in a strip above the document, and a list of its sections beside it.
 * Neither is new information. Both are the difference between reading an agreement and
 * hunting through one.
 */

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, List } from "lucide-react";
import type { ContractDetail } from "@/lib/types";
import { titleCase } from "@/lib/utils";

const RISK_TONE: Record<string, string> = {
  low: "text-ink-2",
  medium: "text-amber-700",
  high: "text-amber-800",
  critical: "text-danger",
};

function money(value: number, currency: string): string {
  if (!value) return "—";
  // No currency symbol lookup: PKR has no widely-recognised glyph, and a wrong symbol on a
  // contract value is worse than the ISO code.
  return `${currency} ${value.toLocaleString()}`;
}

function day(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined,
    { day: "numeric", month: "short", year: "numeric" });
}

function months(from: string | null, to: string | null): string {
  if (!from || !to) return "";
  const a = new Date(from);
  const b = new Date(to);
  const n = Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24 * 30.44));
  return n > 0 ? `${n} months` : "";
}

/** The deal points, so the reader does not have to reconstruct them from the prose. */
export function DealPoints({ contract }: { contract: ContractDetail }) {
  const term = months(contract.effective_date, contract.end_date);
  const items: { label: string; value: string; tone?: string }[] = [
    { label: "Counterparty", value: contract.counterparty || "—" },
    { label: "Value", value: money(contract.value, contract.currency) },
    {
      label: "Term",
      value: contract.effective_date
        ? `${day(contract.effective_date)} → ${day(contract.end_date)}${term ? ` · ${term}` : ""}`
        : "—",
    },
    { label: "Department", value: contract.department || "—" },
    {
      label: "Risk",
      value: titleCase(contract.risk_level || "—"),
      tone: RISK_TONE[contract.risk_level] ?? "text-ink-2",
    },
    { label: "Governing law", value: contract.governing_law || "—" },
  ];

  return (
    <div className="mb-4 rounded-lg border border-line bg-surface-2 px-4 py-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-3">
          What you are approving
        </span>
        <span className="text-xs text-ink-3">· {contract.reference_no}</span>
      </div>
      <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-3">
        {items.map((i) => (
          <div key={i.label}>
            <dt className="text-[11px] uppercase tracking-wide text-ink-3">{i.label}</dt>
            <dd className={`text-sm ${i.tone ?? "text-ink"}`}>{i.value}</dd>
          </div>
        ))}
      </dl>
      {contract.ai_summary && (
        <p className="mt-3 border-t border-line pt-2 text-xs text-ink-2">
          {contract.ai_summary}
        </p>
      )}
      {contract.risk_level === "critical" && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-danger">
          <AlertTriangle className="h-3.5 w-3.5" /> Marked critical risk — check the Policy tab
          before deciding.
        </p>
      )}
    </div>
  );
}

interface Section {
  id: string;
  text: string;
  level: number;
}

/** Section list built from the document's own headings. */
export function DocumentSections({
  body,
  containerRef,
}: {
  body: string;
  containerRef: React.RefObject<HTMLElement | null>;
}) {
  const [active, setActive] = useState("");

  const sections = useMemo<Section[]>(() => {
    const out: Section[] = [];
    for (const line of (body || "").split("\n")) {
      const m = /^(#{1,3})\s+(.*)$/.exec(line.trim());
      if (!m) continue;
      const text = m[2].replace(/[*_`]/g, "").trim();
      if (text) out.push({ id: `${out.length}`, text, level: m[1].length });
    }
    // A document with one heading has nothing worth navigating; the list would be noise.
    return out.length >= 3 ? out : [];
  }, [body]);

  // Headings rendered by the editor carry no ids, so matching is by text. Exact match rather
  // than fuzzy: jumping to the wrong clause is worse than the link doing nothing.
  function jump(section: Section) {
    const root = containerRef.current;
    if (!root) return;
    const headings = Array.from(root.querySelectorAll("h1, h2, h3"));
    const target = headings.find(
      (h) => (h.textContent || "").trim().toLowerCase() === section.text.toLowerCase(),
    );
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    setActive(section.id);
  }

  useEffect(() => setActive(""), [body]);

  if (!sections.length) return null;

  return (
    <nav aria-label="Sections" className="mb-4 rounded-lg border border-line bg-surface px-3 py-2">
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">
        <List className="h-3.5 w-3.5" /> Sections
      </div>
      <ul className="flex flex-wrap gap-x-1 gap-y-1">
        {sections.map((s) => (
          <li key={s.id}>
            <button
              onClick={() => jump(s)}
              className={`rounded px-2 py-0.5 text-xs transition-colors hover:bg-surface-2 ${
                active === s.id ? "bg-surface-2 text-accent" : "text-ink-2"
              } ${s.level > 2 ? "opacity-70" : ""}`}
            >
              {s.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
