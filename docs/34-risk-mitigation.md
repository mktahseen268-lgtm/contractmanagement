# Risk Mitigation Strategy

**Annexure item 7. Weighted at 11% — the joint-heaviest criterion in the RFP's rubric.**

This is the risk register for **delivering the complete solution described in RFP §4a, §4b, §4c
and §4d**, from contract award through to steady-state operation. It covers the whole scope,
including the parts that depend on platforms, credentials and approvals that only MMBL or a
third party can provide.

A risk register that lists "project delay — mitigation: good project management" scores nothing
and deserves to. Every entry below carries a **named owner**, a **trigger that can be observed
rather than felt**, a **planned response**, and the **residual risk that remains after the
mitigation**. The residual is the number that matters: a High/Critical risk with a real control
is safer than a Medium/Medium one with none.

Risks are grouped by what causes them, because that is how they get owned.

---

## 1. How risk is scored here

| Term | Meaning |
|---|---|
| **Likelihood** | Low (unlikely in this engagement) · Medium (has occurred on comparable engagements) · High (expected unless actively prevented) |
| **Impact** | Low (inconvenience) · Medium (rework or delay) · High (go-live at risk) · Critical (legal, regulatory or financial exposure) |
| **Residual** | What remains *after* the mitigation is applied. Stated for every risk. |

**Two conventions are deliberate.** First, a risk owned by MMBL is named as such rather than
softened into "joint" — a shared owner is an unowned risk. Second, where a mitigation reduces
but does not remove exposure, the residual says so instead of being written down to Low.

---

## 2. Regulatory and compliance risks

These come first because they are the ones that cannot be fixed by working harder.

### R-01 · SBP alignment is interpreted differently by the bank's compliance function
**Likelihood** Medium · **Impact** High · **Residual** Low

RFP §4d requires confirmed alignment with the State Bank of Pakistan's **Enterprise Technology
Governance and Risk Management Framework** and the **Outsourcing Risk Management Framework**. A
statement of compliance is not the risk; the risk is that MMBL's compliance function reads a
specific control differently from us, discovers it at UAT, and the remediation lands on the
critical path.

**Mitigation.** Alignment is treated as a *reviewable artefact*, not a declaration. A control-by-
control mapping against both frameworks is submitted with the bid and re-walked with MMBL's
compliance and risk functions in the first two weeks of the engagement, before the configuration
that depends on it is fixed. Every control names the mechanism that satisfies it, so a
disagreement is about one control and not about the whole solution.

**Trigger.** Any control in the mapping challenged, or marked as not-yet-evidenced, at the week-2
compliance walkthrough.
**Response.** Controls are re-scoped against MMBL's own interpretation and, if the change is
material, raised through change control before design freeze rather than after.
**Owner.** MMBL compliance, with our security lead accountable for the mapping.

### R-02 · Outsourcing governance obligations are not met by the delivery arrangement
**Likelihood** Low · **Impact** High · **Residual** Low

SBP's Outsourcing Risk Management Framework places obligations on MMBL regarding vendor
oversight, exit management, data location and sub-contracting. A solution that is technically
correct can still fail this test on its commercial and operational wrapper.

**Mitigation.** Four commitments are made at contract rather than discovered later: the
deployment is **on-premises inside MMBL's own environment**, so the bank retains custody of data
and infrastructure; the complete software bill of materials is delivered with every release, so
the supply chain is inspectable; an exit plan providing data and configuration in open,
documented formats is part of the delivery; and any sub-contractor involved in delivery is named,
with their security obligations flowed down in writing.

**Trigger.** Any request from MMBL's outsourcing risk function that cannot be answered from the
material already supplied.
**Response.** Answer within five working days, and add the artefact to the standing pack so the
gap does not recur at the next review.
**Owner.** Our engagement director.

### R-03 · The electronic signature evidence is challenged in a dispute
**Likelihood** Low · **Impact** Critical · **Residual** Low

