"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileUp, Loader2, Sparkles } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, CardTitle, ConfidenceChip, ErrorBanner, Input } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { titleCase } from "@/lib/utils";
import type { ContractDetail, OcrJob } from "@/lib/types";

export default function IntelligencePage() {
  const router = useRouter();
  const [fileName, setFileName] = useState("Acme_MSA_signed.pdf");
  const [job, setJob] = useState<OcrJob | null>(null);
  const [scanning, setScanning] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  function poll(id: string, tries = 0) {
    pollRef.current = setTimeout(async () => {
      try {
        const j = await api.get<OcrJob>(`/ocr/jobs/${id}`);
        setJob(j);
        if (j.status === "completed" || j.status === "failed") {
          setScanning(false);
        } else if (tries < 40) {
          poll(id, tries + 1);
        } else {
          setScanning(false);
          setError("OCR is taking longer than expected — try again.");
        }
      } catch {
        setScanning(false);
        setError("Lost track of the OCR job.");
      }
    }, 1200);
  }

  async function scan(e: React.FormEvent) {
    e.preventDefault();
    setScanning(true);
    setError("");
    setJob(null);
    if (pollRef.current) clearTimeout(pollRef.current);
    try {
      const j = await api.post<OcrJob>("/ocr/jobs", { file_name: fileName.trim() || "scanned_contract.pdf" });
      setJob(j);
      if (j.status === "completed" || j.status === "failed") setScanning(false);
      else poll(j.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "OCR failed.");
      setScanning(false);
    }
  }

  async function createContract() {
    if (!job || job.status !== "completed") return;
    setCreating(true);
    setError("");
    try {
      const c = await api.post<ContractDetail>(`/ocr/jobs/${job.id}/create-contract`);
      router.push(`/contracts/${c.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the contract.");
      setCreating(false);
    }
  }

  const fields = job?.result?.fields ?? {};
  const done = job?.status === "completed";
  const processing = !!job && (job.status === "queued" || job.status === "processing");

  return (
    <div>
      <PageHeader title="Intelligence — OCR & AI" subtitle="Scan a document, review the extracted fields, then create a contract from it." />
      <div className="space-y-5 p-6">
        <ErrorBanner message={error} />

        {/* "upload" zone */}
        <Card className="ai-aurora border-ai-line/60">
          <CardBody>
            <form onSubmit={scan} className="flex flex-col items-center gap-4 py-6 text-center">
              <div className="grid h-14 w-14 place-items-center rounded-2xl bg-ai-bg text-ai">
                <FileUp className="h-7 w-7" />
              </div>
              <div>
                <div className="text-base font-semibold text-ink">Scan a contract</div>
                <div className="mt-1 max-w-lg text-sm text-ink-2">
                  Demo build: enter a file name and we'll queue an OCR job (Celery → Redis) that produces a realistic extraction.
                  The real pipeline runs OCR → layout → AI on the uploaded PDF.
                </div>
                <div className="mt-1 text-xs text-ink-3">✓ Arabic + English  ✓ tables  ✓ signatures &amp; stamps</div>
              </div>
              <div className="flex w-full max-w-md items-center gap-2">
                <Input value={fileName} onChange={(e) => setFileName(e.target.value)} placeholder="contract_scan.pdf" disabled={scanning} />
                <Button type="submit" loading={scanning}>
                  <Sparkles className="h-4 w-4" /> Scan
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>

        {processing && (
          <Card>
            <CardBody className="flex items-center gap-3 text-sm text-ink-2">
              <Loader2 className="h-4 w-4 animate-spin text-ai" />
              <span>
                {job?.status === "queued" ? "Queued for processing" : "Processing"} — {job?.file_name}
                {job?.progress ? ` (${job.progress}%)` : ""}…
              </span>
            </CardBody>
          </Card>
        )}

        {done && (
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-ai" /> Extracted fields — {job?.file_name}
                </CardTitle>
                <span className="text-xs text-ink-3">
                  {job?.result?.pages ?? "?"} pages · {(job?.result?.languages ?? ["en"]).join(", ")}
                </span>
              </CardHeader>
              <CardBody>
                <dl className="divide-y divide-line">
                  {Object.entries(fields).map(([key, fdef]) => (
                    <div key={key} className="flex items-center justify-between gap-4 py-2.5">
                      <dt className="text-sm text-ink-3">{titleCase(key)}</dt>
                      <dd className="flex items-center gap-2 text-sm font-medium text-ink">
                        <span>{String(fdef.value)}</span>
                        <ConfidenceChip value={fdef.confidence} />
                      </dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-4 flex justify-end">
                  <Button onClick={createContract} loading={creating} disabled={!!job?.created_contract_id}>
                    {job?.created_contract_id ? "Contract created" : "Create contract from this →"}
                  </Button>
                </div>
              </CardBody>
            </Card>
            <div className="space-y-5">
              <Card className="ai-aurora border-ai-line/60">
                <CardHeader className="border-ai-line/40">
                  <CardTitle className="flex items-center gap-1.5 text-ai">
                    <Sparkles className="h-4 w-4" /> AI summary
                  </CardTitle>
                </CardHeader>
                <CardBody className="text-sm text-ink-2">
                  {job?.result?.summary}
                  <p className="mt-3 text-[11px] text-ink-3">AI can be wrong — verify before relying.</p>
                </CardBody>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Detected clauses</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="flex flex-wrap gap-1.5">
                    {(job?.result?.detected_clauses ?? []).map((c) => (
                      <span key={c} className="rounded-full bg-surface-3 px-2 py-0.5 text-xs text-ink-2">
                        {c}
                      </span>
                    ))}
                  </div>
                  {job?.result?.tables_found ? <p className="mt-3 text-xs text-ink-3">{job.result.tables_found} table(s) found.</p> : null}
                  {job?.result?.risk_level && job.result.risk_level !== "low" && (
                    <p className="mt-2 text-xs text-amber-700">⚠ Overall risk: {titleCase(job.result.risk_level)} — review before activating.</p>
                  )}
                </CardBody>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
