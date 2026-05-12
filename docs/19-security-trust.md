# 19 — Security & Trust

A contract system is, fundamentally, a *trust* product — its job is to be the defensible record of who agreed to what, when. Security here isn't a feature list bolted on; it's the spine, and it's **shown** to users (Verified seals, tamper indicators, access transparency) as much as it's enforced. This doc covers: authN/Z & RBAC, multi-tenant isolation, e-signature legal model, tamper-evidence, encryption, secure sharing, audit, app-security hardening, AI governance, and a compliance map.

---

## 1. Authentication

- **Passwords** (when not SSO-only): Argon2id hashing, breach-corpus check on set (reject known-compromised), configurable org policy (length, complexity is *not* over-prescribed — length + breach-check beats complexity theatre), no forced rotation by default (rotate on suspicion), rate-limited + progressively-delayed + lockout-after-N attempts on login.
- **MFA:** TOTP (authenticator apps), email OTP, SMS OTP, and **WebAuthn/passkeys** (the strongest, phishing-resistant — push hard for it); enrollment requires confirming with a live code; **recovery codes** generated at enrollment (shown once, must be downloaded), regenerable, admin-assisted reset path if exhausted. Org policy: MFA optional / required-for-admins / required-for-all; "trusted device for N days" (a revocable device cookie) so MFA isn't asked every login on a known device.
- **SSO:** SAML 2.0 and OIDC for enterprise IdPs (Okta, Entra/Azure AD, Google Workspace, Ping, etc.); domain-claiming (verify a DNS TXT record → all users with that email domain route to SSO); JIT provisioning + SCIM for full lifecycle (create/update/deactivate from the IdP, group→role mapping); an "SSO-only" toggle disables passwords once everyone's linked.
- **Tokens:** short-lived JWT access tokens (~15 min, JWKS-published rotating signing keys, claims = ids + role + scopes only — no secrets/PII); **refresh tokens** httpOnly+Secure+SameSite cookie for browsers, rotated on every use, with **reuse detection** (presenting an already-spent refresh token revokes the whole session chain and forces re-auth — defeats stolen-token replay); API tokens for integrations are scoped, expiring, revocable, rate-limited.
- **Step-up auth:** sensitive operations (export the audit log, change roles/permissions, disable MFA, delete a contract, delete the workspace, manage API keys/SSO, high-assurance signing) require a *recent* re-authentication (password or MFA) regardless of session validity; the elevated state is short-lived; every step-up and every sensitive action is a high-severity audit entry.
- **Session management UX:** users see their active sessions/devices (IP, location, last-active, browser) and can revoke any/all; admins can force-sign-out a user; "new device sign-in" triggers a notification email; idle timeout + max session length are org-configurable.

---

## 2. Authorization — RBAC + resource ACLs (the model)

Access = **(role permissions) ∩ (resource ACL) ∩ (tenant feature/plan flags)**.

- **Roles** (system: Owner, Admin, Manager, Author, Approver, Reviewer, Viewer, Auditor, Billing Admin; plus tenant-defined custom roles): each role grants a set of **permissions** (a static catalog — `contracts.view/create/edit/submit/approve/send_for_signature/delete/share/export`, `templates.manage`, `clauses.manage/approve`, `workflows.manage/run`, `users.manage`, `roles.manage`, `settings.security/integrations/billing`, `audit.view_all/export`, `ai.use`, `reports.view/build`, `tenant.delete`, …). Each permission grant carries a **scope**: `all` (workspace-wide) / `team` (within the user's teams) / `own` (resources they own/created) / `assigned` (where they're in the workflow chain or a named signer/approver) / `shared` (explicitly shared with them) / `none`.
- **Resource ACLs** (`acl_entries`): a contract (or folder/template/report) can be shared to a *user*, a *team*, *everyone-in-the-org*, an *external contact*, or via a *secure link*, each with a permission level (view / comment / suggest / sign / edit), an optional expiry, an optional passcode; the owner + the creator + the workspace admins always have access; sharing/unsharing is audited.
- **Enforcement (defense in depth):** (1) the **API layer** checks `require_permission(...)` deps on every endpoint; (2) the **service layer** re-checks via the domain policy (so a job calling the same service can't bypass it); (3) the **repository layer** always filters by `tenant_id` *and* applies the visibility scope (you literally can't fetch what you can't see); (4) **PostgreSQL RLS** is the hard floor on tenant isolation (a forgotten `WHERE` can't leak across tenants); (5) the **UI** hides what the role can't do (no dead buttons) — but the UI is never the security boundary, the server is.
- **Least privilege:** new users default to a minimal role; broad roles (Admin, Auditor) are deliberate grants; the "last Owner" invariant (always ≥1 active Owner; transfer is the only exit); service accounts get the narrowest scopes that work; impersonation (Platform Admin only) is time-boxed, banner-flagged, tenant-notified, and heavily audited.

