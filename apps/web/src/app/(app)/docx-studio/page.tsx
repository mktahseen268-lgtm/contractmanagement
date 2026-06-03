"use client";

// DOCX / Word Import-Export — PROTOTYPE. Import a .docx (or PDF) and convert it to an editable
// contract with extracted metadata; export the contract back to Word/PDF with options. Mockup:
// simulated conversion. Wires later to a docx engine (e.g. python-docx / docx round-trip).

import { useState } from "react";
import { ArrowRight, Check, Download, FileDown, FileText, FileUp, Loader2, Settings2 } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";

type Stage = "idle" | "converting" | "done";

const EXTRACTED = [
  ["Type", "Master Services Agreement"],
  ["Counterparty", "Northwind Ltd"],
  ["Effective date", "2026-07-01"],
  ["Term", "24 months"],
  ["Value", "$120,000"],
  ["Governing law", "DIFC"],
];

export default function DocxStudioPage() {
  const [stage, setStage] = useState<Stage>("idle");
  const [fmt, setFmt] = useState<"docx" | "pdf">("docx");
  const [withRedlines, setWithRedlines] = useState(false);
  const [withWatermark, setWithWatermark] = useState(true);
  const [exported, setExported] = useState(false);

  function simulateImport() {
    setStage("converting");
    setTimeout(() => setStage("done"), 1400);
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Word Import / Export</span>}
        subtitle="Bring Word documents in as editable contracts, and export back to .docx or PDF."
      />

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* import */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-1.5"><FileUp className="h-4 w-4" /> Import</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            {stage === "idle" && (
              <button
                onClick={simulateImport}
                className="grid w-full place-items-center gap-2 rounded-xl border-2 border-dashed border-line bg-surface-2 py-10 text-center transition hover:border-accent"
              >
                <FileUp className="h-8 w-8 text-ink-3" />
                <div className="text-sm font-medium text-ink">Drop a .docx or .pdf here</div>
                <div className="text-[11px] text-ink-3">We convert it to an editable contract and extract the key terms</div>
              </button>
            )}
            {stage === "converting" && (
              <div className="grid place-items-center gap-2 rounded-xl border border-line bg-surface-2 py-10">
                <Loader2 className="h-7 w-7 animate-spin text-accent" />
                <div className="text-sm font-medium text-ink">Converting &ldquo;Northwind_MSA_v3.docx&rdquo;…</div>
                <div className="text-[11px] text-ink-3">Parsing styles · mapping clauses · extracting fields</div>
              </div>
            )}
            {stage === "done" && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  <Check className="h-4 w-4" /> Converted &mdash; 14 pages, 9 clauses detected
                </div>
                <div className="rounded-lg border border-line">
                  <div className="border-b border-line px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-3">Extracted metadata</div>
                  <div className="divide-y divide-line">
                    {EXTRACTED.map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between px-3 py-1.5 text-sm">
                        <span className="text-ink-3">{k}</span>
                        <span className="font-medium text-ink">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <Button className="w-full">
                  Open as editable contract <ArrowRight className="h-4 w-4" />
                </Button>
                <button onClick={() => setStage("idle")} className="w-full text-center text-xs text-ink-3 hover:underline">Import another</button>
              </div>
            )}
          </CardBody>
        </Card>

        {/* export */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-1.5"><FileDown className="h-4 w-4" /> Export</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">Format</label>
              <div className="flex gap-2">
                {([["docx", "Word (.docx)"], ["pdf", "PDF"]] as const).map(([v, label]) => (
                  <button
                    key={v}
                    onClick={() => setFmt(v)}
                    className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition ${fmt === v ? "border-accent bg-accent/5 font-medium text-accent" : "border-line text-ink-2 hover:bg-surface-2"}`}
                  >
                    <FileText className="h-4 w-4" /> {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2 rounded-lg border border-line p-3">
              <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                <Settings2 className="h-3.5 w-3.5" /> Options
              </div>
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={withRedlines} onChange={(e) => setWithRedlines(e.target.checked)} />
                Include tracked changes / redlines
              </label>
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={withWatermark} onChange={(e) => setWithWatermark(e.target.checked)} />
                Add &ldquo;DRAFT&rdquo; watermark (non-final statuses)
              </label>
            </div>

            <div className="rounded-lg border border-line bg-surface-2 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Preview</div>
              <div className="mt-1 text-sm text-ink-2">
                Northwind MSA → <span className="font-medium text-ink">{fmt === "docx" ? "Northwind_MSA.docx" : "Northwind_MSA.pdf"}</span>
                {withRedlines ? " · with redlines" : ""}{withWatermark ? " · watermarked" : ""}
              </div>
            </div>

            <Button className="w-full" onClick={() => { setExported(true); setTimeout(() => setExported(false), 1800); }}>
              {exported ? <><Check className="h-4 w-4" /> Exported</> : <><Download className="h-4 w-4" /> Export {fmt.toUpperCase()}</>}
            </Button>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
