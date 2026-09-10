# Transparent Data Encryption

Phase 8, item 9. What the application encrypts itself, what it cannot, and the per-engine
commands to close the gap.

## What the application already encrypts

Two column types, both with key rotation:

| Column | Mechanism | Where |
|---|---|---|
| `users.mfa_secret` | Fernet / MultiFernet (AES-128-CBC + HMAC) | `app/secrets_box.py`, `EncryptedString` in `models.py` |
| `webhook_endpoints.secret` | Same | Same |
| `signature_recipients.access_token_secret` | Same | Phase 2 |
| Private keys in `key_material` | Encrypted by the keystore, or never exported at all when a PKCS#11 HSM is configured | `app/pki/keystore.py` |

`MFA_ENCRYPTION_KEYS` is newline-separated: the first key encrypts, the rest decrypt, which is
how rotation happens without downtime.

**This is not database encryption.** It protects specific secrets from someone reading the
table. It does nothing about a stolen disk, a copied backup file, or a snapshot lifted from
the storage array — which is what TDE is for, and what the ETGRMF clause is asking about.

## Why the application cannot enable TDE

TDE is a storage-engine feature. It needs a key held outside the database process, DDL run as
a privileged database user, and in most cases a restart. An application that could turn it on
would need permissions no application should hold. So this is documented as an operator step
with the exact commands, and the app **checks and warns** rather than pretending.

## PostgreSQL

PostgreSQL has no built-in TDE. Three real options, in order of preference:

1. **Filesystem encryption (LUKS / dm-crypt)** — encrypts the whole data directory. Simplest,
   well understood, and what most PostgreSQL deployments in regulated environments actually
   use.

   ```bash
   cryptsetup luksFormat /dev/sdb1
   cryptsetup open /dev/sdb1 pgdata
   mkfs.ext4 /dev/mapper/pgdata
   mount /dev/mapper/pgdata /var/lib/postgresql/data
   ```

   The key belongs in the same place as `MFA_ENCRYPTION_KEYS` — an HSM or a sealed secret
   store, **not** on the machine that mounts the volume, or the encryption protects nothing
   against someone who has that machine.

2. **EDB Postgres Advanced Server** or **Cybertec PGEE**, which do have cluster-level TDE.
   A licensing decision.

3. **pgcrypto per column**, for a handful of additional fields. Not recommended broadly:
   an encrypted column cannot be indexed usefully, so encrypting `contracts.value` this way
   would make every report over value a sequential scan.

Backups must be encrypted separately — `pg_dump` output is plaintext regardless of what the
data directory does. See `docs/29-backup-and-dr.md`.

## SQL Server

Native TDE, and the straightforward case:

```sql
USE master;
CREATE MASTER KEY ENCRYPTION BY PASSWORD = '<strong-password>';
CREATE CERTIFICATE CM_TDE_Cert WITH SUBJECT = 'Contract Management TDE';

USE ContractManagement;
CREATE DATABASE ENCRYPTION KEY
  WITH ALGORITHM = AES_256
  ENCRYPTION BY SERVER CERTIFICATE CM_TDE_Cert;
ALTER DATABASE ContractManagement SET ENCRYPTION ON;

-- Back the certificate up immediately and store it separately. Without it the encrypted
-- database cannot be restored anywhere — including here, after a disaster.
BACKUP CERTIFICATE CM_TDE_Cert
  TO FILE = 'C:\keys\CM_TDE_Cert.cer'
  WITH PRIVATE KEY (FILE = 'C:\keys\CM_TDE_Cert.pvk',
                    ENCRYPTION BY PASSWORD = '<different-strong-password>');
```

Verify:

```sql
SELECT DB_NAME(database_id) AS db, encryption_state, key_algorithm, key_length
FROM sys.dm_database_encryption_keys;
-- encryption_state 3 = encrypted
```

## Oracle

Advanced Security option required.

```sql
ADMINISTER KEY MANAGEMENT CREATE KEYSTORE '/etc/oracle/wallet' IDENTIFIED BY "<password>";
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN IDENTIFIED BY "<password>";
ADMINISTER KEY MANAGEMENT SET KEY IDENTIFIED BY "<password>" WITH BACKUP;

ALTER TABLESPACE cm_data ENCRYPTION ONLINE USING 'AES256' ENCRYPT;
```

Verify:

```sql
SELECT tablespace_name, encrypted FROM dba_tablespaces;
```

## The startup check

`settings.validate_for_production()` warns when a production profile shows no TDE indicator.
It is a **warning, not a refusal**, and that is a deliberate choice: the application cannot
reliably detect filesystem-level encryption from inside the database connection, so refusing
to boot would block a correctly-encrypted LUKS deployment while doing nothing about an
unencrypted one that happened to set a flag. A warning that an operator must acknowledge is
honest about what can actually be verified from here.

Set `TDE_ATTESTED=true` once the encryption above is in place and evidenced. That setting is
an **attestation by the operator**, not a measurement — it is named that way so nobody mistakes
it for the application having checked.

## What to hand an assessor

1. This document.
2. The verification query output for the engine in use.
3. Evidence that the TDE key or LUKS key is stored separately from the data — the control is
   worthless if the key travels with the backup.
4. `docs/29-backup-and-dr.md` §"What has to be backed up", which is where the separation of
   keys from data is specified.
