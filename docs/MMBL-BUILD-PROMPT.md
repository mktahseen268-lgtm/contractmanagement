# Build Prompt — MMBL Contract Digitization Solution (production)

> **How to use this file.** Open Claude Code at the repository root and paste **Section 0 plus the one phase you are working on**. Do not paste the whole file — each phase is a multi-day work package. Phases 1, 4 and 5 should run as three parallel streams from day one; the RFP allows only 2–3 months for delivery.

---

## 0. Standing context — include this with every phase

You are working in `contract_management/contractmanagement`, a multi-tenant E-Contract lifecycle platform: FastAPI + SQLAlchemy 2.0 + Alembic + Celery (`apps/api`) and Next.js 14 App Router + React 18 + TypeScript + Tailwind + Tiptap (`apps/web`). Read `CLAUDE.md` before touching anything — it is accurate and it documents the invariants that will bite you.

**We are building this to win the Mobilink Microfinance Bank (MMBL) RFP for a Contract Digitization Solution.** The two requirement documents are `docs/MMBL-RFP-GAP-ANALYSIS.md` (which maps every RFP clause to its current state in this code) and the RFP/RFI PDFs. MMBL scores 13 weighted parameters and needs 70% to qualify; the work below is ordered by that weighting.

### Non-negotiables for every phase

1. **Production-complete, not scaffolding.** Every feature must be end-to-end: migration → model → service → router → schema → typed API client → UI wired to real endpoints → tests. A page that renders a hard-coded array is a defect, not a milestone. `apps/web/src/app/(app)/` currently contains ~24 such mockup pages (`clauses`, `redline`, `docx-studio`, `signature-studio`, `bulk-send`, `client-portal`, `folders`, `custom-fields`, `departments`, `legal-hold`, `identity-check`, `passkeys`, `roles`, `search`, `sso-admin`, `temporary-access`, `integrations`, `obligations`, `ai-analysis`, `workflow-builder`, …). **Every one of them must either be wired to a real backend by the end of its phase, or deleted.** MMBL reserves the right to a live demo; invented data in front of the evaluation committee is fatal.
2. **Audit everything.** Call `add_audit_entry` for every state-changing action. The per-tenant HMAC hash chain in `audit.py` is one of this product's genuine strengths — do not add a write path that bypasses it.
3. **Keep both isolation layers.** Repository code filters by `tenant_id` *and* Postgres RLS enforces it. Do not remove either, even in single-tenant mode.
4. **Migrations are hand-written where they touch Postgres DDL.** Never blindly accept `alembic revision --autogenerate` output — it does not see RLS policies. Every new migration must be portable per Phase 0.
5. **No new secrets in code.** `gitleaks`, `bandit`, `semgrep p/owasp-top-ten`, `pip-audit` and `npm audit` run in CI and must stay green.
6. **Tests ratchet upward.** Every phase adds `pytest` coverage in `apps/api/tests/`. CI must never regress.
7. **Nothing is "configurable and therefore done".** The RFP is evaluated on demonstrated capability. If a provider seam defaults to a stub (as `ocr_provider.py` does today), the real adapter must be the default for the MMBL build profile.
8. **On-prem only.** No feature may require a foreign-hosted SaaS at runtime. All data — contract content, signatory PII, key material, audit logs — stays inside the deployment. Where an external service is genuinely needed (sanctions lists, TSA), it must be swappable and documented.

### Definition of done, per phase
- [ ] Alembic migration, portable across Postgres / MSSQL / Oracle (Phase 0 rules)
- [ ] SQLAlchemy models + Pydantic schemas
- [ ] Service layer with the business rules; routers stay thin
- [ ] Audit entries on every mutation
- [ ] Typed methods in `apps/web/src/lib/api.ts` and `lib/types.ts`
- [ ] UI wired, loading/empty/error states handled, no sample arrays
- [ ] `pytest` unit + integration tests, including negative and permission cases
- [ ] `next build` and `next lint` clean; `ruff` clean
- [ ] A short entry appended to `docs/MMBL-RFP-GAP-ANALYSIS.md` flipping the affected rows to ✅

---

## Phase 0 — Deployment profile: single-tenant on-prem + Oracle/MSSQL first-class

**Why:** The RFP requires on-premises hosting only, all data inside Pakistan, and states "Database preferably Oracle or MSSQL server". MMBL is one bank — multi-tenancy buys nothing here and its Postgres-only RLS is exactly what makes MSSQL/Oracle painful (`docs/25-database-portability.md` concedes isolation degrades to app-layer filtering on MSSQL).

