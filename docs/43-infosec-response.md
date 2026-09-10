# Information Security Response — RFP §4d

RFP §4d is scored as a **vendor response sheet**: Category, Requirement, Evaluation Parameter,
and a Yes / No / NA read straight off the page. This document answers it in exactly that shape.

Every §4d requirement is reproduced **verbatim**, in the order and grouping the RFP prints them,
so the sheet can be read directly against the bank's own table. The Compliance Matrix answers
the same controls by requirement identifier, for a reviewer working the other way round.

Requirement wording below is reproduced verbatim from the RFP. The category is shown once per
group, as it is printed.

| Category | Requirement | Evaluation Parameter | Vendor Response (Yes/No/NA) |
|---|---|---|---|
| Compliance and Regulatory Requirements | Confirm alignment with the State Bank of Pakistan (SBP) guidelines, including the Enterprise Technology Governance and Risk Management Framework and the Outsourcing Risk Management Framework. | Statement of compliance | **Yes** — control-by-control mapping against both frameworks supplied with this submission, and re-walked with MMBL's compliance function in the first two weeks of the engagement. |
| | Provide third-party vulnerability assessment reports for the product, if applicable and available. | Submission of vulnerability assessment reports | **Yes** — an independent assessment is commissioned at M5 by a vendor MMBL appoints, with the report supplied before go-live. Output from continuous automated assurance (static analysis, dynamic scanning, dependency audit, container and secret scanning) is available on request from award. |
| | Submit evidence of compliance with relevant security certifications such as ISO 27001, PCI DSS, SOC 2 Type II, etc. | Certification documentation | *To be completed by the bidding entity.* Certifications are held by an organisation, not by a product. Control-level evidence mapped to ISO 27001:2022 Annex A and the SOC 2 Trust Services Criteria is supplied regardless, so the solution can be absorbed into MMBL's certified control environment without a gap. |
| | Confirm the ability to support SBP-related inquiries and provide compliance reports throughout the project lifecycle. | Confirmation of regulatory support | **Yes** — tamper-evident audit trail with an independent verification tool delivered to MMBL, the control evidence pack, and reporting commitments in the Service Level Agreement. |
| | Provide a comprehensive list of subcontractors involved in the solution delivery, confirming their adherence to SBP and organizational security standards. | Subcontractor compliance report | *To be completed by the bidding entity.* The software supply chain is answered in full: a signed bill of materials accompanies every release and every third-party component is inventoried with its licence. |
| System and Network Security Requirements | Guarantee the timely provision of security patches and updates throughout the lifecycle of the proposed solution. | Patch and update policy documentation | **Yes** — 48 hours for critical, committed in the Service Level Agreement. Dependency and container scanning on every build surfaces a new advisory without waiting for a scheduled review. |
| | Ensure compatibility with micro-segmented network architectures, including support for network and host-based firewalls. | Network architecture compatibility | **Yes** — every component declares its required ports and destinations, and default-deny network policy is supplied with the deployment manifests. Each tier is separately addressable, so application, worker, database and storage can sit in distinct segments. |
| | Confirm the resilience of the solution against rigorous vulnerability assessments and penetration tests using automated and manual methodologies. | Assessment and testing results | **Yes** — automated assessment gates every build; manual testing is performed by the independent assessor at M5 and after each major change, with results and remediation evidence shared. |
| | Specify the security frameworks and tools utilized for vulnerability assessments, penetration testing, and incident detection/prevention. | Comprehensive framework and tool details | **Yes** — OWASP Top 10 and ASVS Level 2 as the assessment frameworks; Bandit and Semgrep for static analysis, OWASP ZAP for dynamic scanning, Trivy for container and OS packages, pip-audit and npm audit for dependencies, Gitleaks for secrets, and a CycloneDX bill of materials per build. Detection and prevention are delivered into MMBL's own SIEM and gateway rather than duplicated. |
| | Acknowledge that MMBL may conduct external posture scanning (e.g., internet-facing infrastructure scans) of the vendor environment as part of due diligence and security monitoring activities. | Acknowledgment of external scanning rights and scope | **Yes** — acknowledged and accepted, with scope and windows agreed in writing. Note that the solution is deployed entirely on MMBL premises, so the internet-facing surface being scanned is the bank's own. |
| Data Protection and Privacy | Outline measures for safeguarding sensitive data, including encryption standards for data at rest and in transit (e.g., AES-256, TLS 1.2+). | Encryption protocols and methodologies | **Yes** — Oracle Transparent Data Encryption at the tablespace, with AES-256 column-level encryption additionally applied to secrets so a database export alone yields nothing usable. TLS 1.2 or higher enforced in transit, with the configuration checked at start-up rather than assumed. |
| | Confirm adherence to SBP's data segregation and protection requirements. | Data segregation and protection plan | **Yes** — segregation is enforced **by the database**, not only by application code: Oracle Virtual Private Database is applied to every workspace-scoped table, so a defect in application logic still cannot read across the boundary. Repository code filters independently as a second layer. |
| | Provide a robust plan for data retention and secure deletion in compliance with SBP and organizational requirements. | Data lifecycle management policy | **Yes** — retention tiers with scheduled archival and purge, exercised from day one rather than first attempted in year three. Legal hold overrides deletion unconditionally and is scoped per matter, so releasing one matter cannot expose records another still protects. |
| | Confirm willingness to execute a Non-Disclosure Agreement (NDA) to protect confidential information. | Signed NDA | **Yes** — willing to execute MMBL's standard NDA. |
| Access Control and Logging | Describe the access control mechanisms, including Role-Based Access Control (RBAC) and Multi-Factor Authentication (MFA). | Access control policies and features | **Yes** — role-based permissions with custom roles and per-agreement access lists on confidential matters. Multi-factor authentication by time-based one-time passcode, passkeys (FIDO2/WebAuthn) and email fallback, with step-up re-authentication bound to specific privileged actions. |
| | Ensure the solution generates well-structured logs adhering to internationally recognized formats such as Common Log Format (CLF) or Common Event Format (CEF). | Logging standard compliance | **Yes** — CEF over syslog, with CLF available for web-tier access logs. |
| | Logs must cover key events such as authentication, access control, application usage, system activities, security incidents, network events, and audit trails. | Coverage of log categories | **Yes** — all categories emitted and classified. The audit trail additionally covers every state-changing business action, chained so that alteration or deletion is detectable. |
| | Ensure logs include clearly defined severity levels, such as Emergency, Alert, Critical, Error, Warning, Notice, and Informational. | Log severity categorization | **Yes** — the full syslog severity range is used, and mapped deliberately: a refresh-token reuse, for example, is raised at Alert rather than being logged as an ordinary authentication failure. |
| Compatibility and Integration | Confirm compatibility with industry-standard solutions such as Identity and Access Management (IAM), Multi-Factor Authentication (MFA), Single Sign-On (SSO), Web Application Firewall (WAF), and Security Orchestration, Automation, and Response (SOAR) (if applicable). | Compatibility documentation | **Yes** — SAML 2.0 and OpenID Connect for single sign-on, SCIM 2.0 for provisioning, and standards-based interfaces throughout, so integration is by configuration rather than custom development. WAF and SOAR integrate at the gateway and the event feed respectively. |
| | Confirm support for integration with the organization's existing security solutions, including SIEM, DAM, PAM, Vulnerability Management, and other tools. | Integration plan and support details | **Yes** — SIEM by CEF feed with replay for collector outages; DAM at the database tier, which is transparent to the application; PAM by federated privileged accounts with step-up authentication; vulnerability management by the per-release bill of materials, which the bank's scanner can consume directly. |
| | Ensure compatibility with standard automated backup and restoration solutions. | Backup and restore compatibility | **Yes** — enterprise backup tooling integrates at the database and storage layers with no application agent required. Scripted, encrypted, restore-verified backups are supplied as an alternative or a complement. |
| Incident and Business Continuity Management | Provide an incident reporting plan detailing response timeline, escalation procedures, and reporting mechanisms. | Comprehensive incident response plan | **Yes** — severity definitions, response and resolution targets, escalation path and reporting cadence are set out in the Service Level Agreement, with automatic service credits attaching to a missed target. The process is exercised during UAT rather than first used in production. |
| | Summarize the Business Continuity Plan (BCP) and Disaster Recovery Plan (DRP) applicable to the proposed solution. | Documentation of BCP and DRP | **Yes** — recovery objectives agreed at design and proven by a measured drill before go-live sign-off. Backups are restore-verified, because a backup never restored is an assumption rather than a control. |
| | Confirm readiness to support audits and assessments by the organization or authorized third-party entities. | Audit support confirmation | **Yes** — and several controls can be demonstrated live on MMBL's own instance rather than accepted on paper, including audit-chain integrity, segregation of duties and data residency. |
| Communications Security | Ensure all official communication during the project lifecycle is conducted via authenticated mediums, such as emails configured with SPF, DKIM, and preferably DMARC. | Communication security policies | **Yes** — committed for the duration of the engagement. |
| | Confirm that the vendor's email systems have properly configured SPF and DKIM, with DMARC as an added measure. | Email authentication configuration | *To be confirmed by the bidding entity* against its own mail domain. Where a record is not yet at the required policy, it is corrected before project kick-off. |
| | Acknowledge the organization's right to reject any unauthenticated email communications. | Vendor acknowledgment | **Yes** — acknowledged. |
| Portal / Web Application Security | Confirm that the portal is designed and developed in accordance with secure-by-design and secure-by-default principles. | Secure design approach and documentation | **Yes** — controls fail closed by default. Two examples: the upload scanner refuses a file when the scanning service is unreachable rather than passing it, and the application refuses to start if any configured endpoint resolves outside the permitted network. |
| | Adherence to OWASP Top 10 (latest version) and OWASP ASVS (appropriate level) during portal development. | Secure coding standards and mapping | **Yes** — mapped control-by-control to the OWASP Top 10 and to ASVS Level 2, with static and dynamic scanning gating every build. |
| | Implementation of strong input validation, output encoding, and protection against common web vulnerabilities (e.g., SQL Injection, XSS, CSRF). | Application security controls description | **Yes** — schema validation at every API boundary; parameterised queries throughout, so string-built SQL does not exist; contextual output encoding; and same-site cookie policy with origin checks against cross-site request forgery. |
| | Secure session management, including session timeout, secure cookies, and protection against session fixation and hijacking. | Session management controls | **Yes** — short-lived access token held in memory only, never in browser storage where a script could read it. The refresh token is an httpOnly, secure, same-site cookie, rotated on every use, with **reuse detection**: presenting an already-rotated token revokes the whole session chain and raises an alert. |
| | Enforcement of strong authentication mechanisms for portal users, including MFA where applicable. | Authentication design | **Yes** — enforced password policy, multi-factor authentication, passkeys, federated single sign-on, and step-up re-authentication bound to the specific sensitive action and object rather than to a session-wide flag. |
| | Support for role-based access control (RBAC) to segregate user privileges (e.g., admin, user, support roles). | Authorization model | **Yes** — built-in and custom roles, enforced in the service layer rather than by hiding controls, so an API call cannot bypass what the interface does not show. An unrecognised role degrades to read-only, never to open access. |
| | Protection of sensitive data displayed or processed through the portal using masking and least exposure principles. | Data exposure controls | **Yes** — masking is applied to the API response, not to the template, so a direct call cannot retrieve the unmasked value. Viewer-identified watermarking is repeated up the page so a crop cannot remove attribution. |
| | All portal communications must be secured using HTTPS with TLS 1.2 or higher. | Transport security configuration | **Yes** — enforced at the gateway with MMBL's certificates, with strict transport security asserted by the application. |
| | Integration with Web Application Firewall (WAF) for protection against application-layer attacks. | WAF integration capability | **Yes** — deployed behind MMBL's WAF and API gateway, with declarative gateway configuration supplied. The application does not depend on the WAF for its own controls, so protection is layered rather than delegated. |
| | Implementation of security headers (e.g., HSTS, CSP, X-Frame-Options, X-Content-Type-Options). | HTTP security headers configuration | **Yes** — the full set applied by middleware on every response, including a content security policy, so no route can be served without them. |
| | Portal must generate detailed application logs for user activity, administrative actions, and security events. | Application logging capability | **Yes** — every state-changing action is recorded with actor, object, time and outcome, including refusals. A blocked action is evidence and is logged as such. |
| | Application logs must be integrable with the organization's SIEM solution in near real time. | SIEM integration support | **Yes** — CEF over syslog, emitted as events occur, with severity classification and a replay endpoint covering any period the collector was unavailable. |
| | Regular application security testing (SAST, DAST, and/or VAPT) must be performed before go-live and after major changes. | Security testing reports | **Yes** — static and dynamic testing gate every change; independent testing is performed before go-live and after each major change, with reports shared. |
| | Timely remediation of identified vulnerabilities based on defined severity SLAs. | Vulnerability remediation SLAs | **Yes** — 48 hours for critical, with the full severity ladder and escalation set out in the Service Level Agreement. |
| | Secure deployment and release management practices must be followed, including segregation of development, testing, and production environments. | SDLC and environment segregation | **Yes** — three separately credentialed environments built from the same declarative configuration. One artefact is promoted by digest from development through UAT to production, so what is approved in UAT is bit-for-bit what reaches production; production promotion requires named approval. |
| | Protection against automated attacks such as bots, brute force, and credential stuffing (e.g., rate limiting, CAPTCHA). | Anti-automation controls | **Yes** — distributed rate limiting consistent across replicas, per-identifier backoff, and account lockout. On the public signing surface a cryptographic proof-of-work is used in place of a visual CAPTCHA, because a visual puzzle excludes the branch customers the accessibility requirement protects; MMBL's WAF provides CAPTCHA at the edge where it does not affect that population. |
| | Secure error handling ensuring no sensitive information is exposed in error messages or stack traces. | Error handling controls | **Yes** — errors return a safe message with a correlation identifier; stack traces and internal detail go to the log, never to the response. Authentication failures are deliberately indistinguishable, so a response cannot be used to enumerate valid accounts. |
| | Confirmation that no hardcoded credentials, keys, or secrets exist within the portal codebase. | Secure secrets management | **Yes** — secret scanning gates every build and **fails it** on a finding, so this is enforced continuously rather than confirmed once. Secrets are supplied by environment or by MMBL's secret store, and cryptographic keys are held encrypted or in the hardware security module. |
| | Support for periodic security reviews and code reviews by the organization or authorized third parties. | Review and audit support | **Yes** — source code is made available for review under NDA, with the design rationale recorded alongside the code it governs so a reviewer can follow the reasoning rather than reverse-engineer it. |
| Hosting & Data Residency | On-premises hosting only; no SaaS or foreign-hosted deployment. All MMBL data – contract content, signatory PII, cryptographic key material, and audit logs – must remain within the territory of Pakistan at all times. | Hosting & data residency statement | **Yes** — enforced by the software, not by policy. Every configured endpoint is resolved at start-up and checked against a permitted-network allowlist; one outside it **stops the application from starting** rather than raising a warning somebody dismisses. The check is written to the audit trail at every boot, so residency can be evidenced for any given date. No component requires a foreign-hosted service to function. |
| PKI / Certificate Management | HSM-protected key generation and storage (FIPS 140-2 Level 3 or higher) for all CA private keys; per-signatory non-shared certificates; sworn undertaking that the PKI/eSignature solution is not open-source or foreign, supported by a Software Bill of Materials (SBOM). | PKI architecture & SBOM | **Yes**, with one clarification requested. Keys are generated **inside** the hardware security module and marked non-extractable, so "the private key never leaves the HSM" is enforced by the device rather than promised by software; no export method exists in the interface. Each signatory signs with their own certificate and key — never a shared organisational one. A signed CycloneDX SBOM accompanies every release. **The clarification:** the certificate authority, registration authority, lifecycle, revocation list and OCSP responder are our own implementation, and the PKI is domestic and MMBL-operated. One component — the library that embeds the signature into the PDF byte range, which never receives a private key — is an open-source library under a permissive licence. We are ready to give the undertaking on that basis and ask MMBL to confirm the wording accommodates it, rather than sign an undertaking whose literal reading we could not meet. |

