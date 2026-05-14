# 20 · Security & Compliance

This document is the security baseline for enterprise / government RFI submission. It maps every
control to the file/module in the codebase that implements it and the operational steps the
deploying customer must complete (TLS termination, secrets manager, WAF, …).

---

## 1. OWASP Top 10 (2021) — Control Inventory

| # | Risk | How we mitigate | Where in the code | Operator step |
|---|---|---|---|---|
| A01 | Broken Access Control | RBAC + role hierarchy; PostgreSQL **Row-Level Security** (per-tenant `tenant_isolation` policy on every tenant-scoped table); RLS GUC bound to the JWT-asserted `tid` in a request-scoped `ContextVar`; defence-in-depth `tenant_id` filter in every repo query. Owner-protection rules in user-update (can't demote last owner, can't deactivate self, admins can't touch owners). | [`app/database.py`](../apps/api/app/database.py), [`app/deps.py`](../apps/api/app/deps.py), [`migrations/versions/0002_rls.py`](../apps/api/migrations/versions/0002_rls.py), [`routers/misc.py`](../apps/api/app/routers/misc.py) | None — runs on Postgres |
| A02 | Cryptographic Failures | bcrypt (12-round) for passwords; **AES-256-GCM** (Fernet over a 32-byte key) for MFA secrets at rest (see §6.2); HS256 JWT signed with a 256-bit secret in env (32+ bytes enforced in prod); refresh tokens stored as SHA-256 hashes only; webhook payloads HMAC-SHA256 signed; API keys stored as SHA-256 hashes (plaintext shown once). | [`app/security.py`](../apps/api/app/security.py), [`app/secrets_box.py`](../apps/api/app/secrets_box.py), [`app/webhook_service.py`](../apps/api/app/webhook_service.py), [`app/routers/api_keys.py`](../apps/api/app/routers/api_keys.py) | Provision **TLS 1.2+/1.3** at the ingress; rotate `SECRET_KEY` / `MFA_ENCRYPTION_KEY` via secrets manager |
| A03 | Injection | 100 % parameterised SQL via SQLAlchemy ORM — no string-concatenated queries anywhere. JSON columns stored via the ORM JSON type (no raw `json.dumps` into VARCHAR). Markdown body rendered with the safe Tiptap → ReportLab path; the public `/sign/{token}` page never echoes user-supplied HTML. | repo-wide; check `grep -r "execute(\""` returns only one parameterised callsite | None |
| A04 | Insecure Design | Threat model captured in [`docs/19-security-trust.md`](19-security-trust.md). Signed envelopes are sealed (document_hash + executed PDF) so retroactive tampering is detectable. Idempotency in critical sweeps. Append-only `audit_log`. | [`app/audit.py`](../apps/api/app/audit.py), [`app/signing_service.py`](../apps/api/app/signing_service.py) | Plan threat reviews per change |
| A05 | Security Misconfiguration | Strict CORS allowlist via env var; secure security headers middleware (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy); `cookie_secure=True` in prod; debug off; SECRET_KEY validation refuses to boot on the dev default when `ENV != "dev"`. | [`app/main.py`](../apps/api/app/main.py), [`app/middleware/security_headers.py`](../apps/api/app/middleware/security_headers.py), [`app/config.py`](../apps/api/app/config.py) | Set `ENV=production`, `COOKIE_SECURE=true`, `SECRET_KEY=…`, `MFA_ENCRYPTION_KEY=…` |
| A06 | Vulnerable / Outdated Components | Pinned versions in `requirements.txt` + `package-lock.json`; CI runs `pip-audit`, `safety`, `npm audit --audit-level=high`, and a Trivy scan of the built images on every PR. Dependabot weekly. | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Triage CVE alerts per SLA in [`21-devsecops-plan.md`](21-devsecops-plan.md) |
| A07 | Identification & Auth Failures | MFA (TOTP + 8 recovery codes + email OTP); per-account **login lockout** after 5 failures in 10 min; rate limiter on `/auth/*` endpoints (5/min for login, 3/min for register, 10/min for refresh); rotating refresh tokens with **reuse detection** (replay revokes the whole session chain); password rotation on demand; `is_active=false` blocks login. | [`app/middleware/rate_limit.py`](../apps/api/app/middleware/rate_limit.py), [`app/auth_service.py`](../apps/api/app/auth_service.py), [`app/routers/auth.py`](../apps/api/app/routers/auth.py) | Configure CAPTCHA at the WAF for /auth/register + /auth/login (recommendation: turnstile or hCaptcha; see §3.4) |
| A08 | Software & Data Integrity Failures | Code is signed via GitHub commits + Co-Authored-By; images built reproducibly from a pinned base + locked deps; container images signed at release (cosign) — see [`21-devsecops-plan.md`](21-devsecops-plan.md). Executed PDFs carry a SHA-256 document_hash recorded in the signature envelope. | [`app/signing_service.py`](../apps/api/app/signing_service.py) §send_envelope | Run cosign verify in admission policy |
| A09 | Security Logging & Monitoring Failures | Structured JSON access logs (CLF-compatible field names + RFC 5424 severities); audit-trail event for every security-relevant action (login.success/failed/locked, mfa.*, password.changed, role.changed, user.deactivated, api_key.created/revoked, webhook.created, admin.*); each request carries an `X-Request-Id`. Send to SIEM via stdout. | [`app/middleware/logging.py`](../apps/api/app/middleware/logging.py), [`app/audit.py`](../apps/api/app/audit.py) | Wire stdout → SIEM (Splunk / Elastic / Sentinel); see [`23-integrations.md`](23-integrations.md) |
| A10 | Server-Side Request Forgery | Webhook URL allowlist intent (only http/https schemes accepted today; production should additionally block RFC1918 / link-local / metadata IPs at the WAF). OCR uploads stored object-side (no fetch-by-URL). | [`app/routers/webhooks.py`](../apps/api/app/routers/webhooks.py) | Add egress allowlist at the WAF / NetworkPolicy |

---

## 2. OWASP ASVS L2 — Implementation Alignment

We target **ASVS v4.0.3 Level 2** (suitable for sensitive data and standard enterprise apps).
Highlights of compliance — full matrix in [`24-rfi-compliance-matrix.md`](24-rfi-compliance-matrix.md):

- **V1 (Architecture):** threat model documented, multi-tenant boundaries enforced at the DB layer.
- **V2 (Authentication):** §2.1 password length 8+, §2.4 lockout, §2.7 MFA, §2.8 rotation.
- **V3 (Session):** httpOnly + SameSite=Lax refresh cookie, rotation + reuse detection, 30-min access token, server-side session revocation list.
- **V4 (Access Control):** RBAC enforced server-side on every endpoint; RLS at the DB layer.
- **V5 (Validation, Sanitisation, Encoding):** Pydantic v2 strict-typed inputs; React's JSX auto-escapes by default; CSP nonces planned for inline scripts (none today).
- **V7 (Errors & Logging):** structured logs, no PII in stack traces, audit trail.
- **V8 (Data Protection):** secrets out of source control; encryption at rest for sensitive columns; per-tenant prefixing in object storage.
- **V9 (Communications):** TLS only in prod; HSTS + Secure + SameSite cookies.
- **V11 (Business Logic):** lifecycle state machine enforces transitions; envelopes can't be edited after send; recipient ordering enforced.
- **V14 (Configuration):** secure defaults; production guards against dev secrets.

---

## 3. Authentication, Authorisation & Session

### 3.1 MFA

- TOTP enrolment with QR-code provisioning URI (pyotp).
- 8 single-use recovery codes hashed at rest.
- Email-OTP alternative (10-min TTL, 5 attempts max).
- Backup-code consumption is one-time and audited.

### 3.2 SSO / IAM compatibility

The login flow is implemented as a standard OAuth2 password grant returning short JWTs.
SSO/SAML/OIDC integration is **not yet implemented**, but the architecture is ready:

- Adding an IdP would mean a new `/auth/sso/{provider}` redirect endpoint that mints the same
  internal session + JWT as `/auth/login` does today — the rest of the stack is unchanged.
- Recommended adapters: **OIDC via Authlib** (Google / Microsoft Entra / Okta) and
  **SAML 2.0 via python3-saml**.
- **SCIM 2.0** provisioning slots cleanly into the existing `/users` + `PATCH /users/{id}` API.

This is sequenced under "T-3 Enterprise IAM" in the implementation roadmap below.

### 3.3 RBAC hardening

Roles (in hierarchy order): `viewer < reviewer < author < approver < manager < admin < owner`.
Every router enforces both:
1. Role gate (e.g. `_EDIT_ROLES = {"owner","admin","manager","author"}`).
2. Tenant scope via RLS + an explicit `tenant_id` filter.

Owner protection rules (server-side):
- Admins cannot patch an owner.
- The last active owner cannot be demoted or deactivated.
- A user cannot deactivate themselves.

### 3.4 CAPTCHA

The codebase exposes a hook at the auth router level (header `X-CAPTCHA-Token`) but the
verification is performed at the **WAF / API Gateway** (turnstile, hCaptcha, reCAPTCHA v3) for
clean separation. Without a token after N failed attempts on the same IP/account the rate-limit
middleware returns **429** + `Retry-After`. Production recommendation: configure Cloudflare
Turnstile on `/auth/login`, `/auth/register`, `/auth/refresh` and require `cf-turnstile-response`.

### 3.5 Session management

- Access JWT (HS256, 30-min default), claims `sub, tid, role, sid, type, iat, exp`.
- Refresh: opaque random, only SHA-256 stored, **rotated on every use**, presenting an already-
  rotated token revokes the entire chain (reuse detection).
- httpOnly + SameSite=Lax + Secure (in prod) cookie for the refresh; access stays in memory
  (no localStorage).
- `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `DELETE /auth/sessions` (sign out other
  devices), `POST /auth/password-change` (revokes others).
- Idle / absolute session expiry honoured.

---

## 4. Transport & Storage Encryption

- **TLS**: terminate at the ingress (NGINX / Cloudflare / ALB / Application Gateway). Enforce
  TLS 1.2+ with the modern profile (TLS 1.3 preferred). Sample NGINX snippet in
  [`22-infra-deployment.md`](22-infra-deployment.md) §6.
- **HSTS**: emitted by the API itself (`max-age=31536000; includeSubDomains; preload`) in
  addition to ingress, so layered defence holds even if the ingress is misconfigured.
- **At rest (database)**: PostgreSQL **TDE** via AWS RDS / Azure Database / GCP CloudSQL
  encryption-at-rest options, OR `pg_crypto` column-level encryption (recommended for
  PII columns in air-gapped on-prem deployments). The application **also** encrypts the
  `users.mfa_secret` column at the app layer (AES-256-GCM via `cryptography.Fernet` with a
  32-byte key from `MFA_ENCRYPTION_KEY`) so even a leaked DB dump can't unlock TOTPs.
- **At rest (object storage)**: enable SSE-S3 / SSE-KMS on the bucket. The application stores
  per-tenant prefixes (`tenants/<id>/...`) so per-tenant KMS keys are an upgrade path.
- **Backups**: take encrypted backups (`pg_dump | age -e ...` or RDS snapshots with KMS).

---

## 5. Secure Headers (set by the API itself; ingress should also set)

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; img-src 'self' data: https:; style-src 'self'
  'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com;
  connect-src 'self' <api-origin>; frame-ancestors 'none'; base-uri 'self';
  form-action 'self'; object-src 'none'; upgrade-insecure-requests
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: accelerometer=(), camera=(), geolocation=(), microphone=(), payment=()
X-Request-Id: <uuid>
```

CSP for the Next.js frontend is set in `next.config.mjs` headers (see §16 of the deployment
guide). When inline scripts are introduced, **use nonces** rather than `'unsafe-inline'`.

---

## 6. Cryptography

### 6.1 Hashing

- Passwords: **bcrypt** (cost 12, see [`app/security.py`](../apps/api/app/security.py)).
- Refresh tokens & API keys: **SHA-256** of the random token (only the hash is stored).
- Recovery codes: SHA-256.
- Document integrity: SHA-256 hash of the contract body snapshotted on send.

### 6.2 Symmetric encryption at rest

Sensitive columns (currently: `users.mfa_secret`) are encrypted **transparently** via the
`secrets_box` module using **AES-256-GCM** (Fernet — AES-128-CBC + HMAC-SHA256 in classic
Fernet; or AES-256-GCM if `cryptography>=3.4` is available, which it is). Rotation is
supported by chaining old keys via `MFA_ENCRYPTION_KEYS` (newline-separated; first is current).

### 6.3 Signatures

- Webhook payloads: `X-CM-Signature: t=<unix>,v1=<hex>` — HMAC-SHA256(secret, "<unix>.<body>").
- JWT: HS256 + 256-bit secret (production refuses to boot under 32 bytes).

---

## 7. Input Validation & Output Encoding

- **Inbound:** Pydantic v2 models on every route — types, lengths, ranges enforced. `EmailStr`
  validation. Numeric fields clamped at the model.
- **Tab coordinates**: explicitly clamped server-side to `[0..1]`.
- **Outbound:** React/Next.js auto-escapes JSX. Markdown is rendered server-side into a
  controlled PDF (no HTML execution). Public signing page never echoes recipient-supplied HTML.
- **File uploads**: MIME-sniff + magic-bytes check planned; max-size enforced via
  `max_upload_mb`. Per-tenant key prefix. Antivirus scan (clamav / Lambda hook) is a
  deployment-side step.

---

## 8. Rate Limiting & Abuse Controls

In-process middleware (`app/middleware/rate_limit.py`) gates by `(client_ip, route_class)`:

| Route class | Limit | Burst | Note |
|---|---|---|---|
| `/auth/login` | 5 / min | +5 burst | Hard 429 + `Retry-After` |
| `/auth/register` | 3 / min | — | |
| `/auth/refresh` | 10 / min | +10 | |
| `/auth/mfa/*` | 8 / min | — | |
| `/auth/otp/send` | 3 / 5 min | — | |
| `/sign/{token}/sign` | 10 / min / IP | — | Public; tighten at WAF |
| Everything else | 120 / min | +30 | Tenant + user scoped |

**Production**: swap the in-memory bucket store for a Redis-backed one (we have Redis already
for Celery). The bucket interface is decoupled so this is a 1-file change.

**Login lockout**: 5 failed login attempts on the same email in a rolling 10-min window flips
the user to a 15-min lockout (returns 423 *Locked* with `Retry-After`). Successful login or
admin reset clears the counter. Failed-login + lockout events go to the audit log.

---

## 9. Audit Trail & Security Event Logging

Every security-relevant action posts an `AuditLog` row (`audit_log` table, append-only by
convention, RLS-scoped) with `at, actor_id, actor_name, action, object_type, object_id,
object_label, ip, meta`. Audited events include:

```
auth.login.success
auth.login.failed
auth.login.locked
auth.refresh.reuse_detected
auth.mfa.enabled / .disabled / .verified / .failed
auth.password.changed
auth.session.revoked / .revoke_all
user.invited / .updated / .deactivated / .reactivated
contract.created / .updated / .deleted / .status_changed / .submitted
contract.workflow_decision / .signature_prepared / .sent_for_signature
contract.signature_voided / .renewed / .commented / .pdf_generated
obligation.created / .updated / .deleted
workflow.created / .updated / .deleted
api_key.created / .revoked
webhook.created / .updated / .deleted
admin.sweep_renewals
workspace.updated
template.created / .updated / .deleted
```

Combined with structured JSON access logs, this is sufficient for SIEM ingestion (Splunk CIM,
Elastic ECS, Microsoft Sentinel). See [`26-monitoring-observability.md`](26-monitoring-observability.md)
for the mapping.

---

## 10. Secrets Management

Local dev: `.env` files (gitignored). Production:

| Platform | Where secrets live | How the app reads them |
|---|---|---|
| Kubernetes | `Secret` objects, mounted as env vars (see [`infra/k8s/secret.example.yaml`](../infra/k8s/secret.example.yaml)) | Pydantic `Settings()` |
| AWS | **Secrets Manager** or **Parameter Store** (SSM) | Inject via ECS task definition or External Secrets Operator in EKS |
| Azure | **Key Vault** + **CSI driver** or **AAD Workload Identity** | Same as above |
| GCP | **Secret Manager** + Workload Identity | Same |
| On-prem | HashiCorp **Vault** + Vault Agent / Vault Sidecar | Same |

The CI pipeline checks for **hardcoded secrets** via `trufflehog` and `gitleaks` on every PR.

---

## 11. Compliance Mappings (informational)

The control set above gives substantial coverage for:

- **ISO/IEC 27001:2022** Annex A controls (5.x, 8.x);
- **SOC 2** — Trust Services Criteria for **Security**, **Availability**, **Confidentiality**;
- **HIPAA** Security Rule — administrative + technical safeguards (encryption, audit, access);
- **GDPR** — Article 32 (security of processing), Article 30 (records — see Audit), Article 33
  (breach notification — supported by SIEM + alert routing);
- **PCI DSS 4.0** — Req. 2 (config), 3 (data at rest), 4 (in-transit), 7 (need-to-know), 8 (auth),
  10 (logging & monitoring). *Note: we never store cardholder data — billing is external.*

A formal mapping document is requested before procurement; section §11 is provided as
direction, not certified attestation.

---

## 12. Hardening Checklist (use at deployment)

```
☐ ENV=production (refuses the default secret_key + flips cookie_secure=true expectation)
☐ SECRET_KEY rotated, 32+ bytes from a CSPRNG
☐ MFA_ENCRYPTION_KEY set (Fernet key); never logged
☐ TLS 1.2+ at the ingress; HSTS preload submitted after 6 months
☐ Strict CSP (no unsafe-inline once frontend allows); review nonces
☐ CORS_ORIGINS narrowed to actual frontend domains
☐ COOKIE_SECURE=true, COOKIE_SAMESITE=lax (or strict if no cross-site flows)
☐ Database TDE / SSE-KMS for S3
☐ Backups encrypted + tested restore in pre-prod
☐ Antivirus scan on upload (ClamAV / Lambda hook)
☐ WAF in front (OWASP CRS); CAPTCHA on /auth/{login,register}
☐ NetworkPolicy locks egress (block RFC1918 / link-local / cloud metadata)
☐ Audit log retention 10 years; archive >1 year to cold storage
☐ SIEM receives stdout JSON logs; alert on auth.login.failed > N, refresh.reuse_detected, etc.
☐ Container images cosign-signed; admission webhook verifies
☐ Patch SLAs from §21 honoured by ops team
☐ Quarterly VAPT engagement; remediation tickets opened with severity SLAs
```
