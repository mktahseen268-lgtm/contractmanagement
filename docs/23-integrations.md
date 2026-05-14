# 23 · Integrations

The platform is designed to slot into typical enterprise stacks without modification. The
core integration surface is the **API** (REST + OpenAPI 3) and **webhooks** (HMAC-signed
HTTPS), both of which already exist.

## 1. API Gateway / Kong compatibility

Drop-in. The API:

- Honours `X-Forwarded-For` and `X-Forwarded-Proto`.
- Tolerates Kong / AWS API Gateway path stripping (no absolute URLs in responses).
- Returns OpenAPI 3 at `/docs` (Swagger) + `/openapi.json` for **Kong dev-portal** import or
  AWS API Gateway model generation.
- Returns standard 401/403/429 with `WWW-Authenticate` and `Retry-After` headers so the gateway
  surfaces them correctly to clients.
- Accepts either `Authorization: Bearer <JWT>` (user) or `Authorization: Bearer cm_…`
  (API key, see [`20-security-compliance.md`](20-security-compliance.md) §3).

Recommended Kong plugins to layer in front:

| Concern | Plugin |
|---|---|
| WAF / OWASP CRS | `coraza-waf` plugin |
| Rate limiting | `rate-limiting` plugin (Redis backend, mirror our internal limits) |
| CAPTCHA on /auth/* | reCAPTCHA / Turnstile via `request-transformer-advanced` |
| Mutual TLS for partners | `mtls-auth` |
| Per-tenant quotas | `acl` + `request-termination` |
| Logging to SIEM | `http-log` or `tcp-log` to Logstash |

## 2. Microsoft 365 family

### 2.1 Microsoft Teams

Two integration shapes:

**(a) Outbound — notifications to Teams**

Webhook endpoint URL = a Teams **Incoming Webhook** connector or **Workflow** URL. Our
webhook payload (`{event, occurred_at, tenant_id, data}`) maps cleanly to Adaptive Cards via
a 1-line transformer in the customer's Power Automate flow. Sample Power Automate trigger
+ Adaptive Card recipe in [`docs/snippets/teams-webhook-flow.json`](snippets/teams-webhook-flow.json).

**(b) Inbound — bot commands**

Implementation hook: a thin **Teams Bot** (Bot Framework v4) calls our REST API using an
**API key** scoped to a dedicated service-account user (role `manager`). The bot's
`/handle-message` controller maps natural commands to API calls:

| Command | API call |
|---|---|
| `cm contracts expiring` | `GET /reports/summary?from=…&to=…` |
| `cm contracts search <q>` | `GET /contracts?q=<q>` |
| `cm approve <ref>` | `POST /contracts/{id}/workflow/decide` |

Scaffolded under [`integrations/teams-bot/`](../integrations/teams-bot/) (placeholder — sequenced
under "T-7 Teams/Outlook" in the roadmap).

### 2.2 SharePoint

The customer keeps SharePoint as the **document of record** if their policy demands it.
Integration shapes:

- **Outbound copy on completion**: webhook subscribes to `envelope.completed` → Logic App /
  Power Automate copies the executed PDF + certificate from our S3 / GET endpoint into the
  configured SharePoint library, applying metadata from the webhook payload.
- **Inbound link** : a SharePoint column "ContractRef" points back to
  `https://app.contract-management/contracts/<id>` for navigation.
- **OneDrive / SharePoint pickers** for OCR ingest (planned, T-8).

Authentication: the customer's Microsoft Graph app registration + an API key on our side. No
credentials on our infra.

### 2.3 Outlook

- **Outbound**: signing-link, MFA OTP, approval requests, renewal reminders all use SMTP via
  the email outbox. Production SMTP relay points at the customer's M365 connector or SendGrid
  / SES.
- **Outlook Add-in (planned, T-8)**: a small add-in surfaces a "Create contract from this
  email" action that POSTs the message body + attachments to `POST /ocr/jobs` + `POST
  /ocr/jobs/{id}/create-contract`.
- **Calendar**: renewal due-dates can be pushed as Outlook calendar events via Microsoft Graph
  using the customer's app registration (planned).

## 3. WAF compatibility

The product runs cleanly behind a WAF — no inline scripts that would conflict with default
OWASP CRS, no payload bodies > the 60 MB default, no exotic content types. WAF guidance:

- Enable OWASP CRS 4.x at paranoia level 1 (start) → 2 (after baseline noise tuned).
- Exempt `/files/*/download` and `/envelopes/*/signed-pdf` from body inspection (PDFs trigger
  false-positives on byte-pattern rules).
- Add a virtual patch for any CVE before our SLA window closes.
- Block egress to RFC1918, link-local (`169.254/16`), `metadata.google.internal`, IMDS
  (`169.254.169.254`) — these prevent SSRF even though we don't fetch URLs server-side.

## 4. SIEM compatibility

The API emits **structured JSON access logs** on stdout (CLF-style field names) plus the
durable `audit_log` table. Shipping options:

| SIEM | How |
|---|---|
| **Splunk** | Forwarder on the node tails stdout (k8s: Splunk OTel collector). Map to the **CIM** Authentication / Change data models — fields already align. |
| **Elastic / OpenSearch** | Filebeat + ECS field names — see the field map below. |
| **Microsoft Sentinel** | Azure Monitor agent ships container logs to Log Analytics; KQL queries provided in [`infra/sentinel/`](../infra/sentinel/). |
| **Sumo Logic / Datadog / NewRelic** | Standard container-logs collector. |
| **Wazuh / OSSEC** | File-system tail of stdout-redirected files. |

### Field map (key access-log fields ⇒ ECS / CIM)

```
ts            → @timestamp                       / _time
level         → log.level                        / log_level
request_id    → trace.id                         / correlation_id
method        → http.request.method              / http_method
path          → url.path                         / uri_path
status        → http.response.status_code        / status
duration_ms   → event.duration                   / duration
client_ip     → client.ip                        / src_ip
user_id       → user.id                          / user
tenant_id     → organization.id                  / tenant
action        → event.action  (audit only)       / action
```

A Sentinel **Analytics Rule** template is at [`infra/sentinel/auth_failed_brute_force.kql`](../infra/sentinel/auth_failed_brute_force.kql).

## 5. NIFT digital signature integration (Pakistan PKI)

Today's `signing_service` produces a typed-signature flow with a SHA-256 document hash +
appended Signatures page + Certificate of Completion. To meet Pakistani digital-signature
regulations the customer can plug **NIFT eSign** (or any PAdES-LTV CA) at the seal step
without touching the rest of the application:

1. The unsigned, ready-to-seal PDF is produced (already happens in `seal_envelope`).
2. A **pluggable `signing_provider`** (`apps/api/app/signing_provider.py`, planned T-4)
   wraps either:
   - the in-house typed-signature stamp (today's behaviour), **or**
   - a NIFT eSign client that calls `POST /sign` with the PDF + the recipient's CNIC token,
     receiving back a **PAdES-LT** (PKCS#7 detached) signed PDF.
3. The returned PDF replaces the `sealed_pdf_file_id` artefact.

Storage of NIFT credentials: per-tenant **secret reference** (Vault path / Secrets Manager
ARN) — never a plaintext credential in the DB. The integration is **opt-in per tenant**.

Same plug-point can host: Adobe Sign, DocuSign trust services, EU eIDAS-qualified CAs
(Cryptomathic, GlobalSign), or any other certificate-based signer.

## 6. Other planned integrations (designed; not yet built)

| ID | Integration | Purpose | Effort |
|---|---|---|---|
| INT-A | Slack | Mirror of the Teams hooks | XS (1 d) |
| INT-B | Google Drive / Workspace | OCR ingest, executed-PDF copy | M (1 w) |
| INT-C | Salesforce | Contracts module sync | L (2 w) |
| INT-D | SAP Ariba | Procurement-side handoff | L (2 w) |
| INT-E | Zapier / Make.com | Long-tail integrations via the public webhook | XS (existing) |
| INT-F | OAuth2 device-flow | CLI / IoT clients | S (3 d) |