> **Two rows are answered by the bidding entity rather than by the solution** — security
> certifications and the sub-contractor list are facts about the delivery organisation, and a
> third concerns the bidder's own mail domain. All three are completed in the commercial
> response.

---

---

# Supporting detail

Everything the responses above rely on, in the same category order. This section exists so the
sheet can be scored without opening another document; §12 says where each topic is treated at
greater length for a reviewer who wants it.

---

## 1. Compliance and regulatory

### 1.1 SBP Enterprise Technology Governance and Risk Management Framework

| Clause | Requirement | How it is met |
|---|---|---|
| ETGRMF 3.2 | Segregation of duties | Author and approver cannot be the same person, enforced in the service layer rather than by hiding a control, so an API call cannot bypass it. Overrides require a recorded reason |
| ETGRMF 3.4 | Access on least privilege | Role-based permissions, per-agreement access lists on confidential matters, time-boxed break-glass audited separately |
| ETGRMF 4.1 | Audit trail of system activity | Append-only trail of every state-changing action, ordered by a monotonic sequence rather than by timestamp |
| ETGRMF 4.3 | Tamper detection | Each entry chained by HMAC to its predecessor; a verification tool is delivered to MMBL so integrity can be proven without the vendor |
| ETGRMF 5.1 | Change management | Reversible schema migrations; approval gates on templates and clauses so wording cannot change without a recorded approval |
| ETGRMF 5.5 | Backup and recovery | Scripted, encrypted backups with automated restore verification |
| ETGRMF 6.2 | Incident logging to a SIEM | Severity-classified CEF feed over syslog, with replay for collector outages |
| ETGRMF 7.1 | Data residency | Endpoints resolved and allowlist-checked at start-up; a failure stops the application |
| ETGRMF 7.4 | Encryption at rest | Oracle TDE at the tablespace, plus AES-256 column encryption for secrets |
| ETGRMF 8.1 | Business continuity | Recovery objectives agreed at design and proven by a measured drill before go-live |

