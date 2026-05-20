"""hardening: hash+expire signing tokens, encrypt webhook secret, audit hash-chain,
composite indexes, Postgres JSONB conversion.

This migration closes the three credibility-risk hotspots called out in CLAUDE.md and the
hottest performance items from the RFI audit. It is **data-migrating** — in-flight signing
URLs are preserved by hashing the existing plaintext token and re-encrypting it at rest so
reminders keep working, and existing webhook secrets are wrapped in `EncryptedString`.

What this migration does, in order:

1. `signature_recipients`:
     + add `access_token_hash` (sha256 of the raw URL token, indexed — used for lookup)
     + add `access_token_secret` (EncryptedString — Fernet/AES-256-GCM at rest, so the
       server can decrypt to send reminders without ever persisting plaintext)
     + add `access_token_expires_at` (default = NOW + 14 days for migrated rows)
     - data-migrate: for every row with a non-empty plaintext `access_token`, write the
       hash + encrypted secret + expiry, then null the plaintext column
     - drop the old plaintext `access_token` column + its index

2. `webhook_endpoints.secret`: widen column to VARCHAR(512) (Fernet ciphertext is ~100
   chars for typical inputs but headroom matters for rotation), then walk existing rows
   and re-encrypt each plaintext secret via `secrets_box`. The `EncryptedString` decorator
   handles per-read decryption (legacy unprefixed values pass through, per `secrets_box`).

3. `audit_log`: add `prev_hash` + `row_hash` columns (HMAC-SHA256 chain — see audit.py).
   Existing rows are *not* retro-chained (we don't have the historical secret); they get
   sentinel zero hashes and the chain restarts on the first new row. The verifier knows to
   treat any row with empty `prev_hash` AND empty `row_hash` as pre-chain history.

4. Composite indexes for hot access paths identified in the audit (CLAUDE.md):
     - contracts: (tenant_id, status), (tenant_id, owner_id, status), (tenant_id, renewal_type, end_date)
     - signature_envelopes: (tenant_id, contract_id, status)
     - signature_recipients: (envelope_id, sequence)
     - workflow_runs: (tenant_id, contract_id, status)
     - audit_log: (tenant_id, at DESC) — forensic queries
     - webhook_deliveries: (tenant_id, status, created_at)
     - background_jobs: (tenant_id, status, created_at)
     - email_outbox: (status, created_at) — outbox-flush sweep

5. PostgreSQL JSONB conversion (no-op on SQLite / MSSQL) for JSON columns that get filtered
   or scanned: `audit_log.metadata`, `signature_events.metadata`, `contracts.tags`,
   `workflow_definitions.steps`, `workflow_definitions.default_for_types`,
   `webhook_endpoints.events`, `webhook_deliveries.payload`, `contract_templates.default_tags`.
   GIN indexes on the queried-by-key ones (`webhook_endpoints.events`, `contracts.tags`).

Revision ID: 0013_hardening
Revises: 0012_compliance
Create Date: 2026-05-19
"""
from __future__ import annotations

import datetime as dt
import hashlib

import sqlalchemy as sa
from alembic import op

revision = "0013_hardening"
down_revision = "0012_compliance"
branch_labels = None
depends_on = None


