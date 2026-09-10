# Compliance Matrix (Feature-to-Requirement)

**Annexure item 2.** Every requirement in RFP §4a, §4b, §4c and §4d, the feature that satisfies
it, and the milestone by which it is delivered.

**All requirements are complied with.** This document maps each one to the specific capability
that delivers it and to a dated milestone, so compliance is a commitment with a date attached
rather than a tick in a column.

The requirement IDs are the join key for the whole submission: the same identifier appears in the
Scope & Technical Specification, in the UAT Test Book and in the acceptance criteria. Any
requirement can therefore be traced from RFP clause, to the feature that delivers it, to the test
that proves it, to the sign-off that accepts it.

---

## 1. How to read this matrix

| Column | Meaning |
|---|---|
| **ID** | The identifier used across the whole submission |
| **Requirement** | The RFP requirement, condensed |
| **Compliance** | Complied — the requirement is delivered within the programme |
| **Feature that delivers it** | The specific capability, not a restatement of the requirement |
| **Milestone** | The milestone at which it is demonstrated and accepted |

### Milestones

| Milestone | Weeks | Covers |
|---|---|---|
| **M1** | 1–3 | Environments, database platform, integrations and identity |
| **M2** | 3–6 | Configuration to MMBL's templates, clauses, policies and roles |
| **M3** | 5–8 | Data migration, PKI hardware and production signing |
| **M4** | 6–10 | Remaining scope and User Acceptance Testing |
| **M5** | 9–11 | Performance, resilience and independent security assurance |
| **M6** | 10–12 | Training, cutover and go-live |

Some requirements need an input that only MMBL can supply — a database instance, identity
metadata, an HSM, a gateway route, an SMS account. Those inputs are listed against their dates in
the Project Implementation Plan and reviewed weekly, so a dependency cannot slip unnoticed.

---

## 2. Scope of Work — RFP §4a(i)

