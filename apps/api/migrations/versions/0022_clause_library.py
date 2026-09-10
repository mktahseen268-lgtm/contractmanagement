"""Clause library, clause versions and playbooks (Phase 3, items 2 + 6).

Approved language that templates compose by reference, with the same approval gate and version
snapshots templates have, plus the policy rules a draft is measured against.

Revision ID: 0022_clause_library
Revises: 0021_template_merge_fields
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0022_clause_library"
down_revision = "0021_template_merge_fields"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["clauses", "clause_versions", "playbooks"]


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    if table not in _tables(bind):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    if table not in _tables(bind):
        return set()
    return {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    json_type = db_dialect.json_column(dialect)

    if "clauses" not in _tables(bind):
        op.create_table(
            "clauses",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("key", sa.String(80), nullable=False),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("category", sa.String(80), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("position", sa.String(20), nullable=False, server_default="preferred"),
            sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("parent_id", sa.String(32), nullable=True),
            sa.Column("fallback_rank", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("guidance", sa.Text(), nullable=False, server_default=""),
            sa.Column("jurisdiction", sa.String(100), nullable=False, server_default=""),
            sa.Column("tags", json_type, nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("approved_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("approval_note", sa.String(500), nullable=False, server_default=""),
            sa.Column("retired_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_clauses_tenant_id", "clauses", ["tenant_id"])
        op.create_index("ix_clauses_parent_id", "clauses", ["parent_id"])
        op.create_index("ix_clauses_status", "clauses", ["status"])
        op.create_index("ix_clauses_category", "clauses", ["category"])
        # The key is the handle templates point at, so it has to be unique per tenant or
        # `[[clause:x]]` would be ambiguous — the one thing the reference must never be.
        op.create_index("ix_clause_key", "clauses", ["tenant_id", "key"], unique=True)
        op.create_index("ix_clause_lookup", "clauses", ["tenant_id", "category", "status"])

    if "clause_versions" not in _tables(bind):
        op.create_table(
            "clause_versions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("clause_id", sa.String(32), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("position", sa.String(20), nullable=False, server_default="preferred"),
            sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("change_summary", sa.String(500), nullable=False, server_default=""),
            sa.Column("approved_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_clause_versions_tenant_id", "clause_versions", ["tenant_id"])
        op.create_index("ix_clause_versions_clause_id", "clause_versions", ["clause_id"])
        op.create_index("ix_clause_versions_status", "clause_versions", ["status"])
        op.create_index("ix_clause_version", "clause_versions",
                        ["clause_id", "version_no"], unique=True)

    if "playbooks" not in _tables(bind):
        op.create_table(
            "playbooks",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("description", sa.String(500), nullable=False, server_default=""),
            sa.Column("contract_type", sa.String(50), nullable=False, server_default=""),
            sa.Column("applies_when", json_type, nullable=True),
            sa.Column("rules", json_type, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_playbooks_tenant_id", "playbooks", ["tenant_id"])
        op.create_index("ix_playbooks_status", "playbooks", ["status"])
        op.create_index("ix_playbook_scope", "playbooks",
                        ["tenant_id", "contract_type", "status"])

    if "included_clauses" not in _columns(bind, "contracts"):
        op.add_column("contracts", sa.Column("included_clauses", json_type, nullable=True))

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, _TENANT_TABLES):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, _TENANT_TABLES):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass

    if "included_clauses" in _columns(bind, "contracts"):
        with op.batch_alter_table("contracts") as batch:
            batch.drop_column("included_clauses")

    for table in ("playbooks", "clause_versions", "clauses"):
        if table in _tables(bind):
            op.drop_table(table)