The value of the whole system rests on an executed agreement being defensible. A challenge would
come years after execution, when the people involved have moved on and only the record remains.

**Mitigation.** Evidence is designed to be readable by someone with no access to the system.
Each signature is a cryptographic signature made with a certificate belonging to that individual
signatory rather than a shared organisational one; the signed document embeds its certificate
chain, revocation data and a trusted timestamp, so it verifies offline and years later; and a
Certificate of Completion records identity evidence, consent, IP address and timing for every
party. The audit trail is tamper-evident, and its verification tool is delivered to MMBL so the
bank can prove integrity without our involvement.

**Trigger.** Any challenge to an executed agreement, or any verification failure reported by the
integrity check.
**Response.** Produce the signed document, the Certificate of Completion and an audit-chain
verification report as a single evidence bundle.
**Owner.** MMBL legal, with our PKI lead supporting.

### R-04 · Accreditation expectations exceed what a product can hold
**Likelihood** Medium · **Impact** Medium · **Residual** Medium

RFP §4d asks for evidence of ISO 27001, PCI DSS and SOC 2 Type II. These are certifications held
by an **organisation**, and a certificate belonging to a software product does not exist. There
is a real risk of a scoring mismatch between what is asked for and what any vendor can supply for
a product.

**Mitigation.** Two responses, both offered. The bidding entity's own certification position is
stated plainly in the commercial response. Separately, control-level evidence mapped to ISO
27001:2022 Annex A and to the SOC 2 Trust Services Criteria is supplied, so MMBL's own certified
environment can absorb the solution without a gap in its control set.

**Trigger.** Clarification from MMBL that a product-level certificate is required.
**Response.** Raise at the clarification stage rather than assuming an interpretation. If a
certificate is mandatory, the position is stated before award and not after.
**Owner.** Our engagement director. **This is one we would raise at clarification.**

### R-05 · The sworn undertaking cannot be given exactly as drafted
**Likelihood** Medium · **Impact** High · **Residual** Medium

The annexure requires a sworn undertaking. Depending on its final wording, an undertaking that
covers, for example, the behaviour of every third-party open-source component may be broader than
any vendor can truthfully swear to.

**Mitigation.** The wording is reviewed by counsel **before** submission rather than signed and
qualified afterwards. Where a clause cannot be given as written, a specific alternative is
proposed with the reason, rather than the undertaking being returned unsigned or signed
untruthfully.

**Trigger.** Counsel identifies any clause that cannot be given as drafted.
**Response.** Raise it as a formal clarification before the submission deadline.
**Owner.** Joint — MMBL legal and our counsel. **This is a bid-validity question, not a scoring
one, and it is the first item we would raise.**

### R-06 · Data leaves Pakistan, or leaves MMBL's premises
**Likelihood** Low · **Impact** Critical · **Residual** Low

The RFP requires an on-premises deployment with all data resident in Pakistan. The realistic
failure is not a deliberate breach but a convenience: a cloud extraction service, a hosted mail
relay, a foreign observability endpoint, quietly configured by someone solving a different
problem.

**Mitigation.** Residency is enforced by the software rather than by policy. Every configured
external endpoint is resolved at start-up and checked against an allowlist of permitted networks;
an endpoint outside it **stops the application from starting** rather than producing a warning
somebody dismisses. The check is recorded in the audit trail at every boot, so the deployment can
prove its residency posture on any given date. No component of the solution requires a
foreign-hosted service to function.

**Trigger.** Any start-up residency failure, or any change request introducing an external
endpoint.
**Response.** The endpoint is refused or explicitly allowlisted by MMBL with a recorded decision.
**Owner.** MMBL infrastructure, with our engineering lead accountable for the control.

---

## 3. Platform and data risks

### R-07 · Delivery on Oracle, MMBL's preferred database
**Likelihood** Medium · **Impact** High · **Residual** Medium

