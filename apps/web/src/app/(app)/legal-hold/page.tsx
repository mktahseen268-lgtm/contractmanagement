"use client";

/**
 * Legal holds — matter-scoped preservation.
 *
 *   GET/POST /legal-holds
 *   POST /legal-holds/{id}/release   needs a reason and a step-up challenge
 *   GET  /legal-holds/{id}/export    the preserved set, with audit chain positions
 *
 * Replaces the mockup. A hold blocks deletion, purge and archival for everything it covers,
 * and two matters can cover the same agreement — releasing one does not release the other.
 * That is why these are records rather than a checkbox.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Archive, FileDown, Lock, Plus, Scale, Unlock } from "lucide-react";
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
  Textarea,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import type { ContractListItem, LegalHold, Paginated } from "@/lib/types";

export default function LegalHoldPage() {
  const [holds, setHolds] = useState<LegalHold[] | null>(null);
  const [contracts, setContracts] = useState<ContractListItem[]>([]);
  const [showReleased, setShowReleased] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    api
      .get<LegalHold[]>(`/legal-holds?include_released=${showReleased}`)
      .then(setHolds)
      .catch((e) => {
        setHolds([]);
        setError(e instanceof ApiError ? e.message : "");
      });
  }, [showReleased]);
  useEffect(load, [load]);

  useEffect(() => {
    api
      .get<Paginated<ContractListItem>>("/contracts?page_size=200")
      .then((r) => setContracts(r.items))
      .catch(() => setContracts([]));
  }, []);

  async function release(hold: LegalHold) {
    const reason = window.prompt(
      `Release "${hold.matter}"? Anything not covered by another matter becomes eligible for archival and purge again.\n\nWhy is it being released?`,
    );
    if (!reason?.trim()) return;
    setError("");
    try {
      await api.post(`/legal-holds/${hold.id}/release`, { reason: reason.trim() });
      setNote(`Released "${hold.matter}".`);
      load();
    } catch (e) {
      // A 401 here is a step-up challenge, not a refusal — the API is asking the user to
      // confirm who they are before an irreversible preservation change.
      const message =
        e instanceof ApiError && e.status === 401
          ? "Releasing a hold needs you to confirm your identity. Re-enter your password in Settings → Security, then try again."
          : e instanceof ApiError
            ? e.message
            : "That hold could not be released.";
      setError(message);
    }
  }

  return (
    <div>
      <PageHeader
        title="Legal holds"
        subtitle="Preservation that overrides retention — deletion, purge and archival all blocked"
        actions={
          <Button size="sm" onClick={() => setCreating((v) => !v)}>
            <Plus className="h-3.5 w-3.5" /> Place a hold
          </Button>
        }
      />

      <div className="space-y-4 p-6">
        {error && <ErrorBanner message={error} />}
        {note && (
          <Card className="border-accent/50">
            <CardBody className="py-2 text-sm text-ink-2">{note}</CardBody>
          </Card>
        )}

        {creating && (
          <HoldForm
            contracts={contracts}
            onCancel={() => setCreating(false)}
            onSaved={() => {
              setCreating(false);
              load();
            }}
            onError={setError}
          />
        )}

        <label className="inline-flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={showReleased}
            onChange={(e) => setShowReleased(e.target.checked)}
          />
          Include released matters
        </label>

        {holds === null && <Skeleton className="h-32" />}

        {holds?.length === 0 && (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-2">
              <Scale className="mx-auto mb-3 h-10 w-10 text-ink-3" />
              <div className="text-base font-semibold text-ink">No active holds</div>
              <p className="mt-1">
                A hold preserves agreements for a matter — litigation, a regulator enquiry, an
                internal investigation — and overrides the retention schedule while it stands.
              </p>
            </CardBody>
          </Card>
        )}

        {holds?.map((hold) => (
          <Card key={hold.id}>
            <CardBody className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {hold.status === "active" ? (
                  <Lock className="h-4 w-4 text-red-600" />
                ) : (
                  <Unlock className="h-4 w-4 text-ink-3" />
                )}
                <span className="text-sm font-semibold text-ink">{hold.matter}</span>
                {hold.reference && (
                  <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[10px] text-ink-3">
                    {hold.reference}
                  </span>
                )}
                <Badge tone={hold.status === "active" ? "accent" : "neutral"}>
                  {hold.status}
                </Badge>
                <span className="text-[11px] text-ink-3">
                  {hold.contract_ids.length} agreement
                  {hold.contract_ids.length === 1 ? "" : "s"} · placed{" "}
                  {formatDate(hold.placed_at)}
                </span>
              </div>

              {hold.reason && <p className="text-sm text-ink-2">{hold.reason}</p>}
              {hold.custodian && (
                <p className="text-xs text-ink-3">Custodian: {hold.custodian}</p>
              )}
              {hold.status === "released" && (
                <p className="text-xs text-ink-3">
                  Released {formatDate(hold.released_at)} — {hold.release_reason}
                </p>
              )}

              <div className="flex flex-wrap gap-2 pt-1">
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/legal-holds/${hold.id}/export`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
                >
                  <FileDown className="h-3.5 w-3.5" /> Export the preserved set
                </a>
                {hold.status === "active" && (
                  <Button size="sm" variant="ghost" onClick={() => release(hold)}>
                    <Unlock className="h-3.5 w-3.5" /> Release
                  </Button>
                )}
              </div>

              <details className="pt-1">
                <summary className="cursor-pointer text-xs text-ink-3">
                  Agreements covered
                </summary>
                <div className="mt-1 space-y-0.5">
                  {hold.contract_ids.map((id) => {
                    const contract = contracts.find((c) => c.id === id);
                    return (
                      <Link
                        key={id}
                        href={`/contracts/${id}`}
                        className="block text-xs text-ink-2 hover:text-ink"
                      >
                        <Archive className="mr-1 inline h-3 w-3" />
                        {contract ? `${contract.reference_no} — ${contract.title}` : id}
                      </Link>
                    );
                  })}
                </div>
              </details>
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}

function HoldForm({
  contracts,
  onCancel,
  onSaved,
  onError,
}: {
  contracts: ContractListItem[];
  onCancel: () => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [matter, setMatter] = useState("");
  const [reference, setReference] = useState("");
  const [custodian, setCustodian] = useState("");
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (selected.length === 0) {
      onError("A hold has to cover at least one agreement.");
      return;
    }
    setBusy(true);
    onError("");
    try {
      await api.post("/legal-holds", {
        matter: matter.trim(),
        reference: reference.trim(),
        custodian: custodian.trim(),
        reason: reason.trim(),
        contract_ids: selected,
      });
      onSaved();
    } catch (e: unknown) {
      onError(e instanceof ApiError ? e.message : "That hold could not be placed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Place a legal hold</CardTitle>
      </CardHeader>
      <CardBody>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-12">
          <div className="sm:col-span-5">
            <Field label="Matter">
              <Input
                value={matter}
                onChange={(e) => setMatter(e.target.value)}
                required
                placeholder="SBP enquiry — merchant acquiring"
              />
            </Field>
          </div>
          <div className="sm:col-span-3">
            <Field label="Reference">
              <Input value={reference} onChange={(e) => setReference(e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-4">
            <Field label="Custodian">
              <Input
                value={custodian}
                onChange={(e) => setCustodian(e.target.value)}
                placeholder="Head of Legal"
              />
            </Field>
          </div>
          <div className="sm:col-span-12">
            <Field label="Reason">
              <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-12">
            <Field
              label="Agreements to preserve"
              hint="Hold Ctrl or Cmd to pick several"
            >
              <Select
                multiple
                size={8}
                value={selected}
                onChange={(e) =>
                  setSelected(
                    Array.from(e.target.selectedOptions).map((o) => o.value),
                  )
                }
              >
                {contracts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.reference_no} — {c.title}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-12">
            <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={busy}>
              Place the hold ({selected.length})
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
