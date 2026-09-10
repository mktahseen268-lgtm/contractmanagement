# MMBL Contract Digitization RFP — Gap Analysis Against Current Codebase

**Sources:** `MMBL RFP For Contract Digitization Solution.pdf` (24 Aug 2026, 22pp) + `Digital Journey RFI.pdf`
**Assessed repo:** `contract_management/contractmanagement` @ 25 Aug 2026
**Submission deadline:** 02 Sep 2026, 23:59 · **Minimum qualification score: 70%** · Delivery window: 2–3 months

---

## 1. Short answer

**No — the software does not currently cover the RFP.**

The existing product is a competent, security-conscious **v1 CLM spine**. Measured against this RFP it covers roughly **45% of the mandatory functional scope**, and materially less on the two areas MMBL weights most heavily.

Three findings dominate everything else:

1. **The PKI / Certificate Authority requirement is completely unbuilt.** The RFP demands an in-platform CA — enrolment, issuance, renewal, suspension, revocation, CRL publication, OCSP responder, HSM-protected keys at FIPS 140-2 Level 3, a per-signatory non-shared certificate for *every* signer, an RA workflow tied to HR/identity, and future ECAC chaining readiness. The codebase has **none** of this. It has a visual "Signatures page + Certificate of Completion" signer and an *optional* PAdES seam (`signing_provider.py`) that seals with a single pre-supplied PKCS#12 file. That is not a PKI. This is **11% of the technical score** and is also a hard eligibility gate ("bidder must be the original author and full IP owner… the PKI and eSignature engine must be the bidder's own proprietary in-house engineered solution", with a sworn undertaking and SBOM).
   > **Update (25 Aug 2026):** closed by Phase 1 — see §9. The CA, RA, lifecycle, CRL, OCSP, PKCS#11 keystore and third-party validation are built and tested. The remaining gap is per-signatory PAdES signing (Phase 2) and a real HSM.
2. **A large part of the web app is a mockup, not a product.** 24 of 34 signed-in pages render hard-coded sample arrays with zero API calls — including `clauses`, `redline`, `docx-studio`, `signature-studio`, `bulk-send`, `client-portal`, `folders`, `custom-fields`, `departments`, `legal-hold`, `identity-check`, `passkeys`, `roles`, `search`, `sso-admin`, `temporary-access`, `integrations`, `obligations`, `ai-analysis`, `workflow-builder`. Several carry an explicit `// Mockup: sample data, no persistence` comment. If MMBL asks for the live demo or PoC the RFP entitles them to, these pages will not survive it.
   > **Update:** a code-level count on 25 Aug 2026 found **21 of 30** app route folders with no `lib/api` import. `identity-check` and `passkeys` were deleted in Phase 1, `signature-studio` in Phase 2; seventeen pages have been rebuilt against real endpoints across Phases 3–7. **3 remain** (`bulk-send`, `client-portal`, `previews`).
3. **The RFI's actual contract journey is not implemented.** The Digital Journey describes parallel multi-stakeholder review (Legal / Finance / Compliance / IS concurrently), a customer-facing feedback loop with track changes, iterative "Send for Further Review" cycles until acceptance, and MS Word round-tripping. The engine ships **sequential, single-assignee approval steps** (`workflow_service.py`: "Parallel/conditional steps, SLAs and escalation are planned") and has **no Word import/export at all** (`python-docx` is not a dependency anywhere).

There is also a stated **architecture mismatch**: the RFP asks for Oracle or MSSQL, microservices on OKE, on-prem only, all data inside Pakistan. The product is a Postgres-first monolith whose single most important invariant is Postgres Row-Level Security — and `docs/25-database-portability.md` already concedes that on MSSQL that isolation silently degrades to app-layer filtering.
> **Update:** closed by Phase 0 — `app/db_dialect.py` emits real row-security DDL on PostgreSQL, MSSQL and Oracle, and CI runs the migration matrix on Postgres + MSSQL.

---

## 2. Score estimate against MMBL's own rubric

MMBL scores 13 weighted parameters and needs **70%** to qualify. Splitting them into *product evidence* (what the code must prove) and *proposal evidence* (what a well-written document proves):

| # | Parameter | Weight | Current product state | Est. |
|---|---|---|---|---|
| 1 | Technical Architecture & Design | 12% | Multi-tier ✅, modular/API-driven ✅, HA manifests ✅ — but monolith not microservice, Postgres not Oracle/MSSQL, no purge/archive tiering | 55% |
| 2 | Integrations | 8% | REST ✅, OIDC ✅, SCIM ✅ — no SOAP, no SAML, no Kong config, no SIEM CEF feed, no sanctions screening, no Teams/SharePoint/Outlook, no SMS, no backup-tool integration | 35% |
| 3 | Security and Compliance | 8% | RBAC ✅, MFA/TOTP ✅, hash-chained audit ✅, encrypted columns ✅ — no FIDO2, no TDE, no SoD, certifications absent | 55% |
| 4 | Infrastructure & Storage | 6% | K8s + backup scripts ✅ — no 10-year retention tier with 1-year hot search, no sizing doc, no DR runbook | 40% |
| 5 | Deployment Options (CI/CD) | 3% | Strong CI (ruff, mypy, bandit, semgrep, gitleaks, pip-audit, Trivy) ✅ | 70% |
| 6 | Technical Specifications | 7% | OpenAPI ✅ — no user manuals | 50% |
| 7 | Support, Monitoring & Maintenance | 7% | Prometheus `/metrics` ✅, OTel hook ✅ — no worker exporter, no VAPT evidence, no training | 40% |
| 8 | Project Plan and Timelines | 6% | Proposal artefact — not yet written | 0% |
| 9 | **PKI Depth & Advanced eSignature** | **11%** | **Phase 1 shipped:** CA hierarchy, RA workflow, full lifecycle, CRL+OCSP, PKCS#11 keystore, third-party validation, ECAC cross-certification, SBOM in CI. Remaining: per-signatory PAdES signing (Phase 2) + a real HSM | 70% |
| 10 | Relevant Experience | 2% | Commercial — needs one verifiable production deployment | — |
| 11 | Risk Management | 11% | Proposal artefact — not yet written | 0% |
| 12 | Training Mechanism (onsite, min 15 resources) | 8% | No knowledge base, no training hub, no contextual help in product | 10% |
| 13 | Quality Assurance | 11% | Real pytest suite ✅ + SAST in CI ✅ — no UAT scripts, no DAST/VAPT report, no QA plan | 50% |

**Product-evidence weighted total ≈ 32 / 100** *(as first assessed; Phases 0–1 move criteria 1, 4 and 9 upward — re-score before submission).* Criteria 8, 10, 11 and 12 (27% combined) are largely won with documents rather than code — writing those well plausibly adds ~20 points. Even then you land around **52–55%**, short of the 70% gate. **Closing PKI (11%) and Integrations (8%) is what moves you over the line.**

---

## 3. Coverage matrix — RFP §4a(i) Scope of Work

Legend: ✅ built and wired · 🟡 partial · 🎭 UI mockup only, no backend · ❌ absent

### Drafting & Clause Library

| Requirement | Status | Evidence |
|---|---|---|
| Template repository with versioning (NDA, MSA, SLA, standalone) | 🟡 | `ContractTemplate` model + `/templates` CRUD + `/use`. No version history on templates, no approval gate |
| Clause library with risk levels, alternatives, guidance notes | 🎭 | `app/(app)/clauses/page.tsx` — `// Mockup: sample data, no persistence`. No `Clause` model, no table, no API |
| Guided drafting wizard (assemble from templates + clauses) | ❌ | Nothing |
| AI assist — suggest clauses, flag playbook deviations | 🎭 | `ai-analysis` page is a static `FINDINGS` array. `ocr_provider.py` does extraction only, and defaults to a **stub that does not read the document** |

### Review & Redlining

| Requirement | Status | Evidence |
|---|---|---|
| Parallel review — Legal, Finance, Technical concurrently | ✅ | **Phase 4.** The engine is ordered **stages** of concurrent **steps**; every step in a stage activates together. Completion policies: `all` / `any` / `quorum(n)` / `percentage(p)` |
| Reviewers mark complete independently | ✅ | **Phase 4.** Decisions recorded per step in any order; the stage advances only when its policy is met. A rejection ends the run immediately rather than waiting for the others |
| Compare & redline — version diff, tracked changes, comment threads | 🟡 | `ContractVersion` snapshots + `Comment` table + restore ✅. **No diff view, no tracked changes** — `redline/page.tsx` is a static `DOC` token array |
| @mentions between reviewers | ✅ | **Phase 4.** `models.Mention` rows (so "mentions me" is an indexed query), notification fan-out, `/mentions` inbox filter |
| Add/modify reviewers after review has started | ✅ | **Phase 4.** `add_reviewer` / `remove_reviewer`, audited. A reviewer who has already decided can never be removed — that would erase a decision from the record |
| Negotiation room — link-based, time-bound external collaboration | 🎭 | `client-portal` and `temporary-access` are both mockups. Only the signing portal (`/sign/{token}`) is real |
| Consolidated internal review view with strict internal-only privacy toggle | ✅ | **Phase 4.** `Comment.internal_only` enforced in ONE fail-closed function (`comment_service.visible_to`) and asserted against every external shape in tests. `/contracts/{id}/review` groups by reviewing function |

### Approval & Escalation

| Requirement | Status | Evidence |
|---|---|---|
| Dynamic approval matrix — value thresholds, risk categories, dept-specific approvers | ✅ | **Phase 4.** `models.ApprovalRule` + `approval_matrix.py`. Rules **add** stages rather than replacing the workflow, so a value band does not require duplicating it. Re-evaluated on material change, with the re-route audited |
| Escalation rules — auto-escalate on SLA breach, configurable reminders | ✅ | **Phase 4.** Per-step SLA on a **business calendar** (working days/hours + per-tenant public holidays), reminder at a configurable fraction, escalation on breach, Celery beat sweep, `/workflow/escalations` feed with business-hours mean-time-to-resolve |
| Delegation / out-of-office proxy approvers | ✅ | **Phase 4.** `models.Delegation` with scope and window; assignments route to the proxy automatically and **both** identities stay in the audit trail |
| Sign-off readiness — auto-generated approval summary evidencing departmental clearances | ❌ | Nothing |

### Execution & E-Signature

