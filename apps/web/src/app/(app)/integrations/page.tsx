"use client";

/**
 * Integrations — what this deployment is actually wired to.
 *
 *   GET  /connectors             Teams, SharePoint, calendar, SIEM, SMS, SOAP status
 *   POST /connectors/teams/test  post a test card to the configured channel
 *   GET/POST/DELETE /webhooks    outbound webhooks
 *
 * Replaces the mockup, which listed integrations that were not connected to anything.
 * Everything here is read from the running service: a connector shown as configured is one
 * that is configured, and one shown as off will not fire.
 *
 * Nothing on this page is a secret. Destinations and on/off states only — webhook signing
 * secrets are never returned by the API and are not rendered here.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  Check,
  MessageSquare,
  Plug,
  Plus,
  Radio,
  Send,
  Server,
  Trash2,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorBanner,
  Field,
  Input,
  Skeleton,
} from "@/components/ui";
import type { ConnectorStatus, WebhookEndpoint } from "@/lib/types";

export default function IntegrationsPage() {
  const { me } = useAuth();
  const role = me?.user.role;
  const canManage = role === "owner" || role === "admin" || role === "manager";

  const [status, setStatus] = useState<ConnectorStatus | null>(null);
  const [webhooks, setWebhooks] = useState<WebhookEndpoint[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [testing, setTesting] = useState(false);

  const load = useCallback(() => {
    api.get<ConnectorStatus>("/connectors").then(setStatus).catch(() => setStatus(null));
    api.get<WebhookEndpoint[]>("/webhooks").then(setWebhooks).catch(() => setWebhooks([]));
  }, []);
  useEffect(load, [load]);

  async function testTeams() {
    setTesting(true);
    setError("");
    setNote("");
    try {
      const result = await api.post<{ delivered: boolean }>("/connectors/teams/test", {});
      setNote(
        result.delivered
          ? "Test card delivered — check the channel."
          : "The webhook did not accept the message. Check the URL.",
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The test could not be sent.");
    } finally {
      setTesting(false);
    }
  }

  async function removeWebhook(hook: WebhookEndpoint) {
    if (!window.confirm(`Stop sending events to ${hook.url}?`)) return;
    try {
      await api.del(`/webhooks/${hook.id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove that webhook.");
    }
  }

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="What this deployment sends to, and what it accepts from"
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}
        {note && (
          <Card className="border-accent/50">
            <CardBody className="py-2 text-sm text-ink-2">{note}</CardBody>
          </Card>
        )}

        {status === null ? (
          <Skeleton className="h-48" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Connector
              icon={MessageSquare}
              name="Microsoft Teams"
              on={status.teams.enabled}
              detail={
                status.teams.enabled
                  ? `Posts adaptive cards on ${status.teams.events.length} workflow events.`
                  : "Set TEAMS_ENABLED and a channel webhook URL to turn this on."
              }
              action={
                status.teams.enabled && canManage ? (
                  <Button size="sm" variant="ghost" loading={testing} onClick={testTeams}>
                    <Send className="h-3.5 w-3.5" /> Send a test
                  </Button>
                ) : null
              }
            />

            <Connector
              icon={Server}
              name="SharePoint"
              on={status.sharepoint.enabled}
              detail={
                status.sharepoint.enabled
                  ? `Executed agreements copied to ${status.sharepoint.library} at ${status.sharepoint.site_url}.`
                  : "Set SHAREPOINT_ENABLED, the site URL and a library to sync executed agreements."
              }
              footnote={
                status.sharepoint.enabled && !status.sharepoint.authenticated
                  ? "No token configured — uploads will be rejected."
                  : "A copy, not a move: the system of record stays here."
              }
            />

            <Connector
              icon={Calendar}
              name="Calendar invites"
              on={status.calendar.enabled}
              detail="Renewal and review dates as .ics attachments on mail already being sent."
              footnote="No configuration and nothing to rotate — every mail client understands it, including on-prem Exchange."
            />

            <Connector
              icon={Radio}
              name="SIEM"
              on={status.siem.enabled}
              detail={
                status.siem.enabled
                  ? `Security events to ${status.siem.host} as ${status.siem.format.toUpperCase()}${status.siem.tls ? " over TLS" : ""}.`
                  : "Set SIEM_ENABLED and a collector host to ship security events."
              }
              footnote="A projection of the audit log — an outage is replayable, never lost."
            />

            <Connector
              icon={MessageSquare}
              name="SMS"
              on={status.sms.enabled}
              detail={`Backend: ${status.sms.backend}. Used for signing OTPs and reminders.`}
              footnote={
                status.sms.backend === "console"
                  ? "Console backend — messages are logged, never sent."
                  : undefined
              }
            />

            <Connector
              icon={Plug}
              name="SOAP"
              on={status.soap.enabled}
              detail={
                status.soap.enabled
                  ? "Legacy core-banking interface is accepting requests."
                  : "Off. An unused SOAP endpoint is attack surface with no user."
              }
              footnote={status.soap.enabled ? `WSDL at ${status.soap.wsdl}` : undefined}
            />
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              Outbound webhooks
              {canManage && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => setCreating((v) => !v)}
                >
                  <Plus className="h-3.5 w-3.5" /> Add
                </Button>
              )}
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {creating && (
              <WebhookForm
                onCancel={() => setCreating(false)}
                onSaved={() => {
                  setCreating(false);
                  load();
                }}
                onError={setError}
              />
            )}

            {webhooks === null && <Skeleton className="h-16" />}
            {webhooks?.length === 0 && (
              <p className="py-2 text-sm text-ink-3">
                No webhooks. Add one to push contract events into another system.
              </p>
            )}
            {webhooks?.map((hook) => (
              <div
                key={hook.id}
                className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2"
              >
                <Badge tone={hook.is_active ? "accent" : "neutral"}>
                  {hook.is_active ? "active" : "paused"}
                </Badge>
                <code className="flex-1 truncate font-mono text-xs text-ink">{hook.url}</code>
                <span className="text-[11px] text-ink-3">
                  {hook.events.length ? hook.events.join(", ") : "all events"}
                </span>
                {canManage && (
                  <button
                    onClick={() => removeWebhook(hook)}
                    className="p-1 text-ink-3 hover:text-ink"
                    title="Remove"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
            <p className="pt-1 text-xs text-ink-3">
              Each delivery is signed with an HMAC the receiving system verifies. The signing
              secret is shown once when the webhook is created and never again.
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Connector({
  icon: Icon,
  name,
  on,
  detail,
  footnote,
  action,
}: {
  icon: typeof Plug;
  name: string;
  on: boolean;
  detail: string;
  footnote?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card>
      <CardBody className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Icon className="h-4 w-4 text-accent" />
          <span className="text-sm font-semibold text-ink">{name}</span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ${
              on ? "bg-emerald-100 text-emerald-800" : "bg-surface-3 text-ink-3"
            }`}
          >
            {on ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
            {on ? "connected" : "off"}
          </span>
        </div>
        <p className="text-xs text-ink-2">{detail}</p>
        {footnote && (
          <p className="flex items-start gap-1 text-[11px] text-ink-3">
            {footnote.startsWith("No token") && (
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" />
            )}
            {footnote}
          </p>
        )}
        {action}
      </CardBody>
    </Card>
  );
}

function WebhookForm({
  onCancel,
  onSaved,
  onError,
}: {
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState("");
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      const created = await api.post<{ secret?: string }>("/webhooks", {
        url: url.trim(),
        events: events.split(",").map((s) => s.trim()).filter(Boolean),
      });
      // Shown once. The API stores only a hash, so there is no second chance to read it —
      // saying so here is the difference between a copied secret and a support ticket.
      if (created.secret) setSecret(created.secret);
      else onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "Couldn't create that webhook.");
    } finally {
      setBusy(false);
    }
  }

  if (secret) {
    return (
      <div className="space-y-2 rounded-md border border-accent/50 p-3">
        <div className="text-sm font-medium text-ink">Signing secret</div>
        <code className="block break-all rounded bg-surface-3 p-2 font-mono text-xs">
          {secret}
        </code>
        <p className="text-xs text-ink-3">
          Copy it now — only a hash is stored, so this cannot be shown again.
        </p>
        <Button size="sm" onClick={onSaved}>
          Done
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={save} className="grid gap-2 rounded-md bg-surface-2 p-2 sm:grid-cols-12">
      <div className="sm:col-span-6">
        <Field label="Endpoint URL">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://internal.mmbl.test/hooks/contracts"
          />
        </Field>
      </div>
      <div className="sm:col-span-4">
        <Field label="Events" hint="Comma-separated; blank means all">
          <Input
            value={events}
            onChange={(e) => setEvents(e.target.value)}
            placeholder="contract.signed, contract.terminated"
          />
        </Field>
      </div>
      <div className="flex items-end gap-2 pb-1 sm:col-span-2">
        <Button type="submit" size="sm" loading={busy}>
          Create
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
