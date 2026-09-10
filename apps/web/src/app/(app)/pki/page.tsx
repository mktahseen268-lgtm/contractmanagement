"use client";

/**
 * PKI console — CA status, the Registration Authority queue, the certificate register and the
 * trust store. Every panel is backed by a real endpoint under /pki; nothing here is sample data.
 *
 * The tab layout follows the operator's actual workflow rather than the data model: you arrive
 * to answer "is the PKI healthy?", then "what needs my approval?", then "who holds what".
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Ban,
  CheckCircle2,
  Clock,
  Cpu,
  FileKey,
  Landmark,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { api, ApiError, qs } from "@/lib/api";
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
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui";
import { titleCase } from "@/lib/utils";
import type {
  CertificateList,
  Certificate,
  CertificateRequestRow,
  PkiHealth,
  TrustAnchor,
  ValidationResult,
} from "@/lib/types";
import { REVOCATION_REASONS } from "@/lib/types";

type Tab = "overview" | "requests" | "certificates" | "trust";

const TABS: { key: Tab; label: string; icon: typeof ShieldCheck }[] = [
  { key: "overview", label: "Overview", icon: ShieldCheck },
  { key: "requests", label: "Registration Authority", icon: UserCheck },
  { key: "certificates", label: "Certificates", icon: FileKey },
  { key: "trust", label: "Trust store", icon: Landmark },
];

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** Show the CN rather than the full RFC 4514 DN — the DN is unreadable in a table cell. */
function cn(dn: string): string {
  const m = /CN=([^,]+)/.exec(dn);
  return m ? m[1] : dn;
}

function statusTone(status: string): "neutral" | "accent" | "ai" {
  if (status === "active" || status === "issued" || status === "approved") return "accent";
  return "neutral";
}

