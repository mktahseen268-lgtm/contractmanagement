"use client";

/**
 * Visitor eSigning — the public on-ramp for external signatories.
 *
 * Reached by web link, branch-tablet kiosk, mobile link or QR code. No account, no password.
 * Three steps, then the existing /sign/{token} portal takes over:
 *
 *   identify -> verify (OTP) -> read the document -> sign
 *
 * Designed for the RFP's "non-digitally-literate client" requirement: one question per screen,
 * large targets, plain language, no jargon, and an explicit reason whenever something is
 * disabled rather than a button that silently does nothing.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  FileText,
  Loader2,
  Lock,
  MessageSquare,
  Smartphone,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";
import type { EsignConsent, EsignLanding, EsignStart, EsignVerify } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Step = "identify" | "verify" | "review" | "done";

/**
 * Solve the server's proof-of-work challenge.
 *
 * This replaces a CAPTCHA: a CAPTCHA service is a foreign-hosted runtime dependency, which the
 * deployment's data-residency rule forbids. At the default difficulty this costs a real person
 * a fraction of a second and costs a bulk automation run the same per attempt — which is the
 * point. Runs in an async loop that yields, so the page never freezes on a slow phone.
 */
async function solveProofOfWork(challenge: string, bits: number): Promise<string> {
  if (!challenge || bits <= 0) return "";
  const encoder = new TextEncoder();
  const wholeBytes = Math.floor(bits / 8);
  const remainder = bits % 8;

  for (let counter = 0; ; counter++) {
    const digest = new Uint8Array(
      await crypto.subtle.digest("SHA-256", encoder.encode(`${challenge}${counter}`)),
    );
    let ok = true;
    for (let i = 0; i < wholeBytes; i++) {
      if (digest[i] !== 0) {
        ok = false;
        break;
      }
    }
    if (ok && remainder && digest[wholeBytes] >> (8 - remainder) !== 0) ok = false;
    if (ok) return String(counter);
    // Yield periodically so the browser stays responsive on a low-end device.
    if (counter % 5000 === 4999) await new Promise((r) => setTimeout(r, 0));
  }
}