**Build:**

1. **Deployment mode setting.** `DEPLOYMENT_MODE = "saas" | "single_tenant"` in `config.py`. In `single_tenant`: one tenant row is provisioned at install, `SINGLE_TENANT_ID` is resolved once at startup, registration is disabled, and tenant-switching UI is hidden. `deps.get_current_user` still sets the tenant ContextVar — the code path does not fork.
2. **Database dialect abstraction.** Introduce `apps/api/app/db_dialect.py` exposing the operations that currently assume Postgres:
   - `enable_row_security(table)` → Postgres RLS policy; on MSSQL emit a Security Policy with an inline table-valued predicate function; on Oracle emit a VPD policy via `DBMS_RLS.ADD_POLICY`. In `single_tenant` mode all three are optional and gated by `ENFORCE_DB_ISOLATION`.
   - `json_column()` → JSONB on PG, `NVARCHAR(MAX)` + `ISJSON` check on MSSQL, `CLOB` + `IS JSON` on Oracle.
   - `json_index(table, col)` → GIN on PG, computed-column index on MSSQL, function-based index on Oracle.
   - `advisory_lock(key)` → `pg_advisory_xact_lock` on PG, `sp_getapplock` on MSSQL, `DBMS_LOCK.REQUEST` on Oracle. The audit chain depends on this — it must be correct on all three.
   - `set_tenant_guc(tid)` → `set_config` on PG, `SESSION_CONTEXT` on MSSQL, `DBMS_SESSION.SET_CONTEXT` on Oracle.
   - `fulltext_search(col, q)` → `tsvector`/`websearch_to_tsquery` on PG, `CONTAINS` on MSSQL, `Oracle Text CONTAINS` on Oracle. (Consumed in Phase 5.)
3. **Rewrite migrations `0002_rls` and `0013_hardening`** to route their DDL through `db_dialect`, and add a `conftest` matrix so the test suite runs against Postgres and MSSQL (Oracle in CI if a container is available, else a documented manual gate).
4. **Drivers:** add `pyodbc` and `oracledb` as optional extras (`requirements-mssql.txt`, `requirements-oracle.txt`); keep the base install lean.
5. **Remove SQLite from the supported matrix for the MMBL profile.** Keep it for local dev only, and make `validate_for_production()` reject it (it already does) *and* reject `DEPLOYMENT_MODE=single_tenant` with a SaaS-shaped config.
6. **Data residency control.** New setting `DATA_RESIDENCY_REGION` (default `PK`). Startup refuses to boot if any configured storage endpoint (S3/MinIO), SMTP host, OCR endpoint or OTel collector resolves outside the allowlist. Emit a `residency_check` audit entry at boot. This is the evidence for the RFP's "Hosting & data residency statement".
7. **Purge & archive.** `RETENTION_YEARS=10`, `HOT_SEARCH_YEARS=1`. A nightly Celery beat moves executed contracts and their files older than the hot window to a cold storage prefix/tier and drops them from the search index while keeping them retrievable; a second job hard-purges beyond retention with a legal-hold check (Phase 8) and an audit entry. Direct answer to "Storage capacity for 10 years of financial records, with 1 year instantly searchable" and "Data purging and archiving".

**Acceptance:** the full `pytest` suite passes against Postgres and MSSQL; a single-tenant install boots with zero tenant setup; archive and purge jobs are covered by tests using a frozen clock.

---

## Phase 1 — PKI and Certificate Lifecycle Management (RFP weight 11%, eligibility gate)

**Why:** MMBL requires a complete, in-platform PKI, and requires the bidder to swear that the PKI/eSignature engine is its own proprietary, non-open-source, IP-owned work, backed by an SBOM. Nothing in this area exists today: `signing_provider.py` seals with a single shared PKCS#12 file, which is precisely what the RFP forbids ("shared or role-based certificates are not permitted").

**Ground rule:** build the CA on cryptographic *primitives* (`cryptography` / `asn1crypto`), not by wrapping EJBCA, Dogtag, step-ca or any other CA product. Primitive libraries are fine and expected in the SBOM; a wrapped open-source CA breaks the sworn undertaking.

**Build a new package `apps/api/app/pki/`:**

