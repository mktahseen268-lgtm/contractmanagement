# Licensing and Third-Party Components

**Annexure item 5.** Licensing details for the database, APIs and every third-party component.

Two things this document does that a component list usually does not: it separates **what MMBL
must license** from **what is included**, and it flags the components whose licence has a
commercial consequence rather than presenting a flat inventory in which MIT and AGPL look alike.

A machine-readable SBOM in CycloneDX format is generated on every build and submitted alongside
this document. This is the human-readable summary.

---

## 1. What MMBL licenses

These are excluded from our scope (see `§1` of the Scope & Technical Specification) and are the
bank's to procure.

| Component | Why it is MMBL's | Notes |
|---|---|---|
| **Oracle Database** — 19c or later | Runs on MMBL infrastructure, sized to MMBL's estate | Licensed per processor or by named user, and typically already held under the bank's existing agreement. Enterprise Edition is not required — the solution uses no Enterprise-only feature. See §7. |
| **Operating systems** | MMBL platform | Oracle Linux, RHEL or Windows Server |
| **Kubernetes platform** | MMBL platform | Any conformant distribution |
| **HSM** — appliance and firmware | Hardware, plus FIPS validation MMBL relies on | Thales, Utimaco or Entrust. Per-device licensing varies by vendor |
| **Entra ID** | Existing MMBL identity estate | SAML/OIDC and SCIM are standard features |
| **Kong API Gateway** | MMBL edge | Community edition suffices; Enterprise only if MMBL wants its own features |
| **SIEM** | Existing MMBL tooling | We emit CEF over syslog; any collector accepts it |
| **SMS gateway** | Commercial arrangement with a Pakistani provider | Per-message pricing is MMBL's |
| **Mail relay** | Existing MMBL infrastructure | — |
| **Enterprise backup** — Veeam, Commvault | Existing MMBL tooling | Integrates at the storage layer; no application agent |
| **Antivirus** — ClamAV or equivalent | ClamAV is GPL and free; a commercial scanner is MMBL's choice | We speak the ICAP/INSTREAM protocol |

---

## 2. What is included

The application itself, all source code, and the right to use, modify and deploy it within MMBL,
under the terms of the commercial agreement. No per-user, per-agreement or per-signature fee is
charged by us.

**No runtime component calls a hosted service.** There is no metered API, no per-seat SaaS
dependency, and nothing that stops working if a subscription lapses. That is a consequence of the
on-prem requirement and it is also what makes the licence position simple.

---

## 3. Open-source components — backend

All permissive. None imposes an obligation on MMBL beyond attribution.

| Component | Version | Licence | Purpose |
|---|---|---|---|
| FastAPI | 0.115.5 | MIT | HTTP framework |
| Uvicorn | 0.32.1 | BSD-3-Clause | ASGI server |
| SQLAlchemy | 2.0.36 | MIT | Data access |
| Alembic | 1.14.0 | MIT | Schema migrations |
| Pydantic | 2.10.3 | MIT | Validation |
| oracledb | 2.5.1 | Apache-2.0 | Oracle Database driver — thin mode, no Oracle Client installation required |
| PyJWT | 2.10.1 | MIT | Token encoding |
| bcrypt | 4.2.1 | Apache-2.0 | Password hashing |
| pyotp | 2.9.0 | MIT | TOTP |
| Celery | 5.4.0 | BSD-3-Clause | Background jobs |
| Redis (client) | 5.2.1 | MIT | Queue and rate-limit client |
| boto3 | 1.35.71 | Apache-2.0 | S3-compatible storage |
| ReportLab | 4.2.5 | BSD-3-Clause | PDF generation |
| pypdf | 5.1.0 | BSD-3-Clause | PDF manipulation |
| openpyxl | 3.1.5 | MIT | XLSX export |
| python-docx | 1.1.2 | MIT | Word round-trip |
| cryptography | 43.0.1 | Apache-2.0 / BSD | Cryptographic primitives |
| prometheus-client | 0.21.1 | Apache-2.0 | Metrics |

### Optional extras, installed only when the feature is configured

| Component | Licence | Activated by |
|---|---|---|
| pyHanko | **MIT** | `SIGNING_PROVIDER=pki` or `pades` — PDF signature embedding |
| python-pkcs11 | MIT | `KEYSTORE_PROVIDER=pkcs11` — HSM |
| signxml | Apache-2.0 | SAML SSO |
| webauthn | BSD-3-Clause | Passkeys |
| OpenTelemetry SDK | Apache-2.0 | `OTEL_ENABLED=true` |

---

## 4. The one component that needs a sentence rather than a row

**There is no copyleft component in the deployed set.** Every component listed above is under a
permissive licence — MIT, BSD, Apache-2.0 or equivalent — which imposes attribution obligations
and nothing further. The Oracle driver is Apache-2.0 and runs in thin mode, so no Oracle Instant
Client is installed on the application servers and no client-side licensing question arises. One
component is worth a sentence anyway, and it is a contractual point rather than a licensing one.