export default function EsignPage() {
  const { token } = useParams<{ token: string }>();
  const search = useSearchParams();
  const entryPoint = search.get("via") === "qr" ? "qr" : search.get("via") === "kiosk" ? "kiosk" : "web";

  const [landing, setLanding] = useState<EsignLanding | null>(null);
  const [step, setStep] = useState<Step>("identify");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  // identify
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<"email" | "sms">("sms");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [cnic, setCnic] = useState("");

  // verify
  const [session, setSession] = useState<EsignStart | null>(null);
  const [code, setCode] = useState("");

  // review
  const [verified, setVerified] = useState<EsignVerify | null>(null);
  const [consent, setConsent] = useState<EsignConsent | null>(null);
  const docRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api
      .get<EsignLanding>(`/esign/${token}`, { cache: false })
      .then((l) => {
        setLanding(l);
        if (l.otp_channel === "email") setChannel("email");
      })
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "This signing link is not valid. It may have expired or already been used."
            : "We could not open this signing link. Please check your connection and try again.",
        ),
      );
  }, [token]);

  async function identify(e: React.FormEvent) {
    e.preventDefault();
    if (!landing) return;
    setBusy(true);
    setError("");
    try {
      const pow = landing.proof_of_work;
      const solution = pow?.required ? await solveProofOfWork(pow.challenge, pow.bits) : "";
      const started = await api.post<EsignStart>(`/esign/${token}/start`, {
        name: name.trim(),
        email: channel === "email" ? email.trim() : "",
        phone: channel === "sms" ? phone.trim() : "",
        channel,
        cnic: landing.collect_cnic ? cnic.trim() : "",
        entry_point: entryPoint,
        pow_challenge: pow?.challenge ?? "",
        pow_solution: solution,
      });
      setSession(started);
      setStep("verify");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.post<EsignVerify>(`/esign/${token}/verify`, {
        session_id: session.session_id,
        code: code.trim(),
      });
      setVerified(result);
      setStep("review");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We could not verify that code.");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (!session) return;
    setError("");
    setNotice("");
    try {
      const again = await api.post<EsignStart>(`/esign/${token}/resend`, {
        session_id: session.session_id,
      });
      setSession(again);
      setNotice(`A new code is on its way to ${again.masked_identifier}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We could not send another code.");
    }
  }

  const reportConsent = useCallback(
    async (pagesViewed: number, totalPages: number, scrolledToEnd: boolean) => {
      if (!session) return;
      try {
        setConsent(
          await api.post<EsignConsent>(`/esign/${token}/consent`, {
            session_id: session.session_id,
            pages_viewed: pagesViewed,
            total_pages: totalPages,
            scrolled_to_end: scrolledToEnd,
          }),
        );
      } catch {
        /* consent reporting is best-effort; the server gates signing regardless */
      }
    },
    [session, token],
  );

  // Report the initial view as soon as the document is on screen, so an abandoned session
  // still records that it was opened.
  useEffect(() => {
    if (step === "review") void reportConsent(1, 1, false);
  }, [step, reportConsent]);

  function onDocumentScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
    if (atEnd && !consent?.may_sign) void reportConsent(1, 1, true);
  }

  if (error && !landing) {
    return (
      <Shell>
        <Card>
          <CardBody className="space-y-3 py-10 text-center">
            <Lock className="mx-auto h-10 w-10 text-ink-3" />
            <h1 className="font-display text-lg font-semibold text-ink">Link not available</h1>
            <p className="text-sm text-ink-2">{error}</p>
            <p className="text-xs text-ink-3">
              Please ask the person who sent it for a new link.
            </p>
          </CardBody>
        </Card>
      </Shell>
    );
  }

  if (!landing) {
    return (
      <Shell>
        <div className="flex items-center justify-center py-16 text-ink-3">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-4 text-center">
        <p className="text-xs uppercase tracking-wide text-ink-3">{landing.organisation}</p>
        <h1 className="font-display text-xl font-bold text-ink">{landing.contract_title}</h1>
        {landing.contract_reference && (
          <p className="text-xs text-ink-3">{landing.contract_reference}</p>
        )}
      </div>

      <Steps current={step} />

      {error && <ErrorBanner message={error} className="mt-3" />}
      {notice && (
        <p className="mt-3 rounded-md bg-accent-subtle px-3 py-2 text-sm text-accent">{notice}</p>
      )}

      {step === "identify" && (
        <Card className="mt-4">
          <CardBody>
            <form onSubmit={identify} className="space-y-4">
              <div>
                <h2 className="font-display text-base font-semibold text-ink">Who are you?</h2>
                <p className="text-sm text-ink-2">
                  We will send you a one-time code to confirm it is really you.
                </p>
              </div>

              <Field label="Your full name">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="As it should appear on the agreement"
                  autoComplete="name"
                  required
                  className="h-12 text-base"
                />
              </Field>

              {landing.otp_channel === "any" && (
                <div className="grid grid-cols-2 gap-2">
                  <ChannelButton
                    active={channel === "sms"}
                    onClick={() => setChannel("sms")}
                    icon={Smartphone}
                    label="By SMS"
                  />
                  <ChannelButton
                    active={channel === "email"}
                    onClick={() => setChannel("email")}
                    icon={MessageSquare}
                    label="By email"
                  />
                </div>
              )}

              {channel === "sms" ? (
                <Field label="Mobile number">
                  <Input
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="03XX XXXXXXX"
                    inputMode="tel"
                    autoComplete="tel"
                    required
                    className="h-12 text-base"
                  />
                </Field>
              ) : (
                <Field label="Email address">
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    required
                    className="h-12 text-base"
                  />
                </Field>
              )}

              {landing.collect_cnic && (
                <Field label="CNIC number" hint="Only the last four digits are stored.">
                  <Input
                    value={cnic}
                    onChange={(e) => setCnic(e.target.value)}
                    placeholder="42101-1234567-8"
                    inputMode="numeric"
                    className="h-12 text-base"
                  />
                </Field>
              )}

              <Button type="submit" disabled={busy} className="h-12 w-full text-base">
                {busy ? "Sending code…" : "Send me a code"}
                {!busy && <ArrowRight className="h-4 w-4" />}
              </Button>
            </form>
          </CardBody>
        </Card>
      )}

      {step === "verify" && session && (
        <Card className="mt-4">
          <CardBody>
            <form onSubmit={verify} className="space-y-4">
              <div>
                <h2 className="font-display text-base font-semibold text-ink">Enter your code</h2>
                <p className="text-sm text-ink-2">
                  We sent a {landing.require_otp ? "6-digit" : ""} code to{" "}
                  <span className="font-medium text-ink">{session.masked_identifier}</span>.
                </p>
              </div>
              <Field label="Verification code">
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="------"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={8}
                  required
                  className="h-14 text-center font-mono text-2xl tracking-[0.4em]"
                />
              </Field>
              <Button type="submit" disabled={busy} className="h-12 w-full text-base">
                {busy ? "Checking…" : "Confirm"}
              </Button>
              <button
                type="button"
                onClick={resend}
                className="w-full text-center text-sm text-accent hover:underline"
              >
                I did not get a code — send another
              </button>
            </form>
          </CardBody>
        </Card>
      )}

      {step === "review" && verified && (
        <div className="mt-4 space-y-3">
          <Card>
            <CardBody className="space-y-2 py-3">
              <div className="flex items-center gap-2 text-sm">
                <BadgeCheck className="h-4 w-4 text-accent" />
                <span className="text-ink">Identity confirmed</span>
              </div>
              {verified.certificate_serial && (
                <p className="text-xs text-ink-2">
                  A signing certificate has been issued in your name. Serial{" "}
                  <span className="font-mono">{verified.certificate_serial.slice(0, 16)}…</span>
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardBody className="space-y-3">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-ink-3" />
                <h2 className="font-display text-base font-semibold text-ink">
                  Please read the agreement
                </h2>
              </div>
              <div
                ref={docRef}
                onScroll={onDocumentScroll}
                className="h-80 overflow-y-auto rounded-md border border-line bg-surface-2 p-1"
              >
                <iframe
                  title="Agreement"
                  src={`${API}/sign/${verified.signing_token}/document`}
                  className="h-[1200px] w-full rounded"
                />
              </div>

              {landing.require_scroll && !consent?.may_sign && (
                <p className="text-sm text-ink-2">
                  Scroll to the end of the document to continue.
                </p>
              )}

              <Button
                className="h-12 w-full text-base"
                disabled={landing.require_scroll && !consent?.may_sign}
                onClick={() => {
                  window.location.href = `/sign/${verified.signing_token}`;
                }}
              >
                {landing.require_scroll && !consent?.may_sign
                  ? "Read to the end to continue"
                  : "Continue to sign"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardBody>
          </Card>
        </div>
      )}

      <p className="mt-6 text-center text-xs text-ink-3">
        Your name, the time you signed and your device details are recorded as evidence of
        signature.
      </p>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-4 py-8">
      {children}
    </div>
  );
}

function Steps({ current }: { current: Step }) {
  const order: Step[] = ["identify", "verify", "review"];
  const labels: Record<Step, string> = {
    identify: "Identify",
    verify: "Verify",
    review: "Read",
    done: "Sign",
  };
  const index = order.indexOf(current);
  return (
    <ol className="flex items-center justify-center gap-2 text-xs">
      {order.map((s, i) => (
        <li key={s} className="flex items-center gap-2">
          <span
            className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold ${
              i < index
                ? "bg-accent text-white"
                : i === index
                  ? "bg-accent-subtle text-accent ring-2 ring-accent"
                  : "bg-surface-3 text-ink-3"
            }`}
          >
            {i < index ? <CheckCircle2 className="h-3.5 w-3.5" /> : i + 1}
          </span>
          <span className={i === index ? "font-medium text-ink" : "text-ink-3"}>{labels[s]}</span>
          {i < order.length - 1 && <span className="mx-1 h-px w-4 bg-line" />}
        </li>
      ))}
    </ol>
  );
}

function ChannelButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Smartphone;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-12 items-center justify-center gap-2 rounded-md border text-sm font-medium transition ${
        active
          ? "border-accent bg-accent-subtle text-accent"
          : "border-line bg-surface text-ink-2 hover:text-ink"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}
