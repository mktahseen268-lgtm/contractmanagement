"""Post-execution change flows: terminations, legal checklists, renewal notice schedules
and amendment impact (Phase 5, items 7–9 and 11).

Revision ID: 0026_change_flows
Revises: 0025_repository
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0026_change_flows"
down_revision = "0025_repository"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["termination_requests", "legal_checklists"]


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    if table not in _tables(bind):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    json_type = db_dialect.json_column(dialect)

    if "termination_requests" not in _tables(bind):
        op.create_table(
            "termination_requests",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("contract_id", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(30), nullable=False,
                      server_default="convenience"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("effective_date", sa.Date(), nullable=True),
            sa.Column("notice_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("documents", json_type, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("approvals", json_type, nullable=True),
            sa.Column("required_roles", json_type, nullable=True),
            sa.Column("notice_sent_at", sa.DateTime(), nullable=True),
            sa.Column("requested_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("requested_by_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_termination_requests_tenant_id", "termination_requests",
                        ["tenant_id"])
        op.create_index("ix_termination_requests_contract_id", "termination_requests",
                        ["contract_id"])
        op.create_index("ix_termination_requests_status", "termination_requests", ["status"])
        # "Is there an open request on this agreement?" — asked before every new one.
        op.create_index("ix_termination_contract", "termination_requests",
                        ["tenant_id", "contract_id", "status"])

    if "legal_checklists" not in _tables(bind):
        op.create_table(
            "legal_checklists",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.String(500), nullable=False, server_default=""),
            sa.Column("owner_function", sa.String(80), nullable=False, server_default="Legal"),
            sa.Column("contract_type", sa.String(50), nullable=False, server_default=""),
            sa.Column("items", json_type, nullable=True),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("file_id", sa.String(32), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_legal_checklists_tenant_id", "legal_checklists", ["tenant_id"])
        op.create_index("ix_legal_checklists_status", "legal_checklists", ["status"])
        op.create_index("ix_checklist_lookup", "legal_checklists",
                        ["tenant_id", "status", "contract_type"])

    existing = _columns(bind, "contracts")
    for name, column in [
        ("renewal_notice_days", sa.Column("renewal_notice_days", json_type, nullable=True)),
        ("amendment_impact", sa.Column("amendment_impact", json_type, nullable=True)),
    ]:
        if name not in existing:
            op.add_column("contracts", column)

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

    with op.batch_alter_table("contracts") as batch:
        for column in ("amendment_impact", "renewal_notice_days"):
            batch.drop_column(column)

    for table in ("legal_checklists", "termination_requests"):
        if table in _tables(bind):
            op.drop_table(table)