RFP §4b states a preference for **Oracle** or MSSQL. Oracle differs materially from other engines
in exactly the areas this solution depends on: row-level access control is implemented through
Virtual Private Database rather than a policy statement, sequence and locking semantics differ,
and JSON handling and full-text search have their own syntax. A solution that assumes one engine
and is ported late is a solution that fails its isolation testing in UAT.

**Mitigation by architecture, not by porting.** All engine-specific behaviour is confined to a
single database dialect layer — row security, the session security context, advisory locking, JSON
typing and full-text search each have one Oracle implementation behind a common interface. The
application above that layer is identical on every engine, so Oracle is a configuration of the
data layer rather than a second codebase to maintain.

**The first Oracle deployment is a named acceptance gate at M1**, before any data is loaded. That
gate runs the complete schema migration, a cross-workspace isolation test proving that Virtual Private Database refuses a
read across the boundary, and a representative query workload. Passing it is a condition of proceeding
to UAT.

**Trigger.** Any migration failure, isolation failure or material performance difference at the
M1 Oracle gate.
**Response.** The dialect layer is corrected against the live instance while the programme
continues on the alternative engine; the application is unchanged either way, which is the reason
the seam exists.
**Owner.** Our engineering lead. **We ask MMBL for an Oracle instance in week one, not week six**
— this residual falls to Low the day we have one, and every week it is delayed is a week the risk
stays open.

### R-08 · Migrated legacy agreements do not reconcile
**Likelihood** Medium · **Impact** High · **Residual** Medium

Existing agreements have to arrive in the new repository complete and correct. Legacy contract
data is typically inconsistent — missing counterparties, ambiguous dates, documents whose
metadata disagrees with the document itself.

**Mitigation.** Migration is run as **three rehearsals before the live cut**, each producing a
reconciliation report that MMBL signs: counts by status and department, total contract value,
and a checksum of every migrated document. A record that fails validation is quarantined with the
reason rather than loaded with a blank field, because a silently incomplete repository is worse
than a visibly incomplete one.

**Trigger.** Any reconciliation variance not explained by the quarantine list.
**Response.** The cut is rescheduled. Data quality is MMBL's to correct; the reporting that makes
it visible is ours.
**Owner.** MMBL data owner, with our migration lead supporting.

### R-09 · The HSM is not available when the PKI needs it
**Likelihood** Medium · **Impact** High · **Residual** Low

Per-signatory certificate signing to FIPS 140-2 Level 3 requires a PKCS#11 hardware security
module. An HSM is a long-lead procurement item and it is MMBL's to supply.

**Mitigation by design.** Key custody is an interface with two implementations behind it, and
**no method that can export a private key exists on either**. Development and testing proceed on
a software keystore; moving to the HSM is a configuration change with no code change, so the
cutover is a discrete testable step rather than a dependency the whole schedule hangs on. The
platform's health endpoint reports continuously whether production signing is hardware-backed, so
the interim state cannot be quietly forgotten.

**Trigger.** No HSM on site by the end of week 3.
**Response.** Proceed on the software keystore; move HSM acceptance to a named gate; record in
the risk log that production signing is not yet hardware-backed.
**Owner.** MMBL infrastructure, with our PKI lead supporting.

### R-10 · Performance targets are not met at ten-year scale
**Likelihood** Medium · **Impact** Medium · **Residual** Low

Search across a ten-year corpus and sub-200ms revocation responses are architectural commitments
that remain targets until they are measured on production-shaped data. Measuring against a
synthetic set of a few hundred rows produces a number nobody should trust.

**Mitigation.** Load and soak testing is a milestone with its own acceptance criteria, run
against a corpus sized to MMBL's stated ten-year volumes rather than a demonstration set. The
design decisions that carry the targets — indexed single-row revocation lookups, an
elliptic-curve responder key chosen because signature cost dominates the response, and a hot/cold
retention split so the searched set does not grow without bound — are stated in advance so they
can be reviewed before they are measured.

**Trigger.** Any measured 95th percentile above target.
**Response.** The two most likely causes are index selection and revocation-list size; both have
known remedies, which is why the residual is Low rather than unknown.
**Owner.** Our engineering lead.