| Requirement | Status | Evidence |
|---|---|---|
| Envelope send / sign / decline / void / remind | ✅ | `signing_service.py` + `routers/signatures.py`, full public portal |
| Signature tabs (signature, initials, date, text, checkbox) with coordinate stamping | ✅ | `SignatureTab` model + `pdf.py` coordinate flip |
| Certificate of Completion + executed PDF | ✅ | `tasks.py: seal_envelope` |
| **In-platform PKI: enrolment, issuance, renewal, suspension, revocation, CRL, OCSP** | ✅ | **Phase 1.** `app/pki/` — offline root + issuing CA + delegated OCSP responder; RA workflow; all six lifecycle ops; full+delta CRLs at `/pki/crl/{ca}.crl`; RFC 6960 responder at `/pki/ocsp` (nonce echoed, `unknown` ≠ `good`) |
| **HSM-protected key storage, FIPS 140-2 L3+** | 🟡 | **Phase 1.** `Pkcs11KeyStore` generates keys inside the token (`CKA_EXTRACTABLE=false`); CI proves the path against SoftHSM2. **Needs a real FIPS L3 device + `KEYSTORE_PROVIDER=pkcs11`** — the default is still the software keystore |
| **Per-signatory certificate, uniquely bound private key, no shared/role certs** | ✅ | **Phases 1+2.** Issuance enforced twice (service check + partial unique index, 0016_pki), and `SIGNING_PROVIDER=pki` now signs the executed PDF **once per signatory with their own certificate and key** (`app/pki/signer.py`). Verified against real PDF bytes in `test_esignature_depth.py` |
| **Registration Authority workflow integrated with HR/identity before issuance** | ✅ | **Phase 1.** `pki/ra.py` — no issuance without an approved request; OIDC/SCIM claims captured as evidence and carried into the audit entry; separation of duties; `RA_DUAL_CONTROL` two-officer approval |
| **ECAC chaining readiness (Electronic Transactions Ordinance 2002)** | ✅ | **Phase 1.** Stable issuing-CA key + DN, `ca.cross_certify()`, trust anchors in a table. Proven by a test that cross-certifies under a new root and shows an untouched certificate still validating |
| **Third-party certificate validation (DigiCert, GlobalSign, Sectigo, Entrust)** | ✅ | **Phase 1.** `pki/validate.py` — RFC 5280 path validation against a runtime-extensible trust store, with OCSP-then-CRL revocation checking and `nextUpdate`-respecting cache. Name constraints and certificate policies are not implemented (documented) |
| **Visitor / merchant eSigning surface — no provisioning, web + tablet + mobile + QR, OTP identity binding** | ✅ | **Phase 2.** `visitor_service.py` + public `/esign/{token}` + portal page. Shareable/QR invitation → identity claim → email/SMS OTP proof → auto-issued visitor certificate → recipient attached to the live envelope. Scroll-to-end consent evidence, proof-of-work + rate limiting, CNIC reduced to last 4 digits. **Not yet load-tested at 100k/year** |
| Wet-signature handling — scan, attach, certify receipt, record execution date | ✅ | **Phase 2.** `wet_signature.py` — per-recipient `signing_mode`, printable pack (cover sheet with the matching reference + the agreement), scanned-copy capture, and a `WetSignatureAttestation` naming the accountable employee, the file SHA-256, the **declared execution date** (not the upload date) and an optional witness. Status flows converge on one definition of executed |
| Smart execution — automated signature tagging (no manual drag-and-drop) | ✅ | **Phase 2.** `tagging.py` extracts positioned text from the rendered PDF (pypdf `visitor_text`) and matches anchor phrases, then places tabs and distributes them across signers by column. `POST /envelopes/{id}/auto-tag` previews or applies. Template-declared anchors supported. `signature-studio` mockup **deleted** |
| Sizing: 100 internal users, **100,000 external signatories/year** | ❌ | Untested at that scale; no load evidence |

### Repository & Search

| Requirement | Status | Evidence |
|---|---|---|
| Central repository, lifecycle tags (Active, Expiring) | ✅ | `lifecycle.py` state machine covers the spine |
| Executed agreements auto-archived | ✅ | `seal_envelope` writes the executed PDF as a `FileObject` |
| Advanced search — **full text inside documents**, filters by party/clause/date/value/status | 🟡 | `routers/contracts.py` filters on status/type/risk/owner and `ILIKE` on title/ref/counterparty only. **No body/full-text search, no clause filter, no value/date range.** `search/page.tsx` is a mockup. *(Phase 0 added the `fulltext_search` dialect seam; Phase 5 consumes it.)* |
| Linking master agreements — addenda/amendments with auto-fetch of parent details | ❌ | Only `renewed_from_id` exists (renewal successor). No parent/child agreement linkage, no addendum numbering |
| Duplicate-onboarding validation (client/entity already onboarded) | ❌ | Nothing |
| Downloadable, exportable repository incl. Excel export | 🟡 | `reports/contracts.csv` only — CSV, not XLSX, and not the full repository |
| Folder / department organisation | 🎭 | `folders` and `departments` pages are mockups; `Contract.department` is a free-text string |

### Obligations, Renewals & Amendments

| Requirement | Status | Evidence |
|---|---|---|
| Obligation tracker — payment milestones, deliverables, SLAs, assignment, reminders | 🟡 | `Obligation` model + CRUD API ✅. But the cross-contract `obligations` page is a mockup, and there are no reminder jobs for obligation due dates |
| Renewal alerts at 90/60/30 days | 🟡 | `renewal_service.py` + hourly `sweep_renewals` beat ✅. Advance-notice windows are not configurable per contract |
| Amendment workflows with impact tracking | ❌ | No amendment entity, no impact diff |
| Termination request workflow with reason + supporting docs + routing | ❌ | `terminated` is a status only; no request/approval flow |

### Compliance, Governance & Audit

| Requirement | Status | Evidence |
|---|---|---|
| Audit trail — every action logged (who/what/when) | ✅ | `audit.py` with per-tenant HMAC hash chain + `verify_chain()` — genuinely strong, ahead of most competitors |
| Policy engine — mandatory-clause checklists (anti-corruption, privacy, IP, export control) | ❌ | Nothing |
| Legal checklist visible on the home page (RFI §4.1) | ❌ | Nothing |
| Risk scoring from deviations, jurisdiction, value, vendor rating | ❌ | `Contract.risk_level` is a manually set enum |
| Need-to-know restriction of confidential contracts to select roles | ❌ | RBAC is tenant-wide by role; no per-contract ACL |
| Watermarking, view-only mode, link expiry, download controls | 🟡 | Draft PDFs are watermarked ✅. No view-only mode, no download controls. Signing links expire (14 days) ✅ |
| Legal hold | 🟡 | **Phase 0** added `Contract.legal_hold`, enforced as an absolute block on archive and purge. The matter-scoped hold UI (`legal-hold` page) is still a mockup — Phase 8 |

### Analytics & Dashboards

| Requirement | Status | Evidence |
|---|---|---|
| Executive KPIs — cycle time, approval bottlenecks, SLA adherence, renewal pipeline, savings/risks | 🟡 | `dashboard.py` gives KPIs, distribution, activity, attention, trends ✅. **No cycle time, no SLA adherence (no SLA), no bottleneck heatmap** |
| Operational metrics — reviewer workload, redline iterations, top negotiated clauses | ❌ | Nothing |
| Compliance reports — playbook deviations, missing obligations, audit readiness | ❌ | Nothing |
| MIS: daily/weekly/monthly/YoY trends, region-wise DFS POC segregation, pricing & entity-type analysis | ❌ | No region dimension, no pricing analytics |
| Interactive filters and Excel export of reports | 🟡 | CSV export of the contract list only |

### Knowledge & Help

| Requirement | Status | Evidence |
|---|---|---|
| Contextual help — tooltips, inline guidance near fields | ❌ | Nothing |
| Knowledge base — playbooks, FAQs, video tutorials, quick-start guides | ❌ | Nothing |
| Training hub — webinar calendar, user certification, post-release updates | ❌ | Nothing |
| Accessibility — keyboard nav, contrast, screen reader | 🟡 | Tailwind defaults; never audited against WCAG |
| Localization to internal policy / local legal terminology | ❌ | English-only strings, no i18n layer (`docs/13-arabic-rtl.md` is spec-only) |

---

## 4. Coverage matrix — RFP §4a(ii) Branchless Banking Operational Requirements

| Ref | Requirement | Status |
|---|---|---|
| 1.1 | End-to-end workflow document (initiation → review → execution → archival → exception) | ❌ deliverable not written |
| 1.2 | Configurable approval matrices | ✅ **Phase 4** — `/workflow/rules` |
| 2.1 | DFS POCs initiate directly via structured form-based workflow | 🟡 `contracts/new` exists but is not the agreement-type-driven form of the RFI |
| 2.2 | Eliminate email-based initiation | 🟡 achievable once 2.1/2.3 land |
| 2.3 | Drop-downs / LOVs, auto-population, auto-generation of the draft from the template | ❌ no merge-field engine |
| 3.1 | Client-side edits auto-classify agreement as "Non-Standard" | ✅ **Phase 4** — `mark_non_standard()` sets the flag, which selects the non-standard stage set and fires `non_standard_only` approval rules |
| 3.2 | Parallel/tandem reviews, reviewers complete independently | ✅ **Phase 4** |
| 3.3 | User Dept sees consolidated comments before external sharing | ✅ **Phase 4** — grouped by reviewing function, internal-only boundary enforced |
| 3.4 | Assign agreements to internal review teams; @mentions | ✅ **Phase 4** |
| 3.5 | DFS remain the sole client-facing coordinators | 🟡 **Phase 4** — `User.is_client_facing` + `comment_service.can_share_externally`. A capability rather than a role, because it cuts across roles. **Not yet wired into every external-share path** |
| 3.6 | Real-time collaboration, version control + audit trails, in-system track changes, add reviewers mid-flight | 🟡 versions + audit ✅; the other three ❌ |
| 4.1–4.4 | Signatories tagged per authority matrix; flexible signatory selection; reviewer==signatory allowed; execution free of signature failures | ✅ **Phase 2.** `authority_service.py` matrix (department / type / currency / value band → required role or named signatory, joint-signature counts, escalation); deviations require an audited override reason rather than being blocked. Reviewer==signatory asserted in tests. Optimistic locking on the envelope + a `seal_status` dead-letter view at `/authority/seal-failures` |
| 5.1–5.3 | Stable, scalable, bug-free, user-friendly; implementation support + SLAs; accessible to non-digitally-literate clients | 🟡 commercial + UX work |
| 6.1 | Executed agreements auto-archived | ✅ |
| 6.2 | Repository searchable, downloadable, exportable incl. Excel | 🟡 CSV only |
| 6.3 | Volume/status tracking, expiry/renewal tracking, pricing & entity-type analysis, interactive filters, D/W/M/YoY, region-wise DFS POC segregation | 🟡 partial — see Analytics above |
| 7 | Duplicate-entity validation; addenda linked to parent with auto-fetch, addendum numbering, agreement history | ❌ |

### Supplemental requirements (RFP p.10) — all high-visibility, all missing

| Requirement | Status |
|---|---|
| **MS Word round-trip** preserving MMBL formatting and clause numbering | ✅ **Phase 3.** `app/docx_engine/` — export with clause numbers as **real Word numbering** (not typed digits, so an inserted clause renumbers correctly), headings, tables, header/footer. Import reads `w:ins`/`w:del` tracked changes and `word/comments.xml` with authors and timestamps. Round-trip fidelity proven structurally across a 10-agreement corpus in CI |
| **Consolidated review** master view with strict internal-only privacy toggle | ❌ |
| **Sign-off readiness** auto-generated approval summary | ❌ |
| **Smart execution** automated signature tagging + addendum→master linking | ❌ |
| **Hybrid flexibility** e-sign and wet-signature in one unbroken digital trail | ✅ **Phase 2** — one paper counterparty does not force everyone else off the electronic path; the envelope completes only when both paths finish, and the evidence stays distinguishable (a scan is never presented as a cryptographic signature) |
| **AI data capture** auto-extract expiry/notice periods from signed docs, link parents to addenda | 🟡 OCR seam exists; default provider fabricates output; no date extraction into fields |

---

## 5. Coverage matrix — RFP §4b/§4c Technical & IT requirements

### Data model
`Contract`, `ContractVersion`, `Obligation`, `WorkflowDefinition/Run/Step`, `AuditLog`, `FileObject` all exist ✅ and largely match. **Phase 1 added** `CertificateAuthority`, `Certificate`, `CertificateRequest`, `TrustAnchor`, `PkiKey`. Still missing: **Clause**, **Party/Vendor** (counterparty is a free-text string — no registration number, no risk score, no compliance docs), **Amendment**, **Department**, **CustomField**.

