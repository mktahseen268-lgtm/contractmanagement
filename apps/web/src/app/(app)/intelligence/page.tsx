"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, FileUp, Loader2, Sparkles, Upload } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, CardTitle, ConfidenceChip, ErrorBanner, Input } from "@/components/ui";
import { PageHeader } from "@/components/shell";
import { titleCase } from "@/lib/utils";
import type { ContractDetail, OcrJob } from "@/lib/types";

export default function IntelligencePage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("Acme_MSA_signed.pdf"); // demo fallback when no file picked
  const [job, setJob] = useState<OcrJob | null>(null);
  const [scanning, setScanning] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  function poll(id: string, tries = 0) {
    pollRef.current = setTimeout(async () => {
      try {
        const j = await api.get<OcrJob>(`/ocr/jobs/${id}`);
        setJob(j);
        if (j.status === "completed" || j.status === "failed") setScanning(false);
        else if (tries < 40) poll(id, tries + 1);
        else { setScanning(false); setError("OCR is taking longer than expected — try again."); }
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
      const fd = new FormData();
      if (file) fd.append("file", file);
      else fd.append("file_name", fileName.trim() || "scanned_contract.pdf");
      const j = await api.postForm<OcrJob>("/ocr/jobs", fd);
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

  async function openSourceDoc(fileId: string) {
    try {
      const blob = await api.blob(`/files/${fileId}/download`);
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
    } catch {
      setError("Couldn't open the document.");
    }
  }

  function pickFile(f: File | null) {
    setFile(f);
    if (f) setFileName(f.name);
  }

  const fields = job?.result?.fields ?? {};
  const done = job?.status === "completed";
  const processing = !!job && (job.status === "queued" || job.status === "processing");
  const sourceFileId = job?.result?.source_file_id ?? null;

  return (
    <div>
      <PageHeader title="Intelligence — OCR & AI" subtitle="Upload a document, review the extracted fields, then create a contract from it." />
      <div className="space-y-5 p-6">
        <ErrorBanner message={error} />

        {/* upload zone */}
        <Card className="ai-aurora border-ai-line/60">
          <CardBody>
            <form onSubmit={scan} className="flex flex-col items-center gap-4 py-2 text-center">
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,application/pdf,image/*"
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
              />
              <div
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files?.[0] ?? null); }}
                className={`flex w-full max-w-xl cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-8 transition-colors ${dragOver ? "border-ai bg-ai-bg/60" : "border-ai-line/70 hover:bg-ai-bg/40"}`}
              >
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-ai-bg text-ai">
                  {file ? <FileText className="h-6 w-6" /> : <Upload className="h-6 w-6" />}
                </span>
                {file ? (
                  <div>
                    <div className="text-sm font-semibold text-ink">{file.name}</div>
                    <div className="text-xs text-ink-3">{(file.size / 1024).toFixed(0)} KB · click to choose a different file</div>
                  </div>
                ) : (
                  <div>
                    <div className="text-sm font-semibold text-ink">Drop a contract here, or click to browse</div>
                    <div className="mt-0.5 text-xs text-ink-3">PDF, PNG, JPG, TIFF · up to 50 MB · ✓ Arabic + English ✓ tables ✓ signatures &amp; stamps</div>
                  </div>
                )}
              </div>
              <div className="flex w-full max-w-xl items-center gap-2">
                <div className="flex-1 text-left">
                  <span className="mr-2 text-xs text-ink-3">or use a sample file name (demo, no upload):</span>
                  <Input value={fileName} onChange={(e) => { setFileName(e.target.value); setFile(null); }} className="mt-1 h-9" disabled={scanning} />
                </div>
                <Button type="submit" loading={scanning} className="self-end">
                  <Sparkles className="h-4 w-4" /> Scan
                </Button>
              </div>
              <p className="text-xs text-ink-3">
                Real files are stored in S3-compatible object storage (MinIO in Docker; a local-filesystem fallback otherwise) and OCR runs as a Celery job. The extraction is a realistic stub — see docs/09.
              </p>
            </form>
          </CardBody>
        </Card>

        {processing && (
          <Card>
            <CardBody className="flex items-center gap-3 text-sm text-ink-2">
              <Loader2 className="h-4 w-4 animate-spin text-ai" />
              <span>{job?.status === "queued" ? "Queued for processing" : "Processing"} — {job?.file_name}{job?.progress ? ` (${job.progress}%)` : ""}…</span>
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
                <div className="flex items-center gap-3">
                  {sourceFileId && (
                    <button onClick={() => openSourceDoc(sourceFileId)} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                      <FileUp className="h-3.5 w-3.5" /> Open uploaded document
                    </button>
                  )}
                  <span className="text-xs text-ink-3">{job?.result?.pages ?? "?"} pages · {(job?.result?.languages ?? ["en"]).join(", ")}</span>
                </div>
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
                  <CardTitle className="flex items-center gap-1.5 text-ai"><Sparkles className="h-4 w-4" /> AI summary</CardTitle>
                </CardHeader>
                <CardBody className="text-sm text-ink-2">
                  {job?.result?.summary}
                  <p className="mt-3 text-[11px] text-ink-3">AI can be wrong — verify before relying.</p>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Detected clauses</CardTitle></CardHeader>
                <CardBody>
                  <div className="flex flex-wrap gap-1.5">
                    {(job?.result?.detected_clauses ?? []).map((c) => (
                      <span key={c} className="rounded-full bg-surface-3 px-2 py-0.5 text-xs text-ink-2">{c}</span>
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
