"""renewals: contracts.renewed_from_id

The successor created by /contracts/{id}/renew points back to its predecessor via this
nullable FK-by-string. (No new tables — just an ALTER + an index.)

Revision ID: 0007_renewals
Revises: 0006_signatures
Create Date: 2026-05-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_renewals"
down_revision = "0006_signatures"
branch_labels = None
depends_on = None


def _existing_columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _existing_indexes(bind, table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind, "contracts")
    if "renewed_from_id" not in cols:
        op.add_column("contracts", sa.Column("renewed_from_id", sa.String(length=32), nullable=True))
    idx = _existing_indexes(bind, "contracts")
    if "ix_contracts_renewed_from_id" not in idx:
        op.create_index("ix_contracts_renewed_from_id", "contracts", ["renewed_from_id"])


def downgrade() -> None:
    bind = op.get_bind()
    idx = _existing_indexes(bind, "contracts")
    if "ix_contracts_renewed_from_id" in idx:
        op.drop_index("ix_contracts_renewed_from_id", table_name="contracts")
    cols = _existing_columns(bind, "contracts")
    if "renewed_from_id" in cols:
        op.drop_column("contracts", "renewed_from_id")