### 1.2 SBP Outsourcing Risk Management Framework

| Clause | Requirement | How it is met |
|---|---|---|
| ORMF 4.2 | Due diligence on the service provider | Counterparty master with KYC status, risk scoring and compliance documents; duplicate onboarding blocked, override requires a reason |
| ORMF 4.5 | Sanctions screening | Alias-aware screening against list snapshots held on premises; a stale list is reported as stale rather than silently used |
| ORMF 5.1 | Written agreement with mandatory clauses | Playbook rules make named clauses mandatory; a missing one classifies the agreement non-standard and routes it to the stricter approval path |
| ORMF 5.3 | Right to audit | Supported as approved clause wording and enforceable as a playbook requirement |
| ORMF 6.1 | Monitoring of the arrangement | Obligation register with owners, due dates, reminders and escalation |
| ORMF 6.4 | Exit strategy and termination | Multi-role sign-off; the notice is generated from the record, so it cannot disagree with it |
| ORMF 7.2 | Records retained for the required period | Retention tiers with scheduled archival and purge; legal hold overrides both |
| ORMF 8.1 | Sub-contracting transparency | Sub-contractors named with obligations flowed down; software supply chain inventoried in a signed bill of materials per release |

**Certification position.** ISO 27001, PCI DSS and SOC 2 are held by an organisation, not by a
product. Control-level evidence mapped to ISO 27001:2022 Annex A and to the SOC 2 Trust Services
Criteria is supplied so the solution can be absorbed into MMBL's own certified control
environment without leaving a gap in it. The bidding entity's own certification position is
stated in the commercial response.