---

## 3. Multi-tenant isolation

Covered in Doc 14 §5 / Doc 15 / Doc 18 — recap of the security guarantees: every tenant-scoped row carries `tenant_id`; **RLS policies** key off a per-transaction session variable set from the JWT's tenant claim (a privileged role bypasses only for explicit cross-tenant system jobs); the repo layer *also* filters by tenant; S3 uses per-tenant key prefixes + per-tenant encryption keys; Redis keys are tenant-namespaced; the AI assistant only ever sees data the requesting user can see (never another tenant's); the public API/webhooks are tenant-scoped by the token; logs/metrics carry `tenant_id` but cross-tenant queries require operator privileges; a tenant can be promoted to a dedicated schema/DB/region for stronger physical isolation when contracted. **No customer can ever see, query, or be served another customer's data** — and that property is enforced at four layers, not one.

---

## 4. E-signature — the legal model

For an e-signature to hold up, it must establish, and the system must *prove*: **intent** to sign, **consent** to do business electronically, **attribution** to the signer, **integrity** of what was signed, and **retention** of the record. How we do each:

- **Consent:** before signing, the signer is shown an e-sign disclosure (electronic records & signatures consent — wording reviewed by counsel, available in EN/AR) and must affirmatively agree; the consent (text version, timestamp, IP) is recorded.
- **Intent:** the signer must take a deliberate, signature-specific action — open a "Sign" field, adopt a signature (type / draw / upload), and click "Finish" — not a buried checkbox; the document is presented in full (configurably, scroll-to-end required) before signing is enabled.
- **Attribution:** identity assurance is per-recipient and configurable — *email-link* (the link was sent to that address), *email/SMS OTP* (proves control of the inbox/phone), *ID verification* (third-party document/biometric check) for high-assurance contracts; in-person/kiosk signing records the host; "signing on behalf" is recorded as such. The captured signature image, the access token, and the recipient's identifying details tie the act to a person.
- **Integrity:** at the moment a recipient signs, the system records a cryptographic **hash of the document as it stood** for that signer; when all parties have signed, the document is **flattened** into a final PDF (signatures embedded, an audit-trail page appended), a final hash computed, and a **Certificate of Completion** generated (parties, each recipient's name/email/identity-level/timestamp/IP/device/geo, the document hashes, the consent records, a **timestamp-authority token** (RFC 3161) anchoring "this existed at this time"). The sealed PDF + certificate + hash are stored immutably; any later byte-change breaks the hash (detectable — see §5). Optionally, for jurisdictions requiring it, a qualified/advanced electronic signature provider (eIDAS-style, or a regional licensed CA) can be plugged in behind the `signing` module's provider interface.
- **Retention:** the signed document, certificate, full signature event log, and audit slice are retained per the tenant's retention policy (and indefinitely under legal hold), exportable as a sealed **evidence package**, and survive workspace lifecycle changes per the data policy.
- **The audit trail** (the certificate + the per-recipient `signature_events` + the contract's audit log) is what gets produced in a dispute — it reconstructs, minute by minute, who saw what, when, from where, and what they did. This is the product's core value: not "we let you sign" but "we can prove it stands up."

---

## 5. Tamper-evidence & document integrity (shown to the user)

- **Hash-chained audit log** (Doc 15 §3): every audit entry includes `H(prev_hash ‖ entry)` → any insertion, deletion, or modification breaks the chain; the **"verify chain"** action recomputes and confirms; the chain's head hash is periodically anchored externally (emailed to admins / written to a separate store / optionally notarized) so even a full-DB compromise can't silently rewrite history without the anchor disagreeing.
- **Document hashing:** every contract version and every sealed PDF stores its content hash; on access, the served file's hash is checked against the recorded one; a mismatch flips the contract header into a loud red **`IntegrityBanner`** ("this document may have been altered since it was signed — contact your administrator / view audit"), alerts admins, and creates a high-severity audit entry. The **`VerifiedSeal`** component on a signed contract shows (in a popover) the hashes, the signing certificate, the timestamp-authority token, and "unaltered since {date}" — turning integrity from an invisible property into visible reassurance.
- **Access transparency:** every contract's **Access tab** lists everyone who *can* access it (and via what grant) and everyone who *did* (with timestamp, IP, device, geolocation), exportable — so a contract owner can answer "who's seen this?" without filing a request. Every view, download, share, and revoke is logged.

---

## 6. Encryption

- **In transit:** TLS 1.2+ everywhere (public endpoints, service-to-service, DB connections, Redis); HSTS; modern cipher suites; certs auto-managed (cert-manager / ACM) and rotated.
- **At rest:** the database is encrypted at the storage layer (managed-service KMS or self-managed LUKS/TDE); **blobs in S3** use envelope encryption — each object/tenant has a data key wrapped by a KMS master key — plus bucket-level SSE as a baseline; backups encrypted; secrets at rest in a vault.
- **Field-level:** especially sensitive fields (MFA secrets/credentials, SSO/SCIM secrets, API token material, webhook secrets, payment references) are encrypted in the DB with an application key (separate from the storage-layer key) so a DB dump alone doesn't yield them.
- **Key management:** KMS for master keys; rotation supported (data keys re-wrapped on rotation); least-privilege key access (only the services that need a key can use it); key usage is audited; on-prem deployments can BYOK / use their own HSM.
- **Secrets:** never in code, images, or env files in the repo; injected at runtime from Vault / AWS Secrets Manager via the External Secrets Operator; rotated; access scoped per workload.

---

## 7. Secure sharing & the external surface

- **Secure links** (the external portal / share grants): a high-entropy token (hashed at rest), an **expiry** (sender-set, default conservative), a **permission scope** (view / comment / suggest / sign), an optional **passcode**, an optional **email/SMS verification** step, and **revocability** (revoke any link any time → it dies instantly); per-recipient links (forwarding one to a colleague doesn't grant them access); every link creation, use, and revocation is audited; links to *executed* copies also self-expire.
- **The external user sees only** the specific contract(s) shared with them, only the actions granted, never the app, never other contracts, never internal comments/audit, never another tenant — a narrow, time-boxed, audited grant (Module 21).
- **Watermarking:** drafts downloaded by anyone are watermarked "DRAFT — not executed"; pre-execution copies an external signer downloads are watermarked; the executed copy is clean (+ the certificate).
- **Email security:** transactional emails are sent over authenticated, SPF/DKIM/DMARC-aligned domains; the "Review/Sign" links carry the signed token and survive the recipient's auth; sensitive content isn't put *in* the email body, just a secure link.

---

## 8. Application security hardening

- **Input validation** on every endpoint (Pydantic schemas — strict types, lengths, ranges, allowed values); output encoding everywhere in the UI (React escapes by default; sanitize any user-supplied HTML in rich content; the block-editor document is structured JSON, not raw HTML).
- **Injection:** parameterized queries only (SQLAlchemy — no string-built SQL); no shell-out with user input; file uploads validated by type/size/magic-bytes and scanned (malware scan on ingest); uploaded SVGs/HTML never served inline from a user-content origin.
- **XSS/CSRF:** strict **CSP** (no inline scripts except nonce'd, `frame-ancestors 'none'`, tight `connect-src`), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`; state-changing requests use the bearer token (not just a cookie), and where cookies are used (refresh) they're `SameSite` + paired with a CSRF token; the API has no ambient-authority cookies for state changes.
- **CORS:** an explicit allowlist (the app origins + verified tenant custom domains); no wildcard with credentials.
- **Rate limiting & abuse:** per-token, per-tenant, and per-IP (for unauthenticated endpoints like `/sign/{token}`) token-buckets; login/OTP/forgot-password have stricter limits + lockouts; bulk endpoints have batch caps; anomalous patterns (credential stuffing, scraping, OTP brute force) escalate to temporary blocks + alerts; a WAF in front for the common attack patterns + bot management.
- **Dependencies & supply chain:** lockfiles; automated CVE scanning (Dependabot/Renovate + Snyk-style) on PRs and on running images; SBOM generated per build; container images signed (cosign) and verified at deploy; base images pinned by digest and rebuilt regularly; CI runs SAST, secret-scanning, and IaC scanning; least-privilege CI tokens; protected branches; signed commits encouraged.
- **Runtime:** containers run as non-root, read-only root filesystems where possible, dropped capabilities, network policies (only the connections that should exist can), pod security standards enforced, no privileged containers, secrets mounted not baked, resource limits set (no noisy-neighbor / fork-bomb DoS).
- **Logging hygiene:** no secrets/tokens/PII in logs; structured, correlated, retained per policy; audit-grade logs separate and immutable; alerting on security-relevant events (failed-login spikes, step-up failures, RLS-bypass-role usage, hash-chain mismatches, mass-export, permission escalations, new-region access).
- **Vulnerability management:** a coordinated-disclosure program / `security.txt`; regular third-party penetration tests; bug-bounty (when mature); a documented incident-response plan (detect → contain → eradicate → recover → notify → post-mortem) with breach-notification timelines that meet the applicable regimes.

---

## 9. AI governance (because this is contracts)

Recap of Doc 09 §4, security framing: every AI output is **labeled** (model, timestamp), **confidence-scored**, **source-linked**, and **human-overridable**; the AI **never** auto-approves, auto-signs, or auto-edits a contract — it proposes, a human commits; consequential drafts carry "must be reviewed by counsel"; the AI sees **only what the requesting user can see** (enforced through the same authz layers — no cross-tenant, no out-of-scope); PII sent to external LLM/OCR providers is **minimized** and covered by DPAs (and a tenant can choose local/in-region models for residency); tenants control whether the AI feature is on at all, which provider/model, and whether prompts are used to improve models (**default off for enterprise**); prompt templates are **versioned and reviewed** (a prompt library in Platform Admin, change-controlled); outputs are **monitored** (thumbs up/down + "report", aggregate quality dashboards) and a poor-quality model/prompt can be rolled back; **everything the AI does is in the audit log**. The OCR human-correction feedback loop only feeds a fine-tuning dataset with explicit tenant consent, and the dataset is access-controlled.

---

## 10. Compliance map (where this is heading)

Designed *toward* — and built to make achievable — the regimes enterprise/government buyers ask about:

| Regime / standard | What in this design serves it |
|---|---|
| **SOC 2 (Type II)** — security, availability, confidentiality, processing integrity | RBAC + least privilege + audit log; change management (CI gates, reviewed migrations, IaC); encryption in transit & at rest; backups + tested restores + DR; monitoring/alerting/incident response; access reviews; vendor management; the immutable audit trail itself is a control |
| **ISO 27001 / 27017 (cloud) / 27018 (PII in cloud)** | ISMS-friendly: documented controls, risk treatment, access control, crypto policy, supplier security, logging, incident management, business continuity — all of the above |
| **GDPR / UK-GDPR** | data minimization; DSAR support (export a subject's data); right-to-erasure (purge + pseudonymize-in-audit, with the entry/chain preserved); DPAs with sub-processors (OCR/AI/email/storage); records of processing; data residency options; breach notification; privacy by design (the AI scoping, the watermarking, the access transparency) |
| **CCPA/CPRA & similar US state laws** | same DSAR/erasure machinery; "do not sell/share" — N/A (we don't sell data) but disclosed |
| **eIDAS / UNCITRAL e-sign model laws / ESIGN & UETA (US) / regional e-transaction laws** | the e-signature legal model in §4 (intent, consent, attribution, integrity, retention, audit trail, timestamp authority); pluggable qualified-signature providers where advanced/qualified signatures are required |
| **GCC / MENA data-protection & e-transaction laws** (e.g., Oman PDPL, Saudi PDPL, UAE PDPL, Bahrain PDPL, Qatar; Saudi NDMO/SDAIA, UAE/Bahrain cloud rules) | data residency (DB + S3 in-region, dedicated cluster on contract); Arabic + Hijri support (Doc 13); local-model options for AI/OCR; the audit/retention machinery; sovereign/on-prem deployability (the whole stack runs on self-managed K8s + S3-compatible storage) — this is a major reason the architecture avoids cloud-vendor lock-in |
| **HIPAA / financial-sector rules** (if customers in those verticals) | encryption, access controls, audit, BAAs/equivalent, data segregation, retention — the same foundations; vertical-specific add-ons as needed |
| **Accessibility — WCAG 2.2 AA, EN 301 549, ADA/Section 508** | the accessibility commitments in Doc 01 §4.6 / Doc 03 (keyboard, contrast, focus, SR labels, reduced-motion, no color-only status, touch targets, RTL) — baked into `@cm/ui` and checked in CI |

None of these are "done" by a design doc — but the architecture is built so that achieving certification is a matter of *operating* the controls that already exist, not retrofitting them. The single biggest structural decision in service of this market: **no cloud-vendor lock-in** — the entire platform (FastAPI, Postgres, Redis, Celery, S3-compatible storage, Kubernetes) runs equally on a public cloud or on a customer's sovereign/on-prem infrastructure, which is exactly what GCC government and large regional enterprise procurement requires.
