# Training Plan

**Annexure item 9. Weighted at 8%. The RFP requires onsite training for a minimum of fifteen
resources.**

Onsite training happens once. The people who attended change role, leave, or forget — and
eighteen months later a new joiner needs exactly what the original fifteen were taught, from
somebody who was not there. This plan therefore has two halves that are equally weighted: the
onsite programme, and the in-product training system that outlives it.

---

## 1. What "fifteen resources trained" actually means

The requirement is easy to satisfy on paper and easy to fail in substance. Three commitments make
the difference:

**Attendance, not registration.** The training register records who *turned up*, separately from
who signed up. A list of intended attendees cannot answer "have fifteen people been trained",
which is the question being asked. The system enforces the distinction — registration and
attendance are separate fields, and only attendance is reported.

**Certification, not attendance alone.** Sitting in a room is not evidence of competence. Each
course ends in an assessment with a pass mark; the certificate names the score and the date.

**Certificates expire.** A certificate valid forever stops being evidence the moment the process
it covers changes. Each course sets its own validity period — twelve months by default — and
expiry is computed from the date rather than stored as a status that needs a sweep to stay true.
Somebody whose certificate lapsed last month has not been trained on the current process, and the
completion report will not count them.

---

## 2. Audiences and what each one needs

Training is by role, because a contract author and a PKI administrator share almost nothing.

| Audience | People | Duration | Delivery |
|---|---|---|---|
| **Contract authors** — Business, Procurement | 6 | 1 day | Onsite workshop, hands-on |
| **Reviewers and approvers** — Legal, Finance, department heads | 4 | ½ day | Onsite workshop |
| **Legal content owners** — clause library, templates, playbooks | 2 | 1 day | Onsite, deep |
| **System administrators** — configuration, roles, PKI, audit | 2 | 2 days | Onsite, deep |
| **Branch staff** — assisted customer signing | Cascade | 1 hour | Train-the-trainer + printed guide |
| **Executives** — dashboards and MIS | 3 | 1 hour | Onsite briefing |
| **Named minimum** | **≥ 15** | | |

The branch population is unbounded and turns over constantly, so it is deliberately handled by
train-the-trainer plus the printable step-by-step guide rather than by a session nobody can
repeat. Two branch trainers are included in the named fifteen.

---

## 3. The onsite programme

Delivered in weeks 10–12, after UAT sign-off and before cutover. Training against a system that
is still changing teaches people things that will not be true at go-live.

### Day 1 — Contract authors
Origination from a template; structured intake and why generation refuses a gap; the three dates
and what each one drives; the counterparty record and why a typed name is not one; submitting for
approval; responding to requested changes; obligations and renewals.

**Practical:** each attendee originates, submits and executes a real agreement in the UAT
environment, end to end. Nobody leaves having only watched.

### Day 2 (morning) — Reviewers and approvers
The approval matrix and where authority comes from; reading playbook findings before reading the
document; the difference between rejecting and requesting changes, and why saying what would make
it acceptable ends the loop in one pass; delegation and what the record shows; SLA and escalation.

### Day 2 (afternoon) — Legal content owners
Template versioning and the approval gate; why generation reads the approved snapshot and never
the live draft; the clause library and approved alternatives; playbook rules — required,
prohibited, altered; **editing help text and knowledge-base articles without a release**, which is
the capability that keeps guidance correct after we leave.

### Days 3–4 — System administrators
Roles, custom roles and the permission model; separation of duties and step-up authentication;
the PKI console — CA health, RA queue, certificate lifecycle, trust anchors; **the key ceremony**,
rehearsed; audit log and chain verification; retention, archival and legal hold; SIEM feed and
what each severity means; backup and restore, rehearsed; reading the metrics and what each alert
means.

**Practical:** administrators perform a certificate revocation, a chain verification, and a
restore. These are the three things they will have to do under pressure, so they do each once
without it.

### Day 5 — Train-the-trainer and executive briefing
Branch trainers take the assisted-signing path themselves, then teach it back. Executives get
the dashboards, the MIS exports, and what the cycle-time figures do and do not mean.

---

## 4. The in-product half

Available from day one and permanently thereafter.