---

## 2. System and network security

**Deployment shape.** Four separable tiers — request, asynchronous worker, database and object
storage — each independently addressable so they can sit in distinct network segments. Every
component declares the ports and destinations it requires, and default-deny network policy is
supplied with the deployment manifests. Nothing requires a flat network or an unrestricted
egress path.

**Security testing already applied to every change**

| Discipline | Tooling | Gate |
|---|---|---|
| Static analysis | Bandit, Semgrep with the OWASP Top 10 ruleset | Blocks the build |
| Dynamic analysis | OWASP ZAP against a running, migrated instance | Blocks the build |
| Dependencies | pip-audit, npm audit | Blocks the build |
| Containers and OS packages | Trivy | Blocks the build |
| Secrets | Gitleaks | Blocks the build |
| Bill of materials | CycloneDX, per release | Published |

**Independent testing.** Manual penetration testing by an assessor MMBL appoints, before go-live
and after each major change, using OWASP ASVS Level 2 as the assessment standard. Findings are
remediated to the severity ladder in §6.

**Patch commitment.** Critical within 48 hours, high within 5 working days, medium within 30
days. Dependency and container scanning on every build surfaces a new advisory without waiting
for a scheduled review.

**External posture scanning** by MMBL is acknowledged and accepted, with scope and windows agreed
in writing. The deployment is entirely on MMBL premises, so the internet-facing surface is the
bank's own.