### R-11 · High availability and disaster recovery depend on MMBL's platform
**Likelihood** Medium · **Impact** High · **Residual** Medium

The RFP requires high availability across tiers and a DR-ready deployment. The application tier
scales horizontally and is delivered with the manifests to do so. **Database high availability,
storage replication and the DR site itself are MMBL's platform**, and no application design can
substitute for them.

**Mitigation.** The boundary is stated at design rather than discovered at a drill: what the
solution provides, and what the bank's infrastructure must provide, are documented and agreed in
the first four weeks. Backups are scripted, encrypted and **restore-verified** rather than merely
taken, because an unverified backup is an untested assumption. A documented DR drill with a
measured recovery time is a delivery milestone, not a post-go-live intention.

**Trigger.** Recovery objectives not met at the DR drill.
**Response.** The gap is attributed to application or platform explicitly, and the owning party
remediates before go-live sign-off.
**Owner.** MMBL infrastructure, with our engineering lead accountable for the application tier
and the drill evidence.

### R-12 · Ten-year retention is not sustainable in practice
**Likelihood** Low · **Impact** Medium · **Residual** Low

Retaining a decade of agreements with twelve months instantly searchable is a requirement that
degrades slowly: the system works at go-live and becomes unusable in year four, when nobody is
watching.

**Mitigation.** Archival and purge run as scheduled operations from day one, not as a project in
year three, so the behaviour is exercised continuously rather than first attempted at scale. An
archived agreement leaves the active search set but stays retrievable by reference. Legal hold
overrides retention and is scoped per matter, so releasing one matter cannot expose a record
another matter still protects — the failure a single flag cannot avoid, and one whose consequence
(evidence destroyed) is unrecoverable.

**Trigger.** Archive or purge failing to run, or a hold release exposing a held record.
**Response.** Purge is suspended until the cause is found; retention errs towards keeping.
**Owner.** MMBL records management, with our engineering lead accountable for the mechanism.

---

## 4. Security risks

### R-13 · A control is present in configuration but not effective in practice
**Likelihood** Medium · **Impact** High · **Residual** Low

The dangerous security failure is not an absent control, it is one that appears enabled and is
not: encryption switched off on one environment, a scanner unreachable so uploads pass unchecked,
a log feed silently disconnected. Each looks correct on a checklist.

**Mitigation.** Controls report their own state rather than being assumed. Where a control cannot
verify itself from inside the application — full-disk or tablespace encryption is the honest
example — it is recorded as **an operator attestation rather than a measurement**, and named as
such, instead of being claimed as verified. Where failing open would be a silent loss of
protection, the control fails closed: the upload scanner refuses the file if the scanning service
is unreachable, because a scanner that waves files through when it is down protects nothing at
precisely the moment it matters.

**Trigger.** Any control reporting a degraded state, or any environment whose configuration
differs from the agreed baseline.
**Response.** Environments are rebuilt from the same declarative configuration rather than
hand-corrected, so the drift cannot recur.
**Owner.** Joint — MMBL security operations and our engineering lead.

### R-14 · Third-party penetration test findings arrive too late to remediate
**Likelihood** Medium · **Impact** High · **Residual** Medium

An independent VAPT is required. If it is scheduled immediately before go-live, a High finding
becomes a choice between delaying the launch and accepting a known vulnerability.

**Mitigation.** Automated security testing runs continuously through the build — static analysis,
dynamic scanning against a live instance, dependency auditing, container scanning and secret
detection — so the independent test starts from a codebase that has already had the mechanical
findings removed and can spend its time on logic. Remediation turnaround is committed in the SLA:
48 hours for critical.

**Trigger.** Any High or Critical finding raised within three weeks of the go-live date.
**Response.** Remediate and retest, or go live with a documented compensating control accepted in
writing by MMBL's CISO. Not silently.
**Owner.** MMBL security, who appoint the testing vendor. **This residual falls to Low if the
test can be scheduled earlier than the plan currently assumes**, and we will ask for that.