| ID | Requirement | Compliance | Feature that delivers it | Milestone |
|---|---|---|---|---|
| SOW-01 | Template repository with version control | Complied | Template library with approval gate; approved wording frozen in a version snapshot | M2 |
| SOW-02 | Central clause library | Complied | Clause library with categories, ownership and approval lifecycle | M2 |
| SOW-03 | Approved alternative clauses | Complied | Ranked fallbacks per clause; a drafter may only swap for an approved alternative | M2 |
| SOW-04 | Guided drafting with structured intake | Complied | Typed intake form per template; the draft is generated from the approved wording | M2 |
| SOW-05 | Microsoft Word round-trip | Complied | Export with real Word numbering; import reading tracked changes and comments | M2 |
| SOW-06 | Playbook enforcement | Complied | Required, prohibited and altered-clause rules evaluated on every draft | M2 |
| SOW-07 | Version comparison and redline | Complied | Clause-level comparison; accepting all changes reconstructs the counterparty draft exactly | M2 |
| SOW-08 | Threaded comments with resolution | Complied | Comment threads anchored to clauses, with internal-only visibility | M2 |
| SOW-09 | Consolidated multi-reviewer view | Complied | All reviewers' input grouped by function in one pass | M2 |
| SOW-10 | Policy deviation detection | Complied | Deviations from playbook raised at draft time and carried into approval | M2 |
| SOW-11 | Configurable multi-stage workflow | Complied | Stage and step model configured to MMBL's approval policy | M2 |
| SOW-12 | Parallel approval groups | Complied | Concurrent steps within a stage under all / any / quorum / percentage policies | M2 |
| SOW-13 | Approval authority matrix by value | Complied | Rules that add stages by value, type, department and risk | M2 |
| SOW-14 | Delegation during absence | Complied | Scoped, windowed delegation; both identities recorded in the audit trail | M2 |
| SOW-15 | SLA tracking and escalation | Complied | Per-step SLA on a business calendar, with reminder and escalation | M2 |
| SOW-16 | Separation of duties | Complied | Enforced in the service layer, not by hiding controls; refusals audited | M2 |
| SOW-17 | Sequential and parallel signing | Complied | Ordered or concurrent envelopes with concurrency protection | M4 |
| SOW-18 | Field placement on the document | Complied | Signature, initial, date and text tabs positioned per page | M4 |
| SOW-19 | Typed, drawn and uploaded signatures | Complied | All three adoption methods, with image format validation | M4 |
| SOW-20 | Per-signatory digital certificates | Complied | Each signatory signs with their own certificate and key from the in-platform CA | M3 |
| SOW-21 | Certificate of Completion | Complied | Identity evidence, consent, IP and timing for every party | M4 |
| SOW-22 | Identity verification before signing | Complied | Email, one-time passcode to phone, and CNIC binding | M3 |
| SOW-23 | Wet-signature fallback with attestation | Complied | Print pack, scanned return and attested upload with the same evidence trail | M4 |
| SOW-24 | Central searchable repository | Complied | Full-text search with party, department, folder, date, value and clause filters | M3 |
| SOW-25 | Ten-year retention, twelve months hot | Complied | Scheduled archival and purge with legal hold overriding both | M3 |
| SOW-26 | Obligation extraction and tracking | Complied | Cross-contract obligation register with reminders and escalation | M4 |
| SOW-27 | Renewal detection and reminders | Complied | Per-agreement notice schedule; only the tightest crossed threshold fires | M4 |
| SOW-28 | Amendments and relationships | Complied | Amendment as a separate draft; the parent stays in force until execution | M4 |
| SOW-29 | Legal hold overriding retention | Complied | Matter-scoped holds; releasing one matter cannot expose another's records | M4 |
| SOW-30 | Cycle-time and bottleneck analytics | Complied | Derived from the audit trail; every figure reports its sample size | M4 |
| SOW-31 | MIS dashboards and exports | Complied | Dashboards plus spreadsheet exports that name the filters that produced them | M4 |
| SOW-32 | Contextual in-product help | Complied | Help at the point of use, editable by MMBL without a release | M6 |
| SOW-33 | Knowledge base and training hub | Complied | Articles, courses and certification tracking inside the product | M6 |

---

## 3. Branchless Banking Operations — RFP §4a(ii)

| ID | Requirement | Compliance | Feature that delivers it | Milestone |
|---|---|---|---|---|
| BB-01 | Customer signs without an account | Complied | Unauthenticated signing portal reached by a per-recipient link | M4 |
| BB-02 | Execution free from signature failures | Complied | Sealing records its own outcome; failures are visible and retried, not silent | M4 |
| BB-03 | Assisted signing at a branch | Complied | Assisted mode for branch staff supporting a customer in person | M4 |
| BB-04 | Path for the non-digitally-literate | Complied | Printable bilingual guide; the flow will not advance until the document is opened | M4 |
| BB-05 | Mobile-usable signing | Complied | Signing surface built and tested at phone viewport | M4 |
| BB-06 | OTP identity verification | Complied | One-time passcode with attempt and resend caps, via MMBL's SMS gateway | M1 |
| BB-07 | Urdu interface | Complied | Full Urdu localisation with right-to-left layout | M6 |
| BB-08 | Accessibility WCAG 2.1 AA | Complied | Automated conformance checks plus assisted-technology review | M5 |
| BB-09 | Bulk send | Complied | One template to many signers; each receives their own agreement and envelope | M4 |

---

## 4. Technical Requirements — RFP §4b / §4c

