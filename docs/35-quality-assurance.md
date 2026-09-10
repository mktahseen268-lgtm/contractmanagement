# Quality Assurance Plan

**Annexure item 10. Weighted at 11% — joint-heaviest with Risk Mitigation.**

The RFP asks for test-driven development with UAT scripts. This document states how quality is
produced rather than inspected: what is tested, by whom, at which gate, and what happens when a
gate fails.

The distinction matters. A QA plan describing a testing *phase* at the end is describing when
defects will be found, not how they will be prevented. What follows describes gates that a change
cannot pass without meeting.

---

## 1. The assurance regime

Quality is enforced by gates a change cannot pass, not by a testing phase at the end. Every one
of the following is applied to every change, on every environment, for the life of the
engagement.

| Layer | Standard enforced | Applied |
|---|---|---|
| Automated functional tests | Every requirement identifier in the Compliance Matrix is covered by at least one automated test | Every change |
| End-to-end journeys | Both RFI business journeys exercised over the real API, end to end | Every change |
| Coverage | ≥ 80% on the service modules that carry consequential logic | Every change, as a blocking gate |
| Static analysis | Linting, type checking, security static analysis and OWASP Top 10 rules | Every change |
| Dynamic analysis | Automated scanning against a running, migrated instance | Every change |
| Supply chain | Bill of materials, dependency audit, container scan and secret detection | Every build |
| Database engines | The full schema migration and a cross-workspace isolation test on the target engine | Every change |
| Accessibility | Automated WCAG 2.1 AA conformance checks at desktop and phone viewports | Every change |
| Performance | Load and soak against a corpus sized to MMBL's ten-year volumes | M5, and before each release |
| Independent security | Third-party penetration test with a 48-hour critical remediation commitment | M5 |

**Every gate blocks.** A gate that warns is a gate that is ignored by the third sprint, so none of
these produces a warning — a change that fails any of them does not reach an environment MMBL can
see.

---

## 2. The testing pyramid, and what each level is actually for

### 2.1 Unit and service tests — the base

Cover a module in isolation. Fast, numerous, run on every save.

The rule applied throughout: **a test asserts the behaviour that matters, not the implementation
that produces it.** A test that breaks when a function is renamed but not when the logic inverts
is a maintenance cost with no benefit.

Every non-trivial test carries a docstring saying *why the property matters*, because a failing
assertion six months from now needs to tell the person reading it what breaks in the real world
if they "fix" it by changing the expectation. For example, on the certificate-expiry rule:

> Computed from the date, never stored as a status — a status needs a sweep to stay true, and a
> certificate that stays 'valid' because the sweep did not run is the failure this is meant to
> prevent.

### 2.2 Integration tests — the middle

Cover a service against a real database, real encryption keys and a real object store. These are
where the defects that unit tests structurally cannot see get caught: transaction boundaries,
`autoflush` behaviour, dialect differences, index constraints.

**Encryption keys are configured in the test environment deliberately.** Without them the
encrypted-column type falls back to tagged plaintext, and a test asserting "this value is not
readable in the database" passes for the wrong reason — or fails and gets ignored. Which is
exactly what had happened: the test proving signing tokens are not stored in plaintext had been
failing for months, and the reason was the test environment, not the code.

### 2.3 Journey tests — the top

Both RFI journeys walked end to end over the real HTTP surface. Nothing is called directly; every
step is a request a browser could make.

They exist because the unit suites cover each service in isolation and **nothing else covers
whether the pieces line up** — that a contract generated from a template can actually be
submitted, that approval actually unblocks sending, that the link in the email actually signs.

Each journey test names the requirement IDs it satisfies (`SOW-04`, `BB-01`, …), so a passing run
is traceable to the RFP clause. The UAT book in §5 is generated from them.

### 2.4 What automated testing does *not* cover

Stated because a QA plan that implies full coverage is not one:

- Whether the reading order of a screen makes sense to a person using a screen reader
- Whether wording is understandable to a branch customer who is not digitally literate
- Whether an approval matrix matches MMBL's actual delegation policy
- Business-logic authorisation flaws that need an adversarial human
- Anything about the HSM hardware, as opposed to the code path that talks to it

These need people. §4 and §6 say which people.

---

## 3. Quality gates

Every gate blocks. A gate that warns is a gate that gets ignored by the third sprint.