1. **Key custody seam — `pki/keystore.py`.** `KeyStore` ABC with `generate_keypair`, `sign`, `public_key`, `destroy`.
   - `SoftKeyStore` — dev/CI. Private keys encrypted at rest with the existing Fernet chain (`secrets_box.py`).
   - `Pkcs11KeyStore` — production. PKCS#11 via `python-pkcs11`, keys generated **inside** the HSM and never exported. Config: `HSM_LIBRARY_PATH`, `HSM_SLOT`, `HSM_PIN` (from env/secret store, never a file in the repo). Must work against SoftHSM2 in CI so the code path is tested, and against a FIPS 140-2 Level 3 device in production. Ship a documented compatibility note for Thales Luna / Utimaco / Entrust nShield.
2. **CA hierarchy — `pki/ca.py`.** Offline Root CA (generated once, exported for cold storage, never online) → online Issuing CA. Every CA operation is audited.
   - **Critical:** design the Issuing CA so it can later be re-chained to an ECAC-accredited root under the Electronic Transactions Ordinance 2002 **without re-architecture and without re-issuing existing certificates**. Concretely: keep the issuing CA's key and subject DN stable, support cross-certification (issue a second CA certificate for the same key signed by the future ECAC root), and store trust anchors in a table rather than a file so the chain can be extended at runtime. Document this in `docs/PKI-ARCHITECTURE.md` — MMBL asks for exactly this readiness.
3. **Registration Authority workflow — `pki/ra.py` + `models.CertificateRequest`.** No certificate is issued without an approved RA request. Flow: enrolment request (internal user via HR/identity attributes from OIDC/SCIM/SAML claims; external signatory via the Phase 2 OTP-verified identity binding) → RA officer review → approve/reject → issuance. Two-person rule configurable (`RA_DUAL_CONTROL`). Every transition audited with the evidence attached.
4. **Certificate lifecycle — `models.Certificate` + `pki/lifecycle.py`.** Columns: `id`, `tenant_id`, `subject_dn`, `serial_number`, `subject_user_id` *or* `subject_party_id`, `key_id` (keystore handle), `pem`, `not_before`, `not_after`, `status` (`pending|active|suspended|revoked|expired`), `revocation_reason` (RFC 5280 codes), `revoked_at`, `issued_by_ca_id`, `request_id`. Operations: **enrol, issue, renew, suspend, resume, revoke**. Enforce **one certificate per signatory, uniquely bound private key, no shared or role certificates** at the database level (partial unique index on active certs per subject) and in the service layer.
5. **CRL — `pki/crl.py`.** Full and delta CRLs, signed by the issuing CA, regenerated on every revocation and on a schedule (`CRL_VALIDITY_HOURS`), published at `GET /pki/crl/{ca_id}.crl` with `application/pkix-crl`. Include the CRL Distribution Point extension in every issued certificate.
6. **OCSP responder — `pki/ocsp.py` + `POST /pki/ocsp`.** RFC 6960: parse the request, look up status, sign the response with a dedicated OCSP signing certificate carrying the `id-kp-OCSPSigning` EKU, support nonce, return `good|revoked|unknown`. Include the AIA/OCSP URL extension in issued certificates. Must respond in <200 ms at p95 under load.
7. **Third-party certificate validation — `pki/validate.py`.** Full RFC 5280 path validation against a configurable trust store seeded with DigiCert, GlobalSign, Sectigo and Entrust roots, with CRL and OCSP revocation checking, so overseas signatories who cannot be issued an MMBL certificate can still sign. Cache revocation responses with respect to `nextUpdate`.
8. **Admin UI — `app/(app)/pki/`.** Real pages backed by real endpoints: CA status and chain viewer, pending RA queue with approve/reject, certificate register with filters and lifecycle actions, CRL/OCSP health, HSM connection status, audit view. Replace the mockup `identity-check` and `passkeys` pages or delete them.
9. **SBOM.** Wire `cyclonedx-bom` (Python) and `@cyclonedx/cyclonedx-npm` (web) into CI, publishing `sbom-api.json` and `sbom-web.json` as build artefacts. MMBL requires an SBOM with the sworn undertaking.

**Tests:** issue → validate chain → revoke → assert OCSP says `revoked` and the serial appears in the next CRL; renewal preserves subject binding and issues a new serial; suspension blocks signing and resumption restores it; shared-certificate issuance is rejected; SoftHSM round-trip proves the key never leaves the store; path validation accepts a valid third-party chain and rejects an expired/revoked one.

