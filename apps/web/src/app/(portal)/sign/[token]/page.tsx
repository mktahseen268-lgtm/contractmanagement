"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, Eraser, FileText, Loader2, Lock, PenLine, ShieldCheck, Type as TypeIcon, Upload } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { LocaleSwitch } from "@/components/locale-switch";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";
import type { SigningInfo } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

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
  const [tabFills, setTabFills] = useState<Record<string, string>>({});
  // How the signer adopts their mark. Backend values: typed | drawn | uploaded.
  const [sigMode, setSigMode] = useState<"typed" | "drawn" | "uploaded">("typed");
  const [sigImage, setSigImage] = useState("");        // base64 PNG/JPEG data URL for drawn/uploaded
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const lastPtRef = useRef<{ x: number; y: number } | null>(null);
  const [hasDrawing, setHasDrawing] = useState(false);

  const { t, dir } = useI18n();

  /**
   * Assisted mode (Phase 9, item 7) — the branch-tablet path.
   *
   * Same flow, same evidence, different presentation: larger text, larger targets, and one step
   * at a time so the person is never looking at four decisions at once. Nothing is skipped or
   * pre-agreed — a "simplified" signing that quietly agrees on somebody's behalf is not
   * simplification, it is a defect in the consent record.
   *
   * Entered by the toggle, or by `?assisted=1` so a branch tablet can be bookmarked straight
   * into it and staff never have to remember to switch it on.
   */
  const [assisted, setAssisted] = useState(false);
  const [step, setStep] = useState(0);
  const [opened, setOpened] = useState(false);   // did they actually open the document?

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("assisted") === "1") setAssisted(true);
  }, []);

  // Two steps, not three. The name, the consent tick and the signature belong together — they
  // are one decision, and splitting them across screens makes somebody agree on one page to
  // something they sign on another. A stepper that shows more steps than the flow has is a
  // progress bar that lies.
  const STEPS = [t("sign.review"), t("sign.sign")];

  /** In assisted mode a section is shown only on its own step; otherwise everything is shown. */
  const showStep = useCallback(
    (index: number) => !assisted || step === index,
    [assisted, step],
  );

  function canvasPos(e: React.PointerEvent<HTMLCanvasElement>) {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return { x: (e.clientX - r.left) * (c.width / r.width), y: (e.clientY - r.top) * (c.height / r.height) };
  }
  function startDraw(e: React.PointerEvent<HTMLCanvasElement>) {
    drawingRef.current = true;
    lastPtRef.current = canvasPos(e);
    try { (e.target as Element).setPointerCapture(e.pointerId); } catch { /* noop */ }
  }
  function moveDraw(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx || !lastPtRef.current) return;
    const p = canvasPos(e);
    ctx.strokeStyle = "#0F1729";
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(lastPtRef.current.x, lastPtRef.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    lastPtRef.current = p;
    setHasDrawing(true);
  }
  function endDraw() {
    if (drawingRef.current && hasDrawing && canvasRef.current) {
      setSigImage(canvasRef.current.toDataURL("image/png"));
    }
    drawingRef.current = false;
    lastPtRef.current = null;
  }
  function clearCanvas() {
    const c = canvasRef.current;
    if (c) c.getContext("2d")?.clearRect(0, 0, c.width, c.height);
    setHasDrawing(false);
    setSigImage("");
  }
  function onUploadFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError("");
    if (!["image/png", "image/jpeg"].includes(f.type)) {
      setError("Please upload a PNG or JPEG image.");
      return;
    }
    if (f.size > 1_000_000) {
      setError("Signature image must be under 1 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setSigImage(typeof reader.result === "string" ? reader.result : "");
    reader.readAsDataURL(f);
  }

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

  const sigReady = sigMode === "typed" ? !!fullName.trim() : !!sigImage;

  async function sign() {
    if (!consent || !fullName.trim() || !sigReady) return;
    setBusy(true);
    setError("");
    try {
      const fills = Object.entries(tabFills).map(([tab_id, value]) => ({ tab_id, value }));
      const body: Record<string, unknown> = { full_name: fullName.trim(), consent: true, tab_fills: fills, signature_kind: sigMode };
      if (sigMode !== "typed") body.signature_image = sigImage;
      setInfo(await api.post<SigningInfo>(`/sign/${token}/sign`, body));
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

  const canFinish = consent && !!fullName.trim() && sigReady;

  return (
    <div
      dir={dir}
      className={
        // Assisted mode scales the whole subtree with one class rather than touching every
        // element: `text-lg` cascades, and the buttons below key their padding off `assisted`.
        "flex min-h-screen flex-col items-center px-4 py-8 " +
        (assisted ? "text-lg leading-relaxed" : "")
      }
    >
      <div className="mb-3 flex w-full max-w-lg flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-sm text-ink-3">
          <Lock className="h-3.5 w-3.5" aria-hidden="true" /> Secure signing
          {info?.org_name ? ` · ${info.org_name}` : ""}
        </span>
        <div className="flex items-center gap-3">
          <LocaleSwitch />
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink-2">
            <input
              type="checkbox"
              checked={assisted}
              onChange={(e) => {
                setAssisted(e.target.checked);
                setStep(0);
              }}
              className="h-4 w-4"
            />
            {t("sign.assisted")}
          </label>
        </div>
      </div>

      {assisted && info?.valid && info.can_sign && (
        <div className="mb-3 w-full max-w-lg">
          <ol className="flex items-center gap-2" aria-label={t("sign.step", { n: step + 1, total: STEPS.length })}>
            {STEPS.map((label, i) => (
              <li key={label} className="flex flex-1 items-center gap-2">
                <span
                  aria-current={i === step ? "step" : undefined}
                  className={
                    "flex h-11 flex-1 items-center justify-center gap-2 rounded-lg px-3 text-base font-medium " +
                    (i < step
                      ? "bg-accent-subtle text-accent"
                      : i === step
                        ? "bg-accent text-white"
                        : "bg-surface-3 text-ink-3")
                  }
                >
                  <span className="grid h-6 w-6 place-items-center rounded-full bg-white/25 text-sm">
                    {i + 1}
                  </span>
                  {label}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-2 text-sm text-ink-2">{t("sign.help")}</p>
        </div>
      )}

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

              {showStep(0) && (
                <>
                  <a
                    href={docUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setOpened(true)}
                  >
                    <Button
                      variant="secondary"
                      className={assisted ? "h-14 w-full text-lg" : "w-full"}
                    >
                      <FileText className="h-4 w-4" aria-hidden="true" /> {t("sign.review")}
                    </Button>
                  </a>
                  {assisted && (
                    <>
                      <p className="text-base text-ink-2">
                        Open the agreement and read it. Take as long as you need — nothing is
                        signed until you press the button on the last step.
                      </p>
                      {!opened && (
                        <p className="text-sm text-amber-700">
                          Please open the agreement before continuing. Signing something you have
                          not read is exactly what this step exists to prevent.
                        </p>
                      )}
                      <a
                        href={`/sign/${token}/guide`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block text-base text-accent underline underline-offset-2"
                      >
                        Printable step-by-step guide
                      </a>
                    </>
                  )}
                </>
              )}

              {info.can_sign && !declineMode && !showStep(0) && (
                <div className="space-y-3 rounded-lg border border-line bg-surface-2 p-4">
                  <label className={assisted ? "flex items-start gap-3 text-base text-ink-2" : "flex items-start gap-2 text-sm text-ink-2"}>
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                      className={assisted ? "mt-1 h-5 w-5" : "mt-0.5"}
                    />
                    <span>
                      I agree to use electronic records and signatures.{" "}
                      <button type="button" onClick={() => setShowConsent((s) => !s)} className="text-accent hover:underline">
                        {showConsent ? "hide" : "details"}
                      </button>
                    </span>
                  </label>
                  {showConsent && <p className="rounded-md bg-white px-3 py-2 text-xs text-ink-3">{info.consent_text}</p>}
                  <Field label="Your full legal name">
                    <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Doe" />
                  </Field>

                  {/* signature adoption: type / draw / upload */}
                  <div>
                    <div className="mb-2 inline-flex rounded-lg border border-line bg-white p-0.5 text-sm">
                      {([
                        { key: "typed", label: "Type", icon: TypeIcon },
                        { key: "drawn", label: "Draw", icon: PenLine },
                        { key: "uploaded", label: "Upload", icon: Upload },
                      ] as const).map((m) => {
                        const active = sigMode === m.key;
                        const Icon = m.icon;
                        return (
                          <button
                            key={m.key}
                            type="button"
                            onClick={() => setSigMode(m.key)}
                            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition ${active ? "bg-accent text-white" : "text-ink-2 hover:text-ink"}`}
                          >
                            <Icon className="h-3.5 w-3.5" /> {m.label}
                          </button>
                        );
                      })}
                    </div>

                    {sigMode === "typed" && (
                      <div className="rounded-md bg-white px-3 py-2">
                        <span className="font-mono text-[10px] uppercase tracking-wide text-ink-3">Signature preview</span>
                        <div className="mt-0.5 text-2xl font-bold italic text-ink">/s/&nbsp;{fullName.trim() || "—"}</div>
                      </div>
                    )}

                    {sigMode === "drawn" && (
                      <div className="rounded-md bg-white p-3">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="font-mono text-[10px] uppercase tracking-wide text-ink-3">Draw your signature</span>
                          <button type="button" onClick={clearCanvas} className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-danger">
                            <Eraser className="h-3 w-3" /> Clear
                          </button>
                        </div>
                        <canvas
                          ref={canvasRef}
                          width={560}
                          height={160}
                          onPointerDown={startDraw}
                          onPointerMove={moveDraw}
                          onPointerUp={endDraw}
                          onPointerLeave={endDraw}
                          className="h-40 w-full touch-none rounded-md border border-dashed border-line bg-surface-2"
                        />
                        {!hasDrawing && <p className="mt-1 text-xs text-ink-3">Use your mouse or finger to sign above.</p>}
                      </div>
                    )}

                    {sigMode === "uploaded" && (
                      <div className="rounded-md bg-white p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wide text-ink-3">Upload a signature image</span>
                        <input
                          type="file"
                          accept="image/png,image/jpeg"
                          onChange={onUploadFile}
                          className="mt-1 block w-full text-sm text-ink-2 file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink-2 hover:file:bg-line"
                        />
                        {sigImage ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={sigImage} alt="Signature preview" className="mt-2 max-h-24 rounded border border-line bg-surface-2 p-1" />
                        ) : (
                          <p className="mt-1 text-xs text-ink-3">PNG or JPEG, under 1 MB. A transparent PNG looks best.</p>
                        )}
                      </div>
                    )}
                  </div>

                  {info.tabs.length > 0 && (
                    <div className="space-y-2 rounded-md bg-white px-3 py-3">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                        Fields the sender placed on the document ({info.tabs.length})
                      </div>
                      {info.tabs.map((t) => (
                        <div key={t.id} className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="grid h-6 min-w-6 place-items-center rounded bg-surface-2 px-1.5 text-[10px] font-semibold uppercase text-ink-3">
                            p{t.page}
                          </span>
                          <span className="font-medium text-ink">{t.label || `${t.kind} field`}</span>
                          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-3">{t.kind}</span>
                          {t.kind === "signature" && (
                            <span className="ml-auto italic text-ink-2">/s/&nbsp;{fullName.trim() || "—"}</span>
                          )}
                          {t.kind === "initials" && (
                            <span className="ml-auto font-bold text-ink-2">{initialsOf(fullName) || "—"}</span>
                          )}
                          {t.kind === "date" && (
                            <span className="ml-auto text-ink-2">{new Date().toLocaleDateString()}</span>
                          )}
                          {t.kind === "text" && (
                            <input
                              value={tabFills[t.id] ?? ""}
                              onChange={(e) => setTabFills((m) => ({ ...m, [t.id]: e.target.value }))}
                              placeholder={t.required ? "Required" : "Optional"}
                              className="ml-auto h-8 min-w-[10rem] flex-1 rounded-sm border border-line bg-white px-2 text-sm"
                            />
                          )}
                          {t.kind === "checkbox" && (
                            <label className="ml-auto inline-flex items-center gap-2 text-xs text-ink-2">
                              <input
                                type="checkbox"
                                checked={(tabFills[t.id] ?? "") === "true"}
                                onChange={(e) => setTabFills((m) => ({ ...m, [t.id]: e.target.checked ? "true" : "" }))}
                              />
                              I agree {t.required && <span className="text-danger">*</span>}
                            </label>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      onClick={sign}
                      loading={busy}
                      disabled={!canFinish}
                      className={assisted ? "h-14 flex-1 text-lg" : ""}
                    >
                      <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> I agree &amp; sign
                    </Button>
                    <button
                      onClick={() => setDeclineMode(true)}
                      className={
                        assisted
                          ? "h-14 rounded-md px-4 text-base text-ink-3 underline hover:text-danger"
                          : "text-sm text-ink-3 hover:text-danger hover:underline"
                      }
                    >
                      Decline to sign
                    </button>
                  </div>
                  {assisted && !canFinish && (
                    <p className="text-sm text-ink-3">
                      {!consent
                        ? "Tick the box above once you agree."
                        : !fullName.trim()
                          ? "Type your full name above."
                          : "Add your signature above."}
                    </p>
                  )}
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

          {assisted && info?.valid && info.can_sign && !declineMode && (
            <div className="flex items-center gap-3 border-t border-line pt-4">
              <Button
                variant="ghost"
                className="h-14 flex-1 text-lg"
                onClick={() => setStep((n) => Math.max(0, n - 1))}
                disabled={step === 0}
              >
                {t("action.back")}
              </Button>
              {step < STEPS.length - 1 && (
                <Button
                  className="h-14 flex-1 text-lg"
                  onClick={() => setStep((n) => Math.min(STEPS.length - 1, n + 1))}
                  // Step 0 requires the document to have been opened. A "next" that skips
                  // reading turns the signing record into evidence of a click, not of consent.
                  disabled={step === 0 && !opened}
                >
                  {t("action.next")}
                </Button>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {assisted && info?.valid && info.recipient_status === "signed" && (
        <p className="mt-4 max-w-lg text-center text-base text-ink-2">
          {t("sign.copy_sent")} {t("sign.no_email")}
        </p>
      )}

      <p className="mt-4 text-xs text-ink-3">Powered by Contract Management · this link is unique to you — please don&rsquo;t forward it.</p>
    </div>
  );
}