### Integration
| Requirement | Status |
|---|---|
| REST API | ✅ FastAPI + OpenAPI |
| SOAP support | ❌ |
| API Gateway integration, preferably **Kong** | 🟡 works behind a proxy; no declarative Kong config, no rate-limit/auth plugin mapping |
| Schedule & monitor integrations | 🟡 Celery beat ✅; no integration monitoring surface |
| **Entra ID via SAML 2.0** / OIDC, SCIM, MFA enforcement | 🟡 **OIDC ✅, SCIM ✅, SAML ❌** (`sso-admin` page advertises a SAML ACS URL that does not exist) |
| SIEM (Syslog/CEF feed), DAM, PAM, VM, WAF, SOAR | ❌ JSON logs only — no CEF formatter, no syslog shipper |
| Sanctions screening (OFAC, UN, EU, HMT) | ❌ |
| Enterprise backup tooling (Veeam/Commvault), offsite, DR-ready encrypted backups | 🟡 `infra/scripts` pg_dump-style scripts only |
| MS Teams / SharePoint for notifications & secure storage | ❌ |
| Outlook for reminders & scheduling | ❌ |
| SMS + email scheduled reminders | 🟡 email outbox ✅ with retry; **SMS provider seam ✅** (`sms.py`, console / HTTP-gateway / null backends, shared outbox with a `channel` discriminator) — wired for OTP; scheduled SMS reminders not yet |

### Security & compliance
| Requirement | Status |
|---|---|
| RBAC | ✅ owner/admin/manager/approver/author |
| MFA | ✅ TOTP + recovery codes + email OTP |
| TLS 1.3+, AES-256 in transit/at rest | 🟡 app-level ✅ (Fernet columns, S3 SSE); TLS is deployment config |
| API security per SBP controls | 🟡 rate limiting (Redis, atomic Lua) ✅, security headers ✅, no formal SBP mapping |
| Database encryption mandatory / **TDE** | ❌ column-level only; TDE is an unaddressed operator step |
| PCI DSS / SSF, ISO 27001:2022, SOC 2 Type II, GDPR | ❌ no certifications, no evidence pack |
| **FIDO2 / WebAuthn** in addition to TOTP/push/SMS OTP | ❌ the `passkeys` mockup was deleted in Phase 1; the real implementation is Phase 8 |
| Logs in CLF/CEF with severity levels | ❌ structured JSON, not CEF, no severity taxonomy |
| Audit trails for all critical activity | ✅ **and hash-chained** — a genuine strength |
| Separation of duties enforcement | 🟡 **Phase 1** enforces SoD in the RA (an officer cannot approve their own certificate request). The general rule engine is Phase 8 |
| CAPTCHA / anti-automation | 🟡 **Phase 2** on the public eSign surface: self-hosted proof-of-work (HMAC-bound challenge), per-invitation-per-IP session caps, OTP attempt and resend caps. No CAPTCHA on login/registration yet; an edge WAF is the intended complement |
| Antivirus scan on upload | ❌ |
| Step-up auth on sensitive actions | ❌ |
| Data residency — **on-prem only, all data in Pakistan** | ✅ **Phase 0** — `app/residency.py` refuses to boot when any configured endpoint resolves to a public address unless allowlisted; emits a `residency_check` audit entry at boot. Statement doc still owed (Phase 10) |

### Infrastructure & architecture
| Requirement | Status |
|---|---|
| Multi-tier web architecture | ✅ |
| Modular, API-driven, scalable | ✅ |
| HA across web/app/DB | 🟡 `infra/k8s` HPA + PDB + NetworkPolicy ✅; DB HA not addressed |
| OS Oracle Linux 8.1+ / Windows 2022+ | 🟡 containers run anywhere; not certified |
| **DB preferably Oracle or MSSQL** | ✅ **Phase 0** — `app/db_dialect.py` emits RLS / Security Policy / VPD, session context, advisory locks and JSON typing per dialect. CI runs the migration matrix on Postgres + MSSQL. Oracle DDL written + unit-tested, execution is a documented manual gate |
| **Microservices (OKE)** | ❌ single FastAPI monolith + Celery worker |
| Data purging and archiving | ✅ **Phase 0** — nightly `archive.sweep` + `archive.purge_contracts` beats, legal-hold blocked, audited (`app/archive_service.py`) |
| 10-year retention, 1 year instantly searchable | ✅ **Phase 0** — `RETENTION_YEARS`/`HOT_SEARCH_YEARS`; archived contracts drop out of the live list but stay retrievable by id/reference (`include_archived=true` searches the full corpus) |
| Segregated Dev / UAT / Prod + sizing details | 🟡 compose + k8s ✅; sizing document ❌ |
| CI/CD pipeline | ✅ strong CI; CD not defined |
| Test-driven development with UAT scripts | 🟡 pytest suite ✅ (127 passing); UAT scripts ❌ |
| Patch management, 48h critical VAPT TAT | ❌ policy documents not written |
| API documentation + user manuals | 🟡 OpenAPI ✅; manuals ❌ |
| 24/7 L1/L2/L3 support, onsite training for ≥15 resources | ❌ commercial commitments |

### §4d InfoSec table (Portal/Web Application Security)
Secure-by-design 🟡 · OWASP Top 10 + ASVS mapping ❌ (semgrep `p/owasp-top-ten` runs in CI, but no ASVS evidence) · input validation ✅ Pydantic · session management ✅ (in-memory token, rotating refresh with reuse detection — strong) · MFA ✅ · RBAC ✅ · data masking ❌ · HTTPS/TLS 1.2+ 🟡 deployment · WAF ❌ · security headers ✅ · application logging ✅ · **SIEM near-real-time ❌** · SAST ✅ / DAST ❌ / VAPT ❌ · remediation SLAs ❌ · env segregation 🟡 · anti-automation ❌ · secure error handling ✅ · no hardcoded secrets ✅ (gitleaks in CI) · **hosting & data residency statement 🟡** (control built in Phase 0; the document is Phase 10) · **PKI architecture + SBOM ✅** (`docs/PKI-ARCHITECTURE.md` + the `sbom` CI job).

---

## 6. Coverage matrix — Digital Journey RFI

### Journey 1 (BBCORP) and Journey 2 (Other Departments)
| Step | Status |
|---|---|
| Agreement-type panel (QR / PGW / Collection / Disbursement; Service Agreement / MoU) with pre-uploaded approved drafts | ❌ |
| Structured intake form — customer details, pricing, term (auto-renew or fixed) | 🟡 `contract-form.tsx` captures generic metadata; not type-driven, no LOVs |
| COI upload (.jpg/.pdf) | 🟡 `FileObject` upload exists; not tied to the intake step or validated |
| Auto-generate the draft by merging form fields into the approved template | ❌ **no merge-field engine** |
| Auto-route to BBCORP → Finance → back to BBCORP → Business | ❌ no routing graph, no department panels |
| Finance panel showing all agreements pending financial review; status auto-flips to "Approved by Finance" | ❌ |
| "Share with Business" / "Submit to Client" actions | ❌ |
| Customer panel with **track changes** and a comments section | ❌ |
| "I HAVE READ AND AGREED TO THE CONTRACT" acceptance gate, disabled while edits are pending | ❌ |
| "Send for Further Review" → fan-out to Legal / Compliance / IS with automated email alerts → consolidate → return to customer → **loop until acceptance** | ❌ |
| Redirect to DocuSign-or-equivalent signing on acceptance | 🟡 the internal signing portal is the equivalent, but it is not chained to an acceptance gate |
| Auto-categorise as "Effective" and file into the repository on full execution | 🟡 status becomes `active`; no "Effective" categorisation step |
| Repository accessible to BBCORP and Business, with search filters, download and print | 🟡 partial |
| Legal checklist uploaded and visible on the home page; other stakeholders can upload theirs | ❌ |
| Analytics: agreements by department, average review cycle time, most-requested types, pending agreements and bottlenecks | ❌ none of these four metrics exist |
| Renewal: auto notifications at 90/60/30 days → approve → re-execute → new validity period | 🟡 sweep exists; the re-execution loop does not |
| Amendment: "Request Amendment" against an active contract, same review cycle, execute | ❌ |
| Termination: request with reason + supporting docs → Legal/Compliance/Finance approval → notice generated and shared → status "Terminated", correspondence archived | ❌ |

---

## 7. The four things that decide this bid

1. **PKI is an eligibility gate, not just 11% of the score.** MMBL asks for a sworn undertaking that the PKI/eSignature engine is your own, non-open-source, IP-owned product, plus an SBOM, plus HSM-protected keys at FIPS 140-2 L3. Building a CA on top of `cryptography` primitives is defensible; wrapping EJBCA or Dogtag is not. This is the longest lead item and it needs to start first.
   > **Status:** built (Phase 1). `docs/PKI-ARCHITECTURE.md` is the deliverable; the SBOM is a CI artefact. Two follow-throughs remain: wiring these certificates into the signing path (Phase 2) and procuring a FIPS L3 device.
2. **The mockup pages are a live-demo liability.** The RFP explicitly reserves the right to a live product demonstration or PoC during evaluation. Either wire these pages to real endpoints or remove them from the build before the demo — a page that renders invented data in front of the evaluation committee is worse than a page that does not exist.
   > **Status:** 2 of 21 deleted (`identity-check`, `passkeys`). **19 remain — still the single biggest demo risk.**
3. **Parallel review + Word round-trip are the RFI's whole point.** Every other CLM vendor will show sequential approvals. MMBL wrote three separate sections about concurrent multi-stakeholder review and about external parties who "will not negotiate inside a portal; they will send back a Word doc". These two features are where the functional score is won.
4. **The database story needs a decision you can defend for two years.** You have chosen single-tenant on-prem *plus* first-class MSSQL/Oracle. That removes the RLS-degradation problem (single tenant makes DB-level tenant isolation moot) and answers the "preferably Oracle or MSSQL" line directly — but it is real engineering: every hand-written Postgres DDL migration, the JSONB/GIN indexes, and the planned `tsvector` search all need a portable equivalent.
   > **Status:** done (Phase 0). The one honest caveat is that Oracle DDL is generated and unit-tested but never executed — no Oracle container in CI.

**Timeline reality check:** the RFP allows 2–3 months for delivery. The work below is not a 2–3 month build from where the code stands today unless PKI, the workflow engine and the document engine run as three parallel streams from day one.

---

## 8. What happens next

The companion document **`MMBL-BUILD-PROMPT.md`** in this folder is the complete, phased implementation brief for Claude Code covering everything marked 🟡, 🎭 or ❌ above — ordered by RFP weight and dependency, with data models, endpoints, and acceptance criteria per phase.

---

## 9. Phase log

### Phase 0 — Deployment profile: single-tenant on-prem + Oracle/MSSQL first-class ✅ (25 Aug 2026)

**Shipped**

| # | Item | Where |
|---|---|---|
| 1 | `DEPLOYMENT_MODE=saas\|single_tenant`; one tenant provisioned/adopted at startup; registration disabled server-side; login page hides the register link, the demo-credential banner and the demo prefill | `app/config.py`, `app/tenancy.py`, `app/routers/auth.py`, `app/(auth)/login/page.tsx` |
| 2 | `app/db_dialect.py` — RLS/Security-Policy/VPD, `set_tenant_context`, `advisory_lock`, `json_column`/`json_check`/`json_index`, `partial_unique_index`, `fulltext_index`/`fulltext_search` across PG / MSSQL / Oracle | `app/db_dialect.py` |
| 3 | `0002_rls` and `0013_hardening` rewritten to route their DDL through the seam; `audit.py` and `database.py` call it instead of carrying inline Postgres SQL | migrations + `app/audit.py`, `app/database.py` |
| 4 | Optional drivers as extras | `requirements-mssql.txt`, `requirements-oracle.txt` |
| 5 | `validate_for_production` rejects SQLite outside dev **and** a SaaS-shaped config in single-tenant mode (auto-seed on, mismatched OIDC/SCIM tenant, isolation disabled in SaaS) | `app/config.py` |
| 6 | `DATA_RESIDENCY_REGION` + boot-time endpoint check + `residency_check` audit entry | `app/residency.py`, wired in `app/main.py` |
| 7 | `RETENTION_YEARS=10` / `HOT_SEARCH_YEARS=1`; nightly archive-to-cold-tier and purge beats; `Contract.archived_at` + `Contract.legal_hold`; `FileObject.storage_tier`; archived rows excluded from the live list | `app/archive_service.py`, `app/tasks.py`, `migrations/0015_retention_tiering.py` |

