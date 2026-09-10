"""AI data capture awaiting human confirmation (Phase 3, item 7).

Extraction never writes to a contract. A confidence score is not a fact, so every captured set
of fields lands in `extraction_reviews` for a person to confirm field by field, and what they
accepted is audited.

Revision ID: 0024_ai_assist
Revises: 0023_audit_seq
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0024_ai_assist"
down_revision = "0023_audit_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    json_type = db_dialect.json_column(dialect)

    if "extraction_reviews" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "extraction_reviews",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("contract_id", sa.String(32), nullable=False),
            sa.Column("file_name", sa.String(300), nullable=False, server_default=""),
            sa.Column("provider", sa.String(40), nullable=False, server_default="stub"),
            sa.Column("fields", json_type, nullable=True),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("detected_clauses", json_type, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("applied_fields", json_type, nullable=True),
            sa.Column("reviewed_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_extraction_reviews_tenant_id", "extraction_reviews", ["tenant_id"])
        op.create_index("ix_extraction_reviews_contract_id", "extraction_reviews",
                        ["contract_id"])
        op.create_index("ix_extraction_reviews_status", "extraction_reviews", ["status"])
        # The queue view: "what is waiting for confirmation on this agreement?"
        op.create_index("ix_extraction_contract", "extraction_reviews",
                        ["tenant_id", "contract_id", "status"])

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, ["extraction_reviews"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, ["extraction_reviews"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass
    if "extraction_reviews" in sa.inspect(bind).get_table_names():
        op.drop_table("extraction_reviews")