### R-15 · A dependency vulnerability is disclosed during the engagement
**Likelihood** High · **Impact** Medium · **Residual** Low

Over a twelve-week programme, a CVE in some third-party component is close to certain. This is
expected rather than exceptional, and is treated as such.

**Mitigation.** Every build inventories its dependencies, produces a signed software bill of
materials, and fails on a known-vulnerable component rather than warning about one. Version
pinning is deliberate and the reason for each pin is recorded, so an upgrade that would break a
dependent library is caught by the build rather than in production.

**Trigger.** Any advisory affecting a component in the delivered bill of materials.
**Response.** Assess exploitability in context, patch within the SLA turnaround, and notify MMBL
with the assessment — including when the conclusion is that the vulnerable path is not reachable.
**Owner.** Our engineering lead.

### R-16 · A defect corrupts the audit trail
**Likelihood** Low · **Impact** Critical · **Residual** Low

Every compliance claim in this proposal rests on the audit trail being complete and unaltered. A
corrupted trail cannot be repaired after the fact, because the thing that would prove the repair
is the trail.

**Mitigation.** Each entry is chained by HMAC to its predecessor and ordered by a monotonic
sequence rather than by timestamp — two entries written in the same clock tick would
otherwise be ordered arbitrarily, and a chain that verifies under one ordering and not another
proves nothing. An independent verification tool is **delivered to MMBL**, so the bank can
recompute the chain without our participation and identify the first divergent entry.

**Trigger.** Any verification failure.
**Response.** The verifier names the first broken entry; the surrounding transactions are
investigated. A false alarm is treated as a defect in the mechanism and fixed, because a tamper
alarm that cries wolf is worse than none — the first real alert gets dismissed with the rest.
**Owner.** Our engineering lead.

---

## 5. Integration risks

### R-17 · Identity integration with Entra ID does not behave as documented
**Likelihood** Medium · **Impact** Medium · **Residual** Low

Single sign-on and automated user provisioning depend on MMBL's identity platform, its metadata,
its claim mapping and its group structure. Identity integrations rarely fail on protocol; they
fail on a claim that is not where the documentation says it is.

**Mitigation.** Both federation protocols are supported, so the integration does not depend on
MMBL choosing one. Signature verification is delegated to a maintained cryptographic library
rather than hand-rolled, because assertion verification is where identity integrations get
exploited. Role mapping from directory groups is configuration, not code, so a change to MMBL's
group structure is a settings change and not a release.

**Trigger.** Federation or provisioning failing in the integration test window.
**Response.** Password authentication with multi-factor remains available throughout, so identity
is never on the critical path for go-live.
**Owner.** MMBL identity team, with our integration lead supporting.

### R-18 · Gateway, monitoring and notification integrations depend on MMBL infrastructure
**Likelihood** Medium · **Impact** Medium · **Residual** Low

The solution must sit behind MMBL's API gateway, feed the bank's SIEM in a defined format, relay
mail through the bank's servers and send OTP messages through the bank's SMS provider. Each is a
credential, an endpoint or a route that only MMBL can supply.

**Mitigation.** Each integration is built against a documented interface with a working default,
so nothing is blocked waiting for credentials — the SIEM feed, the mail relay and the SMS adapter
each have a local mode that exercises the full path. Delivery state is **recorded rather than
assumed**: a message that failed to send is a visible failed record, not an absence. Where a
collector is unavailable for a period, the feed can be replayed for the gap rather than losing
those events.

**Trigger.** Any integration credential outstanding at its milestone in the dependency schedule.
**Response.** The affected capability is demonstrated in local mode and its acceptance moves to a
named later gate, recorded rather than quietly deferred.
**Owner.** MMBL project manager for the dependencies; our integration lead for the adapters.

### R-19 · A sub-contractor's security posture becomes MMBL's exposure
**Likelihood** Low · **Impact** High · **Residual** Low