| Component | What it does |
|---|---|
| **Contextual help** | Explanations attached to fields that are not self-explanatory, written to say what the field *decides* rather than what it is called. Held in the database so Legal corrects wording without a release. |
| **Knowledge base** | Quick starts, playbooks and FAQs, seeded with real guides rather than placeholders. Self-hosted video — embedding a third-party player would tell that third party who read which internal playbook, and when. |
| **Training hub** | Courses with modules, an assessment, a certificate and an expiry. Progress is per person and resumable. |
| **Live session calendar** | Webinars and onsite sessions in one place, with the attendance register attached — so the calendar and the evidence are the same record. |
| **Completion report** | Who holds a current certificate, by course. Counts people, not enrolments, and counts only *valid* certificates. |
| **Guided actions** | Next-best-action on every agreement and on the dashboard. The best training is not needing to remember. |

Two courses ship configured and are marked required:

- **Contract lifecycle essentials** — four modules, five questions, 75% pass mark
- **Handling agreements securely** — three modules, four questions, 80% pass mark

Both are editable by MMBL. The shipped content is a starting point, not a constraint — and it is
real content, because a training hub that ships empty stays empty.

### On the assessment
The answer key never leaves the server. A quiz whose answers are delivered to the browser
certifies that somebody opened developer tools. Feedback after a failed attempt explains *why* the
right answer is right, for the questions that were wrong only — somebody who passed does not need
the marking scheme, and somebody who failed needs to know where to go back to.

A failed retake never revokes a certificate already earned. Losing a valid certification by trying
to improve on it would teach people not to retake, which is the opposite of the point.

---

## 5. Materials

| Material | Format | Audience |
|---|---|---|
| Role-based user manuals | PDF and in-product | All |
| Quick reference cards | Printed, one page | Authors, approvers |
| Administrator runbook | PDF | Administrators |
| Key ceremony script | PDF, controlled | Administrators |
| Customer signing guide | Printed, **English and Urdu** | Branch staff and customers |
| Assisted-signing staff card | Printed | Branch staff |
| Session recordings | Self-hosted video | All |

All materials are handed over in source form. Materials MMBL cannot edit become wrong the first
time a process changes, and then nobody trusts any of them.

### The customer guide is the one that matters most
It is printed, bilingual, and written for somebody who has never signed anything electronically.
It also tells branch staff what they must **not** do: do not sign on the customer's behalf, do not
enter the code sent to their phone, do not skip the reading step to save time. The signing record
shows what was displayed and for how long — a customer who was rushed can say so afterwards, and
the record will support them.

---

## 6. Post-go-live

| Activity | When | Delivered by |
|---|---|---|
| Hypercare — floorwalking support | Weeks 1–2 after go-live | Onsite, us |
| Refresher clinic | Month 2 | Remote |
| New-joiner onboarding | Continuous | In-product, self-service |
| Release briefings | Each release | Release notes in the knowledge base |
| Annual recertification | Yearly | In-product, triggered by expiry |
| Administrator deep-dive | Month 6 | Onsite, us |

Two years of onsite support after go-live is committed in the SLA. Training is part of that, not
a separate engagement.

---

## 7. How training is evidenced

The completion report is generated from the system, not compiled by hand.

| Evidence | Source |
|---|---|
| Named attendees per session | Attendance register — who turned up |
| Assessment scores | Training record per person |
| Certificates issued, with expiry | Certificate register |
| People holding a current certificate | Completion report, counting people not enrolments |
| Sessions delivered | Session calendar, past-dated and not cancelled |
| Knowledge-base usage | Article view counts |

Acceptance criterion `AC-10` is met when at least fifteen named resources appear in the attendance
register **and** hold a valid certificate. Attendance without certification does not satisfy it,
and neither does certification without attendance at the onsite programme.

---

## 8. What this plan does not claim

- **Training does not make a system adoptable.** If people work around it, the fault is the
  system's. Adoption is tracked as R-24 in the Risk Mitigation Strategy with a measurable
  trigger, not assumed to follow from training.
- **The branch population cannot be fully trained by us.** It is too large and turns over too
  fast. Train-the-trainer plus a printed guide is the honest mechanism; a claim to have trained
  every branch would not survive its first audit.
- **Urdu covers the interface and the customer guide, not the legal wording.** Help topics,
  articles and clause text are per-locale content that MMBL's legal team edits in the product.
  Machine-translated legal guidance presented as authoritative would be worse than English, which
  is why the interface flags an untranslated topic rather than hiding it.
