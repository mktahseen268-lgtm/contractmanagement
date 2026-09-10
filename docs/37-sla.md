# Service Level Agreement

**Annexure item 3.** Commitments for the two-year onsite support period following go-live.

Every commitment below is measurable, and each states **how it is measured** and **what happens
when it is missed**. A target with no measurement method is a statement of intent; a target with
no consequence is a statement of hope.

---

## 1. Service availability

| Service | Target | Measurement window |
|---|---|---|
| Application (web and API) | **99.5%** | Calendar month |
| Signing portal | **99.5%** | Calendar month |
| OCSP responder | **99.9%** | Calendar month |
| Scheduled jobs (renewals, CRL, retention) | 99% of scheduled runs complete | Calendar month |

**The OCSP responder carries a higher target than the application on purpose.** Relying parties
check revocation while validating a signature that may have been made months ago. If the responder
is down and the deployment is configured to fail closed, signature validation fails across the
whole estate — the blast radius is wider than the application's own.

### Measured how
From the monitoring endpoints, not from a ticket count. Availability is `1 − (unavailable minutes
/ minutes in month)`, where unavailable means the readiness probe failing or the error rate above
5% for more than 60 consecutive seconds.

### Excluded
Agreed maintenance windows, failures in MMBL-operated infrastructure (network, database, HSM, IdP,
gateway), and force majeure. **Exclusions are agreed in advance and recorded**, not claimed
retrospectively when a month looks bad.

---

## 2. Incident response

| Severity | Definition | Response | Workaround | Resolution |
|---|---|---|---|---|
| **P1** | Service down, data loss, security breach, or agreements cannot be executed | **30 minutes** | 4 hours | 24 hours |
| **P2** | A core function unavailable with no workaround; significant degradation | 2 hours | 8 hours | 3 business days |
| **P3** | A function impaired with a workaround available | 8 business hours | — | 10 business days |
| **P4** | Cosmetic, or a question | 2 business days | — | Next release |

**Response** means a named engineer is engaged and MMBL has been told who. An automated
acknowledgement is not a response.

### Severity is agreed, not assigned
Severity is set jointly by MMBL and our support lead. **A supplier who assigns severity alone will
always find reasons why a P2 is really a P3**, and the mechanism that prevents that is a shared
decision, not good intentions.

### P1 examples, so there is no argument at 2 a.m.
- Nobody can sign in
- An agreement cannot be executed
- The audit chain fails verification
- Any confirmed unauthorised data access
- The OCSP responder returns incorrect status
- The CA private key is suspected compromised

---

## 3. Support hours

| Tier | Coverage | Channel |
|---|---|---|
| **L1** — triage, known issues, how-to | 24×7 | Phone, email, portal |
| **L2** — configuration, data, integration | Business hours, on-call for P1/P2 | Portal, escalated from L1 |
| **L3** — engineering | Business hours, on-call for P1 | Escalated from L2 |
| **Onsite presence** | Business hours, first 6 months; then on request | On site |

Business hours: Monday–Friday, 09:00–18:00 PKT, excluding Pakistan public holidays.
**P1 response is 24×7 regardless of tier.**

---

## 4. Security patching

| Severity | Assessed within | Patched within |
|---|---|---|
| **Critical** (CVSS ≥ 9.0, or actively exploited) | 4 hours | **48 hours** |
| High (CVSS 7.0–8.9) | 1 business day | 7 days |
| Medium (CVSS 4.0–6.9) | 3 business days | 30 days |
| Low (CVSS < 4.0) | 10 business days | Next scheduled release |

The 48-hour critical turnaround is the RFP's requirement and is committed.

**Assessment is separate from patching for a reason.** Not every critical CVE is exploitable in
this deployment — an advisory against a code path the application does not reach is still worth
assessing quickly and is not worth an emergency change window. The assessment is written down
either way, so "not applicable" is a documented judgement rather than an omission.

Dependency and container scanning run on every build, so an advisory is usually known before it
is reported.

---

## 5. Recovery

| Measure | Commitment | Evidenced by |
|---|---|---|
| **RPO** — maximum data loss | 15 minutes | Continuous archiving with point-in-time recovery |
| **RTO** — time to restore service | 4 hours | DR drill with the restored system verified working |
| Backup retention | 35 days, plus monthly copies for 10 years | Backup catalogue |
| Restore verification | Quarterly | Restore test report |