**Deliverable document:** `docs/PKI-ARCHITECTURE.md` covering hierarchy, key ceremony, HSM model, CP/CPS outline, ECAC chaining plan, and the SBOM reference. This is scored directly under "PKI architecture & SBOM".

---

## Phase 2 — Advanced eSignature depth (same 11% band as Phase 1)

**Build on top of Phase 1:**

1. **Per-signatory cryptographic signing.** Replace the shared-cert `PadesSigningProvider` with a signer that fetches *the signatory's own* certificate from the Phase 1 store and signs with the key in the keystore. PAdES-LTV: embed the signing certificate, the full chain, OCSP/CRL revocation data, and an RFC 3161 timestamp so the signature stays verifiable after certificate expiry. Every `SignatureEvent` records the certificate serial used.
2. **Visitor / merchant eSigning surface — `app/(portal)/esign/`.** Public-facing signing for merchants, customers and external counterparties **with no per-visitor user provisioning**. Entry points: a web link, a branch-tablet kiosk mode, a mobile link, and a **QR code** rendered in the portal and on printable handouts. Flow: land → identity binding (mobile/email **OTP**, plus optional CNIC capture) → view document with full scroll/consent tracking → sign → receive a copy. Identity evidence (OTP channel, masked identifier, timestamp, IP, user agent, device fingerprint, geolocation if consented) is bound into the signature record and printed on the Certificate of Completion. Rate-limited, CAPTCHA-gated, and sized for **100,000 external signatories/year** — add a load test proving it.
3. **Certificate issuance for visitors.** On successful OTP binding, auto-raise an RA request under a "visitor" policy profile and issue a short-lived per-signatory certificate. This is what makes "every signatory gets their own certificate" true for external parties.
4. **Smart signature tagging.** Auto-detect signature blocks in the rendered document (anchor-text detection on strings such as "For and on behalf of", "Authorised Signatory", "Signature", "Date", plus template-defined anchors) and place tabs automatically. Manual drag-and-drop stays as an override, not the default. Wire the `signature-studio` mockup to this or delete it.
5. **Wet-signature / hybrid path.** For counterparties requiring physical stamping (government clients): mark an envelope `hybrid`, generate a print pack, capture the scanned executed copy, run an integrity attestation (uploader identity, hash of the scan, declared execution date, optional witness), and seal it into the same audit chain and repository so the digital trail is unbroken. Status flows must converge with the e-signed path.
6. **Authority matrix.** `models.SignatoryAuthority` (department, contract type, value band, currency, required signatory role, escalation). When preparing an envelope the system proposes the correct signatories from the matrix; deviations require an override with a reason and are audited. Directly answers RFP §4a(ii) 4.1–4.2.
7. **Reviewer-as-signatory.** Explicitly allow the same user ID to be both reviewer and signatory (§4.3) — assert it in tests rather than leaving it implicit.
8. **Execution reliability.** Idempotent signing endpoints, envelope-level optimistic locking, retry with backoff on seal failures, and a dead-letter surface in the admin UI. §4.4 asks for a signing process "free from execution/signature failures" — build the observability that lets you claim it.

---

## Phase 3 — Document engine: Word round-trip, clause library, guided drafting

**Why:** the RFP's supplemental requirements and the whole RFI review loop depend on this. `python-docx` is currently not a dependency anywhere in the repo.

1. **DOCX round-trip — `apps/api/app/docx/`.**
   - **Export**: render a contract to `.docx` preserving MMBL's formatting and, critically, **clause numbering** (multi-level list numbering must survive). Implement against the OOXML part directly where `python-docx` is too high-level; do not flatten numbering into literal text.
   - **Import**: ingest a returned `.docx`, extract body content, **read `w:ins` / `w:del` tracked changes and `w:comment` comments**, and map them to internal revision and comment records with author and timestamp.
   - **Round-trip fidelity test**: export → import → export must be byte-stable for numbering, styles, tables and headers/footers on a corpus of at least 10 real MMBL-shaped agreements. Make this a CI test.
   - Wire the `docx-studio` mockup to this or delete it.
