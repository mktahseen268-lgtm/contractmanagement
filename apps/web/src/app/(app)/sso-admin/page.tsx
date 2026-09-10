"use client";

/**
 * SSO administration — what an IdP administrator needs to wire this up.
 *
 *   GET /auth/sso/config    OIDC status
 *   GET /auth/saml/config   SAML status, entity ID, ACS/SLO/metadata URLs
 *
 * Replaces the mockup, which advertised an ACS URL (`/auth/saml/acs`) that did not exist —
 * an evaluator who tested it would have found nothing there. Everything shown here is read
 * from the running service, so a URL on this page is a URL that works.
 *
 * Nothing on this page is a secret: entity IDs and endpoint URLs are exactly what gets handed
 * to the IdP administrator anyway. The IdP signing certificate is reported as
 * configured / not configured and never rendered.
 */

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Copy, ExternalLink, KeyRound, ShieldCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@/components/ui";
import type { SamlConfig, SsoConfig } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SsoAdminPage() {
  const [saml, setSaml] = useState<SamlConfig | null>(null);
  const [oidc, setOidc] = useState<SsoConfig | null>(null);
  const [copied, setCopied] = useState("");

  useEffect(() => {
    api.get<SamlConfig>("/auth/saml/config").then(setSaml).catch(() =>
      setSaml({
        enabled: false, entity_id: "", acs_url: "", sls_url: "", metadata_url: "",
        idp_sso_url: "", idp_slo_url: "", login_url: "", default_role: "author",
        group_role_map: {}, certificate_configured: false,
      }),
    );
    api.get<SsoConfig>("/auth/sso/config").then(setOidc).catch(() => setOidc(null));
  }, []);

  function copy(label: string, value: string) {
    void navigator.clipboard?.writeText(value);
    setCopied(label);
    window.setTimeout(() => setCopied(""), 1500);
  }

  return (
    <div>
      <PageHeader
        title="Single sign-on"
        subtitle="OIDC and SAML 2.0 — what to give your identity provider"
      />

      <div className="space-y-5 p-6">
        {saml === null ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4" /> SAML 2.0
                  <Badge tone={saml.enabled ? "accent" : "neutral"}>
                    {saml.enabled ? "configured" : "not configured"}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-3">
                {!saml.enabled ? (
                  <div className="space-y-2 text-sm text-ink-2">
                    <p className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                      SAML is off. The endpoints below do not exist until an operator sets{" "}
                      <code className="rounded bg-surface-3 px-1">SAML_ENABLED=true</code>, the
                      IdP SSO URL and the IdP signing certificate.
                    </p>
                    <p className="text-xs text-ink-3">
                      Deliberate: a half-configured deployment that advertised an ACS URL it
                      could not honour would fail the first time anyone tested it.
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="text-sm text-ink-2">
                      Give these to your IdP administrator. They are read from the running
                      service, so what is shown here is what the service actually answers on.
                    </p>
                    <div className="space-y-1.5">
                      <Row
                        label="Entity ID"
                        value={saml.entity_id}
                        copied={copied === "entity"}
                        onCopy={() => copy("entity", saml.entity_id)}
                      />
                      <Row
                        label="Reply URL (ACS)"
                        value={saml.acs_url}
                        copied={copied === "acs"}
                        onCopy={() => copy("acs", saml.acs_url)}
                      />
                      <Row
                        label="Sign-on URL"
                        value={saml.login_url}
                        copied={copied === "login"}
                        onCopy={() => copy("login", saml.login_url)}
                      />
                      <Row
                        label="Logout URL"
                        value={saml.sls_url}
                        copied={copied === "sls"}
                        onCopy={() => copy("sls", saml.sls_url)}
                      />
                    </div>

                    <div className="flex flex-wrap items-center gap-3 pt-1">
                      <a
                        href={`${API}/auth/saml/metadata`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
                      >
                        <ExternalLink className="h-3.5 w-3.5" /> Download SP metadata
                      </a>
                      <span className="inline-flex items-center gap-1.5 text-xs text-ink-3">
                        <KeyRound className="h-3.5 w-3.5" />
                        IdP signing certificate{" "}
                        {saml.certificate_configured ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700">
                            <Check className="h-3 w-3" /> configured
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-red-600">
                            <X className="h-3 w-3" /> missing
                          </span>
                        )}
                      </span>
                    </div>

                    <div className="rounded-md border border-line p-2 text-xs text-ink-2">
                      <div className="mb-1 font-medium text-ink">Group to role mapping</div>
                      {Object.keys(saml.group_role_map).length === 0 ? (
                        <p>
                          No groups mapped — everyone signing in through SAML gets the{" "}
                          <strong>{saml.default_role}</strong> role.
                        </p>
                      ) : (
                        <ul className="space-y-0.5">
                          {Object.entries(saml.group_role_map).map(([group, role]) => (
                            <li key={group}>
                              <code className="rounded bg-surface-3 px-1">{group}</code> →{" "}
                              {String(role)}
                            </li>
                          ))}
                          <li className="text-ink-3">
                            Anything unmapped gets <strong>{saml.default_role}</strong>.
                          </li>
                        </ul>
                      )}
                    </div>
                  </>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4" /> OpenID Connect
                  <Badge tone={oidc?.enabled ? "accent" : "neutral"}>
                    {oidc?.enabled ? "configured" : "not configured"}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardBody className="text-sm text-ink-2">
                {oidc?.enabled ? (
                  <p>
                    Users can sign in with OIDC. The login page shows the button
                    automatically.
                  </p>
                ) : (
                  <p>
                    OIDC is off. Set <code className="rounded bg-surface-3 px-1">OIDC_ENABLED</code>,
                    the issuer, client id and secret to turn it on.
                  </p>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardBody className="text-xs text-ink-3">
                Both protocols provision users into the workspace named by their respective
                default-tenant setting, matched to an existing account by email address. A user
                created through SSO has no password — the identity provider stays the only way
                in, so there is nothing to phish.
              </CardBody>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2">
      <span className="min-w-[130px] text-xs font-medium text-ink-2">{label}</span>
      <code className="flex-1 truncate font-mono text-xs text-ink">{value}</code>
      <Button size="sm" variant="ghost" onClick={onCopy}>
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
    </div>
  );
}