_TOKEN_TTL_DAYS = 14


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_index(bind, table: str, index_name: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---------- 1. signature_recipients: hashed + expiring tokens ----------
    if "signature_recipients" in sa.inspect(bind).get_table_names():
        cols = {c["name"] for c in sa.inspect(bind).get_columns("signature_recipients")}
        if "access_token_hash" not in cols:
            op.add_column("signature_recipients", sa.Column("access_token_hash", sa.String(64), nullable=True))
            op.create_index("ix_sig_recip_access_token_hash", "signature_recipients", ["access_token_hash"])
        if "access_token_secret" not in cols:
            op.add_column("signature_recipients", sa.Column("access_token_secret", sa.String(512), nullable=True))
        if "access_token_expires_at" not in cols:
            op.add_column("signature_recipients", sa.Column("access_token_expires_at", sa.DateTime(), nullable=True))
            op.create_index("ix_sig_recip_token_expires", "signature_recipients", ["access_token_expires_at"])

        # Data migration: hash + encrypt existing plaintext tokens, preserve in-flight URLs.
        if "access_token" in cols:
            # Import lazily — needs the live secrets_box / settings.
            from app.secrets_box import get_box  # type: ignore[import-not-found]

            box = get_box()
            expires_at = dt.datetime.utcnow() + dt.timedelta(days=_TOKEN_TTL_DAYS)
            rows = bind.execute(sa.text(
                "SELECT id, access_token FROM signature_recipients WHERE access_token IS NOT NULL AND access_token <> ''"
            )).fetchall()
            for rid, raw in rows:
                if not raw:
                    continue
                h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                enc = box.encrypt(raw)
                bind.execute(
                    sa.text(
                        "UPDATE signature_recipients SET access_token_hash = :h, access_token_secret = :s, "
                        "access_token_expires_at = :e WHERE id = :id"
                    ),
                    {"h": h, "s": enc, "e": expires_at, "id": rid},
                )
            # Wipe the plaintext column before dropping it. Use a portable UPDATE.
            bind.execute(sa.text("UPDATE signature_recipients SET access_token = NULL WHERE access_token IS NOT NULL"))
            # Drop the old index then column.
            if _has_index(bind, "signature_recipients", "ix_signature_recipients_access_token"):
                op.drop_index("ix_signature_recipients_access_token", table_name="signature_recipients")
            with op.batch_alter_table("signature_recipients") as batch:
                batch.drop_column("access_token")

    # ---------- 2. webhook_endpoints.secret: encrypted at rest ----------
    if "webhook_endpoints" in sa.inspect(bind).get_table_names():
        # Widen the column so Fernet ciphertext fits comfortably (~100 chars + headroom).
        if dialect == "postgresql":
            op.execute("ALTER TABLE webhook_endpoints ALTER COLUMN secret TYPE VARCHAR(512)")
        elif dialect == "mssql":
            op.execute("ALTER TABLE webhook_endpoints ALTER COLUMN secret NVARCHAR(512) NOT NULL")
        # SQLite: no length enforcement — skip.

        # Data migration: re-encrypt any plaintext secret rows. EncryptedString.process_result_value
        # treats unprefixed legacy values as plaintext, so leaving rows untouched would also work —
        # but encrypting now keeps the at-rest invariant clean.
        from app.secrets_box import get_box  # type: ignore[import-not-found]

        box = get_box()
        rows = bind.execute(sa.text(
            "SELECT id, secret FROM webhook_endpoints WHERE secret IS NOT NULL AND secret <> ''"
        )).fetchall()
        for rid, secret in rows:
            if not secret:
                continue
            if secret.startswith("fr$") or secret.startswith("pt$"):
                continue  # already wrapped
            enc = box.encrypt(secret)
            bind.execute(
                sa.text("UPDATE webhook_endpoints SET secret = :s WHERE id = :id"),
                {"s": enc, "id": rid},
            )

    # ---------- 3. audit_log: hash chain columns ----------
    if "audit_log" in sa.inspect(bind).get_table_names():
        cols = {c["name"] for c in sa.inspect(bind).get_columns("audit_log")}
        if "prev_hash" not in cols:
            op.add_column("audit_log", sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""))
        if "row_hash" not in cols:
            op.add_column("audit_log", sa.Column("row_hash", sa.String(64), nullable=False, server_default=""))
            op.create_index("ix_audit_log_row_hash", "audit_log", ["row_hash"])

    # ---------- 4. Composite indexes ----------
    _create_index_if_missing(bind, "ix_contracts_tenant_status", "contracts", ["tenant_id", "status"])
    _create_index_if_missing(bind, "ix_contracts_tenant_owner_status", "contracts", ["tenant_id", "owner_id", "status"])
    _create_index_if_missing(bind, "ix_contracts_tenant_renewal_end", "contracts", ["tenant_id", "renewal_type", "end_date"])
    _create_index_if_missing(bind, "ix_sig_env_tenant_contract_status", "signature_envelopes", ["tenant_id", "contract_id", "status"])
    _create_index_if_missing(bind, "ix_sig_recip_envelope_sequence", "signature_recipients", ["envelope_id", "sequence"])
    _create_index_if_missing(bind, "ix_wf_runs_tenant_contract_status", "workflow_runs", ["tenant_id", "contract_id", "status"])
    _create_index_if_missing(bind, "ix_audit_log_tenant_at", "audit_log", ["tenant_id", "at"])
    _create_index_if_missing(bind, "ix_webhook_deliveries_tenant_status_at", "webhook_deliveries", ["tenant_id", "status", "created_at"])
    _create_index_if_missing(bind, "ix_background_jobs_tenant_status_at", "background_jobs", ["tenant_id", "status", "created_at"])
    _create_index_if_missing(bind, "ix_email_outbox_status_created", "email_outbox", ["status", "created_at"])

    # ---------- 5. JSONB conversion + GIN (PostgreSQL only) ----------
    if dialect == "postgresql":
        _convert_json_to_jsonb(bind, "audit_log", "metadata")
        _convert_json_to_jsonb(bind, "signature_events", "metadata")
        _convert_json_to_jsonb(bind, "contracts", "tags")
        _convert_json_to_jsonb(bind, "workflow_definitions", "steps")
        _convert_json_to_jsonb(bind, "workflow_definitions", "default_for_types")
        _convert_json_to_jsonb(bind, "webhook_endpoints", "events")
        _convert_json_to_jsonb(bind, "webhook_deliveries", "payload")
        _convert_json_to_jsonb(bind, "contract_templates", "default_tags")
        # GIN indexes for the JSON columns we actually filter by.
        op.execute('CREATE INDEX IF NOT EXISTS ix_contracts_tags_gin ON contracts USING GIN (tags)')
        op.execute('CREATE INDEX IF NOT EXISTS ix_webhook_endpoints_events_gin ON webhook_endpoints USING GIN (events)')


