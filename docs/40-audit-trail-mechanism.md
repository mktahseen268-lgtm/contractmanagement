# Audit Trail Mechanism

**Annexure item 8.** How the audit trail works, what it can and cannot prove, and how an auditor
verifies it independently.

This is the mechanism the rest of the submission rests on. Every claim about who approved what,
who signed when, and what a document said at the time is a claim about this record.

**A note on deployment.** MMBL's installation is dedicated and on-premises: it holds MMBL's
data and nothing else. The platform nevertheless carries a **workspace** boundary on every
record, enforced by the database rather than by application code, and each workspace keeps its
own independent chain. That is deliberate and worth keeping in a single-bank deployment: it
means a subsidiary or a ring-fenced business unit can be separated later as a configuration
rather than a re-architecture, and it is a second barrier under the application's own access
controls in the meantime.

---

## 1. What is recorded

**Every state-changing action.** Not a sample, not the ones somebody remembered to instrument —
the rule enforced in review is that a service which changes state calls `add_audit_entry`.

| Field | Purpose |
|---|---|
| Sequence | Monotonic, assigned under a lock. **The ordering authority** — see §3 |
| Workspace | Which workspace the entry belongs to — see below |
| `actor_id`, `actor_name` | Who. The name is denormalised so the record survives the user being renamed or deactivated |
| `action` | What, as a dotted verb: `contract.approved`, `pki.certificate_revoked`, `auth.session.reuse_detected` |
| `object_type`, `object_id`, `object_label` | The thing acted on, with a human-readable label captured at the time |
| `meta` | Structured detail specific to the action |
| `ip` | Where from |
| `at` | When, UTC |
| `prev_hash` | The preceding entry's hash |
| `row_hash` | HMAC over this entry plus `prev_hash` |

### Categories

| Category | Examples |
|---|---|
| Authentication | Sign-in, failure, lockout, MFA, **refresh-token reuse** |
| Authorisation | Role change, permission grant, break-glass, separation-of-duties refusal |
| Contract lifecycle | Created, submitted, approved, rejected, sent, signed, activated, terminated |
| Document | Version created, restored, exported, downloaded |
| Signature | Envelope created, sent, viewed, signed, declined, voided, completed |
| PKI | CA provisioned, request approved, certificate issued, renewed, suspended, revoked |
| Data governance | Retention purge, archive, legal hold placed and released |
| Configuration | Template approved, clause changed, workflow modified, help text edited |
| Security | Step-up satisfied or failed, sanctions hit, antivirus block |

---

## 2. Append-only

There is no update or delete path. No endpoint modifies an audit entry, no service exposes one,
and no administrative screen offers it.

**That is a property of the application, not of the database.** A database administrator with
direct access can still issue a `DELETE`. What the mechanism guarantees is not that tampering is
impossible — it is that **tampering is detectable**, which is a different and more honest claim.

---

## 3. The hash chain

Each entry carries `prev_hash`, the hash of the entry before it in the same chain, and
`row_hash`:

```
row_hash = HMAC-SHA256(audit_chain_key, prev_hash || canonical(entry))
```

`canonical(entry)` is a deterministic serialisation of the fields — same input, same bytes, every
time, on every platform.

Altering any field changes `row_hash`. Because the next entry incorporates that hash, the break
propagates: **every entry after the tampered one fails to verify.** Deleting an entry breaks the
link between its neighbours. Inserting one gives it no valid predecessor.

The key is held in configuration, not in the database. Somebody with database access alone cannot
recompute a valid chain over altered data.

### Ordering is by `seq`, and that is load-bearing

The chain walks a **monotonic sequence**, assigned under an advisory lock so concurrent
writes serialise.

It ordered by timestamp originally, and that was a real defect found during construction: two
entries written in the same clock tick share an `at`, so ordering fell through to a random
identifier. An entry could chain past its true predecessor — and **deleting the skipped entry left
a chain that still verified perfectly.** The one thing the mechanism exists to detect became
undetectable, on a tie that a coarse system clock makes common rather than rare.

Fixed in migration `0023_audit_seq`, and pinned by regression tests that force the tie through a
time seam. The fix is described here rather than omitted because a supplier whose tamper-evidence
has never been stress-tested has not tested it.

### A second defect, in the same area

Two entries recorded in one transaction both claimed sequence 1 and both chained to the genesis
hash — so verification **reported tampering on an honest log**. The cause was that the chain read
its predecessor from the database while the session did not flush the pending entry.

Recording two actions in one request is ordinary — a workflow decision that also notifies, a grant
followed by a break-glass, a refusal that audits its reason. So the mechanism was raising false
positives across a large part of normal use, and a tamper alarm that cries wolf is worse than
none: the first real alert gets dismissed with the rest. Also fixed, also regression-tested.

---

## 4. Verification

Verification recomputes the whole chain and reports whether it holds, plus **the first entry
that does not match**.

It is exposed at `GET /audit/verify` to holders of the `audit.verify` permission, and can be run
by MMBL's own auditors without our involvement.

