"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, FileText, Loader2, Lock, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";
import type { SigningInfo } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SignPage() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<SigningInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fullName, setFullName] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showConsent, setShowConsent] = useState(false);
  const [declineMode, setDeclineMode] = useState(false);
  const [declineReason, setDeclineReason] = useState("");

  useEffect(() => {
    api
      .post<SigningInfo>(`/sign/${token}/view`)
      .then((d) => {
        setInfo(d);
        if (d.recipient_name && !fullName) setFullName(d.recipient_name);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't open this signing link."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function sign() {
    if (!consent || !fullName.trim()) return;
    setBusy(true);
    setError("");
    try {
      setInfo(await api.post<SigningInfo>(`/sign/${token}/sign`, { full_name: fullName.trim(), consent: true }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't record your signature.");
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    setBusy(true);
    setError("");
    try {
      setInfo(await api.post<SigningInfo>(`/sign/${token}/decline`, { reason: declineReason.trim() }));
      setDeclineMode(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't record your response.");
    } finally {
      setBusy(false);
    }
  }

  const docUrl = info?.valid ? `${API}${info.document_path}` : "";

  return (
    <div className="flex min-h-screen flex-col items-center px-4 py-8">
      <div className="mb-4 flex items-center gap-1.5 text-sm text-ink-3">
        <Lock className="h-3.5 w-3.5" /> Secure signing{info?.org_name ? ` · ${info.org_name}` : ""}
      </div>
      <Card className="w-full max-w-lg">
        <CardBody className="space-y-4">
          {loading && (
            <div className="flex items-center justify-center gap-2 py-8 text-ink-3">
              <Loader2 className="h-5 w-5 animate-spin" /> Loading…
            </div>
          )}

          {!loading && (!info || !info.valid) && (
            <div className="py-6 text-center">
              <ShieldCheck className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">This signing link isn&rsquo;t active</div>
              <p className="mt-1 text-sm text-ink-2">
                {info?.reason === "revoked"
                  ? "The request was withdrawn by the sender."
                  : "It may have expired or been replaced. Please contact the person who sent it."}
              </p>
              {error && <ErrorBanner message={error} className="mt-3 text-left" />}
            </div>
          )}

          {!loading && info && info.valid && (
            <>
              {error && <ErrorBanner message={error} />}
              <div>
                <h1 className="text-lg font-semibold text-ink">Review &amp; sign</h1>
                <p className="mt-0.5 text-sm text-ink-2">
                  <span className="font-medium text-ink">{info.org_name}</span> asked you to sign{" "}
                  <span className="font-medium text-ink">{info.contract_title}</span>
                  {info.contract_reference ? ` (${info.contract_reference})` : ""}
                  {info.sender_name ? ` · sent by ${info.sender_name}` : ""}.
                </p>
              </div>
              {info.message && <div className="rounded-md bg-surface-2 px-3 py-2 text-sm text-ink-2">&ldquo;{info.message}&rdquo;</div>}

              <a href={docUrl} target="_blank" rel="noopener noreferrer">
                <Button variant="secondary" className="w-full">
                  <FileText className="h-4 w-4" /> Review the document
                </Button>
              </a>

              {info.can_sign && !declineMode && (
                <div className="space-y-3 rounded-lg border border-line bg-surface-2 p-4">
                  <label className="flex items-start gap-2 text-sm text-ink-2">
                    <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5" />
                    <span>
                      I agree to use electronic records and signatures.{" "}
                      <button type="button" onClick={() => setShowConsent((s) => !s)} className="text-accent hover:underline">
                        {showConsent ? "hide" : "details"}
                      </button>
                    </span>
                  </label>
                  {showConsent && <p className="rounded-md bg-white px-3 py-2 text-xs text-ink-3">{info.consent_text}</p>}
                  <Field label="Your full name — this is your signature">
                    <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Doe" />
                  </Field>
                  <div className="rounded-md bg-white px-3 py-2">
                    <span className="font-mono text-[10px] uppercase tracking-wide text-ink-3">Signature preview</span>
                    <div className="mt-0.5 text-2xl font-bold italic text-ink">/s/&nbsp;{fullName.trim() || "—"}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button onClick={sign} loading={busy} disabled={!consent || !fullName.trim()}>
                      <CheckCircle2 className="h-4 w-4" /> I agree &amp; sign
                    </Button>
                    <button onClick={() => setDeclineMode(true)} className="text-sm text-ink-3 hover:text-danger hover:underline">
                      Decline to sign
                    </button>
                  </div>
                </div>
              )}

              {info.can_sign && declineMode && (
                <div className="space-y-2 rounded-lg border border-line bg-surface-2 p-4">
                  <Field label="Reason for declining (optional, shared with the sender)">
                    <Input value={declineReason} onChange={(e) => setDeclineReason(e.target.value)} placeholder="e.g. the term length needs to change" />
                  </Field>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={decline} loading={busy}>
                      Confirm decline
                    </Button>
                    <Button variant="ghost" onClick={() => setDeclineMode(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {!info.can_sign && (
                <div className="rounded-lg border border-line bg-surface-2 p-4">
                  {info.recipient_status === "signed" ? (
                    <div className="flex items-start gap-2 text-sm text-ink-2">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
                      <div>
                        <div className="font-medium text-ink">You&rsquo;ve signed.</div>
                        {info.envelope_status === "completed" ? (
                          <p>This agreement is now fully executed.</p>
                        ) : (
                          <p>We&rsquo;ll email you the executed copy once everyone has signed.</p>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-ink-2">{info.waiting_reason || "There's nothing for you to do right now."}</p>
                  )}
                  {info.envelope_status === "completed" && (
                    <a href={docUrl} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block">
                      <Button variant="secondary" size="sm">
                        <FileText className="h-3.5 w-3.5" /> Download the executed copy
                      </Button>
                    </a>
                  )}
                </div>
              )}
            </>
          )}
        </CardBody>
      </Card>
      <p className="mt-4 text-xs text-ink-3">Powered by Contract Management · this link is unique to you — please don&rsquo;t forward it.</p>
    </div>
  );
}