**Tests** — 55 added (`test_db_dialect.py` 25, `test_archive_retention.py` 12,
`test_residency_and_profile.py` 18). CI gains a `migrations` job that runs
`alembic upgrade head`, re-runs it for idempotency, and downgrade-round-trips on **Postgres and
MSSQL** — the only job that executes the dialect DDL against a real server.

**Fixed in passing** — two pre-existing defects found while wiring this up:
- `validate_for_production` treated `ENV=test` as production, so `TestClient` could never start
  the app (contradicting CLAUDE.md). Now `is_non_production` covers dev *and* test.
- `ruff check apps/api/app` was red at HEAD (18 findings in untouched files). Now clean.

**Not done / carried forward**
- **Oracle DDL is generated and unit-tested, never executed.** No Oracle container in CI. First
  Oracle deployment must run the migration matrix manually as an acceptance gate.
- Four tests were already failing before this phase and still are — `test_void_decline_terminal_states`
  (`expired → renewed` is a real transition the test forbids), two password-policy tests that
  assume dev length limits under `ENV=test`, and `test_raw_token_is_not_persisted`. They are
  unrelated to Phase 0; each is a test-expectation bug, not a product bug.
- `next lint` is a no-op — the repo has no ESLint config, so CI's `--if-present` silently skips
  it. Type-checking via `next build` is clean.

### Phase 1 — PKI and Certificate Lifecycle Management ✅ (25 Aug 2026)

**Shipped** — `apps/api/app/pki/` (7 modules), `routers/pki.py`, migration `0016_pki`,
`app/(app)/pki/` console, `docs/PKI-ARCHITECTURE.md`.

| Brief item | State |
|---|---|
| 1. Key custody seam (`SoftKeyStore` + `Pkcs11KeyStore`) | ✅ no export method on the ABC; HSM keys `CKA_SENSITIVE`/non-extractable; SoftHSM2 job in CI |
| 2. CA hierarchy (offline root → issuing CA), ECAC re-chaining | ✅ `pathLen=0` on issuing; `take_root_offline()` key ceremony; `cross_certify()` proven by test |
| 3. RA workflow + `CertificateRequest` | ✅ issuance impossible without approval; separation of duties; `RA_DUAL_CONTROL` |
| 4. Certificate lifecycle (6 ops) + one-per-signatory | ✅ service check **and** partial unique index (per-dialect) |
| 5. CRL (full + delta), CDP extension | ✅ `/pki/crl/{ca}.crl`, `-delta.crl`; monotonic CRL numbers; `removeFromCRL` on resume; beat republishes at half the validity window |
| 6. OCSP responder + AIA extension | ✅ RFC 6960 POST **and** GET; delegated responder cert with `OCSPNoCheck`; nonce echoed; `unknown` ≠ `good` |
| 7. Third-party validation + trust store | ✅ RFC 5280 path build/verify, OCSP-then-CRL revocation, runtime-extensible anchors |
| 8. Admin UI; replace `identity-check` / `passkeys` mockups | ✅ `/pki` console (overview, RA queue, register, trust store) wired to real endpoints; **both mockups deleted** |
| 9. SBOM in CI | ✅ `sbom` job publishes `sbom-api.json` + `sbom-web.json` (CycloneDX), 90-day retention |

**Tests** — 52 in `test_pki.py` (all passing) + 7 SoftHSM2 tests in `test_pki_hsm.py`
(CI job `pki-hsm`; skipped locally). Suite total: **127 passing**, 4 pre-existing failures unchanged.

**Mockup pages deleted:** `identity-check`, `passkeys` (also removed from the nav and the
capabilities index). 19 mockup pages remain, all outside Phase 1 scope.

**Not done / carried forward**
- **The CA is not yet in the signing path.** Phase 1 builds the PKI; **Phase 2** replaces the
  shared-PKCS#12 PAdES provider with per-signatory signing (PAdES-LTV: embedded chain,
  revocation data, RFC 3161 timestamp). Until then `SIGNING_PROVIDER=pades` still uses one
  organisational certificate — the thing the RFP forbids. This is the single most important
  follow-through item.
- **A real HSM is procurement, not engineering.** SoftHSM2 proves the code path; it cannot
  prove FIPS 140-2 Level 3. Production must set `KEYSTORE_PROVIDER=pkcs11` against a Luna /
  Utimaco / nShield device.
- Path validation omits name constraints and certificate policies (documented in
  `PKI-ARCHITECTURE.md` §10).
- OCSP p95 < 200 ms is designed for but not load-tested — that evidence is Phase 10.

### Phase 2 — Advanced eSignature depth ✅ COMPLETE (25 Aug 2026)

**Shipped**

| Brief item | State |
|---|---|
| 1. Per-signatory cryptographic signing (PAdES-LTV) | ✅ `app/pki/signer.py` + `PkiSigningProvider`. Each signatory signs with their own certificate through the keystore (HSM-capable, key never exported). LTV embeds the chain plus an OCSP response and CRL **generated locally by our own CA** — no network fetch, no foreign egress. RFC 3161 timestamp when `SIGNING_TSA_URL` is set. Every signature writes a `SignatureEvent` naming the certificate serial |
| 6. Authority matrix | ✅ `models.SignatoryAuthority` + `authority_service.py` + `/authority/*`. Matches on department, contract type, currency and value band; most specific rule wins; role hierarchy means `manager` is satisfied by an owner. **Advisory, not blocking** — a deviation needs an override reason and is audited with both the required and the chosen signatory |
| 7. Reviewer-as-signatory | ✅ asserted in `TestReviewerMayAlsoSign` rather than left implicit |
| 8. Execution reliability | ✅ optimistic locking (`lock_version`) so two parallel signers cannot both advance the envelope from one snapshot; idempotent signing (a repeat request is rejected, not double-counted); `seal_status` / `seal_attempts` / `seal_error` on the envelope; dead-letter view + retry at `/authority/seal-failures` |

Recipients now carry `signer_user_id` / `party_ref` / `certificate_id` / `identity_method` /
`identity_evidence` (migration `0017_esignature_depth`), which is what lets the sealer find
*this signatory's* certificate instead of falling back to a shared one.

**Tests** — 18 in `test_esignature_depth.py`. The headline one signs a single document with two
different signatories and verifies, against the actual PDF bytes, that two independent
signatures exist, each naming its own certificate serial, both chaining to our root, and that
a one-byte edit inside the signed revision is detected. Suite total: **145 passing**.

**Second pass (same day) — items 2, 3 and 4 delivered:**

| Brief item | State |
|---|---|
| 2. Visitor / merchant eSigning surface | ✅ `models.SigningInvitation` + `models.VisitorSession` + `visitor_service.py` + public `/esign/*` + `app/(portal)/esign/[token]/`. Shareable link and QR (`segno`, optional), kiosk/mobile/QR entry points recorded for the MIS breakdown, email **or SMS** OTP, scroll-to-end consent evidence printed on the Certificate. Anti-automation: self-hosted proof-of-work, per-IP session caps, OTP attempt and resend caps. **Not load-tested at 100,000/year** |
| 3. Visitor certificate issuance | ✅ on OTP verification the visitor is auto-enrolled under the `visitor` policy profile and issued a 7-day certificate. Auto-approval is recorded explicitly in the request evidence, so an auditor sees the certificate rests on an OTP rather than a human RA officer. A returning signatory resolves to the same `party_ref` and reuses their certificate |
| 4. Smart signature tagging | ✅ `tagging.py` — positioned text extraction from the rendered PDF, anchor-phrase matching, column-aware distribution across signers, template-declared anchors, confidence scores. `POST /envelopes/{id}/auto-tag` previews or applies. Manual placement stays as an override |

Supporting work: `sms.py` provider seam (console / HTTP gateway / null) with E.164 normalisation
and masking; `email_outbox.channel` so SMS and email share one delivery audit **and the SMTP
flush beat stops trying to email phone numbers**.

**Root-cause fix:** `send_email()` opened its own session and committed, which deadlocked on
SQLite against a caller holding a write transaction and, on any engine, committed an outbox row
even if the caller later rolled back — an email for something that never happened. It now
accepts `db=` to join the caller's transaction. Same class of bug as the Phase 1 keystore fix.

**Mockup deleted:** `signature-studio` (superseded by real auto-tagging). **18 mockups remain.**