| Tampering | Detected as |
|---|---|
| A field altered | `row_hash` mismatch on that entry |
| An entry deleted | `prev_hash` mismatch on the following entry |
| An entry inserted | No valid predecessor |
| Entries reordered | Sequence discontinuity |
| The whole chain rewritten | Requires the chain key, which is not in the database |

**Entries created before the chain existed are skipped**, with empty hashes, and reported as such
rather than silently passed. Claiming to verify a period the mechanism did not cover would be the
worst kind of false assurance.

### Independent verification

An auditor with the chain key and a database export can verify without the application:

1. Extract the entries, ordered by sequence
2. Recompute `canonical(entry)` per the published serialisation
3. Recompute `row_hash = HMAC-SHA256(key, prev_hash || canonical)`
4. Compare

The serialisation is documented so this is reproducible in any language.

---

## 5. Retention and scale

| Property | Value |
|---|---|
| Retention | 10 years, matching contract retention |
| Purge | **Audit entries are never purged by the retention sweep.** Contract data ages out; the record of what was done to it does not |
| Legal hold | Overrides retention unconditionally |
| Growth | Approximately 40–60 entries per agreement lifecycle |

At scale — beyond roughly ten million entries — the table benefits from monthly partitioning.
`infra/scripts/partition-audit-log.sql` performs the conversion.

**It is deliberately an operator script, not a migration.** Converting a populated table holds an
ACCESS EXCLUSIVE lock for minutes to hours; a migration that runs automatically on deploy and
takes the system down for an hour is worse than no migration. The script refuses to run below a
million entries, verifies the copy row-for-row, keeps the old table as the rollback, and
re-applies the Virtual Private Database policy — which does not follow a rename, and an audit table without it is a
read across the workspace boundary.

**The chain survives partitioning** because it is per-entry rather than per-table. That was a
design choice made when the chain was built, specifically so this step would remain available.

---

## 6. SIEM

Every entry is projected to the SIEM in **CEF over syslog**, classified and severity-mapped.

| Category | Examples | Severity |
|---|---|---|
| `security_incident` | Login failure, lockout, SAML rejection, **refresh-token reuse** | Warning to Alert |
| `authentication` | Sign-in, sign-out, MFA challenge | Informational |
| `access_control` | Role change, permission grant, API key created | Notice |
| `data_governance` | Retention purge, legal hold, export | Notice |
| `application_usage` | Everything else | Informational |

Certain actions escalate regardless of category: `audit.chain_broken` (Critical), `auth.lockout`,
`auth.session.reuse_detected` and `party.sanctions_hit` (Alert).

**Emission is best-effort and never raises.** A collector outage must not stop somebody signing an
agreement. The entry is already durable, and `POST /siem/replay` re-emits a period after an
outage — so a gap is recoverable rather than permanent.

### One gap closed in Phase 10
Refresh-token reuse — the strongest signal of token theft the system has — revoked the session
chain and returned a 401, and **wrote nothing to the audit log**. A failed password attempt was
recorded; an actual stolen session was not. It now records `auth.session.reuse_detected` and
escalates to the SIEM at Alert.

---

## 7. What this mechanism does not prove

Stated because an audit mechanism that oversells itself undermines the record it protects.

- **It does not prevent tampering.** It makes tampering detectable. Prevention needs
  database-level controls MMBL operates: privileged access management, database activity
  monitoring, and separation between application and DBA credentials.
- **It does not protect against an attacker who holds the chain key.** Somebody with both the key
  and write access to the database can construct a consistent false chain. The key belongs in a
  secret store with access separate from database administration.
- **It does not record reads.** Only state-changing actions are chained. Access to confidential
  agreements and refused access attempts *are* recorded, but routine viewing is not — recording
  every read would grow the log by two orders of magnitude and bury the entries that matter.
- **Entries predating the chain are not covered**, and are reported as skipped rather than passed.
- **Clock accuracy is the platform's.** Timestamps are as good as NTP on the host. Ordering does
  not depend on them — that is what `seq` is for — but the recorded time does.

---

## 8. Compliance mapping

| Requirement | Where met |
|---|---|
| RFP §4d — audit trails for all critical activity | §1 |
| RFP §4d — logs in CLF/CEF with severity | §6 |
| SBP ETGRMF — audit logging and retention | §1, §5 |
| ISO 27001:2022 A.8.15 — logging | §1, §2 |
| ISO 27001:2022 A.8.16 — monitoring | §6 |
| SOC 2 CC7.2 — anomaly detection | §6 |
| Non-repudiation of electronic signatures | §3, plus the Certificate of Completion |

---

## 9. In the product

| Surface | Who | What |
|---|---|---|
| Contract activity feed | Anyone who can see the agreement | That agreement's lifecycle |
| Audit log screen | `audit.read` | Full log, filterable by actor, action, object and date |
| Chain verification | `audit.verify` | Recompute and report the first break |
| Export | `export.run` | CSV or XLSX for an external auditor |
| SIEM replay | Administrator | Re-emit a period after a collector outage |

Every one of those actions is itself audited. Exporting the audit log leaves an entry in it.