2. **Clause library — `models.Clause` + `models.ClauseVersion`.** Fields: category (IP, indemnity, confidentiality, anti-corruption, data privacy, export control, …), risk level (low/medium/high), jurisdiction tags, guidance notes, alternative/fallback clause references, approval status, version history, usage count. Full CRUD + search API + approval gate. Wire `app/(app)/clauses/`.
3. **Template repository with versioning and approval.** Extend `ContractTemplate` with version history, an approval workflow before a template becomes usable, effective/retired dates, and clause references. Templates carry **merge fields** and **LOV definitions**.
4. **Merge-field / auto-generation engine.** The RFI's core mechanic: select agreement type → structured form with drop-downs and LOVs and auto-population → submit → **the system generates the draft by merging the fields into the pre-approved template**. Build a typed field schema per template (`text|number|money|date|select|entity_ref|file`), server-side validation, and deterministic rendering into both the internal document and the DOCX export.
5. **Guided drafting wizard.** Step-through assembly: type → template → clause selection with risk indicators → field capture → preview → submit for review.
6. **Playbook / policy engine — `models.Playbook`.** Mandatory-clause checklists per contract type (anti-corruption, data privacy, IP, export control). On draft save and before approval, evaluate the document against the playbook and produce a deviation list. Feeds risk scoring (Phase 6) and the compliance report.
7. **AI assist (configurable, real by default in the MMBL profile).** Clause suggestion from metadata and playbook-deviation flagging, plus **AI data capture**: extract expiry dates, notice periods, values and parties from signed documents into contract fields with a confidence score and a human confirmation step. Change `OCR_PROVIDER` default for the MMBL build so extraction is real, not the stub — but keep it fully on-prem-capable (document the model-hosting option) since no MMBL data may leave the deployment. Wire the `ai-analysis` mockup or delete it.
8. **Redline & compare.** Real version diff with word-level highlighting between any two `ContractVersion` rows, in-system track changes with accept/reject per change, and threaded comments anchored to text ranges. Wire the `redline` mockup.

---

## Phase 4 — Workflow engine rebuild: parallel review, matrix, SLA, escalation

**Why:** `workflow_service.py` advances one step at a time and its own docstring says parallel steps, SLAs and escalation are "planned". The RFI is built entirely around concurrent multi-stakeholder review. This is where the functional score is won.

1. **Parallel step groups.** Replace the flat `WorkflowDefinition.steps` JSON list with a stage graph: a run has ordered **stages**, each stage holds one or more **steps** that execute concurrently. Per-stage completion policy: `all`, `any`, `quorum(n)`, `percentage(p)`. Each reviewer marks their own step complete **independently, without waiting for the others** (§3.2).
2. **Dynamic approval matrix — `models.ApprovalRule`.** Conditions on contract value bands, currency, contract type, department, risk level, counterparty jurisdiction and playbook-deviation count → resolved approver set. Evaluated at run start and re-evaluated when a material field changes (with an audited re-route).
3. **SLA and escalation.** Per-step `sla_hours`, business-calendar aware (configurable working days/hours and Pakistani public holidays). A Celery beat sweeps for breaches: reminder at a configurable fraction of the SLA, auto-escalation to the escalation path on breach, and an `escalations` feed. Records `escalations per month` and `mean time to resolve` for the KPI dashboard.
4. **Delegation / out-of-office.** `models.Delegation` (from_user, to_user, scope, start, end). Assignments route to the proxy automatically; both principal and proxy appear in the audit trail.
5. **Mid-flight reviewer changes.** Add or remove reviewers on a running stage (§3.6) with permission checks and audit.
6. **Non-standard classification.** Any client-side edit or tracked change automatically flips the agreement to **"Non-Standard"** (§3.1), which selects the non-standard approval path and forces Legal into the review set.
7. **Consolidated review view.** One master screen showing every internal stakeholder's comments and proposed amendments simultaneously (DFS, Legal, Finance, Risk, IS, Compliance), with a hard **`internal_only` privacy flag** on every comment and amendment. Externally shared views must be provably incapable of returning internal-only content — assert this in tests, it is a data-leak class of bug.
8. **@mentions.** Mention parsing in comments, a `Mention` record, notification fan-out, and an "mentions me" inbox filter (§3.4).
9. **Client-facing coordinator role.** A `client_facing` capability so only DFS/BBCORP users can transmit to the counterparty (§3.5); other reviewers can comment but not share externally.
10. **Sign-off readiness pack.** Auto-generate an approval summary PDF evidencing which departments cleared, when, by whom, with comments and playbook status — the digital replacement for MMBL's current master sheets. Attach it to the envelope before signature.
11. **Workflow builder UI.** Rebuild `workflow-builder` as a real stage/step designer with conditions, SLA and escalation configuration, persisting to the API. Delete the mockup version.