def _create_index_if_missing(bind, name: str, table: str, columns: list[str]) -> None:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes(table)}
    if name in existing:
        return
    op.create_index(name, table, columns)


def _convert_json_to_jsonb(bind, table: str, column: str) -> None:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    cols = {c["name"]: c for c in insp.get_columns(table)}
    if column not in cols:
        return
    coltype = str(cols[column]["type"]).upper()
    if "JSONB" in coltype:
        return  # already converted
    # ALTER COLUMN TYPE … USING preserves data.
    op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE JSONB USING "{column}"::jsonb')


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # GIN indexes
    if dialect == "postgresql":
        op.execute('DROP INDEX IF EXISTS ix_contracts_tags_gin')
        op.execute('DROP INDEX IF EXISTS ix_webhook_endpoints_events_gin')

    # Composite indexes
    for name, table in [
        ("ix_contracts_tenant_status", "contracts"),
        ("ix_contracts_tenant_owner_status", "contracts"),
        ("ix_contracts_tenant_renewal_end", "contracts"),
        ("ix_sig_env_tenant_contract_status", "signature_envelopes"),
        ("ix_sig_recip_envelope_sequence", "signature_recipients"),
        ("ix_wf_runs_tenant_contract_status", "workflow_runs"),
        ("ix_audit_log_tenant_at", "audit_log"),
        ("ix_webhook_deliveries_tenant_status_at", "webhook_deliveries"),
        ("ix_background_jobs_tenant_status_at", "background_jobs"),
        ("ix_email_outbox_status_created", "email_outbox"),
    ]:
        try:
            op.drop_index(name, table_name=table)
        except Exception:  # noqa: BLE001
            pass

    # audit hash chain
    if _has_column(bind, "audit_log", "row_hash"):
        try:
            op.drop_index("ix_audit_log_row_hash", table_name="audit_log")
        except Exception:  # noqa: BLE001
            pass
    for col in ("row_hash", "prev_hash"):
        if _has_column(bind, "audit_log", col):
            with op.batch_alter_table("audit_log") as batch:
                batch.drop_column(col)

    # signing tokens — restore the plaintext column (data is unrecoverable; this is a security feature)
    if _has_column(bind, "signature_recipients", "access_token_hash"):
        with op.batch_alter_table("signature_recipients") as batch:
            batch.add_column(sa.Column("access_token", sa.String(64), nullable=True))
            batch.drop_column("access_token_hash")
            batch.drop_column("access_token_secret")
            batch.drop_column("access_token_expires_at")
        op.create_index("ix_signature_recipients_access_token", "signature_recipients", ["access_token"])

    # We intentionally do *not* downgrade webhook secrets (would require decrypting + storing plaintext)
    # or revert JSONB → JSON (the columns still satisfy the JSON typedecorator).
