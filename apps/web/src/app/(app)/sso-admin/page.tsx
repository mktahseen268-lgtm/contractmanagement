"use client";

// SAML SSO Admin — PROTOTYPE of the enterprise IdP configuration screen (the SAML half of T-3;
// OIDC + SCIM already ship in the backend). Configure the IdP, map attributes, test the
// connection, and manage SCIM provisioning. Mockup: form state + simulated test. Wires later to
// a SAML ACS endpoint + the existing SCIM router.

import { useState } from "react";
import { Check, Copy, KeyRound, Link2, Loader2, ShieldCheck, TestTube2, Users } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Input, Select, Textarea } from "@/components/ui";

const ACS_URL = "https://api.acme-cm.io/auth/saml/acs";
const ENTITY_ID = "https://api.acme-cm.io/saml/metadata";

export default function SsoAdminPage() {
  const [enabled, setEnabled] = useState(false);
  const [idpUrl, setIdpUrl] = useState("https://login.microsoftonline.com/contoso/saml2");
  const [idpEntity, setIdpEntity] = useState("https://sts.windows.net/contoso/");
  const [cert, setCert] = useState("-----BEGIN CERTIFICATE-----\nMIIDpDCCAoygAwIBAgIQ... (paste your IdP signing certificate)\n-----END CERTIFICATE-----");
  const [emailAttr, setEmailAttr] = useState("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress");
  const [nameAttr, setNameAttr] = useState("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name");
  const [defaultRole, setDefaultRole] = useState("author");
  const [test, setTest] = useState<"idle" | "running" | "ok">("idle");
  const [copied, setCopied] = useState<string | null>(null);
  const [scim, setScim] = useState(true);

  function copy(label: string, v: string) {
    try { navigator.clipboard?.writeText(v); } catch { /* noop */ }
    setCopied(label);
    setTimeout(() => setCopied(null), 1400);
  }
  function runTest() {
    setTest("running");
    setTimeout(() => setTest("ok"), 1500);
  }

  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">SAML SSO</span>}
        subtitle="Connect your identity provider (Entra ID, Okta, Google) for single sign-on + SCIM provisioning."
        actions={
          <button
            onClick={() => setEnabled((s) => !s)}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition ${enabled ? "bg-emerald-600 text-white" : "bg-surface-3 text-ink-2"}`}
          >
            <span className={`relative inline-flex h-4 w-7 items-center rounded-full ${enabled ? "bg-white/30" : "bg-ink-3/30"}`}>
              <span className={`h-3 w-3 transform rounded-full bg-white transition ${enabled ? "translate-x-3.5" : "translate-x-0.5"}`} />
            </span>
            {enabled ? "SSO enabled" : "SSO disabled"}
          </button>
        }
      />

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* Service-provider details (give these to the IdP) */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-1.5"><Link2 className="h-4 w-4" /> Give these to your IdP</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            {[["ACS / Reply URL", ACS_URL, "acs"], ["SP Entity ID / Audience", ENTITY_ID, "entity"]].map(([label, val, key]) => (
              <div key={key}>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</label>
                <div className="flex items-center gap-2">
                  <Input value={val} readOnly className="font-mono text-xs" />
                  <Button size="sm" variant="secondary" onClick={() => copy(key, val)}>
                    {copied === key ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>
            ))}
            <div className="rounded-lg border border-dashed border-line bg-surface-2 p-3 text-[11px] text-ink-2">
              Name ID format: <span className="font-mono">emailAddress</span>. Sign the SAML assertion (and optionally the response) with the certificate below.
            </div>
          </CardBody>
        </Card>

        {/* IdP config */}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-1.5"><KeyRound className="h-4 w-4" /> Identity provider</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            <Field label="IdP SSO URL (SAML 2.0)">
              <Input value={idpUrl} onChange={(e) => setIdpUrl(e.target.value)} className="font-mono text-xs" />
            </Field>
            <Field label="IdP Entity ID / Issuer">
              <Input value={idpEntity} onChange={(e) => setIdpEntity(e.target.value)} className="font-mono text-xs" />
            </Field>
            <Field label="IdP signing certificate (x509 PEM)">
              <Textarea value={cert} onChange={(e) => setCert(e.target.value)} rows={4} className="font-mono text-[11px]" />
            </Field>
          </CardBody>
        </Card>

        {/* attribute mapping */}
        <Card>
          <CardHeader><CardTitle>Attribute mapping</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            <Field label="Email attribute">
              <Input value={emailAttr} onChange={(e) => setEmailAttr(e.target.value)} className="font-mono text-[11px]" />
            </Field>
            <Field label="Display-name attribute">
              <Input value={nameAttr} onChange={(e) => setNameAttr(e.target.value)} className="font-mono text-[11px]" />
            </Field>
            <Field label="Default role for new SSO users">
              <Select value={defaultRole} onChange={(e) => setDefaultRole(e.target.value)}>
                {["viewer", "reviewer", "author", "approver", "manager"].map((r) => <option key={r} value={r}>{r}</option>)}
              </Select>
            </Field>
            <p className="text-[11px] text-ink-3">New users are just-in-time provisioned on first login and matched to existing accounts by email.</p>
          </CardBody>
        </Card>

        {/* test + SCIM */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><TestTube2 className="h-4 w-4" /> Test connection</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <Button onClick={runTest} disabled={test === "running"} variant="secondary" className="w-full">
                {test === "running" ? <><Loader2 className="h-4 w-4 animate-spin" /> Testing SAML round-trip…</> : <><ShieldCheck className="h-4 w-4" /> Run test login</>}
              </Button>
              {test === "ok" && (
                <div className="space-y-1 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
                  <div className="flex items-center gap-1.5 font-medium"><Check className="h-4 w-4" /> Assertion verified</div>
                  <div className="text-[11px]">Signature valid · email + name claims present · clock skew OK.</div>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5"><Users className="h-4 w-4" /> SCIM provisioning</CardTitle>
              <button onClick={() => setScim((s) => !s)} className={`relative inline-flex h-5 w-9 items-center rounded-full ${scim ? "bg-accent" : "bg-surface-3"}`}>
                <span className={`h-4 w-4 transform rounded-full bg-white shadow transition ${scim ? "translate-x-4" : "translate-x-0.5"}`} />
              </button>
            </CardHeader>
            <CardBody className="space-y-2">
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">SCIM base URL</label>
                <Input value="https://api.acme-cm.io/scim/v2" readOnly className="font-mono text-xs" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-ink-3">Bearer token</label>
                <div className="flex items-center gap-2">
                  <Input value="scim_•••••••••••••••••••••••••" readOnly className="font-mono text-xs" />
                  <Button size="sm" variant="secondary" onClick={() => copy("scim", "scim_live_token_demo")}>
                    {copied === "scim" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>
              <p className="text-[11px] text-ink-3">Your IdP creates, updates, and deactivates users automatically via SCIM 2.0.</p>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