---

## Phase 5 — Repository, search, relationships, post-execution lifecycle

1. **Full-text search.** Contract body, extracted document text, clause text and comments. Postgres `tsvector` with a GIN index and `websearch_to_tsquery`; MSSQL/Oracle equivalents through the Phase 0 `fulltext_search` seam. Filters: party, clause, effective/end date ranges, value ranges, status, type, department, risk, owner, tags. Highlighted snippets in results. Wire the `search` mockup.
2. **Agreement relationships — `models.ContractRelation`.** Types: `addendum_of`, `amendment_of`, `renewal_of`, `supersedes`, `related_to`. Addenda auto-fetch parent details, receive sequential addendum numbers per parent, and show the full agreement history tree (§7 and "Smart Execution").
3. **Party / vendor master — `models.Party`.** Name, registration number, entity type, jurisdiction, risk score, compliance documents, KYC status, region. Replaces the free-text `Contract.counterparty`; migrate existing values. **Duplicate-onboarding validation**: fuzzy match on name and exact match on registration number, blocking with an override-plus-reason path (§7).
4. **Departments and folders.** Real `Department` model (name, lead, cost centre, region) replacing the free-text string, plus a folder tree with move/permissions. Wire `departments` and `folders`, delete the mockups.
5. **Custom fields.** Tenant-defined typed fields per contract type, rendered in forms, searchable, exportable. Wire `custom-fields`.
6. **Obligation tracker, completed.** Cross-contract rollup API, assignment, status, due-date reminder beat (email + SMS + Teams), overdue escalation. Wire the `obligations` page to the existing endpoints — the backend is already there, only the cross-contract view is missing.
7. **Renewals, completed.** Configurable 90/60/30-day advance notices per contract, a renewal decision workflow, and re-execution of the renewed agreement through the signing pipeline with a new validity period and an updated "Effective" state.
8. **Amendments.** "Request Amendment" against an active contract → same review cycle as the original → counterparty acceptance → execution → linked to parent with impact tracking (which fields/clauses changed, effect on value and dates).
9. **Terminations.** Termination request with reason and supporting documents → routed to Legal, Compliance, Finance and any other required stakeholders → on approval generate the termination notice, share with the counterparty, set status `terminated`, archive all related correspondence.
10. **Repository exports.** Full XLSX export (not just CSV) of the repository and every report, with the active filters applied, generated as a background job with a download link. Add print-friendly views.
11. **Legal checklist.** Uploadable, versioned checklists visible on the home page, owned by Legal with other stakeholders able to publish their own (RFI §4.1).

---

## Phase 6 — Analytics, dashboards and MIS

Build a real metrics layer (`analytics_service.py`) with pre-aggregated rollups so these are fast on 10 years of data.

- **Executive KPIs:** average cycle time per contract type, approval bottleneck heatmap by stage, SLA adherence by stage, renewal pipeline, escalations per month and mean time to resolve, reduction in playbook deviations.
- **Operational metrics:** reviewer workload, redline iteration counts, most-negotiated clauses, top bottleneck stages.
- **Compliance reports:** playbook deviations, contracts missing mandatory clauses, missing obligations, renewals processed on time, audit findings and remediation rate, audit-readiness pack.
- **RFI metrics:** agreements executed by department, average review cycle time, most-requested agreement types, pending agreements and bottlenecks.
- **MIS:** daily / weekly / monthly / YoY trend analysis, **region-wise segregation of DFS POCs**, pricing and entity-type analysis, agreement volume and status tracking (active, agreement pending, onboarded, onboarding pending).
- **Role-based dashboards:** "My Tasks", "Escalations", "Upcoming Renewals", "Reviews due today" — per RFP §4b Adoption Enhancements.
- Interactive filters on every report, drill-through to the contract, and XLSX/PDF export.

---

## Phase 7 — Integrations (RFP weight 8%)

