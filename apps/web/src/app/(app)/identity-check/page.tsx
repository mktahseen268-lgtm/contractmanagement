"use client";

// Identity Verification — PROTOTYPE of the signer identity step that runs *before* the signing
// ceremony for higher-assurance agreements. Methods: SMS OTP, email OTP, government-ID upload,
// and knowledge-based (KBA) questions. Mockup: interactive but simulated. Wires later into the
// /sign/{token} flow as a gating step driven by the envelope's required assurance level.

import { useState } from "react";
import { BadgeCheck, CheckCircle2, IdCard, Mail, MessageSquare, ShieldCheck, Smartphone, Upload } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody } from "@/components/ui";

type Method = "sms" | "email" | "id" | "kba";

const METHODS: { key: Method; label: string; icon: typeof Smartphone; desc: string }[] = [
  { key: "sms", label: "SMS one-time code", icon: Smartphone, desc: "Text a 6-digit code to the signer's phone." },
  { key: "email", label: "Email one-time code", icon: Mail, desc: "Email a 6-digit code to verify the address." },
  { key: "id", label: "Government ID check", icon: IdCard, desc: "Upload + verify a passport or national ID." },
  { key: "kba", label: "Knowledge-based (KBA)", icon: MessageSquare, desc: "Answer identity questions from public records." },
];

const KBA_QUESTIONS = [
  { q: "Which street have you previously lived on?", options: ["Maple Ave", "Cedar St", "Oak Lane", "None of these"] },
  { q: "Which of these is a known associate or employer?", options: ["Northwind Ltd", "Lumen Labs", "Platform Inc", "None of these"] },
];

export default function IdentityCheckPage() {
  const [method, setMethod] = useState<Method>("sms");
  const [otp, setOtp] = useState<string[]>(["", "", "", "", "", ""]);
  const [kba, setKba] = useState<number[]>([-1, -1]);
  const [verified, setVerified] = useState(false);

  const otpComplete = otp.every((d) => d !== "");
  const kbaComplete = kba.every((k) => k >= 0);
  const canVerify = method === "sms" || method === "email" ? otpComplete : method === "kba" ? kbaComplete : true;

  function setOtpAt(i: number, v: string) {
    const d = v.replace(/\D/g, "").slice(-1);
    setOtp((arr) => arr.map((x, idx) => (idx === i ? d : x)));
    if (d && i < 5) {
      const next = document.getElementById(`otp-${i + 1}`);
      next?.focus();
    }
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Identity Verification <Badge tone="accent">Preview</Badge></span>}
        subtitle="A higher-assurance identity step before signing — SMS / email OTP, ID check, or KBA."
      />

      <div className="mx-auto max-w-2xl space-y-4 p-4">
        {/* assurance banner */}
        <div className="flex items-center gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3">
          <ShieldCheck className="h-5 w-5 text-accent" />
          <div className="text-sm">
            <div className="font-semibold text-ink">This agreement requires identity verification</div>
            <div className="text-ink-3">The sender set the assurance level to <span className="font-medium text-ink-2">High</span>. Verify your identity to continue to signing.</div>
          </div>
        </div>

        {verified ? (
          <Card>
            <CardBody className="space-y-3 py-8 text-center">
              <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" />
              <div className="text-lg font-semibold text-ink">Identity verified</div>
              <p className="mx-auto max-w-sm text-sm text-ink-2">
                Verified via <span className="font-medium text-ink">{METHODS.find((m) => m.key === method)?.label}</span>.
                This is recorded in the Certificate of Completion. You can now proceed to sign.
              </p>
              <Button className="mx-auto"><BadgeCheck className="h-4 w-4" /> Continue to signing</Button>
            </CardBody>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-[220px_1fr]">
            {/* method picker */}
            <Card className="h-max">
              <CardBody className="space-y-1.5">
                {METHODS.map((m) => {
                  const on = method === m.key;
                  const Icon = m.icon;
                  return (
                    <button
                      key={m.key}
                      onClick={() => setMethod(m.key)}
                      className={`flex w-full items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition ${on ? "border-accent bg-accent/5" : "border-line hover:bg-surface-2"}`}
                    >
                      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${on ? "text-accent" : "text-ink-3"}`} />
                      <span className="text-sm font-medium text-ink">{m.label}</span>
                    </button>
                  );
                })}
              </CardBody>
            </Card>

            {/* method body */}
            <Card>
              <CardBody className="space-y-4">
                <p className="text-sm text-ink-2">{METHODS.find((m) => m.key === method)?.desc}</p>

                {(method === "sms" || method === "email") && (
                  <div className="space-y-3">
                    <div className="text-[11px] text-ink-3">
                      Code sent to {method === "sms" ? "+971 ••• ••• 4729" : "s•••••@thiqatech.com"}.
                    </div>
                    <div className="flex gap-2">
                      {otp.map((d, i) => (
                        <input
                          key={i}
                          id={`otp-${i}`}
                          value={d}
                          onChange={(e) => setOtpAt(i, e.target.value)}
                          inputMode="numeric"
                          maxLength={1}
                          className="h-12 w-12 rounded-lg border border-line bg-white text-center text-lg font-semibold text-ink focus:border-accent focus:outline-none"
                        />
                      ))}
                    </div>
                    <button className="text-xs text-accent hover:underline">Resend code</button>
                  </div>
                )}

                {method === "id" && (
                  <div className="space-y-3">
                    <div className="grid place-items-center gap-2 rounded-xl border-2 border-dashed border-line bg-surface-2 py-8 text-center">
                      <Upload className="h-7 w-7 text-ink-3" />
                      <div className="text-sm font-medium text-ink">Upload your passport or national ID</div>
                      <div className="text-[11px] text-ink-3">JP, PNG or PDF · front side · max 10 MB</div>
                      <Button size="sm" variant="secondary" className="mt-1">Choose file</Button>
                    </div>
                    <div className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[11px] text-ink-2">
                      <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Document is checked for authenticity and matched to the signer's name.
                    </div>
                  </div>
                )}

                {method === "kba" && (
                  <div className="space-y-4">
                    {KBA_QUESTIONS.map((kq, qi) => (
                      <div key={qi}>
                        <div className="mb-1.5 text-sm font-medium text-ink">{qi + 1}. {kq.q}</div>
                        <div className="grid grid-cols-2 gap-1.5">
                          {kq.options.map((opt, oi) => {
                            const on = kba[qi] === oi;
                            return (
                              <button
                                key={oi}
                                onClick={() => setKba((arr) => arr.map((x, idx) => (idx === qi ? oi : x)))}
                                className={`rounded-lg border px-3 py-2 text-left text-sm transition ${on ? "border-accent bg-accent/5 font-medium text-accent" : "border-line text-ink-2 hover:bg-surface-2"}`}
                              >
                                {opt}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Button className="w-full" disabled={!canVerify} onClick={() => setVerified(true)}>
                  <ShieldCheck className="h-4 w-4" /> Verify identity
                </Button>
              </CardBody>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