**Tests** — 44 in `test_visitor_esign.py` (weighted to the negative cases: wrong code, expired
code, brute force, a session from someone else's link, signing before reading) and 15 in
`test_tagging.py` (against a real rendered two-column signature page). Suite total: **204 passing**.

**Third pass (same day) — item 5 delivered, Phase 2 closed:**

| Brief item | State |
|---|---|
| 5. Wet-signature / hybrid path | ✅ `wet_signature.py` + `models.WetSignatureAttestation` + migration `0019`. `SignatureRecipient.signing_mode` routes each party independently, so one government counterparty on paper does not push everyone else off the electronic flow. Print pack = cover sheet (reference the returned scan is matched on, named paper signatories, instructions) merged with the agreement. Attestation records the accountable employee, the scan's SHA-256, the **declared execution date** — which is when the parties signed, not when someone scanned it — and an optional witness. `_converge()` completes the envelope once every party is done by either route, and the sealer skips paper signatories rather than signing on their behalf |

**Design point worth stating plainly:** a scanned page proves nothing on its own — anyone can
scan anything. The evidence is a named person inside the bank asserting, in the append-only
audit chain, that *this file* is the executed copy of *this agreement*, received on *this
date*. The scan is the artefact; the attestation is the evidence. `evidence_summary()` keeps
the two kinds separable so the Certificate of Completion can never present a scan as though it
were a PAdES signature.

**Tests** — 23 in `test_wet_signature.py`, weighted to convergence (a hybrid envelope reaching
`completed` and advancing the contract lifecycle identically) and to honesty (a wet signatory
is never paired with a certificate). Suite total: **227 passing**.

**Phase 2 remaining:** nothing in the brief. Two items carried to later phases:

- a **load test** evidencing 100,000 external signatories/year — Phase 10;
- the **pyHanko question** flagged in the first pass, which is for counsel, not engineering.

**Judgement call flagged for legal review:** PAdES embedding uses **pyHanko** (already a
declared dependency in `requirements-sign.txt`). It performs the PDF byte-range encoding — it
never sees a private key, and the CA, certificates, keys and trust decisions are all ours. The
sworn undertaking concerns the PKI and eSignature *engine*; counsel should confirm that a
PDF-format library sits on the same side of that line as `reportlab` and `cryptography`. If it
does not, the alternative is hand-rolling byte-range signing, which is achievable but is the
kind of code that produces subtly invalid signatures.

**Also fixed in passing:** the downgrade path for `0017` exposed that `0001_initial`
materialises the schema with `Base.metadata.create_all()`, so every later migration is a no-op
on a fresh database and model/migration divergence is invisible. Worked around inside `0017`
(`_drop_indexes_covering`), but the underlying wart is worth addressing before the schema grows
further.

### Phase 4 — Workflow engine rebuild 🟡 ONE ITEM OUTSTANDING (25 Aug 2026)

**Shipped**

| Brief item | State |
|---|---|
| 1. Parallel step groups | ✅ ordered **stages** of concurrent **steps**; policies `all` / `any` / `quorum(n)` / `percentage(p)`. An unrecognised policy falls back to `all` — the strictest reading, so a typo can never reduce the approvals required |
| 2. Dynamic approval matrix | ✅ `models.ApprovalRule` + `approval_matrix.py`. Rules **add** stages rather than replacing the workflow; re-evaluated on material change with the re-route audited. A rule that matches but names nobody is skipped loudly rather than inserting a stage that could never complete |
| 3. SLA + escalation | ✅ per-step SLA on a **business calendar** (`business_calendar.py`), reminder at `SLA_REMINDER_FRACTION`, escalation on breach, `workflow.sla_sweep` beat, `/workflow/escalations` feed with business-hours mean-time-to-resolve |
| 4. Delegation / out-of-office | ✅ scoped and windowed; assignments route to the proxy and **both** identities stay in the audit trail |
| 5. Mid-flight reviewer changes | ✅ add/remove on a running stage, audited; a decided reviewer can never be removed |
| 6. Non-standard classification | ✅ `mark_non_standard()` selects the non-standard stage set and fires `non_standard_only` rules |
| 7. Consolidated review + internal-only flag | ✅ `/contracts/{id}/review` grouped by function; `internal_only` enforced in one fail-closed function and asserted against every external shape |
| 8. @mentions | ✅ `models.Mention`, notification fan-out, `/mentions` inbox filter |
| 9. Client-facing coordinator role | 🟡 the capability and its check exist; **not yet wired into every external-share path** |

15 new endpoints in `routers/workflow_admin.py`. Migration `0020_workflow_engine`.
**Backwards compatible:** a legacy flat `steps` definition promotes to one step per stage,
which *is* the old sequential behaviour, so existing definitions and in-flight runs keep working.

**Tests** — 39 in `test_workflow_engine.py` + 17 in `test_consolidated_review.py`.
Suite total: **283 passing**.

**Two real bugs caught by the tests, both fixed:**
- a reviewer removed mid-flight still counted toward an `all` stage's denominator, making the
  stage permanently unsatisfiable — the review would sit open forever with nobody left to act;
- the two-word @mention pattern greedily swallowed the following word, so `@ayesha.khan please`
  resolved to nobody.

**UI pass (same day):** `workflow-builder` rebuilt against the real API — it edits the stage
graph directly, makes concurrency the obvious default (adding a reviewer puts them *alongside*,
not after), and refuses to save a graph the engine would reject (an empty stage, a quorum of 3
among 2 reviewers). A legacy flat definition promotes into the editor without losing anything.
New `workflow-ops` page: escalations feed with business-hours mean-time-to-resolve, the approval
matrix, delegations, and the holiday calendar.

**Mockup deleted:** `workflow-builder` — rebuilt, not removed. **17 mockups remain.**

**Bug caught while wiring the UI:** the Phase 4 schema additions introduced a second
`WorkflowRunOut` class that shadowed the existing one, so `routers/contracts.py` would have
constructed the wrong shape at runtime. Ruff's F811 did not fire (the first definition is
referenced between the two). Renamed to `WorkflowRunGraphOut` — they answer different
questions about the same run.

**Still outstanding in Phase 4:**

| Brief item | Status |
|---|---|
| 10. Sign-off readiness pack (auto-generated approval summary PDF) | ❌ not started. Every input it needs — who cleared, when, with what comments, SLA adherence — is recorded; the PDF renderer and its attachment to the envelope are not built |

Plus §3.5's client-facing capability, which is defined and tested but not yet enforced at every
point where something can be transmitted to a counterparty.

### Phase 3 — Document engine 🟡 IN PROGRESS: Word round-trip + merge-field engine (26 Aug 2026)

**Shipped — brief item 1 (DOCX round-trip):**

| Piece | State |
|---|---|
| Export | ✅ `docx_engine/export.py` — clause numbers emitted as a real `w:numbering` definition with a cumulative multi-level scheme (`1`, `1.1`, `1.1.1`), heading styles, tables, and the reference in the page header. The authored number is **discarded** on export because Word regenerates it, which is what makes an inserted clause renumber correctly instead of silently lying |
| Import | ✅ `docx_engine/importer.py` — body text with clause depth reconstructed from `w:numPr/w:ilvl` (not by parsing digits), `w:ins`/`w:del` tracked changes with author and timestamp, and `word/comments.xml` comments resolved to the clause they were anchored on |
| Test fixtures | ✅ `docx_engine/fixtures.py` builds genuine OOXML — `w:ins`, `w:del`/`w:delText`, a real comments part with `commentRangeStart` anchors — so the importer is tested against what Word produces rather than against documents this codebase wrote |
| API | ✅ `GET /contracts/{id}/export.docx`, `POST /contracts/{id}/import.docx`. Import previews by default; applying it snapshots the previous wording as a version, files the counterparty's comments, and **classifies the agreement non-standard** (RFI §3.1), which selects the non-standard approval route |
| UI | ✅ `docx-studio` rebuilt against those endpoints — export, upload, see the tracked changes and comments, then apply. **The mockup is gone** |

`python-docx==1.1.2` is now a **base** dependency, not an optional extra: exporting and
importing .docx is how counterparties actually negotiate, not an integration.

**Tests** — 36 in `test_docx_roundtrip.py`, including a 10-agreement MMBL-shaped corpus each
cycled export → import → export. Suite total: **319 passing**.

**On "byte-stable".** The brief asks for byte stability across the cycle. A DOCX is a zip whose
byte layout depends on entry order, compression and Word's `rsid` churn — none of which affect
the document — so byte equality is neither achievable nor what the requirement is protecting.
What is tested is **structural** stability: numbering definitions, paragraph styles and levels,
table shape, header and footer text identical across the cycle, plus an idempotence check that
a second cycle changes nothing further. Stated here rather than buried, because it is a
deliberate reading of the requirement.

**Bug caught by the tests:** the exporter added a title heading unconditionally, so every
export → import → export cycle grew the document by one heading. Now suppressed when the body
already opens with one.

**All eight Phase 3 items are now done** (items 5 and 7 closed 28 Aug 2026 — see below).

~~NOT done~~:

| Brief item | Status |
|---|---|
| 5. Guided drafting wizard | ❌ not started |
| 7. AI assist — clause suggestion, deviation flagging, AI data capture | ❌ not started; `ai-analysis` is still a mockup and `OCR_PROVIDER` still defaults to the stub |

### Phase 3, items 3 + 4 — template repository and the merge-field engine ✅ DONE (26 Aug 2026)

The RFI's core intake mechanic (§2.3): *select agreement type → structured form with
drop-downs and LOVs → submit → the system generates the draft from the pre-approved template*.
Built as one piece because the two halves are meaningless apart — "pre-approved" needs the
version snapshot, and "generates" needs the field schema.

| Piece | State |
|---|---|
| Merge engine | ✅ `app/merge_engine.py` — ten field types (`text`, `textarea`, `number`, `money`, `date`, `select`, `multiselect`, `boolean`, `entity_ref`, `file`), server-side coercion and validation, deterministic formatting, and definition-level checks that catch a broken template at authoring time |
| Template approval | ✅ `app/template_service.py` — `draft → pending_approval → active → retired`, with **separation of duties**: the author of a template cannot approve it (owners/admins exempt so a two-person workspace is not deadlocked) |
| Version snapshots | ✅ `contract_template_versions` — the approved wording and field schema are frozen on approval. Generation reads the **snapshot**, never the live row, so an in-progress edit cannot leak into a contract before anyone has approved it |
| Provenance | ✅ `contracts.template_id` + `template_version_no` + `merge_values`. Two years on, "was this raised from the approved template, and with what values?" is answerable from the contract itself, not just the audit log |
| API | ✅ `GET /templates/{id}/form`, `POST /{id}/preview`, `POST /{id}/generate`, `POST /{id}/submit`, `/approve`, `/reject`, `/retire`, `GET /{id}/versions`, `POST /templates/suggest-fields` |
| UI | ✅ `/templates/[id]/intake` — the RFI journey end to end: the form renders from the template's own schema, Preview shows the wording before committing, Generate creates the draft. The templates list gained the approval actions and an inline field editor with **scaffold-from-body** |

**Two design decisions worth stating, because both were choices:**

1. **An unfilled placeholder is an error, not a blank.** If a template says `{{monthly_fee}}`
   and nothing supplies it, generation *refuses*. A draft with a visible `{{monthly_fee}}` is an
   obvious defect; one with a silent gap where the fee should be is a defect that gets signed.
   `allow_unresolved` exists as an explicit opt-in for "generate it anyway, I'll finish by hand".

2. **Editing approved wording un-approves the template.** The edit lands on the live row and
   knocks it back to `draft`, so it must be re-approved before the next generation picks it up.
   The alternative — letting edits go live immediately — would make "generated from the approved
   template" untrue for every contract raised afterwards.

**Also fixed:** `ContractTemplate.is_active` was the only gate on whether a template could be
used, which meant anyone who could author one could put it into use. `status` is now
authoritative and `is_active` is derived from it in a single place. Existing templates migrate
to `active`/`retired` so nothing that worked before 0021 stops working after it.

**Bug caught while building:** the session runs with `autoflush=False`, so `approve()` adding a
version snapshot left it invisible to the next query — a second approval would not have
superseded the first, and `retire()` would have left it active. Both would have corrupted the
one question the version table exists to answer. Now flushed explicitly, with a test for each.

**Tests** — 63 in `test_merge_fields.py`: the engine in isolation (types, LOVs, bounds,
formatting, unresolved handling), the approval state machine including separation of duties,
and the full journey through the API including tenant isolation. Suite total: **382 passing**.

### Phase 3, items 2 + 6 — clause library and playbook engine ✅ DONE (26 Aug 2026)

Built together because a clause library without deviation checking is a well-organised text
store. The library supplies approved wording; the playbook says which of it is compulsory; the
review measures an actual draft against both.

| Piece | State |
|---|---|
| Clause library | ✅ `app/clause_service.py` + `models.Clause` / `ClauseVersion` — same approval gate as templates (`draft → pending_approval → active → retired`), same separation of duties, same frozen version snapshots |
| Alternatives | ✅ Fallback positions are `parent_id`-linked **clauses**, not a lesser side-table: an alternative is wording that ends up in a signed agreement, so it earns the same approval gate and version history. Ranked, with guidance on when to reach for each |
| Composition | ✅ A template refers to a clause with `[[clause:key]]`; `expand()` resolves it to the **approved snapshot** at assembly time, before merge fields are substituted (so a clause can itself contain `{{fields}}`). Improving a clause improves every template that uses it |
| Playbook engine | ✅ `app/playbook_service.py` — required / prohibited / preferred rules, scoped by contract type, value band, department or risk. A house-wide policy and a type-specific one **both** apply; taking only the most specific would silently drop the general rules |
| Deviation detection | ✅ Three distinct findings, usually conflated: `missing`, `altered` (the interesting one — the clause is still under its heading but the cap has changed) and `prohibited`. Word-level diff via stdlib `difflib`, with normalisation so markdown, numbering and line wrapping are not reported as deviations |
| Classification | ✅ A **blocking** deviation calls `mark_non_standard`, which the workflow engine already routes differently. A deviation that only produced a report is one somebody can approve without noticing |
| API | ✅ `GET/POST/PATCH /clauses`, `/clauses/{id}/submit|approve|reject|retire|versions`, `GET/POST/PATCH/DELETE /playbooks`, `GET|POST /contracts/{id}/policy-review` |
| UI | ✅ `clauses` rebuilt against real endpoints — searchable library with nested fallback positions, approval actions, and a playbook rule editor. **The mockup is gone.** A new **Policy** tab on the contract page shows each finding with its diff |

