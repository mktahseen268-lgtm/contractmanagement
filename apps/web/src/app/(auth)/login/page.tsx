"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("demo@acme.io");
  const [password, setPassword] = useState("demo1234");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
