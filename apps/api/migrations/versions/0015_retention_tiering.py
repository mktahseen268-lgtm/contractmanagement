"""retention tiering: contract archive state + legal hold

Phase 0 item 7 — "Storage capacity for 10 years of financial records, with 1 year instantly
searchable" and "Data purging and archiving" (RFP §4c Infrastructure).

Adds to `contracts`:
  - `archived_at`  — set when the nightly sweep moved the contract and its files to the cold
                     storage tier. Archived contracts are excluded from the live search index
                     but the row stays queryable by id/reference, so nothing becomes
                     unretrievable. NULL = hot.
  - `legal_hold`   — blocks archival and purge unconditionally. Phase 8 layers matter-scoped
                     holds on top; this column is the enforcement point both paths read.

And to `file_objects`:
  - `archived_at`  — mirrors the contract flag for the object it belongs to.
  - `storage_tier` — "hot" | "cold". The cold tier is a key prefix (and, on S3, optionally a
                     different storage class) inside the same bucket, so the object never
                     leaves the deployment.

Portable across PostgreSQL / MSSQL / Oracle / SQLite — plain column adds and B-tree indexes,
no dialect-specific DDL. Re-runnable: every add is guarded by an inspection.

Revision ID: 0015_retention_tiering
Revises: 0014_signature_methods
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_retention_tiering"
down_revision = "0014_signature_methods"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    cols = _columns(bind, "contracts")
    if cols:
        if "archived_at" not in cols:
            op.add_column("contracts", sa.Column("archived_at", sa.DateTime(), nullable=True))
        if "legal_hold" not in cols:
            # server_default so the NOT NULL add works on a populated table; the model default
            # takes over for new rows.
            op.add_column(
                "contracts",
                sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        idx = _indexes(bind, "contracts")
        if "ix_contracts_archived_at" not in idx:
            op.create_index("ix_contracts_archived_at", "contracts", ["archived_at"])
        if "ix_contracts_legal_hold" not in idx:
            op.create_index("ix_contracts_legal_hold", "contracts", ["legal_hold"])
        # The sweep scans for "executed, not on hold, older than the hot window".
        if "ix_contracts_tenant_archived_end" not in idx:
            op.create_index(
                "ix_contracts_tenant_archived_end", "contracts", ["tenant_id", "archived_at", "end_date"]
            )

    fcols = _columns(bind, "file_objects")
    if fcols:
        if "archived_at" not in fcols:
            op.add_column("file_objects", sa.Column("archived_at", sa.DateTime(), nullable=True))
        if "storage_tier" not in fcols:
            op.add_column(
                "file_objects",
                sa.Column("storage_tier", sa.String(10), nullable=False, server_default="hot"),
            )
        if "ix_file_objects_parent" not in _indexes(bind, "file_objects"):
            op.create_index("ix_file_objects_parent", "file_objects", ["parent_type", "parent_id"])


def downgrade() -> None:
    bind = op.get_bind()

    for name in ("ix_file_objects_parent",):
        if name in _indexes(bind, "file_objects"):
            op.drop_index(name, table_name="file_objects")
    fcols = _columns(bind, "file_objects")
    with op.batch_alter_table("file_objects") as batch:
        for col in ("storage_tier", "archived_at"):
            if col in fcols:
                batch.drop_column(col)

    for name in ("ix_contracts_tenant_archived_end", "ix_contracts_legal_hold", "ix_contracts_archived_at"):
        if name in _indexes(bind, "contracts"):
            op.drop_index(name, table_name="contracts")
    cols = _columns(bind, "contracts")
    with op.batch_alter_table("contracts") as batch:
        for col in ("legal_hold", "archived_at"):
            if col in cols:
                batch.drop_column(col)
