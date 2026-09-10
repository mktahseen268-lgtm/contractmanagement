"""Access control: custom roles, need-to-know ACLs, legal holds, temporary access, step-up
(Phase 8, items 2, 3, 4, 10, 12, 13).

`Contract.legal_hold` stays as the fast boolean every retention path already reads — it
becomes *derived* from the new `legal_holds` records rather than set by hand, so two matters
covering one agreement no longer release each other.

Revision ID: 0028_access_control
Revises: 0027_sanctions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0028_access_control"
down_revision = "0027_sanctions"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["custom_roles", "contract_access", "legal_holds", "temporary_access",
                  "step_up_challenges"]


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

    if "custom_roles" not in _tables(bind):
        op.create_table(
            "custom_roles",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("key", sa.String(50), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.String(400), nullable=False, server_default=""),
            sa.Column("base_role", sa.String(20), nullable=False, server_default="viewer"),
            sa.Column("grants", json_type, nullable=True),
            sa.Column("revokes", json_type, nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_custom_roles_tenant_id", "custom_roles", ["tenant_id"])
        op.create_index("ix_custom_role_key", "custom_roles", ["tenant_id", "key"],
                        unique=True)

    if "contract_access" not in _tables(bind):
        op.create_table(
            "contract_access",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("contract_id", sa.String(32), nullable=False),
            sa.Column("user_id", sa.String(32), nullable=True),
            sa.Column("role", sa.String(50), nullable=True),
            sa.Column("level", sa.String(10), nullable=False, server_default="read"),
            sa.Column("reason", sa.String(400), nullable=False, server_default=""),
            sa.Column("granted_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_contract_access_tenant_id", "contract_access", ["tenant_id"])
        op.create_index("ix_contract_access_contract_id", "contract_access", ["contract_id"])
        op.create_index("ix_contract_access_user_id", "contract_access", ["user_id"])
        op.create_index("ix_access_lookup", "contract_access",
                        ["tenant_id", "contract_id", "user_id"])

    if "legal_holds" not in _tables(bind):
        op.create_table(
            "legal_holds",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("matter", sa.String(200), nullable=False),
            sa.Column("reference", sa.String(100), nullable=False, server_default=""),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("contract_ids", json_type, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("custodian", sa.String(200), nullable=False, server_default=""),
            sa.Column("placed_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("placed_at", sa.DateTime(), nullable=False),
            sa.Column("released_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("release_reason", sa.String(500), nullable=False, server_default=""),
        )
        op.create_index("ix_legal_holds_tenant_id", "legal_holds", ["tenant_id"])
        op.create_index("ix_legal_holds_status", "legal_holds", ["status"])
        op.create_index("ix_hold_matter", "legal_holds", ["tenant_id", "status"])

    if "temporary_access" not in _tables(bind):
        op.create_table(
            "temporary_access",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("contract_id", sa.String(32), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("organisation", sa.String(200), nullable=False, server_default=""),
            # Hash only. A link that leaks from a mailbox must not be replayable from the
            # database if the database is later exposed.
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("scope", sa.String(20), nullable=False, server_default="view"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("watermark", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("allow_download", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("granted_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("revoked_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_temporary_access_tenant_id", "temporary_access", ["tenant_id"])
        op.create_index("ix_temporary_access_contract_id", "temporary_access",
                        ["contract_id"])
        op.create_index("ix_temporary_access_token_hash", "temporary_access", ["token_hash"])
        op.create_index("ix_temporary_access_status", "temporary_access", ["status"])
        op.create_index("ix_temporary_access_expires_at", "temporary_access", ["expires_at"])
        op.create_index("ix_temp_access_lookup", "temporary_access",
                        ["tenant_id", "contract_id", "status"])

    if "step_up_challenges" not in _tables(bind):
        op.create_table(
            "step_up_challenges",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("user_id", sa.String(32), nullable=False),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("object_type", sa.String(40), nullable=False, server_default=""),
            sa.Column("object_id", sa.String(32), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("method", sa.String(20), nullable=False, server_default=""),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("satisfied_at", sa.DateTime(), nullable=True),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_step_up_challenges_tenant_id", "step_up_challenges",
                        ["tenant_id"])
        op.create_index("ix_step_up_challenges_user_id", "step_up_challenges", ["user_id"])
        op.create_index("ix_step_up_challenges_status", "step_up_challenges", ["status"])
        op.create_index("ix_stepup_lookup", "step_up_challenges",
                        ["tenant_id", "user_id", "status"])

    if "confidential" not in _columns(bind, "contracts"):
        op.add_column("contracts", sa.Column(
            "confidential", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.create_index("ix_contracts_confidential", "contracts",
                        ["tenant_id", "confidential"])

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

    inspector = sa.inspect(bind)
    present = {i["name"] for i in inspector.get_indexes("contracts")}
    for name in ("ix_contracts_confidential",):
        if name in present:
            op.drop_index(name, table_name="contracts")
    if "confidential" in _columns(bind, "contracts"):
        with op.batch_alter_table("contracts") as batch:
            batch.drop_column("confidential")

    for table in ("step_up_challenges", "temporary_access", "legal_holds",
                  "contract_access", "custom_roles"):
        if table in _tables(bind):
            op.drop_table(table)
