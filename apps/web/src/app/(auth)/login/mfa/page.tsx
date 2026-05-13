"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Mail, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";

export default function MfaPage() {
  const { mfaToken, verifyMfa, sendLoginOtp } = useAuth();
  const router = useRouter();
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    // arriving here without a pending sign-in (e.g. a page reload) -> back to login
    if (!mfaToken) router.replace("/login");
  }, [mfaToken, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setError("");
    try {
      await verifyMfa(code.trim()); // navigates to /dashboard on success
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That code didn't work.");
      setLoading(false);
    }
  }

  async function emailCode() {
    setSending(true);
    setError("");
    setNote("");
    try {
      const r = await sendLoginOtp();
      setNote(r.dev_code ? `Dev mode — your code is ${r.dev_code}` : "We've emailed you a one-time code.");
      if (r.dev_code) setCode(r.dev_code);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send a code.");
    } finally {
      setSending(false);
    }
  }

  if (!mfaToken) return null;

  return (
    <Card className="w-full max-w-sm">
      <CardBody className="space-y-4">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent-subtle text-accent">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-ink">Two-factor authentication</h1>
            <p className="text-sm text-ink-2">Enter the 6-digit code from your authenticator app.</p>
          </div>
        </div>
        <ErrorBanner message={error} />
        {note && <div className="rounded-md bg-accent-subtle px-3 py-2 text-sm text-accent">{note}</div>}
        <form onSubmit={submit} className="space-y-3">
          <Field label="Code" hint="A recovery code also works here.">
            <Input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" autoFocus className="tracking-widest" />
          </Field>
          <Button type="submit" className="w-full" loading={loading}>
            Verify
          </Button>
        </form>
        <button onClick={emailCode} disabled={sending} className="flex w-full items-center justify-center gap-1.5 text-sm text-accent hover:underline disabled:opacity-50">
          <Mail className="h-3.5 w-3.5" /> {sending ? "Sending…" : "Email me a one-time code instead"}
        </button>
        <button onClick={() => router.push("/login")} className="block w-full text-center text-xs text-ink-3 hover:underline">
          Use a different account
        </button>
      </CardBody>
    </Card>
  );
}