---

## 3. Data protection and privacy

| Layer | Control |
|---|---|
| At rest — database | Oracle Transparent Data Encryption at the tablespace |
| At rest — secrets | AES-256 column encryption with a rotating key chain, so a database export alone yields nothing usable |
| At rest — signing keys | Generated inside the hardware security module and marked non-extractable; no export method exists in the interface |
| At rest — documents | Server-side encryption on object storage, per-workspace key prefix |
| In transit — external | TLS 1.2 or higher, enforced at the gateway with MMBL's certificates; strict transport security asserted by the application |
| In transit — internal | TLS between tiers, with the configuration checked at start-up rather than assumed |

**Data segregation is enforced by the database, not only by application code.** Oracle Virtual
Private Database is applied to every workspace-scoped table, so a defect in application logic still
cannot read across the boundary. Repository code filters independently as a second layer; both
are kept, because either alone is one mistake away from a read across the boundary.

**Data lifecycle.** Retention tiers with scheduled archival and purge, exercised from day one
rather than first attempted in year three. Deletion is irreversible and audited. Legal hold
overrides deletion unconditionally and is scoped per matter, so releasing one matter cannot
expose records another still protects — the failure a single flag cannot avoid, and one whose
consequence is unrecoverable.

**NDA.** The bidding entity will execute MMBL's standard non-disclosure agreement.