1. **SAML 2.0** for Microsoft Entra ID, alongside the existing OIDC. SP-initiated and IdP-initiated SSO, signed assertions, encrypted assertions, metadata endpoint, ACS endpoint, SLO. Wire the `sso-admin` mockup — it currently advertises an ACS URL (`/auth/saml/acs`) that does not exist. Enforce MFA claims. Keep SCIM provisioning working against both.
2. **SIEM feed.** CEF and CLF formatters with severity levels (Emergency, Alert, Critical, Error, Warning, Notice, Informational), shipped over syslog (TCP/TLS) in near real time. Log categories must cover authentication, access control, application usage, system activity, security incidents, network events and audit trails, exactly as the InfoSec table enumerates.
3. **Kong API Gateway.** Ship a declarative `infra/kong/kong.yaml` with routes, rate-limit, request-size, IP-restriction, JWT/OIDC and CORS plugins, plus a documented deployment topology showing the app behind Kong and a WAF.
4. **Microsoft Teams + SharePoint.** Adaptive-card notifications to Teams channels on workflow events; optional SharePoint document-library sync for executed agreements (on-prem SharePoint Server supported, since no foreign hosting is allowed).
5. **Outlook / Exchange.** Calendar invites for review deadlines and renewal dates, and reminder mails via on-prem Exchange (EWS or Graph against a permitted endpoint).
6. **SMS.** Provider seam with a Pakistani gateway adapter (Jazz/Telenor aggregator) for OTP delivery and reminders. Required by the Visitor eSigning surface and by "Periodic/scheduled reminders via SMS/email".
7. **Sanctions screening.** Screen every party against OFAC, UN, EU and HMT lists at onboarding and on a scheduled re-screen. Import list snapshots locally (no runtime dependency on a foreign endpoint), fuzzy match with a configurable threshold, and produce a review queue for hits.
8. **Backup tooling.** Document and script integration with Veeam/Commvault, offsite DR-ready encrypted backups, plus restore verification. Extend `infra/scripts`.
9. **SOAP endpoint.** A thin SOAP facade over the core contract API for legacy core-banking integration — the RFP asks for "REST/SOAP based API support".
10. **Webhooks + connectors UI.** Wire the `integrations` mockup to the real `webhooks` API and the connectors above.

---

## Phase 8 — Security, compliance and governance hardening (weight 8% + InfoSec gate)

1. **FIDO2 / WebAuthn** as a first-class MFA factor alongside TOTP, push and SMS OTP. Wire the `passkeys` mockup.
2. **Separation of duties.** Rule engine preventing the same identity from performing conflicting actions (draft author ≠ final approver; RA officer ≠ certificate subject; webhook-secret reveal ≠ webhook creator). Configurable per action, enforced in the service layer, audited on every override.
3. **Step-up authentication** on sensitive actions: role change, webhook-secret reveal, signature voiding, certificate revocation, RA approval, purge.
4. **Need-to-know access control.** Per-contract ACLs so confidential contracts are visible only to named users/roles, with an audited break-glass path.
5. **Watermarking and download controls.** Dynamic per-viewer watermarks (name, email, timestamp), view-only rendering that does not serve the source file, disable-download per recipient, and link expiry on every shared view.
6. **Data masking** of sensitive fields (CNIC, account numbers, pricing) by role, per the InfoSec "Data exposure controls" line.
7. **Antivirus on upload.** ClamAV (on-prem) scanning every uploaded file before it becomes retrievable; quarantine + notify on detection.
8. **CAPTCHA / anti-automation** on login, registration, OTP request and the public signing surfaces, plus brute-force and credential-stuffing protections layered on the existing Redis rate limiter.
9. **TDE.** Document and script Transparent Data Encryption enablement for each supported database, with encrypted backups; add a startup check that warns when TDE is not detected in a production profile.
10. **Legal hold.** Real implementation: place a matter-scoped hold that blocks deletion, purge and archival; preserve everything; export the hold set. Wire the `legal-hold` mockup.
11. **Audit-log partitioning.** Monthly declarative partitioning (per-dialect) so the hash chain survives at >10M rows, plus an auditor-facing `verify_chain` UI.
12. **Temporary / time-bound access.** Real time-bound external collaboration links (the "Negotiation Room"), with scope, expiry and revocation. Wire the `temporary-access` mockup.
13. **Custom roles and permissions.** Replace the fixed five-role enum with configurable roles and a permission matrix. Wire the `roles` mockup.
14. **Compliance evidence pack.** `docs/COMPLIANCE-EVIDENCE.md` mapping every control to SBP ETGRMF and Outsourcing Risk Management Framework, ISO 27001:2022 Annex A, SOC 2 TSC, PCI DSS/SSF and GDPR — this is what the §4d table is actually asking you to submit.
15. **OWASP.** Explicit OWASP Top 10 (latest) and ASVS Level 2 mapping document, plus DAST in CI (OWASP ZAP baseline against a running instance) alongside the existing SAST.

