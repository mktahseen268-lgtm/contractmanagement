"use client";

// Passkeys / WebAuthn — PROTOTYPE of passwordless + phishing-resistant sign-in management.
// List registered passkeys, register a new one (simulated WebAuthn ceremony), and see other MFA
// factors. Mockup: in-memory. Wires later to a WebAuthn registration/assertion backend.

import { useState } from "react";
import { Check, Fingerprint, KeyRound, Laptop, Loader2, Plus, Shield, Smartphone, Trash2, Usb } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";

type Passkey = { id: string; name: string; kind: "platform" | "phone" | "security-key"; added: string; lastUsed: string };

const INITIAL: Passkey[] = [
  { id: "1", name: "MacBook Pro (Touch ID)", kind: "platform", added: "Apr 2, 2026", lastUsed: "2 hours ago" },
  { id: "2", name: "iPhone 15", kind: "phone", added: "Mar 18, 2026", lastUsed: "Yesterday" },
  { id: "3", name: "YubiKey 5C", kind: "security-key", added: "Jan 9, 2026", lastUsed: "3 weeks ago" },
];

const KIND_META = {
  platform: { label: "This device", icon: Laptop },
  phone: { label: "Phone", icon: Smartphone },
  "security-key": { label: "Security key", icon: Usb },
};

export default function PasskeysPage() {
  const [keys, setKeys] = useState<Passkey[]>(INITIAL);
  const [registering, setRegistering] = useState(false);

  function register() {
    setRegistering(true);
    setTimeout(() => {
      setKeys((k) => [
        { id: `${Date.now()}`, name: "New device (Face/Touch ID)", kind: "platform", added: "Just now", lastUsed: "Just now" },
        ...k,
      ]);
      setRegistering(false);
    }, 1600);
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Passkeys <Badge tone="accent">Preview</Badge></span>}
        subtitle="Passwordless, phishing-resistant sign-in with WebAuthn passkeys."
        actions={
          <Button size="sm" onClick={register} disabled={registering}>
            {registering ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Waiting for device…</> : <><Plus className="h-3.5 w-3.5" /> Add a passkey</>}
          </Button>
        }
      />

      <div className="mx-auto max-w-2xl space-y-4 p-4">
        <div className="flex items-start gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3">
          <Fingerprint className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div className="text-sm">
            <div className="font-semibold text-ink">Sign in without a password</div>
            <div className="text-ink-3">Passkeys use your device&rsquo;s Face ID, Touch ID, Windows Hello, or a security key. They can&rsquo;t be phished or reused.</div>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5"><KeyRound className="h-4 w-4" /> Your passkeys</CardTitle>
            <span className="text-xs text-ink-3">{keys.length} registered</span>
          </CardHeader>
          <CardBody className="space-y-1.5">
            {keys.map((k) => {
              const M = KIND_META[k.kind];
              const Icon = M.icon;
              return (
                <div key={k.id} className="flex items-center gap-3 rounded-lg border border-line px-3 py-2.5">
                  <span className="grid h-9 w-9 place-items-center rounded-lg bg-surface-2 text-ink-2"><Icon className="h-4 w-4" /></span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-ink">{k.name}</div>
                    <div className="text-[11px] text-ink-3">{M.label} · added {k.added} · last used {k.lastUsed}</div>
                  </div>
                  <button onClick={() => setKeys((arr) => arr.filter((x) => x.id !== k.id))} className="text-ink-3 hover:text-danger">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
            {keys.length === 0 && <p className="py-4 text-center text-sm text-ink-3">No passkeys yet. Add one to sign in without a password.</p>}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-1.5"><Shield className="h-4 w-4" /> Other sign-in factors</CardTitle></CardHeader>
          <CardBody className="space-y-1.5">
            {[
              { label: "Authenticator app (TOTP)", state: "Enabled", ok: true },
              { label: "Email one-time codes", state: "Enabled", ok: true },
              { label: "Recovery codes", state: "8 remaining", ok: true },
              { label: "Password", state: "Set · can be removed once a passkey exists", ok: true },
            ].map((f) => (
              <div key={f.label} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                <Check className="h-4 w-4 text-emerald-600" />
                <span className="flex-1 text-ink">{f.label}</span>
                <span className="text-[11px] text-ink-3">{f.state}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>

      {registering && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
          <Card className="w-full max-w-sm">
            <CardBody className="space-y-3 py-6 text-center">
              <Fingerprint className="mx-auto h-12 w-12 animate-pulse text-accent" />
              <div className="text-base font-semibold text-ink">Confirm on your device</div>
              <p className="text-sm text-ink-2">Use Face ID, Touch ID, Windows Hello, or your security key to create a passkey for this account.</p>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
