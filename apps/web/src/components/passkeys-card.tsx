"use client";

/**
 * Passkeys (FIDO2 / WebAuthn).
 *
 *   GET    /passkeys
 *   POST   /passkeys/register/begin | /passkeys/register/finish
 *   PATCH  /passkeys/{id}
 *   DELETE /passkeys/{id}
 *
 * The browser does the cryptography. This file's whole job is to move base64url between the
 * API and `navigator.credentials`, which speaks ArrayBuffers — a mismatch that is the usual
 * cause of a passkey that "doesn't work" for no visible reason.
 *
 * WebAuthn is unavailable over plain HTTP away from localhost, and on a device with no
 * authenticator. Both are said plainly below rather than left as a button that does nothing.
 */

import { useCallback, useEffect, useState } from "react";
import { Fingerprint, Loader2, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { Badge, Button, ErrorBanner, Input, Skeleton } from "@/components/ui";
import type { PasskeyStatus } from "@/lib/types";

function b64urlToBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes.buffer;
}

function bufferToB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

type PublicKeyOptions = Record<string, unknown> & {
  challenge: string;
  user?: { id: string };
  allowCredentials?: { id: string }[];
  excludeCredentials?: { id: string }[];
};

/** The API sends base64url (JSON has no ArrayBuffer); the browser requires buffers. */
function decodeOptions(options: PublicKeyOptions): PublicKeyCredentialCreationOptions {
  const mapIds = (list?: { id: string }[]) =>
    list?.map((c) => ({ ...c, id: b64urlToBuffer(c.id) }));
  return {
    ...options,
    challenge: b64urlToBuffer(options.challenge),
    ...(options.user ? { user: { ...options.user, id: b64urlToBuffer(options.user.id) } } : {}),
    ...(options.allowCredentials ? { allowCredentials: mapIds(options.allowCredentials) } : {}),
    ...(options.excludeCredentials
      ? { excludeCredentials: mapIds(options.excludeCredentials) }
      : {}),
  } as unknown as PublicKeyCredentialCreationOptions;
}

function encodeCredential(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse &
    AuthenticatorAssertionResponse;
  const encoded: Record<string, unknown> = {
    id: credential.id,
    rawId: bufferToB64url(credential.rawId),
    type: credential.type,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToB64url(response.clientDataJSON),
    } as Record<string, unknown>,
  };
  const inner = encoded.response as Record<string, unknown>;
  if (response.attestationObject) {
    inner.attestationObject = bufferToB64url(response.attestationObject);
    if (typeof response.getTransports === "function") {
      encoded.transports = response.getTransports();
    }
  }
  if (response.authenticatorData) {
    inner.authenticatorData = bufferToB64url(response.authenticatorData);
    inner.signature = bufferToB64url(response.signature);
    inner.userHandle = response.userHandle ? bufferToB64url(response.userHandle) : null;
  }
  return encoded;
}

export function PasskeysCard() {
  const [state, setState] = useState<PasskeyStatus | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const supported =
    typeof window !== "undefined" &&
    typeof window.PublicKeyCredential !== "undefined" &&
    !!navigator.credentials;

  const load = useCallback(() => {
    api
      .get<PasskeyStatus>("/passkeys")
      .then(setState)
      .catch(() => setState({ enabled: false, rp_id: "", credentials: [], count: 0, has_fallback: true }));
  }, []);
  useEffect(load, [load]);

  async function enrol() {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const options = await api.post<PublicKeyOptions>("/passkeys/register/begin", {});
      const credential = (await navigator.credentials.create({
        publicKey: decodeOptions(options),
      })) as PublicKeyCredential | null;
      if (!credential) throw new Error("cancelled");
      await api.post("/passkeys/register/finish", {
        credential: encodeCredential(credential),
        label: label.trim(),
      });
      setLabel("");
      setNote("That passkey is registered. You can now use it to confirm sensitive actions.");
      load();
    } catch (e: unknown) {
      // A cancelled prompt is not a failure — the user closed a dialog and knows it.
      if (e instanceof DOMException && (e.name === "NotAllowedError" || e.name === "AbortError")) {
        setError("");
      } else if (e instanceof DOMException && e.name === "InvalidStateError") {
        setError("That device already has a passkey registered here.");
      } else {
        setError(e instanceof ApiError ? e.message : "That passkey could not be registered.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string, name: string) {
    if (!window.confirm(`Remove "${name}"? You will not be able to sign in with it again.`))
      return;
    setError("");
    setNote("");
    try {
      await api.del(`/passkeys/${id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That passkey could not be removed.");
    }
  }

  async function rename(id: string, current: string) {
    const next = window.prompt("Name this passkey", current);
    if (!next || next.trim() === current) return;
    try {
      await api.patch(`/passkeys/${id}`, { label: next.trim() });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That passkey could not be renamed.");
    }
  }

  if (state === null) return <Skeleton className="h-24" />;

  return (
    <section>
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
        <Fingerprint className="h-4 w-4" /> Passkeys
      </h3>

      {!state.enabled ? (
        <p className="text-sm text-ink-2">
          Passkeys are not enabled for this deployment. An administrator turns them on by
          setting the relying-party domain — they are bound to it, so it cannot be guessed.
        </p>
      ) : !supported ? (
        <p className="text-sm text-ink-2">
          This browser cannot use passkeys. They need a secure connection (HTTPS) and a device
          with a fingerprint reader, a screen lock, or a security key.
        </p>
      ) : (
        <>
          <p className="mb-3 text-sm text-ink-2">
            A passkey cannot be phished. It only ever signs for{" "}
            <span className="font-medium text-ink">{state.rp_id}</span>, so a convincing copy of
            this site gets nothing — unlike a 6-digit code, which can be read out over the phone
            to somebody claiming to be IT.
          </p>

          {error && <ErrorBanner message={error} />}
          {note && (
            <p className="mb-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              {note}
            </p>
          )}

          {state.credentials.length === 0 ? (
            <p className="mb-3 text-sm text-ink-3">No passkeys registered yet.</p>
          ) : (
            <ul className="mb-3 divide-y divide-line rounded border border-line">
              {state.credentials.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => rename(c.id, c.label)}
                        className="truncate text-sm text-ink hover:underline"
                      >
                        {c.label}
                      </button>
                      {c.backed_up && (
                        <span title="Synced to the account's cloud keychain, so it survives losing the device — and is present on every device signed into that account">
                          <Badge tone="neutral">synced</Badge>
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-ink-3">
                      added {formatDateTime(c.created_at)}
                      {c.last_used_at ? ` · last used ${timeAgo(c.last_used_at)}` : " · never used"}
                      {c.transports.length ? ` · ${c.transports.join(", ")}` : ""}
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => remove(c.id, c.label)}>
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}

          {!state.has_fallback && state.count === 1 && (
            <p className="mb-3 text-sm text-amber-700">
              This is the only way you can sign in. Add a second passkey before you lose the
              first one — there is no way back into the account without it.
            </p>
          )}

          <div className="flex flex-wrap items-end gap-2">
            <label className="text-sm">
              <span className="mb-1 block text-xs font-medium text-ink-2">Name it</span>
              <Input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Work laptop"
                maxLength={120}
              />
            </label>
            <Button size="sm" onClick={enrol} disabled={busy}>
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Fingerprint className="h-3.5 w-3.5" />
              )}
              Add a passkey
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
