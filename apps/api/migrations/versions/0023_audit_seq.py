"""Audit chain: order by a monotonic sequence, not by timestamp.

Closes a hole in the tamper-evidence chain. The chain picked its predecessor with
`ORDER BY (at DESC, id DESC)` and verification walked with `(at ASC, id ASC)` — consistent with
each other, but neither is *insertion* order. Two rows written inside the same clock tick share
an `at`, so ordering fell through to a random uuid: a row could chain past its true
predecessor, and silently deleting the skipped row then left a chain that verified perfectly.
That is exactly the tampering `audit_log` exists to detect.

`seq` is assigned under the same per-tenant advisory lock that already serialises audit writes,
so it is monotonic per tenant and safe under concurrency.

Existing rows are backfilled in `(at, id)` order per tenant — the order the old verifier used —
so their verification result is unchanged by this migration.

Revision ID: 0023_audit_seq
Revises: 0022_clause_library
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect

revision = "0023_audit_seq"
down_revision = "0022_clause_library"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if "seq" not in _columns(bind, "audit_log"):
        op.add_column("audit_log",
                      sa.Column("seq", sa.Integer(), nullable=False, server_default="0"))

        # Backfill in the order the previous verifier walked, so nothing that verified before
        # this migration stops verifying after it. Row-number support differs by engine;
        # SQLite 3.25+ and every supported server engine have window functions, but the
        # portable loop below is used on SQLite because older builds ship without them.
        if dialect in (db_dialect.PG, db_dialect.MSSQL, db_dialect.ORACLE):
            op.execute(sa.text("""
                UPDATE audit_log SET seq = numbered.rn
                FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY tenant_id ORDER BY at ASC, id ASC
                    ) AS rn
                    FROM audit_log
                ) AS numbered
                WHERE audit_log.id = numbered.id
            """) if dialect == db_dialect.PG else sa.text("""
                WITH numbered AS (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY tenant_id ORDER BY at ASC, id ASC
                    ) AS rn
                    FROM audit_log
                )
                UPDATE audit_log SET seq = (
                    SELECT rn FROM numbered WHERE numbered.id = audit_log.id
                )
            """))
        else:
            rows = bind.execute(sa.text(
                "SELECT id, tenant_id FROM audit_log ORDER BY tenant_id, at ASC, id ASC"
            )).fetchall()
            counters: dict[str, int] = {}
            for row_id, tenant_id in rows:
                counters[tenant_id] = counters.get(tenant_id, 0) + 1
                bind.execute(
                    sa.text("UPDATE audit_log SET seq = :seq WHERE id = :id"),
                    {"seq": counters[tenant_id], "id": row_id},
                )

    if "ix_audit_seq" not in _indexes(bind, "audit_log"):
        # The chain walk is "every row for this tenant, in seq order" — the one query that
        # matters for both appending and verifying.
        op.create_index("ix_audit_seq", "audit_log", ["tenant_id", "seq"])


def downgrade() -> None:
    bind = op.get_bind()
    # Both this migration's index and the one the model's `index=True` produces on a
    # create_all-built schema. Batch mode rebuilds the table and then recreates its reflected
    # indexes, so any index over the dropped column has to go first.
    present = _indexes(bind, "audit_log")
    for name in ("ix_audit_seq", "ix_audit_log_seq"):
        if name in present:
            op.drop_index(name, table_name="audit_log")
    if "seq" in _columns(bind, "audit_log"):
        with op.batch_alter_table("audit_log") as batch:
            batch.drop_column("seq")