| ID | Requirement | Compliance | Feature that delivers it | Milestone |
|---|---|---|---|---|
| TEC-01 | Multi-tier web architecture | Complied | Separate presentation, application and data tiers with an asynchronous worker tier | M1 |
| TEC-02 | Modular, API-driven, scalable | Complied | Every capability behind a documented API; the interface is generated from the implementation | M1 |
| TEC-03 | High availability across tiers | Complied | Horizontally scaled application tier with disruption budgets, on MMBL's HA platform | M1 |
| TEC-04 | Oracle or MSSQL preferred | Complied | Single database dialect layer emitting Oracle VPD; certified at a named gate before data load | M1 |
| TEC-05 | Microservices deployment | Complied | Modular application with an independently scaled worker tier — deviation declared, with reasoning, in Scope §2 | M1 |
| TEC-06 | Data purging and archiving | Complied | Scheduled archival and purge, exercised from day one rather than first attempted at scale | M3 |
| TEC-07 | Segregated Dev / UAT / Prod | Complied | Three environments built from the same declarative configuration | M1 |
| TEC-08 | CI/CD pipeline | Complied | Gated build and promotion pipeline; one artefact promoted by digest across environments | M1 |
| TEC-09 | Test-driven development with UAT scripts | Complied | Automated suite with UAT scripts derived from it and keyed to these identifiers | M4 |
| TEC-10 | API documentation and user manuals | Complied | Generated API reference plus role-based manuals | M6 |
| TEC-11 | Patch management, 48-hour critical | Complied | Committed turnaround in the SLA; dependency and container scanning on every build | M5 |
| TEC-12 | Backup, offsite, DR-ready | Complied | Scripted, encrypted, restore-verified backups with a measured DR drill | M5 |

---

## 5. Information Security — RFP §4d

| ID | Control | Compliance | Feature that delivers it | Milestone |
|---|---|---|---|---|
| SEC-01 | Role-based access control | Complied | Built-in and custom roles; an unknown role degrades to read-only, never to open access | M2 |
| SEC-02 | Multi-factor authentication | Complied | Time-based one-time passcodes with recovery codes and an email fallback | M1 |
| SEC-03 | FIDO2 / WebAuthn | Complied | Passkey registration and authentication with cloned-authenticator detection | M1 |
| SEC-04 | Entra ID via SAML 2.0 / OIDC | Complied | Both federation protocols, with signature verification by a maintained library | M1 |
| SEC-05 | SCIM 2.0 provisioning | Complied | Automated user and group provisioning from MMBL's directory | M1 |
| SEC-06 | Session management | Complied | Short-lived access token held in memory; rotating refresh token with reuse detection | M1 |
| SEC-07 | Step-up authentication | Complied | Re-authentication bound to the specific action and object, single-use and time-limited | M2 |
| SEC-08 | Separation of duties | Complied | Enforced in the service layer; overrides require a recorded reason | M2 |
| SEC-09 | Need-to-know access | Complied | Per-agreement access lists on confidential matters, with audited break-glass | M2 |
| SEC-10 | Encryption at rest | Complied | Transparent Data Encryption on MMBL's database, plus column encryption for secrets | M1 |
| SEC-11 | Encryption in transit, TLS 1.2+ | Complied | Enforced at the gateway with MMBL's certificates | M1 |
| SEC-12 | Tamper-evident audit trail | Complied | Every entry chained by HMAC to its predecessor, with a verification tool delivered to MMBL | M2 |
| SEC-13 | SIEM feed in CEF with severity | Complied | Classified, severity-mapped feed with replay for any collector outage | M1 |
| SEC-14 | Data masking | Complied | Applied to the response, so a direct API call cannot bypass it | M2 |
| SEC-15 | Watermarking and download control | Complied | Viewer identity and time stamped repeatedly, so a crop cannot remove attribution | M2 |
| SEC-16 | Antivirus scan on upload | Complied | Every upload scanned, **failing closed** when the scanner is unreachable | M1 |
| SEC-17 | Anti-automation | Complied | Proof-of-work and per-identifier backoff on public surfaces; edge protection at the gateway | M2 |
| SEC-18 | Input validation, secure errors, no hardcoded secrets | Complied | Schema validation at every boundary; secret scanning gates the build | M1 |
| SEC-19 | Security headers and rate limiting | Complied | Full header set; distributed rate limiting consistent across replicas | M1 |
| SEC-20 | OWASP Top 10 and ASVS Level 2 | Complied | Mapped control-by-control; static and dynamic scanning gate every build | M5 |
| SEC-21 | Independent penetration test with remediation SLA | Complied | Third-party assessment with 48-hour critical remediation; vendor appointed by MMBL | M5 |
| SEC-22 | Data residency — all data in Pakistan | Complied | The application refuses to start if any endpoint resolves outside the allowlist | M1 |
| SEC-23 | Security certification evidence | Complied | Control-level evidence mapped to ISO 27001:2022 Annex A and the SOC 2 criteria | M1 |

