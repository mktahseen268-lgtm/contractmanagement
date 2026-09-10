# Compliance Evidence Pack

Every control mapped to the framework clause it satisfies, **with the mechanism that delivers
it**. A compliance statement without that mechanism is a claim; with it, it is evidence an
assessor can test.

This pack supports the response to RFP §4d. It covers the two State Bank of Pakistan frameworks
named in the RFP, together with ISO/IEC 27001:2022 Annex A and the SOC 2 Trust Services
Criteria, so that the solution can be absorbed into MMBL's own certified control environment
without leaving a gap in it.

**All controls listed are complied with.** Where a control depends on an input that only MMBL can
supply — a database platform, a scanning service, a log collector, an identity provider — the
required input is named alongside it, and it appears in the Project Implementation Plan against
the milestone by which it is needed.

Section 6 is the part an assessor will use in practice: it lists controls that can be
**demonstrated live**, on the bank's own instance, rather than accepted on paper.

---

## 1. SBP Enterprise Technology Governance and Risk Management Framework

| Clause | Requirement | Compliance | Mechanism | MMBL input |
|---|---|---|---|---|
| ETGRMF 3.2 | Segregation of duties | Complied | Author and approver cannot be the same person; enforced in the service layer rather than by hiding a control, so an API call cannot bypass it. Overrides require a recorded reason | — |
| ETGRMF 3.4 | Access on least privilege | Complied | Role-based permissions with per-agreement access lists on confidential matters; break-glass access is time-boxed and separately audited | Role-to-job-function mapping |
| ETGRMF 4.1 | Audit trail of system activity | Complied | Append-only trail covering every state-changing action, ordered by a monotonic sequence rather than by timestamp | — |
| ETGRMF 4.3 | Tamper detection | Complied | Each entry chained by HMAC to its predecessor; an independent verification tool is delivered to MMBL, so integrity can be proven without the vendor | — |
| ETGRMF 5.1 | Change management | Complied | Reversible schema migrations, plus approval gates on templates and clauses so wording cannot change without a recorded approval | — |
| ETGRMF 5.5 | Backup and recovery | Complied | Scripted, encrypted backups with automated restore verification — a backup that has never been restored is an assumption, not a control | Backup target and offsite location |
| ETGRMF 6.2 | Incident logging to a SIEM | Complied | Severity-classified event feed in CEF over syslog, with replay for any collector outage | SIEM collector endpoint |
| ETGRMF 7.1 | Data residency | Complied | Every configured endpoint is resolved at start-up and checked against an allowlist; a failure stops the application rather than warning | Permitted network ranges |
| ETGRMF 7.4 | Encryption at rest | Complied | Transparent Data Encryption at the database, with additional column-level encryption for secrets so a database export alone yields nothing usable | TDE enabled on the instance |
| ETGRMF 8.1 | Business continuity | Complied | Recovery objectives agreed at design and proven by a measured disaster-recovery drill before go-live sign-off | DR site and drill window |

---

## 2. SBP Outsourcing Risk Management Framework

| Clause | Requirement | Compliance | Mechanism | MMBL input |
|---|---|---|---|---|
| ORMF 4.2 | Due diligence on the service provider | Complied | Counterparty master with KYC status, risk scoring and compliance documents; duplicate onboarding is blocked and an override requires a reason | — |
| ORMF 4.5 | Sanctions screening | Complied | Alias-aware screening against list snapshots held on premises; a stale list is reported as stale rather than silently used | Screening list subscription |
| ORMF 5.1 | Written agreement with mandatory clauses | Complied | Playbook rules make named clauses mandatory; a missing one classifies the agreement non-standard and routes it to the stricter approval path | MMBL's clause policy |
| ORMF 5.3 | Right to audit | Complied | Supported as approved clause wording and enforceable as a playbook requirement | Approved wording |
| ORMF 6.1 | Monitoring of the arrangement | Complied | Obligation register with owners, due dates, reminders and escalation across the whole portfolio | — |
| ORMF 6.4 | Exit strategy and termination | Complied | Termination with multi-role sign-off; the notice is generated from the record, so it cannot disagree with it | Sign-off authorities |
| ORMF 7.2 | Records retained for the required period | Complied | Retention tiers with scheduled archival and purge; legal hold overrides both unconditionally | Retention policy |
| ORMF 8.1 | Sub-contracting transparency | Complied | Any sub-contractor is named with security obligations flowed down contractually; the software supply chain is inventoried in a signed bill of materials with every release | — |

---

## 3. ISO/IEC 27001:2022 Annex A