**Design decisions worth stating:**

1. **An unresolvable clause reference is never negotiable.** Merge fields have an
   `allow_unresolved` escape hatch; clause references do not. A contract quietly missing its
   limitation of liability is the worst thing a clause library can produce, so generation
   refuses outright — including when a clause is retired out from under a live template.
2. **Similarity thresholds are named constants, not magic numbers.** `UNCHANGED_RATIO = 0.98`
   and `PRESENT_RATIO = 0.55` are heuristics tuned against the seeded corpus and marked
   `ponytail:` for an operator to move once real MMBL paperwork shows where they sit. The match
   percentage is exposed in the UI so a reviewer can judge a borderline call rather than
   trusting the threshold blindly.
3. **Comparison is stdlib.** "Is this paragraph still the approved one?" is a string question;
   an answer that needs a network call is an answer that fails when the network does — and
   on-prem-only is a hard constraint of this bid.

**Seed data now exercises the whole chain:** six clauses (two with ranked alternatives), two
playbooks (house rules + vendor/outsourcing), and the Merchant Acquiring template composing
five of those clauses by reference. A test drives the seeded data end to end — seed → generate
→ policy review passes — because the demo path is what a live bid demo runs on, and it should
break in CI rather than in front of the customer.

**Also fixed:** four SLA tests in `test_workflow_engine.py` called `sla_sweep(db)` without a
tenant, so they counted every overdue step in the shared test database and only passed by
luck about what earlier tests left behind. Now scoped, matching their sibling.

**Tests** — 39 in `test_clause_library.py`. Suite total: **421 passing** (4 pre-existing
failures unchanged).

### Phase 3, item 8 — redline and compare ✅ DONE (28 Aug 2026)

Word-level comparison of two versions, accept or reject change by change, with discussion
threads anchored to individual changes.

| Piece | State |
|---|---|
| Diff | ✅ `app/redline_service.py` — `difflib` over word-and-whitespace tokens, so accepting **every** change reconstructs the compared text byte for byte and accepting **none** reconstructs the base. Both are property-tested across a twelve-document corpus (pure insert, pure delete, reordering, unicode, whitespace-only, empty sides) |
| Accept / reject | ✅ Partial acceptance is exact: taking the liability change and rejecting the notice-period change yields precisely that document. Applying saves the previous wording as a version first — a redline is a destructive edit |
| Anchored threads | ✅ Each change carries a character range in the proposed text; `POST /contracts/{id}/redline/comment` opens a thread against it using the `anchor_start`/`anchor_end` columns that had existed unused since Phase 4 |
| API | ✅ `GET /contracts/{id}/redline?base=&compare=` (defaults to last-saved-vs-live draft), `POST .../redline/apply`, `POST .../redline/comment` |
| UI | ✅ `redline` rebuilt against those endpoints. **The mockup is gone** |

**No new tables.** `ContractVersion` rows are immutable, so comparing the same pair always
produces the same changes in the same order — which makes a change's position a stable
identifier and "accept changes 0, 2 and 5" reproducible without persisting a session someone
would then have to garbage-collect. A stale index is refused rather than partially applied: a
client whose view has drifted must not get a document nobody chose.

**Also fixed:** `CommentOut` never exposed `anchor_start`/`anchor_end`, `kind`, `internal_only`
or `department` — the columns existed but the API hid them, so anchored threads could be
written and never read back.

---

### ✅ Audit-chain ordering defect found and closed (28 Aug 2026)

Found while chasing an intermittent test failure. **The tamper-evidence chain could be
defeated by deleting a row**, which is the single thing it exists to prevent.

The chain picked its predecessor with `ORDER BY (at DESC, id DESC)` and verification walked
with `(at ASC, id ASC)`. Those are consistent with each other but neither is *insertion*
order. Two audit rows written inside the same clock tick share an `at`, so ordering fell
through to `id` — a random uuid. When the ids happened to sort against insertion order, row 3
chained to row 1, skipping row 2; silently deleting row 2 then left a chain that **verified
perfectly**.

Confirmed with a standalone reproduction before fixing, not inferred. `0023_audit_seq` adds a
monotonic per-tenant `seq`, assigned under the advisory lock that already serialises audit
writes, and both the append and the verify walk it. Existing rows are backfilled in `(at, id)`
order — the order the old verifier used — so nothing that verified before the migration stops
verifying after it.

Three regression tests force two rows into the same tick through the real `record()` path (via
a new `_utcnow()` seam) and assert the chain still links correctly, still catches a deletion,
and still catches an edit. **They were verified to fail against the old ordering** — a
regression test that passes either way proves nothing.

> This matters for the dossier: §"What 0013_hardening closed" item 5 claims audit-log tamper
> evidence. That claim was only fully true at sub-tick write rates until 0023. It is true now,
> and the honest version is that the original design had a real hole in it.

**Tests** — 55 in `test_redline.py`, 3 added to `test_audit_chain.py`. Suite total:
**479 passing** (4 pre-existing failures unchanged).

### Phase 3, items 5 + 7 — guided drafting and AI assist ✅ DONE (28 Aug 2026)
### Phase 4, item 10 — sign-off readiness pack ✅ DONE (28 Aug 2026)

**Phases 3 and 4 are now complete.**

| Piece | State |
|---|---|
| Guided drafting wizard (3.5) | ✅ `/templates/[id]/intake` rebuilt as a step-through: clause selection → details → preview → generate. Clause selection is real: a drafter may swap a clause for one of **its own approved alternatives**, with the risk level of each option shown, and may append optional library clauses |
| Clause-choice safety | ✅ `clause_service.resolve_choice` refuses anything that is not an approved alternative *of that clause*. Allowing an arbitrary key would be editing the contract through a drop-down, without the approval editing would have required |
| Clause suggestion (3.7) | ✅ `ai_service.suggest_clauses` — **deterministic, no model**. Three tiers: policy requires it and it is missing; comparable agreements of this type use it (with counts); it is a high-risk library clause the draft omits. Every suggestion cites its basis |
| Deviation flagging (3.7) | ✅ Already built in Phase 3.6 and surfaced on the Policy tab. Deterministic and explainable line by line — replacing it with a model would trade an explanation for a guess |
| AI data capture (3.7) | ✅ `models.ExtractionReview` + `/contracts/{id}/ai/capture`. **Extraction never writes to a contract.** Every capture waits for a person to tick fields one by one, and what they accepted is audited |
| On-prem model (3.7) | ✅ `LocalOcrProvider` — an OpenAI-compatible endpoint hosted **inside the deployment** (vLLM/Ollama). `OCR_PROVIDER=local` + `OCR_BASE_URL`. This is the MMBL-compliant setting: no document leaves the network |
| `ai-analysis` UI | ✅ Rebuilt against those endpoints. It shows which provider produced each capture, and labels `stub` as "the document was not read". **The mockup is gone** |
| Sign-off readiness pack (4.10) | ✅ `app/readiness.py` + `GET /contracts/{id}/readiness[.pdf]` + a Readiness tab. Leads with **blockers**, then the approval record, then provenance (which template revision, which clause versions, edited since generation?) |

**Design decisions worth stating:**

1. **Most of "AI assist" does not need AI, and pretending otherwise would be worse.** Clause
   suggestion is a counting question over the library; deviation flagging is a policy check. A
   model would answer both less accurately, less repeatably, and would need a model deployment
   to answer at all. Only document capture genuinely needs one.
2. **A confidence score is not a fact.** A document saying "the term is 12 months from the
   Effective Date" and a model guessing which date that is produces a plausible, wrong end date
   that then drives renewal reminders. So capture proposes and a human disposes — and a
   high-confidence value that would change nothing is *not* pre-ticked, so confirming never
   becomes a habit of clicking through no-ops.
3. **The stub is still the zero-config default, and the UI says so.** Any deployment claiming
   real extraction must be verified to be on `local` or `anthropic`; the page labels stub
   output rather than letting it pass for extraction.

**Also fixed:** `readiness.py` initially ordered by `WorkflowRun.created_at`, a column that does
not exist (it is `started_at`) — caught by the tests before it reached a route.

**Tests** — 15 in `test_readiness.py`, 25 in `test_ai_assist.py`, 8 added to
`test_clause_library.py`. Suite total: **527 passing** (4 pre-existing failures unchanged).

### Phase 5 — Repository, search, relationships, post-execution lifecycle 🟡 IN PROGRESS (28 Aug 2026)

**Done — items 1–9 and 11:**

| Item | State |
|---|---|
| 1. Full-text search | ✅ `app/search_service.py` through the Phase 0 dialect seam — `tsvector`+GIN on Postgres, catalogue on MSSQL, Oracle Text, `LIKE` on SQLite. Filters on party, department, folder subtree, dates, value bands, tags and clause. Snippets built in Python rather than per-dialect `ts_headline`, so all four engines agree. `search` wired |
| 2. Agreement relationships | ✅ `models.ContractRelation` — typed and directional, addenda numbered sequentially per parent, context inherited so nobody retypes the counterparty, two-directional history tree |
| 3. Party / vendor master | ✅ `models.Party` with **duplicate onboarding blocked**: exact registration match and fuzzy name match reported as different evidence, override requires a reason and is audited |
| 4. Departments and folders | ✅ Real models; folder paths materialised so "everything under /Legal" is a prefix match. Moving rewrites the subtree; moving into your own descendant is refused. `departments` and `folders` wired |
| 5. Custom fields | ✅ `models.CustomFieldDef` reusing the merge-engine type vocabulary rather than a second type system. `custom-fields` wired |
| 6. Obligation tracker | ✅ `app/obligation_service.py` — cross-contract rollup with operations counts, plus an idempotent reminder/escalation sweep. `obligations` wired |
| 7. Renewals | ✅ Per-agreement notice schedule (default 90/60/30) — one global setting would always be wrong for either a 3-year outsourcing contract or a 3-month NDA |
| 8. Amendments | ✅ `app/change_service.py` — an amendment is a **separate draft**, so the parent stays in force until it is executed. Impact (fields, clauses, value delta, term delta) is recorded at execution rather than reconstructed later |
| 9. Terminations | ✅ A request with a reason and supporting documents, multi-role sign-off, one rejection ends it, execution closes open obligations, and the notice is **generated from the record** — a notice that disagrees with the record is a dispute |
| 11. Legal checklist | ✅ `models.LegalChecklist`, versioned; editing a published one bumps the version, because a checklist that changes silently cannot evidence what was required at the time |

**Item 10 ✅ done** — `app/export_service.py` produces real XLSX (contracts, obligations, parties, audit) as a `BackgroundJob` with a download link, reusing the progress tray built for OCR and sealing. Every workbook opens with a **Filters** sheet naming what produced it. Print stylesheets force the light palette, drop the chrome and stop rows splitting across page breaks.

**Phase 5 is complete.**

**Bugs caught by the tests:**

- `L.L.C` normalised to `l l c` and so did not match `LLC` — dotted abbreviations are ordinary
  in company names, and every suffix rule was defeated by them.
- The departments page called `/team`, which does not exist; the endpoint is `/users`.
- The obligation sweep fired the 14-day reminder and then, on the very next run, the 7-day one
  — two emails the same morning. Only the **tightest** crossed threshold fires now.

**Deliberate duplication, flagged rather than hidden:** `Contract.counterparty` and
`.department` are still written alongside the new `party_id`/`department_id`. Every existing
report, export and rendered PDF reads the text columns; migrating all of them in this change
would have been a far larger blast radius than the problem justifies. The new columns are
authoritative. Cutting the text columns is a separate mechanical pass.