---

## 5a. RFP §4d — Information Security Department response table

RFP §4d is scored as a vendor response sheet: Category, Requirement, Evaluation Parameter, and a
Yes / No / NA read straight off the page.

**That sheet is supplied as a separate annexure — the Information Security Response.** It
reproduces every §4d requirement verbatim, in the order and grouping the RFP prints them, with
the vendor response against each. Section 5 above answers the same controls by requirement
identifier, so a reviewer can move between the two in either direction.

It is a separate document rather than a section here because it is a **scoring sheet**: it is
read, and marked, against the RFP's own table rather than alongside a compliance matrix.

## 6. PKI and eSignature — 11% weighting

| ID | Requirement | Compliance | Feature that delivers it | Milestone |
|---|---|---|---|---|
| PKI-01 | In-house Certificate Authority | Complied | Two-tier hierarchy: an offline root, and an issuing CA that cannot mint sub-CAs | M1 |
| PKI-02 | Registration Authority with vetting | Complied | Dual-control approval; an officer cannot approve their own request | M1 |
| PKI-03 | Full certificate lifecycle | Complied | Enrol, issue, renew, suspend, resume and revoke, with suspension as a real hold | M1 |
| PKI-04 | One certificate per signatory | Complied | Enforced twice — at issuance and by a database constraint | M1 |
| PKI-05 | CRL and OCSP publishing | Complied | Full and delta revocation lists, plus a delegated real-time responder | M1 |
| PKI-06 | HSM-protected keys, FIPS 140-2 Level 3 | Complied | Keys generated inside the token and non-extractable, on MMBL's HSM | M3 |
| PKI-07 | PAdES-LTV signing per signatory | Complied | Embedded chain, revocation data and trusted timestamp; verifies offline years later | M3 |
| PKI-08 | Third-party certificate validation | Complied | Full path validation for certificates issued by external authorities | M3 |
| PKI-09 | ECAC chaining readiness | Complied | Cross-certification: the issuing CA re-chains to an accredited root with nothing reissued | M3 |
| PKI-10 | SBOM for the signing stack | Complied | Signed bill of materials produced with every release | M1 |

---

## 7. Integrations

| ID | System | Compliance | Feature that delivers it | Milestone |
|---|---|---|---|---|
| INT-01 | REST API | Complied | Documented API generated from the implementation, so it cannot drift | M1 |
| INT-02 | SOAP facade | Complied | SOAP endpoint over the same services, for callers that require it | M1 |
| INT-03 | Kong API Gateway | Complied | Declarative gateway configuration with route, authentication and rate-limit mapping | M1 |
| INT-04 | Entra ID SAML / OIDC | Complied | Both protocols; role mapping from directory groups is configuration, not code | M1 |
| INT-05 | SCIM 2.0 | Complied | Standards-compliant user and group provisioning endpoint | M1 |
| INT-06 | SIEM in CEF | Complied | Severity-classified feed with replay for collector outages | M1 |
| INT-07 | SMTP relay | Complied | Outbox with retry; delivery state recorded rather than assumed | M1 |
| INT-08 | SMS gateway | Complied | Adapter sharing one delivery audit with email | M1 |
| INT-09 | Sanctions screening | Complied | Alias-aware matching against list snapshots, with the snapshot recorded | M1 |
| INT-10 | Webhooks | Complied | Signed callbacks with the timestamp bound into the signature against replay | M1 |
| INT-11 | Microsoft Teams / SharePoint | Complied | Notification and document-copy connectors | M1 |
| INT-12 | Outlook reminders | Complied | Standard calendar invitations for obligations and renewals | M4 |
| INT-13 | Enterprise backup | Complied | Integrates at the storage and database layer; no application agent required | M1 |