| Control | Compliance | Mechanism |
|---|---|---|
| A.5.15 Access control | Complied | Role-based permissions with per-agreement access lists |
| A.5.16 Identity management | Complied | Federated identity with automated provisioning and de-provisioning from MMBL's directory |
| A.5.17 Authentication information | Complied | Modern password hashing, an enforced strength policy, and multi-factor authentication |
| A.5.18 Access rights | Complied | Rights reviewable in the product, with a posture view for periodic recertification |
| A.5.23 Cloud services security | Complied | On-premises by design; no component requires a foreign-hosted service to function |
| A.5.28 Collection of evidence | Complied | Legal-hold export producing a defensible evidence set including audit-chain positions |
| A.5.31 Legal and contractual requirements | Complied | This pack, together with the Compliance Matrix |
| A.6.3 Awareness and training | Complied | Training programme at go-live plus a permanent in-product training system with certification tracking |
| A.8.2 Privileged access rights | Complied | Step-up re-authentication bound to the specific privileged action and object |
| A.8.5 Secure authentication | Complied | Multi-factor authentication, passkeys, and federated single sign-on |
| A.8.7 Protection against malware | Complied | Every upload scanned, failing closed when the scanner is unreachable |
| A.8.8 Management of technical vulnerabilities | Complied | Static analysis, dynamic scanning, dependency auditing and container scanning on every build |
| A.8.10 Information deletion | Complied | Scheduled purge with legal hold blocking it unconditionally |
| A.8.12 Data leakage prevention | Complied | Response-level masking, viewer-identified watermarking, and download control |
| A.8.15 Logging | Complied | Comprehensive, tamper-evident logging of every state-changing action |
| A.8.16 Monitoring activities | Complied | Metrics and event feed to MMBL's monitoring and SIEM platforms |
| A.8.24 Use of cryptography | Complied | Encryption at rest and in transit; signing keys held in a hardware security module and non-extractable |
| A.8.25 Secure development lifecycle | Complied | Gated pipeline with security testing at every stage, described in the Quality Assurance Plan |
| A.8.28 Secure coding | Complied | Schema validation at every boundary, secure error handling, and secret scanning that blocks the build |

---

## 4. SOC 2 Trust Services Criteria

| Criterion | Compliance | Mechanism |
|---|---|---|
| CC6.1 Logical access | Complied | Roles, permissions and per-agreement access lists |
| CC6.2 Registration and authorisation | Complied | Automated provisioning, single sign-on, and a controlled invitation flow |
| CC6.3 Role changes and removal | Complied | Role change requires step-up authentication and is audited |
| CC6.6 External threat protection | Complied | Distributed rate limiting, anti-automation on public surfaces, and gateway-level protection |
| CC6.7 Restricted transmission | Complied | TLS enforced, with the configuration checked at start-up rather than assumed |
| CC6.8 Malicious software | Complied | Upload scanning that fails closed |
| CC7.2 Monitoring for anomalies | Complied | Severity-classified event feed to MMBL's SIEM |
| CC7.3 Incident evaluation | Complied | Tamper-evident audit trail and SIEM feed, with incident runbooks handed over at go-live |
| CC8.1 Change management | Complied | Reversible migrations, approval gates, and versioned templates and clauses |
| A1.2 Availability and recovery | Complied | Restore-verified backups and a measured recovery drill |

---

## 5. Controls that depend on an MMBL-supplied input

Listed together so nothing has to be inferred from the tables above. Each is complied with; each
needs one input from the bank, and each of those inputs appears in the Project Implementation
Plan against the date it is required.

| Control | Input required | Needed by |
|---|---|---|
| Encryption at rest (TDE) | Transparent Data Encryption enabled on the database instance | M1 |
| Malware scanning on upload | A reachable scanning service endpoint | M1 |
| SIEM event feed | Collector endpoint and accepted format confirmation | M1 |
| Federated identity and provisioning | Identity provider metadata, reply URL and provisioning token | M1 |
| One-time passcode delivery | SMS gateway account and sender identity | M1 |
| Hardware-backed signing keys | Hardware security module on site | M3 |
| Independent penetration test | Testing vendor appointed | M5 |
| Disaster recovery objectives | DR site and an agreed drill window | M5 |

**One control is deliberately implemented differently from the obvious approach.** Anti-automation
on the public signing surface uses proof-of-work and per-identifier backoff rather than a visual
puzzle, because a visual challenge excludes exactly the branch customers the accessibility
requirement protects. Edge protection at the gateway complements it. The reasoning is stated here
rather than left for an assessor to discover as an apparent omission.

---

## 6. Controls that can be demonstrated live during an assessment

The strongest evidence is a control an assessor watches work on MMBL's own instance. Each of the
following takes minutes, needs no vendor involvement, and produces a result the assessor can keep.

1. **Access control.** Query the caller's effective permissions and the full role matrix, and
   compare them against the documented model.
2. **Segregation of duties.** Attempt to approve an agreement you authored. The action is refused
   and the refusal is written to the audit trail — query the trail for it.
3. **Audit integrity.** Run the verification tool: it recomputes the chain and reports the first
   divergent entry, if any. Alter or delete a row directly in the database and it fails, naming
   that row. This is demonstrable in front of the assessor.
4. **Retention and legal hold.** Place a hold, run the purge, and observe the agreement skipped
   with the reason recorded.
5. **Sanctions screening.** Query screening status: list ages are reported, and a stale list is
   reported as stale rather than used silently.
6. **Data residency.** Point a configured endpoint at an address outside the allowlist. The
   application refuses to start, and the check is recorded in the audit trail.
7. **Signature evidence.** Take an executed agreement and verify it offline, with no access to
   the system: the certificate chain, revocation data and trusted timestamp are embedded in the
   document itself.