| # | Gate | Blocks | Runs |
|---|---|---|---|
| G1 | Lint (`ruff`) and type-check (`mypy`) | Merge | Every push |
| G2 | Full test suite against the target database platform | Merge | Every change |
| G3 | Migration matrix — up, down and up again on Oracle | Merge | Every change |
| G4 | PKCS#11 tests against a real token (SoftHSM2) | Merge | Every push |
| G5 | SAST — `bandit`, `semgrep p/owasp-top-ten` | Merge | Every push |
| G6 | Secret scanning (`gitleaks`) | Merge | Every push |
| G7 | Dependency and container scanning, SBOM | Merge | Every push |
| G8 | DAST — ZAP baseline against a live migrated instance | Merge | Every push |
| G9 | Accessibility — axe, zero serious or critical, two viewports | Merge | Every push |
| G10 | Web build and type-check | Merge | Every push |
| G11 | All of the above green | Deploy | Every push |

### 3.1 On thresholds that are set to pass

Two gates use a threshold rather than zero, and both say why in the code:

**DAST** fails on serious and critical, prints moderate and minor. The known-open accessibility
items sit at moderate; a job red on its first run is disabled by its second week. `.zap/rules.tsv`
lists every non-failing rule *with the reason it does not fail*, so a suppression is a decision
somebody wrote down rather than a threshold quietly lowered.

**Accessibility** uses the same threshold, and currently reports **zero violations at any
impact**. That was not achieved by choosing a lenient threshold — the first run failed on three
pages, and the contrast and label defects it found were fixed rather than excluded.

---

## 4. Roles

| Role | Responsibility |
|---|---|
| Engineer | Writes the test with the change. A change without a test does not merge. |
| Reviewer | Reviews the test as carefully as the code — a wrong assertion is worse than none, because it looks like coverage. |
| QA lead | Owns the UAT book, defect triage, and the gate definitions. |
| Security lead | Owns G5–G8, VAPT coordination, and remediation sign-off. |
| MMBL business owner | Owns UAT acceptance. Sign-off is theirs, not ours. |
| MMBL data owner | Owns migration reconciliation acceptance. |

**Testing is not a separate team's job.** There is no hand-off point at which quality becomes
somebody else's problem, because a hand-off is where accountability goes to die.

---

## 5. UAT

### 5.1 Structure

The UAT book is a numbered, executable test book keyed to the requirement IDs in the Scope &
Technical Specification. Each script states preconditions, numbered steps, the expected result,
and the requirement it proves.

```
UAT-SOW-04-01   Generate an agreement from an approved template
  Requirement   SOW-04 — guided drafting with intake questions
  Precondition  An approved template exists with required fields
  Role          Author

  1. Open Templates and select "BBCORP Merchant Agreement".
  2. Leave "Merchant discount rate" blank. Submit.
     EXPECTED: generation is refused and the message names the missing field.
  3. Enter 1.75 and submit.
     EXPECTED: a draft is created; the body shows 1.75; no {{placeholder}} remains.

  Proves        A gap cannot reach an executed document.
  Automated by  test_journey_1_bbcorp_intake_to_execution (step 3-4)
```

Every script carries an **Automated by** line, or explicitly says `Manual — requires human
judgement`. That column is how MMBL can see which acceptance rests on a machine and which rests
on a person.

### 5.2 Entry and exit

**Entry:** all gates green; migration into UAT reconciled; test data loaded; trainees briefed.
**Exit:** every script executed with a recorded result; no open severity-1 or severity-2 defects;
sign-off by the MMBL business owner.

### 5.3 Defect severity

| Severity | Definition | Response | Blocks go-live |
|---|---|---|---|
| **S1** | Data loss, security exposure, or an agreement cannot be executed | Immediate, hotfix path | Yes |
| **S2** | A core journey is blocked with no workaround | Within the sprint | Yes |
| **S3** | A journey works but a step is wrong or awkward; a workaround exists | Scheduled | No |
| **S4** | Cosmetic, or an enhancement | Backlog | No |

Severity is assigned by the QA lead and the MMBL business owner **together**. Unilateral severity
assignment by the supplier is how S2s become S3s in week eleven.

---

## 6. Performance and resilience testing

Run at M5, against production-shaped data. Measuring against a few hundred tidy rows produces a
number nobody should trust.

| Test | Target | Method |
|---|---|---|
| Concurrency | 100 concurrent users sustained one hour, within response targets | Ramped load against UAT |
| Signature throughput | A day's peak (≈1,200 signatures, 3× the daily mean) with no failed or duplicated signature | Soak, with the audit trail reconciled afterwards |
| OCSP latency | p95 < 200 ms | Sustained responder load against a populated CRL |
| Search latency | p95 < 500 ms across a ten-year corpus | Query mix against the migrated data set |
| Recovery | Restore within the 4-hour RTO | Full DR drill with the restored system verified working |
| Audit integrity | Chain verifies across the full migrated history | Verification over the full history |