export default function PkiPage() {
  const { me } = useAuth();
  const isAdmin = me?.user.role === "owner" || me?.user.role === "admin";
  const [tab, setTab] = useState<Tab>("overview");
  const [health, setHealth] = useState<PkiHealth | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadHealth = useCallback(() => {
    api
      .get<PkiHealth>("/pki/health", { cache: false })
      .then(setHealth)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load PKI status."));
  }, []);

  useEffect(loadHealth, [loadHealth]);

  async function provision() {
    setBusy(true);
    setError("");
    try {
      setHealth(await api.post<PkiHealth>("/pki/provision"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not provision the PKI.");
    } finally {
      setBusy(false);
    }
  }

  if (health === null) {
    return (
      <div className="space-y-4">
        <PageHeader title="Public Key Infrastructure" subtitle="Certificate authority, enrolment and revocation" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Public Key Infrastructure"
        subtitle="Certificate authority, enrolment, revocation, CRL and OCSP"
        actions={
          <Button variant="ghost" onClick={loadHealth}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      {error && <ErrorBanner message={error} />}

      {!health.provisioned ? (
        <NotProvisioned isAdmin={isAdmin} busy={busy} onProvision={provision} />
      ) : (
        <>
          <nav className="flex flex-wrap gap-1 border-b border-line">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition ${
                  tab === key
                    ? "border-accent text-accent"
                    : "border-transparent text-ink-2 hover:text-ink"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
                {key === "requests" && health.pending_requests > 0 && (
                  <Badge tone="accent">{health.pending_requests}</Badge>
                )}
              </button>
            ))}
          </nav>

          {tab === "overview" && <Overview health={health} isAdmin={isAdmin} onChange={loadHealth} />}
          {tab === "requests" && <Requests isAdmin={isAdmin} onChange={loadHealth} />}
          {tab === "certificates" && <Certificates isAdmin={isAdmin} onChange={loadHealth} />}
          {tab === "trust" && <TrustStore isAdmin={isAdmin} />}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------- not provisioned

function NotProvisioned({
  isAdmin,
  busy,
  onProvision,
}: {
  isAdmin: boolean;
  busy: boolean;
  onProvision: () => void;
}) {
  return (
    <Card>
      <CardBody className="space-y-4 py-10 text-center">
        <ShieldCheck className="mx-auto h-10 w-10 text-ink-3" />
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">No certificate authority yet</h2>
          <p className="mx-auto mt-1 max-w-lg text-sm text-ink-2">
            Provisioning creates an offline root CA, an online issuing CA beneath it, and a
            delegated OCSP responder. Every signatory is then issued their own certificate — no
            shared or role-based certificates.
          </p>
        </div>
        {isAdmin ? (
          <Button onClick={onProvision} disabled={busy}>
            {busy ? "Generating keys…" : "Provision the PKI"}
          </Button>
        ) : (
          <p className="text-sm text-ink-3">Ask an owner or admin to provision it.</p>
        )}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------- overview

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className={`font-display text-2xl font-semibold ${tone ?? "text-ink"}`}>{value}</div>
      <div className="text-xs text-ink-2">{label}</div>
    </div>
  );
}

function CaCard({ ca, label }: { ca: PkiHealth["root_ca"]; label: string }) {
  if (!ca) return null;
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-ink">{cn(ca.subject_dn)}</div>
          <div className="text-xs text-ink-2">{label}</div>
        </div>
        {ca.is_offline && <Badge tone="accent">offline</Badge>}
      </div>
      <dl className="mt-2 space-y-1 text-xs text-ink-2">
        <div className="flex justify-between gap-2">
          <dt>Algorithm</dt>
          <dd className="font-mono text-ink">{ca.key_algorithm}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Serial</dt>
          <dd className="truncate font-mono text-ink" title={ca.serial_number}>
            {ca.serial_number.slice(0, 16)}…
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Expires</dt>
          <dd className="text-ink">{fmtDate(ca.not_after)}</dd>
        </div>
      </dl>
    </div>
  );
}

function Overview({
  health,
  isAdmin,
  onChange,
}: {
  health: PkiHealth;
  isAdmin: boolean;
  onChange: () => void;
}) {
  const [exported, setExported] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function takeOffline() {
    if (!health.root_ca) return;
    if (
      !window.confirm(
        "This exports the root CA private key once and destroys it from the online keystore. " +
          "You must store it on offline media immediately — it cannot be recovered. Continue?",
      )
    )
      return;
    try {
      const res = await api.post<{ private_key_pem: string }>(`/pki/cas/${health.root_ca.id}/offline`);
      setExported(res.private_key_pem);
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not take the root offline.");
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      {health.warnings.length > 0 && (
        <Card className="border-amber-300/60 bg-amber-50/50 dark:bg-amber-950/20">
          <CardBody className="space-y-2 py-3">
            {health.warnings.map((w) => (
              <div key={w} className="flex items-start gap-2 text-sm text-ink-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <span>{w}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Active" value={health.certificates_active} tone="text-accent" />
        <Stat label="Expiring in 30 days" value={health.certificates_expiring_30d} />
        <Stat label="Suspended" value={health.certificates_suspended} />
        <Stat label="Revoked" value={health.certificates_revoked} />
        <Stat label="Pending enrolments" value={health.pending_requests} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Certificate authority chain</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            <CaCard ca={health.root_ca} label="Root CA (offline)" />
            <div className="pl-4">
              <CaCard ca={health.issuing_ca} label="Issuing CA" />
            </div>
            <div className="pl-8">
              <CaCard ca={health.ocsp_responder} label="OCSP responder" />
            </div>
            {isAdmin && health.root_ca && !health.root_offline && (
              <Button variant="ghost" onClick={takeOffline}>
                Run root offlining ceremony
              </Button>
            )}
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Key custody</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-ink-3" />
                <span className="text-ink-2">Keystore</span>
                <Badge tone={health.keystore_provider === "pkcs11" ? "accent" : "neutral"}>
                  {health.keystore_provider === "pkcs11" ? "PKCS#11 / HSM" : "Software"}
                </Badge>
              </div>
              {health.hsm_connected !== null && (
                <div className="flex items-center gap-2">
                  {health.hsm_connected ? (
                    <CheckCircle2 className="h-4 w-4 text-accent" />
                  ) : (
                    <Ban className="h-4 w-4 text-red-500" />
                  )}
                  <span className="text-ink-2">{health.hsm_detail || "—"}</span>
                </div>
              )}
              <div className="flex items-center gap-2">
                <UserCheck className="h-4 w-4 text-ink-3" />
                <span className="text-ink-2">RA dual control</span>
                <Badge tone={health.dual_control ? "accent" : "neutral"}>
                  {health.dual_control ? "on" : "off"}
                </Badge>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Revocation publishing</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-ink-2">CRL number</span>
                <span className="font-mono text-ink">{health.crl_number}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-2">Last published</span>
                <span className="text-ink">{fmt(health.crl_last_published)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-2">Next update</span>
                <span className={health.crl_stale ? "text-red-500" : "text-ink"}>
                  {fmt(health.crl_next_update)}
                </span>
              </div>
              {health.issuing_ca && (
                <div className="flex flex-wrap gap-2 pt-1">
                  <a
                    className="text-xs font-medium text-accent hover:underline"
                    href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/pki/crl/${health.issuing_ca.id}.crl`}
                  >
                    Download CRL
                  </a>
                  <a
                    className="text-xs font-medium text-accent hover:underline"
                    href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/pki/ca/${health.issuing_ca.id}.cer`}
                  >
                    Download CA certificate
                  </a>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      {exported && (
        <Card className="border-red-300">
          <CardHeader>
            <CardTitle>Root private key — shown once</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <p className="text-sm text-ink-2">
              Copy this to offline media now. It is not stored anywhere and will not be shown again.
            </p>
            <Textarea readOnly rows={8} value={exported} className="font-mono text-[11px]" />
            <Button variant="ghost" onClick={() => setExported(null)}>
              I have stored it securely
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------- RA queue

function Requests({ isAdmin, onChange }: { isAdmin: boolean; onChange: () => void }) {
  const [rows, setRows] = useState<CertificateRequestRow[] | null>(null);
  const [filter, setFilter] = useState("pending");
  const [error, setError] = useState("");
  const [note, setNote] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api
      .get<CertificateRequestRow[]>(`/pki/requests${qs({ status: filter })}`, { cache: false })
      .then(setRows)
      .catch(() => setRows([]));
  }, [filter]);

  useEffect(load, [load]);

  async function act(id: string, action: "approve" | "reject" | "issue") {
    setError("");
    try {
      await api.post(`/pki/requests/${id}/${action}`, action === "issue" ? undefined : { note: note[id] ?? "" });
      load();
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `Could not ${action} the request.`);
    }
  }

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}
      <div className="flex items-center gap-2">
        <Select value={filter} onChange={(e) => setFilter(e.target.value)} className="w-48">
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="issued">Issued</option>
          <option value="rejected">Rejected</option>
          <option value="">All</option>
        </Select>
      </div>

      {rows === null ? (
        <Skeleton className="h-32 w-full" />
      ) : rows.length === 0 ? (
        <Card>
          <CardBody className="py-10 text-center text-sm text-ink-2">
            No {filter || ""} enrolment requests.
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => (
            <Card key={r.id}>
              <CardBody className="space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium text-ink">{r.subject_name || cn(r.subject_dn)}</div>
                    <div className="truncate text-xs text-ink-2" title={r.subject_dn}>
                      {r.subject_dn}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">{r.profile}</Badge>
                    <Badge tone={statusTone(r.status)}>{titleCase(r.status)}</Badge>
                  </div>
                </div>

                <dl className="grid gap-2 text-xs text-ink-2 sm:grid-cols-3">
                  <div>
                    <dt className="text-ink-3">Requested</dt>
                    <dd className="text-ink">{fmt(r.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">First approval</dt>
                    <dd className="text-ink">{r.reviewed_at ? fmt(r.reviewed_at) : "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">Second approval</dt>
                    <dd className="text-ink">{r.second_reviewed_at ? fmt(r.second_reviewed_at) : "—"}</dd>
                  </div>
                </dl>

                {/* The evidence that bound this subject's identity — what an RA officer is
                    actually being asked to judge. */}
                {Object.keys(r.evidence ?? {}).length > 0 && (
                  <details className="rounded-md border border-line bg-surface-2 p-2 text-xs">
                    <summary className="cursor-pointer font-medium text-ink-2">Identity evidence</summary>
                    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-[11px] text-ink-2">
                      {JSON.stringify(r.evidence, null, 2)}
                    </pre>
                  </details>
                )}

                {isAdmin && (r.status === "pending" || r.status === "approved") && (
                  <div className="flex flex-wrap items-end gap-2">
                    {r.status === "pending" && (
                      <>
                        <div className="min-w-[200px] flex-1">
                          <Field label="Review note">
                            <Input
                              value={note[r.id] ?? ""}
                              onChange={(e) => setNote((n) => ({ ...n, [r.id]: e.target.value }))}
                              placeholder="How was this identity verified?"
                            />
                          </Field>
                        </div>
                        <Button onClick={() => act(r.id, "approve")}>
                          <CheckCircle2 className="h-4 w-4" /> Approve
                        </Button>
                        <Button variant="ghost" onClick={() => act(r.id, "reject")}>
                          <Ban className="h-4 w-4" /> Reject
                        </Button>
                      </>
                    )}
                    {r.status === "approved" && (
                      <Button onClick={() => act(r.id, "issue")}>
                        <BadgeCheck className="h-4 w-4" /> Issue certificate
                      </Button>
                    )}
                  </div>
                )}
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------- register

function Certificates({ isAdmin, onChange }: { isAdmin: boolean; onChange: () => void }) {
  const [data, setData] = useState<CertificateList | null>(null);
  const [status, setStatus] = useState("active");
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState<Certificate | null>(null);

  const load = useCallback(() => {
    api
      .get<CertificateList>(`/pki/certificates${qs({ status, q, page_size: 50 })}`, { cache: false })
      .then(setData)
      .catch(() => setData({ items: [], total: 0, page: 1, page_size: 50 }));
  }, [status, q]);

  useEffect(load, [load]);

  async function act(cert: Certificate, action: "renew" | "suspend" | "resume") {
    setError("");
    try {
      await api.post(`/pki/certificates/${cert.id}/${action}`, action === "renew" ? undefined : { note: "" });
      load();
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `Could not ${action} the certificate.`);
    }
  }

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}

      <div className="flex flex-wrap items-center gap-2">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="revoked">Revoked</option>
          <option value="expired">Expired</option>
          <option value="">All</option>
        </Select>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search subject, email or serial…"
          className="w-72"
        />
      </div>

      {data === null ? (
        <Skeleton className="h-40 w-full" />
      ) : data.items.length === 0 ? (
        <Card>
          <CardBody className="py-10 text-center text-sm text-ink-2">No certificates match.</CardBody>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs text-ink-2">
                <tr>
                  <th className="px-3 py-2 font-medium">Subject</th>
                  <th className="px-3 py-2 font-medium">Serial</th>
                  <th className="px-3 py-2 font-medium">Profile</th>
                  <th className="px-3 py-2 font-medium">Expires</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  {isAdmin && <th className="px-3 py-2 font-medium">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">
                      <div className="font-medium text-ink">{c.subject_name || cn(c.subject_dn)}</div>
                      <div className="text-xs text-ink-2">{c.subject_email}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs text-ink-2" title={c.serial_number}>
                        {c.serial_number.slice(0, 12)}…
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-2">{c.profile}</td>
                    <td className="px-3 py-2">
                      <div className="text-ink">{fmtDate(c.not_after)}</div>
                      {c.status === "active" && c.days_remaining <= 30 && (
                        <div className="flex items-center gap-1 text-xs text-amber-600">
                          <Clock className="h-3 w-3" /> {c.days_remaining}d left
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={statusTone(c.status)}>{titleCase(c.status)}</Badge>
                      {c.revocation_reason && (
                        <div className="mt-0.5 text-[11px] text-ink-3">{c.revocation_reason.replace(/_/g, " ")}</div>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {c.status === "active" && (
                            <>
                              <Button variant="ghost" className="h-7 px-2 text-xs" onClick={() => act(c, "suspend")}>
                                <Pause className="h-3 w-3" /> Suspend
                              </Button>
                              <Button variant="ghost" className="h-7 px-2 text-xs" onClick={() => setRevoking(c)}>
                                <Ban className="h-3 w-3" /> Revoke
                              </Button>
                            </>
                          )}
                          {c.status === "suspended" && (
                            <Button variant="ghost" className="h-7 px-2 text-xs" onClick={() => act(c, "resume")}>
                              <Play className="h-3 w-3" /> Resume
                            </Button>
                          )}
                          {(c.status === "active" || c.status === "expired") && (
                            <Button variant="ghost" className="h-7 px-2 text-xs" onClick={() => act(c, "renew")}>
                              <RefreshCw className="h-3 w-3" /> Renew
                            </Button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {revoking && (
        <RevokeDialog
          cert={revoking}
          onClose={() => setRevoking(null)}
          onDone={() => {
            setRevoking(null);
            load();
            onChange();
          }}
          onError={setError}
        />
      )}
    </div>
  );
}

function RevokeDialog({
  cert,
  onClose,
  onDone,
  onError,
}: {
  cert: Certificate;
  onClose: () => void;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [reason, setReason] = useState<string>("unspecified");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await api.post(`/pki/certificates/${cert.id}/revoke`, { reason, note });
      onDone();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Could not revoke the certificate.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Revoke certificate</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-ink-2">
            Revocation is permanent. The serial is published on the next CRL and the OCSP responder
            reports it immediately. Use <strong>suspend</strong> if you may need to undo this.
          </p>
          <Field label="Reason (RFC 5280)">
            <Select value={reason} onChange={(e) => setReason(e.target.value)}>
              {REVOCATION_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Note">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Recorded in the audit trail" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy}>
              {busy ? "Revoking…" : "Revoke"}
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------- trust store

function TrustStore({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<TrustAnchor[] | null>(null);
  const [pem, setPem] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [check, setCheck] = useState("");
  const [result, setResult] = useState<ValidationResult | null>(null);

  const load = useCallback(() => {
    api
      .get<TrustAnchor[]>("/pki/trust-anchors", { cache: false })
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  useEffect(load, [load]);

  async function add() {
    setError("");
    try {
      await api.post("/pki/trust-anchors", { pem, name });
      setPem("");
      setName("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add the trust anchor.");
    }
  }

  async function remove(id: string) {
    try {
      await api.del(`/pki/trust-anchors/${id}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove the trust anchor.");
    }
  }

  async function validate() {
    setError("");
    setResult(null);
    try {
      setResult(await api.post<ValidationResult>("/pki/validate", { pem: check }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Validation failed.");
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      <Card>
        <CardHeader>
          <CardTitle>Trusted roots</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-ink-2">
            Roots accepted when validating certificates this CA did not issue — so an overseas
            counterparty can sign with their own DigiCert, GlobalSign, Sectigo or Entrust
            certificate. Stored in the database, so the chain can be extended at runtime.
          </p>
          {rows === null ? (
            <Skeleton className="h-20 w-full" />
          ) : rows.length === 0 ? (
            <p className="text-sm text-ink-3">No trust anchors configured yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {rows.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-ink">{a.name}</div>
                    <div className="truncate font-mono text-[11px] text-ink-3" title={a.fingerprint_sha256}>
                      {a.fingerprint_sha256.slice(0, 32)}…
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge tone={a.source === "internal" ? "accent" : "neutral"}>{a.source}</Badge>
                    <Badge tone={a.is_active ? "accent" : "neutral"}>{a.is_active ? "active" : "removed"}</Badge>
                    <span className="text-xs text-ink-2">exp {fmtDate(a.not_after)}</span>
                    {isAdmin && a.is_active && (
                      <Button variant="ghost" className="h-7 px-2 text-xs" onClick={() => remove(a.id)}>
                        Remove
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {isAdmin && (
            <div className="space-y-2 border-t border-line pt-3">
              <Field label="Add a root (PEM)">
                <Textarea
                  rows={4}
                  value={pem}
                  onChange={(e) => setPem(e.target.value)}
                  placeholder="-----BEGIN CERTIFICATE-----"
                  className="font-mono text-[11px]"
                />
              </Field>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <Field label="Label">
                    <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. DigiCert Global Root G2" />
                  </Field>
                </div>
                <Button onClick={add} disabled={!pem.trim()}>
                  Add root
                </Button>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Validate a third-party certificate</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <Field label="Certificate (PEM)">
            <Textarea
              rows={4}
              value={check}
              onChange={(e) => setCheck(e.target.value)}
              placeholder="-----BEGIN CERTIFICATE-----"
              className="font-mono text-[11px]"
            />
          </Field>
          <Button onClick={validate} disabled={!check.trim()}>
            Validate chain
          </Button>
          {result && (
            <div
              className={`rounded-md border p-3 text-sm ${
                result.ok ? "border-accent/40 bg-accent-subtle" : "border-red-300 bg-red-50 dark:bg-red-950/20"
              }`}
            >
              <div className="flex items-center gap-2 font-medium">
                {result.ok ? (
                  <CheckCircle2 className="h-4 w-4 text-accent" />
                ) : (
                  <Ban className="h-4 w-4 text-red-500" />
                )}
                {result.ok ? "Valid" : "Rejected"}
              </div>
              {result.reason && <p className="mt-1 text-ink-2">{result.reason}</p>}
              {result.chain.length > 0 && (
                <ol className="mt-2 space-y-0.5 text-xs text-ink-2">
                  {result.chain.map((dn, i) => (
                    <li key={dn} style={{ paddingLeft: `${i * 12}px` }}>
                      ↳ {cn(dn)}
                    </li>
                  ))}
                </ol>
              )}
              {result.warnings.map((w) => (
                <p key={w} className="mt-1 flex items-start gap-1 text-xs text-amber-700">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {w}
                </p>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
