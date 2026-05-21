"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SSO_ERRORS: Record<string, string> = {
  missing_code: "SSO sign-in was cancelled or returned no code.",
  expired: "Your SSO session expired — please try again.",
  state_mismatch: "SSO security check failed — please try again.",
};

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("demo@acme.io");
  const [password, setPassword] = useState("demo1234");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ssoEnabled, setSsoEnabled] = useState(false);

  // is SSO configured? + surface any sso_error the callback redirected with
  useEffect(() => {
    api.get<{ enabled: boolean }>("/auth/sso/config").then((c) => setSsoEnabled(!!c.enabled)).catch(() => {});
    if (typeof window !== "undefined") {
      const err = new URLSearchParams(window.location.search).get("sso_error");
      if (err) setError(SSO_ERRORS[err] || "Single sign-on failed — please try again or use your password.");
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { mfaRequired } = await login(email.trim(), password);
      if (mfaRequired) router.push("/login/mfa");
      // otherwise the (auth) layout redirects to /dashboard once `me` is set
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't sign in.");
      setLoading(false);
    }
  }

  return (
    <Card className="glass w-full max-w-sm border-white/60 shadow-pop">
      <CardBody className="space-y-4">
        <div>
          <h1 className="font-display text-xl font-bold tracking-tight text-ink">Welcome back</h1>
          <p className="text-sm text-ink-2">Sign in to your workspace.</p>
        </div>
        <ErrorBanner message={error} />
        <form onSubmit={submit} className="space-y-3">
          <Field label="Email">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </Field>
          <Button type="submit" className="w-full" loading={loading}>
            Sign in
          </Button>
        </form>
        {ssoEnabled && (
          <>
            <div className="flex items-center gap-3 text-[11px] uppercase tracking-wide text-ink-3">
              <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
            </div>
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => { window.location.href = `${API_BASE}/auth/sso/login`; }}
            >
              <ShieldCheck className="h-4 w-4" /> Sign in with SSO
            </Button>
          </>
        )}
        <div className="rounded-md bg-surface-2 px-3 py-2 text-xs text-ink-3">
          Demo workspace seeded automatically — <span className="font-medium text-ink-2">demo@acme.io</span> / <span className="font-medium text-ink-2">demo1234</span>
        </div>
        <p className="text-center text-sm text-ink-2">
          No account?{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Create a workspace
          </Link>
        </p>
      </CardBody>
    </Card>
  );
}