**The signature soak is the one that matters most.** RFP §4a(ii) 4.4 asks for execution free from
signature failures, and a duplicated or lost signature is the failure mode with legal
consequences. The optimistic lock that prevents it is unit-tested; the soak is what proves it
under real concurrency.

---

## 7. Security testing

| Layer | Method | Frequency |
|---|---|---|
| Static | `bandit`, `semgrep p/owasp-top-ten` | Every push |
| Secrets | `gitleaks` over full history | Every push |
| Dependencies | `pip-audit`, `safety`, `npm audit` | Every push |
| Container | Trivy against the built image | Every push |
| Dynamic | ZAP baseline against a live instance | Every push |
| Penetration | Third-party, by a vendor MMBL appoints | M5, then annually |

**The ZAP baseline is passive and unauthenticated.** It finds missing headers, information
disclosure and TLS misconfiguration. It does not reach the authorisation logic — which, in a
system, is where the interesting bugs live. That surface is covered by the workspace
isolation, Virtual Private Database, separation-of-duties and need-to-know tests, and by the human penetration test.
Automated scanning finds roughly a third of what a qualified tester finds; it is a useful third
and not a substitute.

---

## 8. Regression policy

**Every defect that reaches UAT or production gets a test before it gets a fix.** Without it, the
same defect returns under a different name and the suite grows without getting safer.

This is not aspirational — the suite contains regression tests written for exactly this reason,
each naming the defect it prevents. Three examples, all found during construction:

- **Audit chain ordering** — two entries in the same clock tick could chain past each other,
  making deletion of the skipped entry undetectable. Test forces the tie through a time seam.
- **Audit chain within one transaction** — two entries in one request both claimed sequence 1,
  so verification reported tampering on an honest log. Test records two entries before a single
  commit and verifies.
- **Signing invitations committed on a rolled-back request** — the outbox row was written on its
  own connection, so a recipient could receive a link to an envelope that was never sent. Test
  drives the whole send path.

A supplier whose regression list is empty either has a very new codebase or has not been looking.

---

## 9. Documentation quality

Documentation is reviewed like code, in the same pull request as the change it describes.

Two standards are enforced:

**Say what is not done.** Every architecture document has a "known limits" section, and it is not
decorative — `docs/PKI-ARCHITECTURE.md` states that SoftHSM2 proves the code path and not the
hardware; `docs/32-accessibility.md` lists four unresolved criteria with their impact;
`docs/30-tde.md` says the application cannot verify filesystem encryption from inside a
connection and records TDE as an operator attestation rather than a measurement.

**Explain the reason, not the mechanism.** A comment restating what the next line does is noise.
A comment saying why the obvious approach was rejected is the thing that stops somebody
reintroducing the bug.

---

## 10. Metrics

Reported fortnightly at the risk review.

| Metric | Target | Why this one |
|---|---|---|
| Gate pass rate on first attempt | > 85% | Below this, the gates are being used as the test cycle |
| Mean time to green after a red build | < 4 hours | A long-red pipeline trains people to ignore it |
| Escaped defects (found in UAT, not CI) | Trending down | The only real measure of whether the gates are catching things |
| S1/S2 defects open | 0 at any milestone gate | Non-negotiable |
| Coverage on service modules | ≥ 80% | Named modules, not a repository-wide average that hides gaps |
| Regression tests added per escaped defect | 1 or more | §8, measured |

**Coverage is deliberately scoped to service modules.** A repository-wide percentage is easy to
inflate with generated code and configuration, and tells nobody whether the logic that matters is
tested. The measured modules are the engines: signing, workflow, authentication, PKI, retention,
merge, redline, access control.

---

## 11. Continuous improvement of the assurance regime

The gates above are the baseline, not the ceiling. Three commitments extend them over the
engagement, each with a milestone rather than an intention.

1. **Coverage widens from the engines outward.** The blocking gate applies first to the modules
   carrying consequential logic — signing, workflow, authentication, PKI, retention, drafting and
   access control — and is extended across the infrastructure adapters during M4, so the same
   standard applies to the whole codebase by UAT.
2. **Accessibility testing extends into the authenticated application.** Automated conformance
   checks run against the signed-out surfaces from the first build and are extended to the
   signed-in application during M4, complemented by assisted-technology review with a person,
   because automation finds roughly a third of accessibility defects and no more.
3. **Performance and resilience become continuous.** The load, soak and disaster-recovery
   exercises at M5 establish the baseline; from that point they run against every release
   candidate, so a regression is caught by the pipeline rather than by a user at month-end.

**The regression policy in §8 governs all three**: every defect found in UAT or in production
results in an automated test that would have caught it, added before the fix is accepted. The
suite therefore grows in exactly the places where defects have actually occurred, rather than
where they were expected.