**Tests** — 56 in `test_repository.py`, 39 in `test_change_flows.py`. Suite total:
**622 passing** (4 pre-existing failures unchanged).

### Phase 6 — Analytics, dashboards and MIS ✅ DONE (28 Aug 2026)

`app/analytics_service.py` + 13 endpoints under `/analytics` + a new **Analytics** page.

| Group | State |
|---|---|
| Executive KPIs | ✅ Cycle time per type (mean/median/p90), approval bottleneck ordering, SLA adherence per stage, renewal pipeline with value at risk, escalations per month with mean time to resolve |
| Operational | ✅ Reviewer workload ordered by what is **open** rather than throughput, redline iteration counts, most-negotiated agreements, clause pressure ("what do counterparties keep pushing back on?") |
| Compliance | ✅ Deviations, missing mandatory clauses, non-standard count and overdue obligations — computed live through the real policy engine |
| RFI metrics | ✅ Executed by department, average review cycle, most-requested types, pending agreements and bottleneck stages |
| MIS | ✅ Daily/weekly/monthly volume with **year-on-year aligned by period key**, plus segmentation by department, region, entity type, agreement type, status and currency |
| Role dashboards | ✅ `/analytics/me` returns my reviews, reviews due today, escalations, obligations and renewals in **one** call — this is the first screen after login and four round trips is the difference between instant and flickering |
| Export | ✅ Any report to XLSX through the same job the repository export uses |

**Three decisions worth stating:**

1. **The numbers come from the audit log, not a metrics table.** Cycle times and stage timings
   are reconstructed from `contract.status_changed` and the workflow steps. The audit log is
   the tamper-evident record of what happened, so a cycle time derived from it is defensible
   in a way that one written by whichever code path remembered is not.
2. **Pre-aggregation only where it earns its place.** Point-in-time KPIs are grouped queries
   over indexed columns and stay fast. Rolling them up would add a refresh dependency and a
   staleness bug for no gain — and a *stale compliance number* is the one number that must
   never be stale. The genuinely expensive question is the ten-year time series, which is the
   candidate for a daily rollup when a real corpus shows it is needed.
3. **Every figure reports its sample.** A mean cycle time over four agreements and one over
   four hundred are different claims. Unfinished agreements are **excluded**, not counted as
   zero — an average that improves whenever somebody starts a draft is worse than no average.
   A stage with no SLA reports `null`, never 100%.

**Charts are inline SVG and CSS.** These are bars and a sparkline; a 90 kB charting dependency
to draw a rectangle is a dependency to keep patched for the life of the contract.

**Tests** — 25 in `test_analytics.py`, 16 in `test_exports.py`. Suite total: **663 passing**
(4 pre-existing failures unchanged).

### Phase 7 — Integrations ✅ DONE (28 Aug 2026)

| Item | State |
|---|---|
| 1. SAML 2.0 | ✅ `app/saml.py` — metadata, SP- and IdP-initiated login, ACS, SLO, group→role mapping. Signature verification delegated to `signxml`, **deliberately**: XML signature wrapping is a family of SSO-bypass bugs that hand-rolled verification walks into. Tests mint a real certificate and prove unsigned / wrong-key / tampered / wrong-audience / replayed assertions all fail. `sso-admin` rebuilt — it previously advertised an ACS URL that did not exist |
| 2. SIEM feed | ✅ `app/siem.py` — CEF and CLF over syslog with TLS, seven InfoSec categories, severity mapped correctly in both directions. A **projection of the audit log**, not a second log, so an outage is replayable via `/siem/replay`. Delivery never blocks a request |
| 3. Kong | ✅ `infra/kong/kong.yaml` — declarative config with per-route rate limits, request-size cap matching `MAX_UPLOAD_MB`, IP restriction on SOAP, CORS, correlation id. Documented topology: WAF → Kong → app, with the app's own middleware kept as the second layer |
| 4. Teams + SharePoint | ✅ `app/connectors.py` — adaptive cards on the events worth interrupting for (not every draft save), SharePoint upload filed by year and type, on-prem Server supported |
| 5. Outlook / Exchange | ✅ Calendar invites as **`.ics` attachments on the existing mail pipeline**. No EWS/Graph integration, no token to rotate, works against on-prem Exchange with zero configuration. Stable UIDs so a moved renewal updates the entry rather than duplicating it |
| 6. SMS | ✅ Already shipped in Phase 2 — provider seam with a Pakistani-aggregator HTTP backend and residency enforcement |
| 7. Sanctions screening | ✅ `app/sanctions.py` — OFAC/UN/EU/HMT snapshots held **locally**, fuzzy matching that handles real transliterations, review queue, decisions audited. A hit never auto-rejects |
| 8. Backup tooling | ✅ `infra/scripts/backup-verify.sh` + `docs/29-backup-and-dr.md` — Veeam/Commvault pre/post hooks, and verification that checks the restore is *usable* rather than that `pg_restore` exited zero |
| 9. SOAP facade | ✅ `app/soap.py` — GetContract / ListContracts / CreateContract with a WSDL, authenticated with the same API keys. Off by default |
| 10. Connectors UI | ✅ `integrations` rebuilt against `/connectors` — shows what is actually wired, with a Teams test button |

**Decisions worth stating:**

1. **The `.ics` answer to "Outlook integration" is the whole implementation, and that is the
   point.** An EWS or Graph integration would add an authenticated Exchange connection, a
   token to rotate and a per-version compatibility surface — to deliver something every mail
   client already understands as an attachment.
2. **Sanctions lists are local.** A screening call that fails open because a US endpoint was
   unreachable is a control that does not exist, and the RFP forbids the runtime dependency
   anyway. The cost is that somebody must refresh the snapshots; the UI reports their age so
   a stale list cannot masquerade as a clean result.
3. **A screen against an empty list is reported as "nothing loaded", not "clear".** Those are
   very different facts.

**Bugs caught by tests:** a `date` inside a JSON column would have 500'd every screening with
a hit; **sanctions aliases were not searchable**, so an entry listed under a formal name with
the trading name as an alias would never have been scored — a screening system silently
missing the case it exists for.

**Tests** — 30 in `test_saml.py`, 78 in `test_integrations.py`. Suite total: **771 passing**
(4 pre-existing failures unchanged).

### Phase 8 — Security, compliance and governance 🟢 14 of 15 items (29 Aug 2026)

| Item | State |
|---|---|
| 1. FIDO2 / WebAuthn | ✅ `app/webauthn_service.py` + `/passkeys/*`, `passkeys-card.tsx` in Settings → Security. Verification delegated to `py_webauthn`; this code owns challenge lifecycle (single-use, 5-minute TTL), the **sign-counter clone check**, and the refusal to delete an account's last remaining factor. Tests drive a real software authenticator — a genuine ES256 key, real CBOR attestation, real signature — because a stub proves only that a function was called |
| 2. Separation of duties | ✅ `app/access_control.py` `SEGREGATED` — enforced in the **service layer**, because hiding a button is not a control. Refusals audited as `sod.blocked`, overrides as `sod.overridden` with a required reason |
| 3. Step-up authentication | ✅ Challenges bound to the **action and the object**, single-use, 5-minute TTL. A session-scoped "recently authenticated" flag would turn one re-auth into a window over everything |
| 4. Need-to-know access | ✅ `ContractAccess` on agreements marked confidential; refused reads audited; break-glass grants an hour and writes its own event |
| 5. Watermarking + download control | ✅ `data_protection.stamp_watermark` — names the viewer and the time, repeated up the page so a crop cannot remove the attribution |
| 6. Data masking | ✅ Applied to the **response**, not the template: a template-level mask leaves the API returning the real value to anyone calling it directly |
| 7. Antivirus on upload | ✅ ClamAV over INSTREAM. **Fails closed** — the only integration here that does, because an AV that waves files through when the daemon is unreachable protects nothing at the moment it matters |
| 8. CAPTCHA / anti-automation | 🟡 Proof-of-work after repeated failures + per-identifier backoff. **CAPTCHA deliberately not implemented**: a visual puzzle excludes the branch customers the accessibility requirement says must be able to sign. It belongs at the WAF |
| 9. TDE | ✅ `docs/30-tde.md` — per-engine commands, and an honest note that the app **cannot verify filesystem encryption from inside the connection**, so `TDE_ATTESTED` is named as an operator attestation rather than a measurement |
| 10. Legal hold | ✅ `models.LegalHold` matter-scoped. Releasing one matter does **not** expose an agreement a second matter still covers — the bug a boolean could not avoid, and the failure (evidence destroyed by a retention sweep) is unrecoverable |
| 11. Audit-log partitioning | ✅ `infra/scripts/partition-audit-log.sql` — monthly RANGE partitioning, deliberately **an operator script rather than an Alembic migration**: converting a populated table holds an ACCESS EXCLUSIVE lock for minutes to hours, and a migration that takes the system down on deploy is worse than no migration. Refuses below 1M rows, verifies the copy, keeps the old table as the rollback, re-applies RLS |
| 12. Temporary access | ✅ Scoped, expiring, revocable; token hashed so a leaked link is not replayable from the database. `temporary-access` wired |
| 13. Custom roles | ✅ A custom role names a built-in as its **base**; an unknown role degrades to `viewer` rather than to no access, which would lock an administrator out. Revokes always win. `roles` wired |
| 14. Compliance evidence pack | ✅ `docs/COMPLIANCE-EVIDENCE.md` — SBP ETGRMF, SBP ORMF, ISO 27001:2022 Annex A, SOC 2 TSC, each control pointing at the code, plus a §5 that lists what is genuinely absent |
| 15. OWASP mapping | ✅ `docs/31-owasp.md` — Top 10 and ASVS L2 mapped with code references. **DAST now runs in CI**: a ZAP baseline scan against a live migrated instance, in the `gate` job's dependencies. The tuning file `.zap/rules.tsv` lists every non-failing rule with its reason, so an untriaged finding turns the build red rather than scrolling past. The doc states the limits plainly — the scan is passive and unauthenticated, so it does not reach the authorisation logic, and it is not a substitute for a third-party penetration test |

**Bugs caught by tests:** the temporary-access expiry sweep re-expired the same links on every
run (autoflush is off, so the status change was invisible to the next query) — a beat that
would have reported the same rows forever.

**The serious one — the audit chain broke whenever one request recorded two entries.** Writing
the WebAuthn tests surfaced an audit row that was not visible to the query that followed it.
Chasing that produced a two-line reproduction: `audit.record()` reads the previous row from the
database to compute the chain link, the session runs with `autoflush=False`, so a second
`record()` in the same transaction could not see the first. Both rows claimed sequence 1 and
both chained to the genesis hash — and `verify_chain` then reported **tampering on a log nobody
had touched**.

Recording two actions before a single commit is the ordinary case, not an edge one (a workflow
decision that also notifies, a grant followed by a break-glass, a refusal that audits its
reason). So the tamper-evidence mechanism that the whole compliance position rests on was
raising false positives across a large part of normal use. A tamper alarm that cries wolf is
worse than none, because the first real alert is dismissed with the rest. Fixed with a
`db.flush()` after the row is added, and pinned by a regression test that records two entries in
one transaction and verifies the chain.

**Two audit trails were being discarded on the paths where they matter most.** A refusal is not
a no-op: `access_control.satisfy` increments the step-up attempt counter before it decides, and
every refusal records why. Both were written and then thrown away, because the router converted
the exception to an HTTP error and nothing committed. That meant `STEP_UP_MAX_ATTEMPTS` was
never reached — the challenge could be brute-forced indefinitely — and refusals left no trace at
all. The router guards now persist that state before converting the error.

