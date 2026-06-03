"use client";

// Redlining / Track Changes — PROTOTYPE of inline tracked changes with accept/reject + comments.
// Shows insertions, deletions, and an author-attributed change list. Mockup: in-memory changes.
// Wires later into the Tiptap editor with a suggestions/marks extension.

import { useMemo, useState } from "react";
import { Check, Eye, FileText, MessageSquare, X } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody } from "@/components/ui";

type ChangeKind = "insert" | "delete";
type Change = { id: string; kind: ChangeKind; author: string; color: string; text: string; note?: string; status: "open" | "accepted" | "rejected" };

type Token =
  | { t: "text"; v: string }
  | { t: "change"; id: string };

// A short clause rendered as tokens; "change" tokens reference the changes below.
const DOC: Token[] = [
  { t: "text", v: "7. Limitation of Liability. Except for breaches of confidentiality, each party's aggregate liability shall not exceed the fees paid in the preceding " },
  { t: "change", id: "c1" }, // delete "twelve (12)"
  { t: "change", id: "c2" }, // insert "twenty-four (24)"
  { t: "text", v: " months. " },
  { t: "change", id: "c3" }, // insert sentence
  { t: "text", v: " Each party shall maintain insurance adequate to cover its obligations hereunder." },
];

const INITIAL: Change[] = [
  { id: "c1", kind: "delete", author: "Northwind", color: "#EF4444", text: "twelve (12)", status: "open" },
  { id: "c2", kind: "insert", author: "Northwind", color: "#3E7BFA", text: "twenty-four (24)", note: "Requesting a longer cap for data-breach events.", status: "open" },
  { id: "c3", kind: "insert", author: "Acme Legal", color: "#12B76A", text: "This cap shall not apply to a party's indemnification obligations.", status: "open" },
];

export default function RedlinePage() {
  const [changes, setChanges] = useState<Change[]>(INITIAL);
  const [view, setView] = useState<"markup" | "final" | "original">("markup");
  const [focus, setFocus] = useState<string | null>(null);

  const open = useMemo(() => changes.filter((c) => c.status === "open"), [changes]);

  function decide(id: string, status: "accepted" | "rejected") {
    setChanges((arr) => arr.map((c) => (c.id === id ? { ...c, status } : c)));
  }
  function decideAll(status: "accepted" | "rejected") {
    setChanges((arr) => arr.map((c) => (c.status === "open" ? { ...c, status } : c)));
  }

  function renderChange(c: Change) {
    // visibility rules by view + status
    const isAccepted = c.status === "accepted";
    const isRejected = c.status === "rejected";
    if (view === "original") {
      // show deletions as normal text, hide insertions
      return c.kind === "delete" ? <span>{c.text}</span> : null;
    }
    if (view === "final") {
      // show accepted insertions + non-deleted text; hide accepted deletions
      if (c.kind === "insert") return isRejected ? null : <span>{c.text}</span>;
      return isAccepted ? null : <span>{c.text}</span>; // deletion not yet accepted → text stays
    }
    // markup view
    const base = "rounded px-0.5";
    if (c.kind === "delete") {
      return (
        <span
          onClick={() => setFocus(c.id)}
          className={`${base} cursor-pointer line-through ${isAccepted ? "opacity-40" : ""}`}
          style={{ color: c.color, background: focus === c.id ? `${c.color}22` : undefined }}
        >
          {c.text}
        </span>
      );
    }
    return (
      <span
        onClick={() => setFocus(c.id)}
        className={`${base} cursor-pointer underline decoration-2 underline-offset-2 ${isRejected ? "opacity-40 line-through" : ""}`}
        style={{ color: c.color, background: focus === c.id ? `${c.color}22` : undefined }}
      >
        {c.text}
      </span>
    );
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Redlining <Badge tone="accent">Preview</Badge></span>}
        subtitle="Tracked changes with accept / reject and author attribution — collaborative redlines."
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => decideAll("rejected")} disabled={open.length === 0}><X className="h-3.5 w-3.5" /> Reject all</Button>
            <Button size="sm" onClick={() => decideAll("accepted")} disabled={open.length === 0}><Check className="h-3.5 w-3.5" /> Accept all</Button>
          </div>
        }
      />

      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_320px]">
        {/* document */}
        <Card>
          <CardBody className="space-y-4">
            <div className="flex items-center gap-1 rounded-lg border border-line bg-surface-2 p-0.5 text-sm">
              {([["markup", "Show markup"], ["final", "Final"], ["original", "Original"]] as const).map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition ${view === v ? "bg-white text-ink shadow-sm" : "text-ink-3 hover:text-ink"}`}
                >
                  <Eye className="h-3.5 w-3.5" /> {label}
                </button>
              ))}
            </div>
            <div className="rounded-lg border border-line bg-white p-6 text-[15px] leading-8 text-ink">
              <div className="mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-ink-3">
                <FileText className="h-3.5 w-3.5" /> Master Services Agreement · §7
              </div>
              <p>
                {DOC.map((tok, i) =>
                  tok.t === "text" ? (
                    <span key={i}>{tok.v}</span>
                  ) : (
                    <span key={i}>{renderChange(changes.find((c) => c.id === tok.id)!)}</span>
                  )
                )}
              </p>
            </div>
          </CardBody>
        </Card>

        {/* changes list */}
        <Card className="h-max lg:sticky lg:top-20">
          <CardBody className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-ink">Changes</div>
              <span className="text-xs text-ink-3">{open.length} open · {changes.length} total</span>
            </div>
            {changes.map((c) => (
              <div
                key={c.id}
                onClick={() => setFocus(c.id)}
                className={`rounded-lg border p-2.5 text-sm transition ${focus === c.id ? "border-accent" : "border-line"} ${c.status !== "open" ? "opacity-70" : ""}`}
              >
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color }} />
                  <span className="text-xs font-medium text-ink">{c.author}</span>
                  <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink-3">{c.kind}</span>
                  {c.status !== "open" && (
                    <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-medium ${c.status === "accepted" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{c.status}</span>
                  )}
                </div>
                <p className="mt-1 text-xs text-ink-2">
                  <span style={{ color: c.color }} className={c.kind === "delete" ? "line-through" : "underline"}>{c.text}</span>
                </p>
                {c.note && (
                  <p className="mt-1 flex items-start gap-1 text-[11px] text-ink-3">
                    <MessageSquare className="mt-0.5 h-3 w-3 shrink-0" /> {c.note}
                  </p>
                )}
                {c.status === "open" && (
                  <div className="mt-2 flex gap-1.5">
                    <button onClick={(e) => { e.stopPropagation(); decide(c.id, "accepted"); }} className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100">
                      <Check className="h-3 w-3" /> Accept
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); decide(c.id, "rejected"); }} className="inline-flex items-center gap-1 rounded-md bg-red-50 px-2 py-1 text-[11px] font-medium text-red-700 hover:bg-red-100">
                      <X className="h-3 w-3" /> Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
            {changes.length > 0 && open.length === 0 && (
              <p className="pt-1 text-center text-xs text-ink-3">All changes resolved.</p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