RFP §4d requires a list of sub-contractors and confirmation of their adherence to SBP and
organisational security standards. Under the outsourcing framework, their weaknesses become the
bank's.

**Mitigation.** Any sub-contractor involved in delivery is named at bid, with security obligations
flowed down contractually and access granted on a least-privilege, time-bounded basis. Access to
MMBL environments is auditable and revocable by MMBL directly, not only through us.

**Trigger.** Any change to the sub-contractor list during delivery.
**Response.** Notify MMBL in advance and re-confirm the flow-down before access is granted.
**Owner.** Our engagement director.

---

## 6. Delivery and schedule risks

### R-20 · Dependencies owed by MMBL arrive late
**Likelihood** High · **Impact** High · **Residual** Medium

This is the single most likely cause of schedule slip on an on-premises programme, and most of
it sits outside our control: environments, database instances, identity metadata, gateway routes,
certificates, the HSM, SMS and SIEM credentials, and named business users for configuration and
UAT.

**Mitigation.** Every dependency is listed with its owner, the milestone it blocks, and the date
it is needed — and that list is reviewed **weekly, item by item**, from week one rather than at
the first slip. Wherever a dependency can be worked around, it is: each integration has a working
default so development is never blocked, only acceptance is.

**Trigger.** Any dependency passing its needed-by date.
**Response.** Escalate at the next steering group with the milestone impact stated in days.
Continue on the default; move only the acceptance.
**Owner.** MMBL project manager. **This is the risk most likely to move the go-live date, and it
is the one we will be most persistent about.**

### R-21 · Scope grows during configuration
**Likelihood** High · **Impact** Medium · **Residual** Low

Configuration workshops surface real needs that were not in the RFP. Refusing them all produces a
system nobody wants; accepting them all produces a system that does not ship.

**Mitigation.** The requirement identifiers in the Compliance Matrix are the scope baseline, and
they are the same identifiers used in the acceptance criteria and the UAT scripts. Anything not
carrying one is a change, sized and scheduled rather than absorbed. Much of what surfaces is
configuration the platform already supports — templates, clauses, approval rules, roles — and
those are delivered as configuration inside the existing scope rather than as change requests.

**Trigger.** Any request that does not map to a requirement identifier.
**Response.** Size it, and either schedule it into a later release or take it through change
control. Never absorb it silently — silent absorption is how a delivery date moves without anyone
deciding to move it.
**Owner.** Joint — both project managers.

### R-22 · The architecture is judged not to meet the stated microservices preference
**Likelihood** Medium · **Impact** Low · **Residual** Low

RFP §4b expresses a preference for a microservices deployment. The solution is a modular
application with a separate asynchronous worker tier, which is a deliberate deviation.

**Mitigation.** The deviation is declared in the technical response with its reasoning rather
than left for an evaluator to notice: the operational requirement is an on-premises deployment the
bank's own team can run, and a distributed service mesh multiplies the operational surface without
serving any requirement in this RFP. The properties the preference exists to secure —
independent scaling of the heavy asynchronous work, horizontal scaling of the request tier,
API-driven modularity — are delivered.

**Trigger.** Clarification that a microservices topology is mandatory rather than preferred.
**Response.** Answer at the clarification stage with the decomposition path and its operational
cost, so the trade is MMBL's to make with the facts in front of them.
**Owner.** Our engineering lead.

### R-23 · Key personnel leave mid-engagement
**Likelihood** Low · **Impact** Medium · **Residual** Low

A twelve-week programme is short enough that one departure is disruptive and long enough that one
is possible — on either side.

**Mitigation.** No component has a single person who understands it. Design decisions and their
reasoning are written down with the code they govern rather than held in someone's head, and
every environment is built from declarative configuration so it can be rebuilt by someone who has
never seen it before.

**Trigger.** Any named key person leaving the engagement.
**Response.** A named replacement within five working days, with a documented handover.
**Owner.** Both parties, for their own staff.

### R-24 · The system is delivered and not adopted
**Likelihood** Medium · **Impact** High · **Residual** Low