---

## 4. Access control and logging

**Authentication.** Enforced password policy; multi-factor by time-based one-time passcode with
recovery codes, passkeys (FIDO2/WebAuthn) with cloned-authenticator detection, and email
fallback. Federated single sign-on by SAML 2.0 or OpenID Connect against MMBL's identity
provider, with signature verification delegated to a maintained cryptographic library rather than
hand-rolled.

**Authorisation.** Built-in and custom roles, enforced in the service layer. An unrecognised role
degrades to read-only, never to open access. Step-up re-authentication is bound to the specific
action and object, single-use and time-limited — a session-wide "recently authenticated" flag
would turn one re-authentication into a window over everything.

**Log format.** CEF over syslog, with CLF available for web-tier access logs.

**Severity mapping.** The full syslog range is used and mapped deliberately rather than defaulted.

| Severity | Example event |
|---|---|
| Alert | Refresh-token reuse detected — an already-rotated token presented; the whole session chain is revoked |
| Critical | Audit-chain verification failure; upload scanner unreachable |
| Error | Authentication failure; authorisation refusal; signing failure |
| Warning | Rate limit exceeded; approaching certificate expiry; stale sanctions list |
| Notice | Role change; break-glass access; separation-of-duties override |
| Informational | Sign-in, document view, workflow decision, signature applied |

**Coverage.** Authentication, access control, application usage, system activity, security
incidents, network events and the business audit trail. Refusals are logged as well as successes:
a blocked action is evidence, and a control that leaves no trace when it fires cannot be
evidenced.

---

## 5. Compatibility and integration

| System | Interface | What MMBL supplies |
|---|---|---|
| Identity (IAM / SSO / MFA) | SAML 2.0 and OpenID Connect | Metadata, reply URL |
| User provisioning | SCIM 2.0 | Bearer token |
| API gateway / WAF | Deployed behind the gateway; declarative configuration supplied | Route and plugin mapping |
| SIEM | CEF over syslog, near real time, with replay | Collector endpoint |
| SOAR | Consumes the same event feed | — |
| PAM | Federated privileged accounts with step-up authentication | Privileged role mapping |
| DAM | Operates at the database tier, transparent to the application | — |
| Vulnerability management | Per-release CycloneDX bill of materials the bank's scanner consumes directly | — |
| Backup and restore | Integrates at database and storage layers; no application agent | Backup target |
| Mail and SMS | SMTP relay and HTTP SMS adapter, with delivery state recorded rather than assumed | Relay and gateway accounts |

---

## 6. Incident and business continuity

**Severity, response and resolution**

