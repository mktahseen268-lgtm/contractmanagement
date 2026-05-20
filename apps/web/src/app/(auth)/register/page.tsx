"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Card, CardBody, ErrorBanner, Field, Input } from "@/components/ui";

export default function RegisterPage() {
  const { register } = useAuth();
  const [workspace, setWorkspace] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await register(workspace.trim(), name.trim(), email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the workspace.");
      setLoading(false);
    }
  }

  return (
    <Card className="glass w-full max-w-sm border-white/60 shadow-pop">
      <CardBody className="space-y-4">
        <div>
          <h1 className="font-display text-xl font-bold tracking-tight text-ink">Create your workspace</h1>
          <p className="text-sm text-ink-2">You'll be the owner. Invite your team afterwards.</p>
        </div>
        <ErrorBanner message={error} />
        <form onSubmit={submit} className="space-y-3">
          <Field label="Workspace name">
            <Input value={workspace} onChange={(e) => setWorkspace(e.target.value)} placeholder="Acme Holdings" required minLength={2} autoFocus />
          </Field>
          <Field label="Your name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" required />
          </Field>
          <Field label="Work email">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@acme.com" autoComplete="username" required />
          </Field>
          <Field label="Password" hint="At least 8 characters.">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required minLength={8} />
          </Field>
          <Button type="submit" className="w-full" loading={loading}>
            Create workspace
          </Button>
        </form>
        <p className="text-center text-sm text-ink-2">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </CardBody>
    </Card>
  );
}