The commonest way a contract management programme fails is not technical. It is delivered,
trained once, and quietly worked around, with agreements still circulating by email.

**Mitigation.** Training is not a single week. An onsite programme covers the named cohorts at
go-live — the RFP's fifteen-plus resources — and a training system stays inside the product
afterwards, because the people who need it most join after launch week. Contextual help sits at
the point of use rather than in a manual nobody opens, and adoption is measured from the audit
trail, so a department that has stopped using the system is visible within a fortnight rather
than at the annual review.

**Trigger.** Adoption in any department below the agreed threshold at the 30- or 60-day review.
**Response.** Targeted intervention for that department rather than a repeat of the general
training.
**Owner.** MMBL business owner, with our training lead supporting.

### R-25 · The support model is not operational at go-live
**Likelihood** Low · **Impact** Medium · **Residual** Low

Round-the-clock support with defined response and resolution times is a commitment that has to
exist as a working rota, contact path and escalation chain on the first day of production, not as
a clause.

**Mitigation.** The support model is stood up and **exercised during UAT**, not at go-live: the
same channels, the same severity definitions and the same escalation path are used for UAT
defects, so the process is proven with real tickets before it protects production. Service credits
attach automatically to a missed target rather than being discretionary.

**Trigger.** Any severity-1 raised during UAT that does not follow the documented path.
**Response.** Correct the process during UAT, where it costs nothing.
**Owner.** Our service delivery manager.

---

## 7. Operational risks after go-live

### R-26 · Data loss
**Likelihood** Low · **Impact** Critical · **Residual** Low

**Mitigation.** Backups are scripted, encrypted and **restore-verified** — a backup that has
never been restored is an assumption, not a control. Documents and database are backed up on the
same schedule so a restore produces a consistent state rather than records pointing at documents
that no longer exist. Recovery objectives are agreed and proven by drill.
**Trigger.** Any backup failure, or any restore test that does not reconcile.
**Owner.** MMBL infrastructure.

### R-27 · A scheduled job stops without anyone noticing
**Likelihood** Medium · **Impact** Medium · **Residual** Low

Renewal reminders, obligation escalations, revocation-list publishing, archival and retention all
run unattended. Their failure mode is **silence** — nothing breaks, notices simply stop, and the
first symptom is a renewal missed months later.

**Mitigation.** Every scheduled job exports its own outcome — success, failure, duration, and how
many items it acted on — so "the sweep ran and found nothing" is distinguishable from "the sweep
did not run". That distinction is the entire control; without it a dead job and a quiet one look
identical. Alert thresholds are agreed with MMBL operations and handed over with the runbooks.
**Trigger.** Any job with no successful run inside its expected window.
**Owner.** MMBL operations, with our engineering lead accountable for the instrumentation.

### R-28 · A certificate or revocation list expires unnoticed
**Likelihood** Medium · **Impact** High · **Residual** Low

An expired issuing certificate stops all signing. An expired revocation list causes relying
parties to reject signatures that are perfectly valid — the same visible outcome as a compromise,
which is why it gets escalated as one.

**Mitigation.** Revocation lists are republished at **half their validity window**, so a single
failed publication still leaves a valid list in place for another full cycle rather than causing
an immediate outage. Certificate expiry is monitored with escalating notice, and the platform's
health endpoint reports the nearest expiry continuously.
**Trigger.** Any certificate within 30 days of expiry, or any failed republication.
**Owner.** MMBL operations, with our PKI lead supporting.

---

## 8. Risk summary

