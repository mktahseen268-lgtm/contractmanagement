"use client";

/**
 * Temporary access — time-bound links for external collaborators.
 *
 *   GET/POST /contracts/{id}/temporary-access
 *   DELETE   /temporary-access/{id}
 *
 * Replaces the mockup. The link is shown once: only its hash is stored, so it cannot be
 * retrieved again — and a link that leaks from a mailbox is not replayable out of the
 * database if the database is later exposed.
 *
 * Watermarks name the viewer. That does not prevent a screenshot; it makes one attributable,
 * which is the actual deterrent.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Ban,
  Check,
  Clock,
  Copy,
  Download,
  Eye,
  Link2,
  MessageSquare,
  Plus,
  Stamp,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
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
  Select,
  Skeleton,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import type { ContractListItem, Paginated, TemporaryAccess } from "@/lib/types";

export default function TemporaryAccessPage() {
  const [contracts, setContracts] = useState<ContractListItem[] | null>(null);
  const [contractId, setContractId] = useState("");
  const [links, setLinks] = useState<TemporaryAccess[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [issued, setIssued] = useState<{ url: string; email: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<Paginated<ContractListItem>>("/contracts?page_size=100")
      .then((r) => {
        setContracts(r.items);
        if (r.items.length) setContractId(r.items[0].id);
      })
      .catch(() => setContracts([]));
  }, []);

  const load = useCallback(() => {
    if (!contractId) return;
    api
      .get<TemporaryAccess[]>(`/contracts/${contractId}/temporary-access`)
      .then(setLinks)
      .catch(() => setLinks([]));
  }, [contractId]);
  useEffect(load, [load]);

  async function revoke(link: TemporaryAccess) {
    if (!window.confirm(`Revoke access for ${link.email}? The link stops working at once.`))
      return;
    setError("");
    try {
      await api.del(`/temporary-access/${link.id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That link could not be revoked.");
    }
  }

  return (
    <div>
      <PageHeader
        title="Temporary access"
        subtitle="Time-bound, scoped, revocable links for people outside the workspace"
        actions={
          contractId ? (
            <Button size="sm" onClick={() => setCreating((v) => !v)}>
              <Plus className="h-3.5 w-3.5" /> New link
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}

        {issued && (
          <Card className="border-accent/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Link2 className="h-4 w-4" /> Link for {issued.email}
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              <code className="block break-all rounded bg-surface-3 p-2 font-mono text-xs">
                {issued.url}
              </code>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    void navigator.clipboard?.writeText(issued.url);
                    setCopied(true);
                    window.setTimeout(() => setCopied(false), 1500);
                  }}
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? "Copied" : "Copy the link"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setIssued(null)}>
                  Done
                </Button>
              </div>
              <p className="text-xs text-ink-3">
                Copy it now. Only a hash is stored, so this cannot be shown again — which is
                also why a leaked link cannot be recovered from the database.
              </p>
            </CardBody>
          </Card>
        )}

        {contracts === null ? (
          <Skeleton className="h-24" />
        ) : contracts.length === 0 ? (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-2">
              No agreements yet.
            </CardBody>
          </Card>
        ) : (
          <>
            <Card>
              <CardBody>
                <Field label="Agreement">
                  <Select
                    value={contractId}
                    onChange={(e) => {
                      setContractId(e.target.value);
                      setIssued(null);
                    }}
                  >
                    {contracts.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.reference_no} — {c.title}
                      </option>
                    ))}
                  </Select>
                </Field>
              </CardBody>
            </Card>

            {creating && (
              <LinkForm
                contractId={contractId}
                onCancel={() => setCreating(false)}
                onIssued={(url, email) => {
                  setCreating(false);
                  setIssued({ url, email });
                  load();
                }}
                onError={setError}
              />
            )}

            {links === null && <Skeleton className="h-24" />}
            {links?.length === 0 && (
              <Card>
                <CardBody className="py-8 text-center text-sm text-ink-2">
                  <Link2 className="mx-auto mb-3 h-9 w-9 text-ink-3" />
                  <div className="text-base font-semibold text-ink">No links yet</div>
                  <p className="mt-1">
                    Give outside counsel or a counterparty a scoped, expiring view without
                    creating them an account.
                  </p>
                </CardBody>
              </Card>
            )}

            {links?.map((link) => (
              <Card key={link.id}>
                <CardBody className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">
                      {link.name || link.email}
                    </span>
                    {link.organisation && (
                      <span className="text-xs text-ink-3">{link.organisation}</span>
                    )}
                    <Badge tone={link.status === "active" ? "accent" : "neutral"}>
                      {link.status}
                    </Badge>
                    <span className="inline-flex items-center gap-1 text-[11px] text-ink-3">
                      {link.scope === "comment" ? (
                        <MessageSquare className="h-3 w-3" />
                      ) : (
                        <Eye className="h-3 w-3" />
                      )}
                      {link.scope}
                    </span>
                    {link.watermark && (
                      <span
                        className="inline-flex items-center gap-1 text-[11px] text-ink-3"
                        title="The viewer's name and the time are stamped across every page"
                      >
                        <Stamp className="h-3 w-3" /> watermarked
                      </span>
                    )}
                    {link.allow_download && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
                        <Download className="h-3 w-3" /> download allowed
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-3">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" /> expires {formatDate(link.expires_at)}
                    </span>
                    <span>
                      {link.view_count} view{link.view_count === 1 ? "" : "s"}
                      {link.last_seen_at && ` · last ${formatDate(link.last_seen_at)}`}
                    </span>
                  </div>
                  {link.status === "active" && (
                    <Button size="sm" variant="ghost" onClick={() => revoke(link)}>
                      <Ban className="h-3.5 w-3.5" /> Revoke
                    </Button>
                  )}
                </CardBody>
              </Card>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function LinkForm({
  contractId,
  onCancel,
  onIssued,
  onError,
}: {
  contractId: string;
  onCancel: () => void;
  onIssued: (url: string, email: string) => void;
  onError: (m: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [organisation, setOrganisation] = useState("");
  const [scope, setScope] = useState("view");
  const [days, setDays] = useState(14);
  const [watermark, setWatermark] = useState(true);
  const [allowDownload, setAllowDownload] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError("");
    try {
      const created = await api.post<TemporaryAccess & { url: string }>(
        `/contracts/${contractId}/temporary-access`,
        {
          email: email.trim(),
          name: name.trim(),
          organisation: organisation.trim(),
          scope,
          days: Number(days) || 14,
          watermark,
          allow_download: allowDownload,
        },
      );
      onIssued(created.url, created.email);
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "That link could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New temporary link</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-4">
            <Field label="Email">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Organisation">
              <Input
                value={organisation}
                onChange={(e) => setOrganisation(e.target.value)}
              />
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="They may">
              <Select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="view">View only</option>
                <option value="comment">View and comment</option>
              </Select>
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Days" hint="1–90">
              <Input
                type="number"
                min={1}
                max={90}
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </Field>
          </div>
          <div className="flex items-end gap-4 pb-2 sm:col-span-7">
            <label className="inline-flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={watermark}
                onChange={(e) => setWatermark(e.target.checked)}
              />
              Watermark with their name
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={allowDownload}
                onChange={(e) => setAllowDownload(e.target.checked)}
              />
              Allow download
            </label>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              Create the link
            </Button>
          </div>
        </form>
        <p className="mt-2 text-xs text-ink-3">
          Without download, the document is served for viewing only. That is the honest limit
          of what a server can enforce — a determined viewer can still keep what their browser
          received, which is why the watermark that names them is the control that matters.
        </p>
      </CardBody>
    </Card>
  );
}
