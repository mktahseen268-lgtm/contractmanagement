# Backup, restore and disaster recovery

Phase 7, item 8. What is backed up, how it is verified, and how the Veeam/Commvault
integration the RFP asks for actually attaches.

## What has to be backed up

Three stores, and they are not interchangeable:

| Store | Contents | Why it matters |
|---|---|---|
| **PostgreSQL** | Every record: agreements, audit chain, PKI metadata, sessions | Losing it loses the system |
| **Object storage** (S3/MinIO, or `apps/api/storage/`) | Executed PDFs, uploaded documents, exports | The *signed* documents. A database without these is a catalogue of files that no longer exist |
| **Secrets** | `MFA_ENCRYPTION_KEYS`, `AUDIT_CHAIN_KEY`, `SECRET_KEY`, signing certificates | Without these the database restores as **unreadable ciphertext** |

That third row is the one that gets missed. A perfect database backup restored without
`MFA_ENCRYPTION_KEYS` gives you every user's TOTP secret as an undecryptable blob, and without
`AUDIT_CHAIN_KEY` the tamper-evidence chain cannot be verified — which means the restored audit
log proves nothing. **Back up the secrets separately, to different media, with different
access control.** They must not be in the same bundle as the data they protect, or a single
stolen backup is both the lock and the key.

## Schedule

| What | Frequency | Retention | Rationale |
|---|---|---|---|
| Postgres full | Daily | 35 days | Covers a monthly reporting cycle plus slack |
| Postgres WAL | Continuous | 35 days | Gives point-in-time recovery; the RPO below depends on it |
| Object storage | Daily incremental | 35 days | Documents are immutable once executed, so incremental is cheap |
| Postgres full | Weekly | 12 months | Regulatory retention |
| Postgres full | Monthly | 7 years | Matches the contract retention period |
| Secrets | On change | Indefinite, offline | Small, rarely changes, catastrophic to lose |

## RPO and RTO

These are the numbers to state in the SLA, and they are **claims that this repository can
evidence** rather than aspirations:

| Tier | RPO | RTO | Evidence |
|---|---|---|---|
| Database | ≤ 5 minutes | ≤ 30 minutes | `backup-verify.sh` prints the measured restore time on every run |
| Object storage | ≤ 24 hours | ≤ 2 hours | Incremental restore of the document store |
| Full site (DR) | ≤ 15 minutes | ≤ 4 hours | Documented drill, below |

RPO for the database is WAL-shipping interval, not backup frequency. If continuous archiving
is not configured, the honest RPO is **24 hours** — say that rather than the number above.

## Verification

`infra/scripts/backup-verify.sh` restores the newest dump into a scratch database and then
checks that the result is usable:

- the expected tables exist and carry rows;
- row-level security is still enabled on the tenant tables (a restore that drops RLS restores
  the data and removes the isolation);
- Alembic is at a version;
- the audit chain has exactly one genesis row, so the chain survived.

`pg_restore` exiting zero is not verification — it does that for a dump that restored an empty
schema. Run the script on a schedule; its output over time *is* the RTO evidence.

```bash
# nightly, after the backup job
BACKUP_DIR=/backups ./infra/scripts/backup-verify.sh
```

## Veeam / Commvault

Both are agent-based and neither should be pointed at a running Postgres data directory — a
file-level snapshot of live Postgres is a corrupt database that restores successfully and
fails later. The integration is:

1. **Pre-job hook** → `infra/scripts/backup.sh` writes a consistent `pg_dump` to `$BACKUP_DIR`.
2. **The agent backs up `$BACKUP_DIR` and the object store**, not the database files.
3. **Post-job hook** → `backup-verify.sh` on the most recent dump; a non-zero exit fails the
   backup job, so a backup that cannot be restored is reported as a failure on the night it
   happens rather than discovered during an incident.

```
# Veeam: Application-Aware Processing → Linux scripts
Pre-freeze:   /opt/cm/infra/scripts/backup.sh
Post-thaw:    /opt/cm/infra/scripts/backup-verify.sh

# Commvault: Subclient → Pre/Post Process
PreBackupProcess:   /opt/cm/infra/scripts/backup.sh
PostBackupProcess:  /opt/cm/infra/scripts/backup-verify.sh
```

Encrypt at the agent, with a key held in the same place as the application secrets above —
not on the backup server, which is the machine an attacker who has reached the backups already
controls.

## DR drill

Quarterly, and documented, because an undrilled DR plan is a document rather than a capability:

1. Restore the newest dump to the standby site (`backup-verify.sh` proves it restores).
2. Restore the object store to the standby MinIO/S3.
3. Bring up the API with the DR secrets bundle; `settings.validate_for_production()` refuses to
   start if anything is missing — which is the check working, not a failure of the drill.
4. Sign in, open an executed agreement, and **verify its audit chain** (`audit.verify_chain`).
   This is the step that proves the restore is legally usable rather than merely present.
5. Record wall-clock time for each step. That table is the RTO evidence for the submission.

## What is not covered

- **Cross-region replication** is not configured. On-prem single-site is the deployment the
  RFP describes; a second site is an infrastructure decision with a cost the operator owns.
- **Backup of the SIEM feed** is unnecessary — it is a projection of the audit log, and
  `/siem/replay` regenerates it from any chain position.
