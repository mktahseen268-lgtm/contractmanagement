"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound, Laptop, RefreshCw, ShieldCheck, ShieldOff } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, ErrorBanner, Field, Input, Skeleton } from "@/components/ui";
import type { MfaSetup, SessionInfo } from "@/lib/types";

export function SecurityPanel() {
  const { me, refreshMe } = useAuth();
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  // ---- 2FA enable flow ----
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);

  // ---- sessions ----
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);

  // ---- change password ----
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwBusy, setPwBusy] = useState(false);

  const mfaEnabled = me?.user.mfa_enabled ?? false;

  const loadSessions = useCallback(() => {
    api.get<SessionInfo[]>("/auth/sessions").then(setSessions).catch(() => setSessions([]));
  }, []);
  useEffect(loadSessions, [loadSessions]);

  function fail(e: unknown) {
    setError(e instanceof ApiError ? e.message : "Something went wrong.");
  }

  async function beginEnable() {
    setBusy(true); setError(""); setNote(""); setRecoveryCodes(null);
    try {
      setSetup(await api.post<MfaSetup>("/auth/mfa/setup"));
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function confirmEnable() {
    if (!confirmCode.trim()) return;
    setBusy(true); setError("");
    try {
      const r = await api.post<{ recovery_codes: string[] }>("/auth/mfa/enable", { code: confirmCode.trim() });
      setRecoveryCodes(r.recovery_codes);
      setSetup(null);
      setConfirmCode("");
      await refreshMe();
      setNote("Two-factor authentication is on.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function disable() {
    const pw = window.prompt("Confirm your password to turn off two-factor authentication:");
    if (pw == null) return;
    setBusy(true); setError("");
    try {
      await api.post("/auth/mfa/disable", { password: pw });
      setRecoveryCodes(null);
      await refreshMe();
      setNote("Two-factor authentication is off.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function regenRecovery() {
    const pw = window.prompt("Confirm your password to generate a fresh set of recovery codes:");
    if (pw == null) return;
    setBusy(true); setError("");
    try {
      const r = await api.post<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", { password: pw });
      setRecoveryCodes(r.recovery_codes);
      setNote("New recovery codes generated — your old ones no longer work.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function signOutSession(id: string) {
    try { await api.del(`/auth/sessions/${id}`); loadSessions(); } catch (e) { fail(e); }
  }
  async function signOutOthers() {
    try { const r = await api.post<{ revoked: number }>("/auth/sessions/revoke-all"); setNote(`Signed out ${r.revoked} other session(s).`); loadSessions(); } catch (e) { fail(e); }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setNote("");
    if (next.length < 8) { setError("New password must be at least 8 characters."); return; }
    if (next !== confirm) { setError("New password and confirmation don't match."); return; }
    setPwBusy(true);
    try {
      const r = await api.post<{ revoked_other_sessions: number }>("/auth/change-password", { current_password: cur, new_password: next });
      setCur(""); setNext(""); setConfirm("");
      setNote(`Password changed.${r.revoked_other_sessions ? ` ${r.revoked_other_sessions} other session(s) were signed out.` : ""}`);
      loadSessions();
    } catch (e) { fail(e); } finally { setPwBusy(false); }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5"><ShieldCheck className="h-4 w-4" /> Security</CardTitle>
      </CardHeader>
      <CardBody className="space-y-6">
        <ErrorBanner message={error} />
        {note && <div className="rounded-md bg-accent-subtle px-3 py-2 text-sm text-accent">{note}</div>}

        {/* --- 2FA --- */}
        <section>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-ink">Two-factor authentication</h3>
              <p className="text-xs text-ink-2">Require a code from an authenticator app (or a recovery / email code) when signing in.</p>
            </div>
            {mfaEnabled ? (
              <div className="flex items-center gap-2">
                <Badge tone="accent">Enabled</Badge>
                <Button size="sm" variant="ghost" onClick={regenRecovery} disabled={busy}><RefreshCw className="h-3.5 w-3.5" /> Recovery codes</Button>
                <Button size="sm" variant="outline" onClick={disable} disabled={busy}><ShieldOff className="h-3.5 w-3.5" /> Disable</Button>
              </div>
            ) : setup ? null : (
              <Button size="sm" onClick={beginEnable} loading={busy}>Enable</Button>
            )}
          </div>

          {setup && (
            <div className="mt-3 space-y-3 rounded-lg border border-line bg-surface-2 p-4">
              <p className="text-sm text-ink-2">In your authenticator app, add an account and enter this key (or paste the setup URL):</p>
              <div className="rounded-md bg-white px-3 py-2 font-mono text-sm tracking-wider text-ink select-all">{setup.secret}</div>
              <details className="text-xs text-ink-3"><summary className="cursor-pointer">Setup URL</summary><div className="mt-1 break-all font-mono">{setup.otpauth_uri}</div></details>
              <Field label="Enter the 6-digit code to confirm">
                <div className="flex gap-2">
                  <Input value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)} inputMode="numeric" placeholder="123456" className="tracking-widest" />
                  <Button onClick={confirmEnable} loading={busy} disabled={!confirmCode.trim()}>Confirm</Button>
                  <Button variant="ghost" onClick={() => { setSetup(null); setConfirmCode(""); }}>Cancel</Button>
                </div>
              </Field>
            </div>
          )}

          {recoveryCodes && (
            <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
              <p className="text-sm font-medium text-amber-900">Save these recovery codes somewhere safe — each can be used once if you lose your authenticator. They won't be shown again.</p>
              <div className="mt-2 grid grid-cols-2 gap-1 font-mono text-sm text-amber-900 sm:grid-cols-4">
                {recoveryCodes.map((c) => <span key={c} className="rounded bg-white px-2 py-1 text-center">{c}</span>)}
              </div>
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setRecoveryCodes(null)}>I've saved them</Button>
            </div>
          )}
        </section>

        {/* --- active sessions --- */}
        <section>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">Active sessions</h3>
            <Button size="sm" variant="ghost" onClick={signOutOthers}>Sign out all other sessions</Button>
          </div>
          <div className="mt-2 divide-y divide-line rounded-lg border border-line">
            {sessions === null && <div className="p-3"><Skeleton className="h-4" /></div>}
            {sessions && sessions.length === 0 && <div className="p-3 text-sm text-ink-3">No active sessions.</div>}
            {sessions?.map((s) => (
              <div key={s.id} className="flex items-center gap-3 p-3 text-sm">
                <Laptop className="h-4 w-4 text-ink-3" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-ink">{s.user_agent || "Unknown device"} {s.current && <Badge tone="accent" className="ml-1">This device</Badge>}</div>
                  <div className="text-xs text-ink-3">{s.ip || "—"} · last used {timeAgo(s.last_used_at)} · started {formatDateTime(s.created_at)}</div>
                </div>
                {!s.current && <Button size="sm" variant="ghost" onClick={() => signOutSession(s.id)}>Sign out</Button>}
              </div>
            ))}
          </div>
        </section>

        {/* --- change password --- */}
        <section>
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink"><KeyRound className="h-4 w-4" /> Change password</h3>
          <form onSubmit={changePassword} className="grid gap-3 sm:grid-cols-3">
            <Field label="Current password"><Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required /></Field>
            <Field label="New password" hint="≥ 8 characters"><Input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required /></Field>
            <Field label="Confirm new password"><Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" minLength={8} required /></Field>
            <div className="sm:col-span-3 flex justify-end">
              <Button type="submit" size="sm" loading={pwBusy}>Update password</Button>
            </div>
          </form>
        </section>
      </CardBody>
    </Card>
  );
}