**Backups are restored quarterly, not merely taken.** A backup nobody has restored is a
hypothesis. The quarterly test restores to an isolated environment and verifies that the
application starts, data is intact, and the audit chain still verifies across the restored
history.

---

## 6. Change management

| Change type | Notice | Window | Approval |
|---|---|---|---|
| Emergency (P1 fix) | Immediate, notified during | Any | Post-hoc, within 24 h |
| Standard release | 5 business days | Agreed maintenance window | MMBL change board |
| Configuration | 2 business days | Business hours | MMBL business owner |
| Infrastructure | 10 business days | Agreed window | MMBL change board |

Every release passes the full CI gate set before it is offered. A release that cannot pass the
gates is not deployed, including under P1 pressure — **the emergency path is a faster review, not
a skipped one**, because a hotfix that causes a second incident is how a bad day becomes a bad
week.

---

## 7. Reporting

| Report | Frequency | Contents |
|---|---|---|
| Service report | Monthly | Availability against target, incidents by severity, response and resolution against SLA, patches applied, changes made |
| Security report | Monthly | Vulnerabilities found and remediated, scan results, SIEM alert summary, access reviews |
| Risk review | Fortnightly | The risk register — residuals, triggers fired, new entries |
| Capacity report | Quarterly | Storage growth, response-time trends, headroom against sizing |
| DR test report | Quarterly | Restore test result with evidence |

**A missed SLA appears in the monthly report whether or not MMBL raised it.** Self-reporting is
the difference between a service report and a marketing document.

---

## 8. Service credits

| Monthly availability | Credit (% of monthly fee) |
|---|---|
| ≥ 99.5% | None — target met |
| 99.0% – 99.49% | 5% |
| 98.0% – 98.99% | 10% |
| 95.0% – 97.99% | 20% |
| < 95.0% | 30% |

| SLA breached | Credit |
|---|---|
| P1 response missed | 5% per occurrence |
| P1 resolution missed | 10% per occurrence |
| Critical patch beyond 48 hours | 10% per occurrence |

Credits are capped at 30% of the monthly fee and are applied automatically from our own service
report — **MMBL does not have to claim them**. A credit regime that depends on the customer
noticing is one the supplier profits from when the customer is busy.

Credits are the agreed remedy for service failures and do not limit liability for data loss,
security breach, or breach of the data residency commitment.

---

## 9. What is excluded, and who owns it

| Excluded | Owner |
|---|---|
| Network, firewall, WAF, load balancer | MMBL |
| Database platform, licensing, HA, TDE | MMBL |
| HSM hardware, firmware, PKI accreditation | MMBL |
| Identity provider availability | MMBL |
| SMS gateway and mail relay availability | MMBL |
| Operating system and Kubernetes platform | MMBL |
| Third-party penetration testing | MMBL appoints; we facilitate and remediate |
| MMBL's own template and clause content | MMBL Legal |

**An incident caused by an excluded component is still triaged by us** — the customer should not
have to work out which supplier to call. It is diagnosed, attributed with evidence, and handed
over with that evidence. What is excluded is the *remedy*, not the *diagnosis*.

---

## 10. Escalation

| Level | Contact | When |
|---|---|---|
| 1 | Support lead | Any incident |
| 2 | Delivery manager | P1 beyond 4 hours; P2 beyond 1 business day |
| 3 | Account director | P1 beyond 12 hours; any SLA breach two months running |
| 4 | Managing director | Systemic failure; any unresolved P1 beyond 24 hours |

Named individuals with direct numbers are provided at contract signature and kept current. An
escalation path that resolves to a shared inbox is not one.

---

## 11. Two commitments not usually written down

**We report our own breaches.** Every missed target appears in the monthly service report,
self-identified, whether or not MMBL noticed.

**We tell MMBL when a control is not working, not only when a service is down.** If the antivirus
daemon is unreachable, if the SIEM feed has gapped, if the software keystore is in use where the
HSM should be — MMBL is told, because a security control that has quietly stopped working is more
dangerous than an outage, and it will not appear in an availability figure.