---

## Phase 9 — Adoption, accessibility, localization, training

1. **Contextual help.** Tooltips and inline guidance on every non-obvious field, driven by a content file so Legal can edit copy without a deploy.
2. **Knowledge base** inside the product: playbooks, FAQs, quick-start guides, embedded video tutorials (self-hosted).
3. **Training hub:** webinar calendar, per-user progress tracking, certification quiz and certificate, post-release update notes. MMBL scores "Training Mechanism" at 8% and requires onsite training for at least 15 resources — the in-product hub is the durable half of that answer.
4. **Guided actions:** next-best-action prompts, pre-filled metadata, and a clear stage progress tracker (Intake → Drafting → Review → Approval → Sign).
5. **Accessibility:** audit and fix to WCAG 2.1 AA — keyboard navigation, focus management, colour contrast, screen-reader labelling, and an accessibility statement. Add `axe` checks to CI.
6. **Localization:** an i18n layer with English and Urdu, terminology aligned to MMBL's internal policy language, and locale-aware dates, numbers and currency (PKR).
7. **Non-digitally-literate client path** (§5.3): simplified signing UI, large targets, plain-language instructions, assisted/branch-tablet mode, and printable step-by-step guides.
8. **Mobile.** The signing surfaces and reviewer approve/reject actions must be fully usable on a phone, not merely responsive.

---

## Phase 10 — QA, operations and the RFP submission artefacts

**Engineering:**
- Raise API coverage to ≥80% on service modules; add end-to-end tests (Playwright) for the two RFI journeys end to end.
- **UAT scripts** per RFP §4c "Test-driven development with UAT scripts" — a numbered, executable test book mapped to each RFP requirement ID.
- Load and soak testing: 100 concurrent internal users, 100,000 external signatures/year (~400/business day, with peaks), OCSP p95 <200 ms, search p95 <500 ms on a 10-year corpus.
- DR drill: documented RPO/RTO with an evidenced restore test.
- Worker-side Prometheus exporter (the API `/metrics` does not cover Celery), plus dashboards and alert rules.
- CD pipeline to Dev / UAT / Prod with segregated environments and approval gates.

**Documents MMBL explicitly requires (Annexure list, §9 — all marked "Yes"):**
1. Bill of Quantities & Technical Specs
2. **Compliance Matrix (feature-to-requirement)** — generate it from `docs/MMBL-RFP-GAP-ANALYSIS.md` once the phases land
3. Service Level Agreement
4. Project Implementation Plan / Gantt (fits the 2–3 month window; 2 years onsite support after go-live)
5. Licensing details (database, APIs, all third-party components)
6. **HLD / LLD diagrams**
7. Risk Mitigation Strategy (11% of the score — do not treat as optional)
8. Audit Trail Mechanism Overview
9. Training plan for ≥15 resources onsite (8%)
10. Quality Assurance plan (11%)
11. **Sworn undertaking** that the PKI/eSignature engine is proprietary, in-house engineered, not open-source or a derivative, with all source, IP and engineering residing with the bidder in Pakistan — **plus the SBOM** from Phase 1
12. Hosting & data residency statement (Phase 0)
13. PKI architecture document (Phase 1)
14. Third-party vulnerability assessment report, if available

---

## Suggested sequencing

| Stream | Phases | Rationale |
|---|---|---|
| **A — Crypto** | 0 → 1 → 2 | Longest lead time, hardest to fake, 11% of score, eligibility gate |
| **B — Workflow** | 4 → 6 | The RFI's core mechanic; unblocks analytics |
| **C — Document** | 3 → 5 | Word round-trip is the single most-cited supplemental requirement |
| **D — Platform** | 7 → 8 → 9 → 10 | Runs behind the other three; 10 must not start last |

Phase 0 gates everything — do it first and do it once.

---

## Final instruction to Claude Code

Work one phase at a time. At the end of each phase, produce: (a) a summary of what shipped, (b) the updated rows in `docs/MMBL-RFP-GAP-ANALYSIS.md`, (c) the list of mockup pages deleted or wired, and (d) anything you could not complete and why. **Do not report a phase complete while any page in its scope still renders sample data.**