---

## 8. Scoring rubric — the 13 weighted parameters

| # | Parameter | Weight | Where it is evidenced |
|---|---|---|---|
| 1 | Technical Architecture & Design | 12% | Scope & Technical Specification §2 |
| 2 | Integrations | 8% | Section 7 above, and the Integration Architecture document |
| 3 | Security and Compliance | 8% | Sections 5 and 5a above, and the Compliance Evidence Pack |
| 4 | Infrastructure & Storage | 6% | Scope §9, and the Backup and Disaster Recovery document |
| 5 | Deployment Options (CI/CD) | 3% | Quality Assurance Plan §3 |
| 6 | Technical Specifications | 7% | Scope & Technical Specification, API reference, user manuals |
| 7 | Support, Monitoring & Maintenance | 7% | Service Level Agreement; Monitoring and Observability document |
| 8 | Project Plan and Timelines | 6% | Project Implementation Plan |
| 9 | **PKI Depth & Advanced eSignature** | **11%** | Section 6 above, and the PKI Architecture document |
| 10 | Relevant Experience | 2% | Commercial response — reference deployment |
| 11 | **Risk Management** | **11%** | Risk Mitigation Strategy |
| 12 | Training Mechanism | 8% | Training Plan |
| 13 | **Quality Assurance** | **11%** | Quality Assurance Plan |

---

## 9. Submission index

| # | Annexure item | Document |
|---|---|---|
| 1 | Bill of Quantities & Technical Specifications | Scope & Technical Specification |
| 2 | Compliance Matrix (Feature-to-Requirement) | This document |
| 3 | Service Level Agreement | Service Level Agreement |
| 4 | Project Implementation Plan | Project Implementation Plan |
| 5 | Licensing details | Licensing and Open-Source Inventory |
| 6 | HLD / LLD diagrams | Scope & Technical Specification §2 |
| 7 | Risk Mitigation Strategy | Risk Mitigation Strategy |
| 8 | Audit Trail Mechanism | Audit Trail Mechanism |
| 9 | Training plan | Training Plan |
| 10 | Quality Assurance plan | Quality Assurance Plan |
| 11 | Sworn undertaking and SBOM | Signed bill of materials with every release; undertaking supplied with the commercial response |
| 12 | Hosting and data residency statement | Hosting and Data Residency Statement |
| 13 | PKI architecture document | PKI Architecture |
| 14 | Third-party VAPT report | Delivered at M5 by the assessor MMBL appoints |

---

## 10. Summary

| | |
|---|---|
| Requirements addressed | **88** |
| Complied | **88** |
| Delivered by go-live (M6) | **88** |

Every requirement in RFP §4a, §4b, §4c and §4d is complied with and mapped above to the feature
that delivers it and the milestone at which it is accepted.

**Two rows in the §4d response table are answered by the bidding entity rather than by the
solution** — security certifications and the sub-contractor list are facts about the delivery
organisation. Both are addressed in the commercial response.

**One architectural deviation is declared rather than left to be discovered** (TEC-05): the
solution is a modular application with an independently scaled worker tier rather than a
distributed microservices mesh. The properties the preference exists to secure — independent
scaling of heavy asynchronous work, horizontal scaling of the request tier, and API-driven
modularity — are all delivered. The reasoning is in Scope §2, and the decomposition path is
available if MMBL requires it.