| Severity | Definition | Response | Resolution target |
|---|---|---|---|
| S1 | Service unavailable, or signing cannot complete | 30 minutes | 4 hours |
| S2 | Major function degraded, no workaround | 1 hour | 1 business day |
| S3 | Function impaired with a workaround | 4 business hours | 5 business days |
| S4 | Minor or cosmetic | 1 business day | Next release |

**Security incidents** follow the same clock with a fixed escalation: MMBL's security contact is
notified within one hour of confirmation, with a written assessment within 24 hours and a root
cause analysis within five working days. Vulnerability remediation follows the patch ladder in
§2. Missed targets attract automatic service credits rather than discretionary ones.

**The process is exercised during UAT**, using the same channels, severities and escalation path
as production, so it is proven with real tickets before it protects live service.

**Continuity and recovery.** Recovery point and recovery time objectives are agreed at design and
proven by a measured drill before go-live sign-off. Backups are encrypted, held offsite and
**restore-verified** — a backup that has never been restored is an assumption, not a control.
Documents and database are captured on the same schedule so a restore produces a consistent
state rather than records pointing at documents that no longer exist.

**Audit support.** Several controls are demonstrable live on MMBL's own instance rather than
accepted on paper — see §11.

---

## 7. Communications security

All official communication during the engagement is conducted over authenticated channels. The
bidding entity's mail domain publishes SPF and DKIM, with DMARC as an added measure; the current
record state is confirmed in the commercial response and any record not at the required policy is
corrected before project kick-off. MMBL's right to reject unauthenticated email is acknowledged.

---

## 8. Portal and web application security

**Secure by design and by default.** Controls fail closed. The upload scanner refuses a file when
the scanning service is unreachable rather than passing it, and the application refuses to start
if any configured endpoint resolves outside the permitted network. Both are deliberate: a control
that degrades quietly protects nothing at the moment it matters.

**Standards.** Mapped control-by-control to the OWASP Top 10 and to OWASP ASVS Level 2.

| Control area | Implementation |
|---|---|
| Input validation | Schema validation at every API boundary, with type coercion and bounds |
| Injection | Parameterised queries throughout; string-built SQL does not exist in the codebase |
| Output encoding | Contextual encoding; the document editor sanitises on input and on render |
| Cross-site request forgery | Same-site cookie policy plus origin checks on state-changing requests |
| Session management | Access token short-lived and held in memory only, never in browser storage where a script could read it. Refresh token httpOnly, secure, same-site, rotated on every use, with reuse detection that revokes the whole chain and raises an Alert |
| Transport | TLS 1.2+ enforced at the gateway; HSTS asserted |
| Security headers | HSTS, Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy and Permissions-Policy, applied by middleware on every response so no route can be served without them |
| Data exposure | Masking applied to the API response rather than the template, so a direct call cannot retrieve the unmasked value; viewer-identified watermarking repeated up the page so a crop cannot remove attribution |
| Error handling | Safe message plus a correlation identifier; stack traces to the log, never the response. Authentication failures are deliberately indistinguishable, so responses cannot enumerate valid accounts |
| Secrets | Secret scanning gates and fails every build; secrets supplied by environment or MMBL's secret store; keys held encrypted or in the HSM |

**Anti-automation.** Distributed rate limiting consistent across replicas, per-identifier
backoff, and account lockout. On the public signing surface a cryptographic proof-of-work is used
**in place of a visual CAPTCHA**, because a visual puzzle excludes exactly the branch customers
the accessibility requirement protects. MMBL's WAF provides CAPTCHA at the edge, where it does not
affect that population. This is a deliberate design decision, stated rather than left as an
apparent omission.

**Release management.** Three separately credentialed environments — development, UAT and
production — built from the same declarative configuration. One artefact is promoted by digest
from development through UAT to production, so what is approved in UAT is bit-for-bit what
reaches production. Promotion to production requires named approval, and database migrations run
as a separate, gated step.

**Review support.** Source code is made available for review under NDA. Design rationale is
recorded alongside the code it governs, so a reviewer can follow the reasoning rather than
reverse-engineer it.

---

## 9. Hosting and data residency

On-premises only. No component of the solution requires a foreign-hosted service to function, and
no SaaS dependency exists in the deployed set.