| ID | Risk | Likelihood | Impact | Residual | Owner |
|---|---|---|---|---|---|
| R-01 | SBP alignment interpreted differently | Medium | High | Low | MMBL compliance |
| R-02 | Outsourcing governance obligations | Low | High | Low | Engagement director |
| R-03 | eSignature evidence challenged | Low | Critical | Low | MMBL legal |
| R-04 | Accreditation expectations exceed a product | Medium | Medium | **Medium** | Engagement director |
| R-05 | Sworn undertaking as drafted | Medium | High | **Medium** | Joint — counsel |
| R-06 | Data residency breach | Low | Critical | Low | MMBL infrastructure |
| R-07 | Delivery on Oracle | Medium | High | **Medium** | Engineering lead |
| R-08 | Migration does not reconcile | Medium | High | **Medium** | MMBL data owner |
| R-09 | HSM unavailable | Medium | High | Low | MMBL infrastructure |
| R-10 | Performance at ten-year scale | Medium | Medium | Low | Engineering lead |
| R-11 | HA and DR depend on MMBL platform | Medium | High | **Medium** | MMBL infrastructure |
| R-12 | Retention unsustainable in practice | Low | Medium | Low | MMBL records management |
| R-13 | Control present but not effective | Medium | High | Low | Joint |
| R-14 | Late penetration test findings | Medium | High | **Medium** | MMBL security |
| R-15 | Dependency vulnerability | High | Medium | Low | Engineering lead |
| R-16 | Audit trail corruption | Low | Critical | Low | Engineering lead |
| R-17 | Identity integration behaviour | Medium | Medium | Low | MMBL identity team |
| R-18 | Gateway, SIEM, mail and SMS dependencies | Medium | Medium | Low | MMBL project manager |
| R-19 | Sub-contractor security posture | Low | High | Low | Engagement director |
| R-20 | MMBL dependencies arrive late | High | High | **Medium** | MMBL project manager |
| R-21 | Scope growth during configuration | High | Medium | Low | Joint |
| R-22 | Architecture deviation from microservices | Medium | Low | Low | Engineering lead |
| R-23 | Key personnel leave | Low | Medium | Low | Both |
| R-24 | System delivered but not adopted | Medium | High | Low | MMBL business owner |
| R-25 | Support model not operational | Low | Medium | Low | Service delivery manager |
| R-26 | Data loss | Low | Critical | Low | MMBL infrastructure |
| R-27 | Silent scheduled-job failure | Medium | Medium | Low | MMBL operations |
| R-28 | Certificate or revocation list expiry | Medium | High | Low | MMBL operations |

### The seven that carry Medium residual

These are the ones worth a steering group's attention. **None is closable by us acting alone**,
which is precisely why they are named rather than written down to Low.

| Risk | What closes it | When |
|---|---|---|
| **R-07 Oracle** | An Oracle instance to certify against | Falls to Low the week we are given one. **We ask in week one.** |
| **R-20 Late dependencies** | The weekly dependency review being attended and acted on | Continuous, from week one |
| **R-08 Migration** | The first reconciliation rehearsal passing | Before the live cut |
| **R-11 HA and DR** | A DR drill with a measured recovery time | Before go-live sign-off |
| **R-14 Late VAPT** | Scheduling the independent test earlier | As soon as MMBL's vendor has availability |
| **R-05 Sworn undertaking** | A legal reading of the final wording | **Before submission** — a bid-validity question |
| **R-04 Accreditation** | MMBL confirming whether a product-level certificate is required | At clarification |

Two of these — R-05 and R-04 — should be raised at the clarification stage rather than after
award. We would rather ask an awkward question now than discover the answer later.

---

## 9. Governance

| Forum | Frequency | Attendees | Purpose |
|---|---|---|---|
| Delivery stand-up | Daily | Both delivery teams | Blockers, not status |
| Dependency review | Weekly | Both project managers | The dependency schedule, item by item, against its milestone |
| Risk review | Fortnightly | Steering group | This register — residuals, triggers fired, new entries |
| Steering group | Monthly | Sponsors | Decisions needing authority, and anything Medium residual or worse |

**Three rules govern this register.**

A risk is only closed when its **trigger can no longer fire**, not when the milestone it was
attached to passes. A risk that is accepted rather than mitigated is recorded as accepted, **with
the name of the person who accepted it**. And a new risk is added the day it is identified, not
at the next review — a register that is only updated on a schedule is a register that is always
a fortnight out of date.
