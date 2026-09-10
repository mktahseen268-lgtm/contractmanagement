"""Bulk send: one template to many signers, plus envelope chasing and expiry (BB-09).

The five columns added to `signature_envelopes` are deliberately not on the batch. Chasing and
expiry are properties of an envelope, not of how it happened to be created — an envelope sent
one at a time from the contract page needs them just as much, and a reminder schedule that only
existed for bulk sends would have to be built a second time the first time anybody asked.

Revision ID: 0031_bulk_send
Revises: 0030_adoption
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0031_bulk_send"
down_revision = "0030_adoption"
branch_labels = None
depends_on = None

TABLES = ("bulk_send_batches", "bulk_send_items")

ENVELOPE_COLUMNS = (
    ("expires_at", sa.Column("expires_at", sa.DateTime(), nullable=True)),
    ("reminder_interval_days",
     sa.Column("reminder_interval_days", sa.Integer(), nullable=False, server_default="0")),
    ("max_reminders",
     sa.Column("max_reminders", sa.Integer(), nullable=False, server_default="0")),
    ("reminders_sent",
     sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0")),
    ("last_reminder_at", sa.Column("last_reminder_at", sa.DateTime(), nullable=True)),
)


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    existing = _tables(bind)
    json_type = db_dialect.json_column(dialect)

    if "signature_envelopes" in existing:
        have = _columns(bind, "signature_envelopes")
        for name, column in ENVELOPE_COLUMNS:
            if name not in have:
                op.add_column("signature_envelopes", column)
        # The chase sweep filters on it and nothing else, so it is the whole index.
        if "expires_at" not in have:
            op.create_index("ix_signature_envelopes_expires_at",
                            "signature_envelopes", ["expires_at"])

    if "bulk_send_batches" not in existing:
        op.create_table(
            "bulk_send_batches",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("template_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(240), nullable=False, server_default=""),
            sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
            sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("shared_values", json_type, nullable=True),
            sa.Column("reminder_interval_days", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("max_reminders", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expiry_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("job_id", sa.String(32), nullable=True),
            sa.Column("created_by", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_bulk_send_batches_tenant_id", "bulk_send_batches", ["tenant_id"])
        op.create_index("ix_bulk_send_batches_template_id", "bulk_send_batches",
                        ["template_id"])
        op.create_index("ix_bulk_send_batches_status", "bulk_send_batches", ["status"])
        op.create_index("ix_bulk_send_batches_created_at", "bulk_send_batches", ["created_at"])
        # The list page asks one question: what is this tenant running right now.
        op.create_index("ix_bulk_batch_tenant_status", "bulk_send_batches",
                        ["tenant_id", "status"])

    if "bulk_send_items" not in existing:
        op.create_table(
            "bulk_send_items",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("batch_id", sa.String(32),
                      sa.ForeignKey("bulk_send_batches.id"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("values", json_type, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("contract_id", sa.String(32), nullable=True),
            sa.Column("envelope_id", sa.String(32), nullable=True),
            sa.Column("error", sa.String(600), nullable=False, server_default=""),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_bulk_send_items_tenant_id", "bulk_send_items", ["tenant_id"])
        op.create_index("ix_bulk_send_items_batch_id", "bulk_send_items", ["batch_id"])
        op.create_index("ix_bulk_send_items_status", "bulk_send_items", ["status"])
        # The worker's own query: this batch's rows, in order. Also what the detail page reads.
        op.create_index("ix_bulk_item_batch_seq", "bulk_send_items", ["batch_id", "sequence"])

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, list(TABLES)):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, list(TABLES)):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass

    existing = _tables(bind)
    for table in reversed(TABLES):
        if table in existing:
            op.drop_table(table)

    if "signature_envelopes" in existing:
        have = _columns(bind, "signature_envelopes")
        if "expires_at" in have:
            try:
                op.drop_index("ix_signature_envelopes_expires_at",
                              table_name="signature_envelopes")
            except Exception:  # noqa: BLE001
                pass
        for name, _column in reversed(ENVELOPE_COLUMNS):
            if name in have:
                op.drop_column("signature_envelopes", name)
