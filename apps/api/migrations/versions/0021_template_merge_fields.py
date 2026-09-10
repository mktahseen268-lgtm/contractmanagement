"""Template merge fields, versioning and approval (Phase 3, RFI 2.3).

Adds the typed intake form to `contract_templates`, an approval state machine, and a version
snapshot table so "which approved wording generated this contract?" stays answerable after
somebody edits the template. Contracts gain a back-reference to the exact revision used.

Existing templates are migrated to `status='active'` when they were active, so nothing that
worked before this migration stops working after it.

Revision ID: 0021_template_merge_fields
Revises: 0020_workflow_engine
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0021_template_merge_fields"
down_revision = "0020_workflow_engine"
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


def _drop_indexes(bind, table: str, names: list[str]) -> None:
    present = _indexes(bind, table)
    for name in names:
        if name in present:
            op.drop_index(name, table_name=table)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    json_type = db_dialect.json_column(dialect)

    template_columns = [
        ("fields", sa.Column("fields", json_type, nullable=True)),
        ("status", sa.Column("status", sa.String(20), nullable=False, server_default="draft")),
        ("version_no", sa.Column("version_no", sa.Integer(), nullable=False, server_default="1")),
        ("effective_from", sa.Column("effective_from", sa.Date(), nullable=True)),
        ("retired_at", sa.Column("retired_at", sa.DateTime(), nullable=True)),
        ("approved_by", sa.Column("approved_by", sa.String(32), nullable=False, server_default="")),
        ("approved_at", sa.Column("approved_at", sa.DateTime(), nullable=True)),
        ("approval_note", sa.Column("approval_note", sa.String(500), nullable=False, server_default="")),
    ]
    existing = _columns(bind, "contract_templates")
    added = False
    for name, column in template_columns:
        if name not in existing:
            op.add_column("contract_templates", column)
            added = True

    if added:
        # Templates usable before this migration stay usable after it. Anything already
        # archived becomes `retired` rather than `draft` — it was deliberately taken out of
        # use, and dropping it back to draft would misrepresent that as unfinished work.
        op.execute("UPDATE contract_templates SET fields = '[]' WHERE fields IS NULL")
        op.execute(
            "UPDATE contract_templates SET status = CASE WHEN is_active IN (1, TRUE) "
            "THEN 'active' ELSE 'retired' END"
            if dialect == db_dialect.SQLITE else
            "UPDATE contract_templates SET status = CASE WHEN is_active THEN 'active' "
            "ELSE 'retired' END"
        )

    if "ix_contract_templates_status" not in _indexes(bind, "contract_templates"):
        op.create_index("ix_contract_templates_status", "contract_templates",
                        ["tenant_id", "status"])

    existing = _columns(bind, "contracts")
    for name, column in [
        ("template_id", sa.Column("template_id", sa.String(32), nullable=True)),
        ("template_version_no", sa.Column("template_version_no", sa.Integer(), nullable=True)),
        ("merge_values", sa.Column("merge_values", json_type, nullable=True)),
    ]:
        if name not in existing:
            op.add_column("contracts", column)
    if "ix_contracts_template" not in _indexes(bind, "contracts"):
        op.create_index("ix_contracts_template", "contracts", ["tenant_id", "template_id"])

    if "contract_template_versions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "contract_template_versions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("template_id", sa.String(32), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("fields", json_type, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("change_summary", sa.String(500), nullable=False, server_default=""),
            sa.Column("approved_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_ctv_tenant", "contract_template_versions", ["tenant_id"])
        # One row per (template, version) — a duplicate would make "which wording?"
        # ambiguous, which is the single thing this table exists to prevent.
        op.create_index("ix_ctv_template_version", "contract_template_versions",
                        ["template_id", "version_no"], unique=True)
        op.create_index("ix_ctv_tenant_status", "contract_template_versions",
                        ["tenant_id", "status"])

    # Tenant-scoped, so it carries the same row security as every other tenant table.
    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, ["contract_template_versions"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, ["contract_template_versions"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass
    op.drop_table("contract_template_versions")

    # Both the index this migration created and the one the model's `index=True` produces on
    # a create_all-built schema. Batch mode rebuilds a table and then recreates its reflected
    # indexes, so an index over a dropped column has to go first.
    _drop_indexes(bind, "contracts", ["ix_contracts_template", "ix_contracts_template_id"])
    with op.batch_alter_table("contracts") as batch:
        for column in ("merge_values", "template_version_no", "template_id"):
            batch.drop_column(column)

    _drop_indexes(bind, "contract_templates",
                  ["ix_contract_templates_status", "ix_contract_templates_status_1"])
    with op.batch_alter_table("contract_templates") as batch:
        for column in ("approval_note", "approved_at", "approved_by", "retired_at",
                       "effective_from", "version_no", "status", "fields"):
            batch.drop_column(column)
