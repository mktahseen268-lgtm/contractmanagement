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
  // Single-tenant on-prem deployments have no self-service signup and no demo workspace.
  // Default to `true` so the link doesn't flicker out on the SaaS build while config loads.
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const [singleTenant, setSingleTenant] = useState(false);

  // is SSO configured? which deployment profile? + surface any sso_error the callback redirected with
  useEffect(() => {
    api
      .get<{ enabled: boolean; registration_enabled?: boolean; deployment_mode?: string }>("/auth/sso/config")
      .then((c) => {
        setSsoEnabled(!!c.enabled);
        setRegistrationEnabled(c.registration_enabled !== false);
        const single = c.deployment_mode === "single_tenant";
        setSingleTenant(single);
        // The demo credentials below are a convenience for the seeded SaaS demo. On a
        // single-tenant install there is no demo workspace, and prefilling someone else's
        // login on a bank's sign-in screen is not a good look.
        if (single) {
          setEmail("");
          setPassword("");
        }
      })
      .catch(() => {});
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
        {!singleTenant && (
          <div className="rounded-md bg-surface-2 px-3 py-2 text-xs text-ink-3">
            Demo workspace seeded automatically — <span className="font-medium text-ink-2">demo@acme.io</span> / <span className="font-medium text-ink-2">demo1234</span>
          </div>
        )}
        {registrationEnabled ? (
          <p className="text-center text-sm text-ink-2">
            No account?{" "}
            <Link href="/register" className="font-medium text-accent hover:underline">
              Create a workspace
            </Link>
          </p>
        ) : (
          <p className="text-center text-sm text-ink-3">
            Accounts are provisioned by your administrator.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
