"""Sanctions list snapshots and screening results (Phase 7, item 7).

The lists are held locally because the RFP forbids a runtime dependency on a foreign-hosted
service — a screen that fails open because a US endpoint was unreachable is a control that
does not exist.

`sanctions_entries` is deliberately **not** tenant-scoped and carries no row security: OFAC's
list is the same list for everybody, and a per-tenant copy would multiply a 20,000-row list by
the number of workspaces for nothing. `sanctions_screenings` — the results — is tenant-scoped
and does carry it.

Revision ID: 0027_sanctions
Revises: 0026_change_flows
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0027_sanctions"
down_revision = "0026_change_flows"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    json_type = db_dialect.json_column(dialect)

    if "sanctions_entries" not in _tables(bind):
        op.create_table(
            "sanctions_entries",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("list_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("name", sa.String(400), nullable=False),
            sa.Column("name_key", sa.String(400), nullable=False, server_default=""),
            sa.Column("aliases", json_type, nullable=True),
            sa.Column("entity_type", sa.String(30), nullable=False, server_default="unknown"),
            sa.Column("country", sa.String(100), nullable=False, server_default=""),
            sa.Column("programme", sa.String(200), nullable=False, server_default=""),
            sa.Column("reference", sa.String(100), nullable=False, server_default=""),
            sa.Column("snapshot_date", sa.Date(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_sanctions_entries_source", "sanctions_entries", ["source"])
        op.create_index("ix_sanctions_entries_is_active", "sanctions_entries", ["is_active"])
        op.create_index("ix_sanctions_entries_snapshot_date", "sanctions_entries",
                        ["snapshot_date"])
        op.create_index("ix_sanctions_lookup", "sanctions_entries", ["source", "is_active"])
        # Candidate narrowing happens on this before anything is scored in Python — scoring
        # every row of a real list on every screen is the difference between milliseconds and
        # minutes.
        op.create_index("ix_sanctions_name", "sanctions_entries", ["name_key"])

    if "sanctions_screenings" not in _tables(bind):
        op.create_table(
            "sanctions_screenings",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("party_id", sa.String(32), nullable=False),
            sa.Column("party_name", sa.String(300), nullable=False, server_default=""),
            sa.Column("hits", json_type, nullable=True),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="clear"),
            sa.Column("threshold", sa.Float(), nullable=False, server_default="0.85"),
            sa.Column("list_snapshot_date", sa.Date(), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("screened_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("decided_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_sanctions_screenings_tenant_id", "sanctions_screenings",
                        ["tenant_id"])
        op.create_index("ix_sanctions_screenings_party_id", "sanctions_screenings",
                        ["party_id"])
        op.create_index("ix_sanctions_screenings_status", "sanctions_screenings", ["status"])
        op.create_index("ix_sanctions_screenings_created_at", "sanctions_screenings",
                        ["created_at"])
        op.create_index("ix_screening_queue", "sanctions_screenings",
                        ["tenant_id", "status", "created_at"])

    # Only the results are tenant data. The lists themselves are public reference data.
    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, ["sanctions_screenings"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, ["sanctions_screenings"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass

    for table in ("sanctions_screenings", "sanctions_entries"):
        if table in _tables(bind):
            op.drop_table(table)