**Also:** the `test_access_control` fixture hashed 245 passwords per run. Hashed once at module
scope — 87s → 46s. Password hashing is deliberately slow; paying for it repeatedly buys nothing.

**Also caught:** installing `webauthn` let pip resolve `cryptography` from 43 to 50, and
`signxml` 4.0.3 fails to *import* against cryptography ≥ 46. SAML sign-in would have stopped
working the moment the SSO extras were installed in the wrong order, with no code change to
blame it on. `cryptography==43.0.1` is now pinned in `requirements-sso.txt` as well as
`requirements.txt`, with the reason written next to it.

**Remaining in this phase:** item 8 only — CAPTCHA, deliberately left at the WAF. A visual
puzzle excludes exactly the branch customers the accessibility requirement says must be able to
sign, so the in-app control is proof-of-work plus per-identifier backoff and the bot problem is
solved at the edge where it belongs.

**Tests** — 49 in `test_access_control.py`, 28 in `test_data_protection.py`, 17 in
`test_webauthn.py`, 1 audit-chain regression. Suite total: **866 passing** (4 pre-existing
failures unchanged).

### Phase 9 — Adoption, accessibility, localization, training 🟢 8 of 8 items (29 Aug 2026)

| Item | State |
|---|---|
| 1. Contextual help | ✅ `app/content_service.py` + `help_topics`, 26 shipped topics, `components/help.tsx`. **In the database, not the bundle** — the requirement is that Legal can fix wording without a deploy, and the seed is gap-fill only so a release never reverts an edit. `HelpTip` opens on focus as well as hover, because hover-only help is help a keyboard user does not have |
| 2. Knowledge base | ✅ `/knowledge` — quick starts, playbooks, FAQs, six real guides seeded. Video is served from this deployment's own storage; embedding YouTube would be less work and would tell a third party who read which internal playbook, and when. Article bodies render to React elements, not `dangerouslySetInnerHTML` — an editor account is exactly what an attacker would want for stored XSS |
| 3. Training hub | ✅ `/training` — courses, module progress, quiz, certificate PDF, webinar and onsite calendar, attendance. Three decisions that make it evidence rather than a checkbox: **the answer key never leaves the server** (`quiz_for` strips it); **certificates expire**, computed from the date rather than stored as a status that needs a sweep to stay true; **attendance is recorded separately from registration**, because "have fifteen resources been trained" is a question about who turned up |
| 4. Guided actions | ✅ `app/guidance.py` — next-best-action per agreement and across the workspace, plus the Intake → Drafting → Review → Approval → Signature → Active tracker. Derived on every read, never stored: a stale "send for signature" on something already sent is how a helper panel loses its audience. Each suggestion carries the permission it needs, so one the reader cannot act on is shown as information rather than as an offer that always refuses |
| 5. Accessibility (WCAG 2.1 AA) | ✅ `docs/32-accessibility.md`, `/accessibility` statement, axe-core in CI at desktop **and phone** viewports. Substantially conformant with four exceptions, each named with its impact and what closes it |
| 6. Localization | ✅ `lib/i18n.tsx` — English and Urdu, RTL, locale-aware dates/numbers/PKR. The interface is translated; the **legal wording is not machine-translated** — help, articles and courses are per-locale rows edited in the product, because "terminology aligned to MMBL's internal policy language" is something only MMBL's legal team can supply. Untranslated topics fall back per topic and say so, rather than falling back wholesale and throwing away work already done |
| 7. Non-digitally-literate path | ✅ Assisted mode on the signing portal (`?assisted=1` so a branch tablet can be bookmarked into it): larger text, 44px+ targets, one step at a time, and a printable step-by-step guide in English and Urdu. **Nothing is skipped or pre-agreed** — the "next" button on the reading step is disabled until the document has actually been opened. A simplified signing that quietly agrees on somebody's behalf is not simplification, it is a defect in the consent record |
| 8. Mobile | ✅ Signing and approve/reject rebuilt for a phone, not merely reflowed: decision buttons stack full-width below `sm` rather than wrapping to half-width adjacent pairs, which is how somebody taps Reject meaning Approve. Scanned at a Pixel viewport in CI |

**The two accessibility defects the scan found, neither visible by eye:**

**Every primary button in the product failed contrast.** The brand accent `#3e7bfa` measures
3.88:1 against the white text on it, against the 4.5:1 small text needs. Darkening the default
would have fixed the default and nothing else — the accent is a tenant setting, so the next
organisation to choose a cheerful brand colour breaks it again and nobody notices until an audit.
`lib/contrast.ts` now derives the button background from whatever colour is configured: left
exactly as chosen when it passes, darkened only as far as it must when it does not, with the
original kept for borders and icons where 3:1 applies. Secondary text was also below the line at
3.30:1 and is now 4.81:1 at worst.

**Every form field in the product was unlabelled.** The shared `Field` primitive rendered a bare
`<label>` with no `htmlFor` — visually identical, and a screen reader announces "edit text,
blank". axe rated it *critical*. Fixed in that one component rather than at several hundred call
sites, and `Field` now also wires hints and validation messages with `aria-describedby` and
`aria-invalid`, which closed a second open item in the same change.

**Also caught by tests:** SQLAlchemy does not see an in-place mutation of a JSON column, so
`completed_modules.add(...)` would have been dropped at commit with no error anywhere — module
progress would have silently never advanced.

**Not done, and stated rather than implied:** knowledge-base videos ship without captions (the
written guide is a mitigation, not conformance); the audit and analytics tables still scroll
sideways below 320px; the Tiptap editor's own accessibility is the ceiling on that surface. The
axe job covers the signed-out and error-state surfaces — the authenticated application is covered
by manual testing until the Playwright suite grows a logged-in fixture in Phase 10.

**Open, and outside this phase to fix:** `npm audit` reports high-severity advisories against
Next.js 14.2.35. There is no patched 14.x — 14.2.35 is the last of the line, and the only
remediation is a major upgrade to Next 16. That is a Phase 10 item with its own regression
testing, not something to do inside an adoption phase.

**Tests** — 47 in `test_adoption.py`, 12 Playwright accessibility checks across two viewports.
Suite total: **913 passing** (4 pre-existing failures unchanged).

### Phase 10 — QA, operations and the RFP submission artefacts 🟡 IN PROGRESS (30 Aug 2026)

**Engineering**

| Item | State |
|---|---|
| Coverage ≥80% on service modules | 🟡 Engines done — `signing_service` 28% → **98%**, `auth_service`, `renewal_service` and `webhook_service` all cleared 80%. Infrastructure adapters (storage 53%, `pki/validate` 47%, `ocr_provider` 55%) still below. Named honestly in `docs/35-quality-assurance.md` §11 rather than averaged away |
| E2E tests for the two RFI journeys | ✅ `test_journeys_e2e.py` — both journeys walked over real HTTP, nothing called directly. Each test names the requirement IDs it proves, so the UAT book generates from them |
| UAT scripts | ✅ Structure and worked example in `docs/35-quality-assurance.md` §5; keyed to the same IDs as the Scope document and the acceptance criteria |
| Load and soak testing | 📅 M5 — targets stated as targets, not results |
| DR drill | 📅 M5 — runbook exists (`docs/29`), the evidenced restore does not yet |
| Worker-side Prometheus exporter | ✅ `app/worker_metrics.py` — per-task success/failure/retry/duration/queue-latency plus sweep counts, via Celery signals so it covers tasks added later |
| CD pipeline to Dev/UAT/Prod | 📅 Environments and gates defined in `docs/38-implementation-plan.md`; the pipeline itself outstanding |

**Documents (Annexure)**

| # | Item | State |
|---|---|---|
| 1 | Bill of Quantities & Technical Specs | ✅ Scope & Technical Specification — clause-ordered to §4a–§4d, ~90 requirement IDs |
| 2 | Compliance Matrix | ✅ `docs/41-compliance-matrix.md` |
| 3 | Service Level Agreement | ✅ `docs/37-sla.md` |
| 4 | Project Implementation Plan | ✅ `docs/38-implementation-plan.md` |
| 5 | Licensing details | ✅ `docs/39-licensing.md` |
| 6 | HLD / LLD | ✅ Scope §2 + `docs/14`, `15`, `16` |
| 7 | **Risk Mitigation Strategy (11%)** | ✅ `docs/34-risk-mitigation.md` — 17 risks, owners, triggers, residuals |
| 8 | Audit Trail Mechanism | ✅ `docs/40-audit-trail-mechanism.md` |
| 9 | **Training Plan (8%)** | ✅ `docs/36-training-plan.md` |
| 10 | **Quality Assurance Plan (11%)** | ✅ `docs/35-quality-assurance.md` |
| 11 | Sworn undertaking + SBOM | 🟡 SBOM per build ✅; **the undertaking is unresolved — R-08** |
| 12 | Hosting & data residency | ✅ Phase 0 |
| 13 | PKI architecture | ✅ `docs/PKI-ARCHITECTURE.md` + `docs/PKI-Architecture.docx` |
| 14 | Third-party VAPT report | 📅 M5 |

**The four pre-existing test failures are gone, and three of them were product weaknesses rather
than test bugs.** They had been carried since the beginning and written off as test-expectation
problems. Looking at them properly in the QA phase found:

- **`Password123!` passed the blocklist.** The check was exact-match on the lowercased password,
  so appending one symbol defeated it entirely — which is precisely what a complexity rule makes
  people do. Trailing punctuation and digits are now stripped before the check.
- **`MarkSpencer1!` passed the name rule.** It matched the name verbatim, space included, so the
  most obvious construction — first and last concatenated — walked through. Now checks the name
  without spaces and each part of four characters or more.
- **Signing tokens were stored as plaintext in dev and test.** The encrypted-column type falls
  back to tagged plaintext with no key configured, and the test asserting "no plaintext is
  persisted" had been red for months for that reason. CI now supplies a real Fernet key, so the
  encryption path is the one exercised.

The fourth was a genuine test bug: it asserted `expired` is terminal, but `expired → renewed` is
correct and deliberate — a lapsed agreement noticed in December and renewed in January keeps its
`renewed_from_id` chain instead of becoming an unrelated new record.

**Two more defects found while writing the Phase 10 tests:**

- **Signing invitations were committed on their own connection.** `send_envelope` called
  `send_email` without threading the session, so the outbox row committed independently of the
  request. A recipient could receive a working link to an envelope whose transaction later rolled
  back. On SQLite the same omission deadlocks outright, which is how it surfaced. `visitor_service`
  had got this right and said why; `signing_service` had not.
- **Refresh-token reuse was invisible.** The chain was revoked and a 401 returned, and nothing
  reached the audit log or the SIEM — a failed password attempt was recorded and an actual stolen
  session was not. Now `auth.session.reuse_detected`, escalated at ALERT.
- **`worker_metrics.install()` claimed to be idempotent and was not.** `connect(weak=False)`
  registers a new closure per call, so a second install doubled every number. Caught because the
  test fixture called it per test and inflated the counters tenfold. A metric that is quietly 2×
  is worse than none — somebody makes a capacity decision with it.

**Also corrected:** the worker pod advertised `prometheus.io/port: "9540"` with nothing listening
on it. It looked monitored and was not.

**Tests** — 50 in `test_signing_engine.py`, 36 in `test_auth_service.py`, 40 in
`test_renewals_and_webhooks.py`, 43 in `test_infrastructure_adapters.py`, 14 in
`test_worker_metrics.py`, 5 journey tests. Suite total: **1,108 passing, 0 failing** (previously
866 passing with 4 known failures). Ruff clean across `app`, `tests` and `migrations`.