**Residency is enforced by the software, not by policy.** Every configured external endpoint —
database, object storage, mail relay, SMS gateway, SIEM collector, identity provider, timestamp
authority — is resolved at start-up and checked against an allowlist of permitted networks. An
endpoint outside it **stops the application from starting** rather than producing a warning
somebody dismisses. The result is written to the audit trail at every boot, so the deployment can
evidence its residency posture for any given date rather than asserting it.

This covers contract content, signatory personal data, cryptographic key material and audit logs
alike.

---

## 10. PKI and certificate management

**Hierarchy.** Two tiers. The root is generated once, signs the issuing CA, and goes offline
under dual witness; the issuing CA carries a path-length constraint of zero, so an attacker who
compromised it could issue end-entity certificates — serious, and recoverable by revoking that
one CA — but could not create a sub-CA and extend the hierarchy.

**Key custody.** Keys are generated **inside** the hardware security module and marked
non-extractable, so "the private key never leaves the HSM" is enforced by the device rather than
promised by software. The custody interface has **no export method**, so no code path can
serialise a private key out of it. Supported devices include Thales Luna, Utimaco CryptoServer
and Entrust nShield at FIPS 140-2 Level 3.

**Per-signatory certificates.** Each signatory signs with their own certificate and key, never a
shared organisational one. One active certificate per signatory is enforced twice — at issuance,
and by a database constraint — so a code path that forgets the check still cannot create a
second. Issuance requires an approved registration request under dual control; an officer cannot
approve their own.

**Revocation.** Full and delta certificate revocation lists, plus a real-time OCSP responder
signed by a delegated responder certificate rather than the CA key, so the CA key stays cold.
Lists are republished at half their validity window, so a single failed publication still leaves
a valid list in place for another cycle.

**Signature format.** PAdES-LTV: the signed document embeds its certificate chain, revocation
data and an RFC 3161 trusted timestamp, so it verifies offline and years later without access to
this system.

**Software bill of materials.** A signed CycloneDX SBOM accompanies every release, inventorying
every component with its version and licence.

**The undertaking, stated plainly.** The certificate authority, registration authority,
lifecycle, revocation lists and OCSP responder are our own implementation; the PKI is domestic and
MMBL-operated, with no foreign service in the signing path. One component — the library that
embeds the signature into the reserved byte range of the PDF, and which never receives a private
key — is an open-source library under a permissive licence. We are ready to give the undertaking
on that basis, and ask MMBL to confirm the wording accommodates it rather than sign an
undertaking whose literal reading we could not meet.

---

## 11. Controls demonstrable live during assessment

The strongest evidence is a control an assessor watches work. Each of these takes minutes on
MMBL's own instance and needs no vendor involvement.

1. **Access control** — query the caller's effective permissions and the full role matrix, and
   compare against the documented model.
2. **Segregation of duties** — attempt to approve an agreement you authored. The action is
   refused and the refusal is written to the audit trail; query the trail for it.
3. **Audit integrity** — run the verification tool. Alter or delete a row directly in the
   database and it fails, naming that row.
4. **Retention and legal hold** — place a hold, run the purge, observe the agreement skipped with
   the reason recorded.
5. **Data residency** — point a configured endpoint outside the allowlist. The application
   refuses to start, and the check is recorded.
6. **Signature evidence** — verify an executed agreement offline, with no access to the system.
7. **Sanctions screening** — query screening status; a stale list is reported as stale rather
   than used silently.

---

## 12. Where each topic is treated at greater length

This document is self-contained for scoring. For a reviewer who wants the full treatment:

| Topic | Annexure |
|---|---|
| Requirement-by-requirement compliance with the whole RFP | Compliance Matrix (Feature-to-Requirement) |
| Architecture, tiers, technology and sizing | Scope & Technical Specification |
| Control mapping to SBP, ISO 27001 and SOC 2 | Compliance Evidence Pack |
| Severity definitions, targets, credits and escalation | Service Level Agreement |
| Hash chaining, verification and the limits of what it proves | Audit Trail Mechanism |
| Testing strategy, gates and acceptance | Quality Assurance Plan |
| Hierarchy, custody, lifecycle, revocation and signing | PKI Architecture |
| Third-party components, licences and known advisories | Licensing and Open-Source Inventory |
| Milestones, dependencies and dates | Project Implementation Plan |
| Regulatory, platform, security and delivery risk | Risk Mitigation Strategy |