**pyHanko — MIT, and the reason for the Annexure item 11 question.** It performs PDF signature
embedding: reserving a byte range, hashing around it, writing the signature in. It is MIT
licensed, imposes no obligation, and **never receives a private key** — it is handed a digest to
sign.

The licence is not the issue. The issue is that Annexure item 11 requires an undertaking that the
PKI and eSignature engine is proprietary and not an open-source derivative. Our CA, RA, lifecycle,
CRL and OCSP responder are our own implementation; this one component is not. Whether that
composition satisfies the undertaking as drafted is a question for MMBL's counsel and ours, and it
is tracked as **R-05** in the Risk Mitigation Strategy. It is raised at submission rather than
discovered at signature.

---

## 5. Open-source components — frontend

| Component | Version | Licence | Purpose |
|---|---|---|---|
| Next.js | 14.2.35 | MIT | Application framework |
| React / React-DOM | 18.3.1 | MIT | UI runtime |
| TypeScript | 5.6.3 | Apache-2.0 | Type checking (build only) |
| Tailwind CSS | 3.4.14 | MIT | Styling (build only) |
| Tiptap | 2.10.3 | MIT | Rich-text editor |
| lucide-react | 0.460.0 | ISC | Icons |
| clsx | 2.1.1 | MIT | Class composition |

**One open advisory, named rather than omitted.** `npm audit` reports high-severity advisories
against Next.js 14.2.35. There is no patched 14.x — that is the last of the line — so the only
remediation is a major upgrade to Next 16, planned with its own regression cycle rather than
performed hastily mid-delivery. The affected surfaces (image optimiser, middleware rewrites) are
not exposed directly to the internet in this deployment; the application sits behind MMBL's WAF.
Tracked as **R-15**.

---

## 6. Fonts and assets

| Asset | Licence | Note |
|---|---|---|
| Inter | SIL OFL 1.1 | Self-hosted, not fetched from a CDN |

Web fonts are bundled rather than loaded from a font service. A CDN font request tells a third
party which internal pages a bank employee opened, and when.

---

## 7. Oracle Database — the licence position

The solution is delivered on **Oracle Database 19c or later**, in line with the preference stated
in RFP §4b. The licence is MMBL's, held under the bank's existing agreement, and is not part of
this proposal's commercial scope.

| Item | Position |
|---|---|
| Edition | **Standard Edition 2 is sufficient.** No Enterprise-only feature is used — no partitioning option, no Advanced Security option, no In-Memory. Enterprise Edition brings operational benefits the bank may already rely on, but the solution does not require it |
| Metric | Per processor, or by named user plus, under MMBL's existing agreement |
| Workspace isolation | Oracle **Virtual Private Database**, applied to every workspace-scoped table |
| Encryption at rest | Oracle **Transparent Data Encryption**, enabled at the tablespace |
| Driver | `oracledb` in thin mode — Apache-2.0 licensed, and **no Oracle Instant Client installation is required** on the application servers, which removes a client-side licensing and packaging question entirely |
| Character set | AL32UTF8, required for Urdu content |

**Why the solution is not written against Oracle-specific SQL.** Every engine-specific
construct — workspace isolation, session context, locking, JSON handling and full-text search —
is confined to a single dialect layer, with one Oracle implementation behind a common interface.
This matters for two reasons that are MMBL's rather than ours: the application logic above that
layer is not coupled to a vendor, so a future platform decision is a configuration change rather
than a rewrite; and the Oracle implementation is a small, reviewable surface that MMBL's DBA team
can inspect in full rather than a vendor-specific idiom scattered through the codebase.

**Certification before data.** The first Oracle deployment is a named acceptance gate at M1: the
complete schema migration, a cross-workspace isolation test proving Virtual Private Database refuses a read across
the boundary, and a representative query workload — all run and signed off **before any data is
loaded**. This is tracked as R-07 in the Risk Mitigation Strategy.

---

## 8. Licence compliance

| Control | Mechanism |
|---|---|
| Component inventory | CycloneDX SBOM generated on every build |
| Licence detection | Automated as part of dependency scanning |
| Copyleft detection | Flagged at build; no GPL or AGPL component is in the runtime set |
| Vulnerability tracking | `pip-audit`, `safety`, `npm audit`, Trivy — all gating |
| Attribution | A NOTICE file ships with the application listing every component and licence |

**No GPL or AGPL component is in the runtime set.** ClamAV is GPL but runs as a separate daemon
MMBL operates, spoken to over a network protocol — it is not linked, and it is MMBL's to license
or replace.

---

## 9. Export and cryptography

The application uses standard cryptographic primitives — AES, RSA, ECDSA, SHA-2 — through the
`cryptography` library and, in production, an HSM. There is no proprietary cryptography.

Pakistani import and use regulations for cryptographic software are MMBL's to satisfy as the
operator. The deployment is entirely on-premises within Pakistan, so no cryptographic material
crosses a border in operation.
