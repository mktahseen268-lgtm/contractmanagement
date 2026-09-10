"""Repository structure: parties, relationships, departments, folders, custom fields
(Phase 5, items 2–5), plus the full-text search index (item 1).

Turns the free-text columns a contract carries into records that can be reported on. The
free-text `counterparty` and `department` stay populated alongside the new foreign keys —
every existing report, export and rendered PDF reads them, and migrating all of those in one
change would be a far larger blast radius than the problem justifies.

Revision ID: 0025_repository
Revises: 0024_ai_assist
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0025_repository"
down_revision = "0024_ai_assist"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["parties", "contract_relations", "departments", "folders",
                  "custom_field_defs"]

#: What a repository search actually looks through.
_FTS_COLUMNS = ["title", "counterparty", "body", "ai_summary"]


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

    if "parties" not in _tables(bind):
        op.create_table(
            "parties",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("name_key", sa.String(300), nullable=False, server_default=""),
            sa.Column("registration_no", sa.String(100), nullable=False, server_default=""),
            sa.Column("entity_type", sa.String(50), nullable=False, server_default="company"),
            sa.Column("jurisdiction", sa.String(100), nullable=False, server_default=""),
            sa.Column("region", sa.String(100), nullable=False, server_default=""),
            sa.Column("kyc_status", sa.String(20), nullable=False, server_default="none"),
            sa.Column("kyc_note", sa.String(500), nullable=False, server_default=""),
            sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("documents", json_type, nullable=True),
            sa.Column("contact_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("contact_email", sa.String(320), nullable=False, server_default=""),
            sa.Column("contact_phone", sa.String(64), nullable=False, server_default=""),
            sa.Column("address", sa.Text(), nullable=False, server_default=""),
            sa.Column("tags", json_type, nullable=True),
            sa.Column("duplicate_override_of", sa.String(32), nullable=True),
            sa.Column("duplicate_override_reason", sa.String(500), nullable=False,
                      server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_parties_tenant_id", "parties", ["tenant_id"])
        op.create_index("ix_parties_name_key", "parties", ["name_key"])
        op.create_index("ix_parties_region", "parties", ["region"])
        op.create_index("ix_parties_kyc_status", "parties", ["kyc_status"])
        op.create_index("ix_parties_is_active", "parties", ["is_active"])
        op.create_index("ix_party_lookup", "parties", ["tenant_id", "name"])
        # The duplicate check is an index lookup on the normalised name, not a scan.
        op.create_index("ix_party_registration", "parties", ["tenant_id", "registration_no"])

    if "contract_relations" not in _tables(bind):
        op.create_table(
            "contract_relations",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("parent_id", sa.String(32), nullable=False),
            sa.Column("child_id", sa.String(32), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False, server_default="related_to"),
            sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.String(500), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_contract_relations_tenant_id", "contract_relations", ["tenant_id"])
        op.create_index("ix_contract_relations_parent_id", "contract_relations", ["parent_id"])
        op.create_index("ix_contract_relations_child_id", "contract_relations", ["child_id"])
        op.create_index("ix_contract_relations_kind", "contract_relations", ["kind"])
        op.create_index("ix_relation_parent", "contract_relations",
                        ["tenant_id", "parent_id", "kind"])
        op.create_index("ix_relation_child", "contract_relations", ["tenant_id", "child_id"])
        # One link of a given kind between two agreements; a duplicate would double-count an
        # addendum in the history tree.
        op.create_index("ix_relation_unique", "contract_relations",
                        ["parent_id", "child_id", "kind"], unique=True)

    if "departments" not in _tables(bind):
        op.create_table(
            "departments",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("lead_user_id", sa.String(32), nullable=True),
            sa.Column("cost_centre", sa.String(60), nullable=False, server_default=""),
            sa.Column("region", sa.String(100), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_departments_tenant_id", "departments", ["tenant_id"])
        op.create_index("ix_department_name", "departments", ["tenant_id", "name"], unique=True)

    if "folders" not in _tables(bind):
        op.create_table(
            "folders",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("parent_id", sa.String(32), nullable=True),
            sa.Column("path", sa.String(1000), nullable=False, server_default=""),
            sa.Column("visible_to_roles", json_type, nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_folders_tenant_id", "folders", ["tenant_id"])
        # The materialised path is the lookup key: "everything under /Legal" is a prefix match.
        op.create_index("ix_folder_path", "folders", ["tenant_id", "path"], unique=True)
        op.create_index("ix_folder_parent", "folders", ["tenant_id", "parent_id"])

    if "custom_field_defs" not in _tables(bind):
        op.create_table(
            "custom_field_defs",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("contract_type", sa.String(50), nullable=False, server_default=""),
            sa.Column("key", sa.String(80), nullable=False),
            sa.Column("label", sa.String(200), nullable=False, server_default=""),
            sa.Column("type", sa.String(20), nullable=False, server_default="text"),
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("options", json_type, nullable=True),
            sa.Column("help", sa.String(500), nullable=False, server_default=""),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_custom_field_defs_tenant_id", "custom_field_defs", ["tenant_id"])
        op.create_index("ix_custom_field_defs_contract_type", "custom_field_defs",
                        ["contract_type"])
        op.create_index("ix_custom_field_key", "custom_field_defs",
                        ["tenant_id", "contract_type", "key"], unique=True)

    existing = _columns(bind, "contracts")
    for name, column in [
        ("party_id", sa.Column("party_id", sa.String(32), nullable=True)),
        ("department_id", sa.Column("department_id", sa.String(32), nullable=True)),
        ("folder_id", sa.Column("folder_id", sa.String(32), nullable=True)),
        ("custom_fields", sa.Column("custom_fields", json_type, nullable=True)),
    ]:
        if name not in existing:
            op.add_column("contracts", column)
    for name, cols in [
        ("ix_contracts_party", ["tenant_id", "party_id"]),
        ("ix_contracts_department", ["tenant_id", "department_id"]),
        ("ix_contracts_folder", ["tenant_id", "folder_id"]),
    ]:
        if name not in _indexes(bind, "contracts"):
            op.create_index(name, "contracts", cols)

    # --- Full-text search (Phase 5, item 1) ------------------------------------------------
    # Postgres gets a GIN index over a tsvector; MSSQL/Oracle get their own catalogue DDL. On
    # SQLite the search seam degrades to LIKE, so there is nothing to build.
    if "ix_contracts_fts" not in _indexes(bind, "contracts"):
        for stmt in db_dialect.fulltext_index(dialect, "contracts", _FTS_COLUMNS,
                                              key_index="ix_contracts_fts_key"):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001 — catalogue DDL varies by server configuration
                pass

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

    present = _indexes(bind, "contracts")
    for name in ("ix_contracts_party", "ix_contracts_department", "ix_contracts_folder",
                 "ix_contracts_party_id", "ix_contracts_department_id",
                 "ix_contracts_folder_id", "ix_contracts_fts"):
        if name in present:
            try:
                op.drop_index(name, table_name="contracts")
            except Exception:  # noqa: BLE001
                pass
    with op.batch_alter_table("contracts") as batch:
        for column in ("custom_fields", "folder_id", "department_id", "party_id"):
            batch.drop_column(column)

    for table in ("custom_field_defs", "folders", "departments", "contract_relations",
                  "parties"):
        if table in _tables(bind):
            op.drop_table(table)
