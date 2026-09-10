"""hybrid execution: per-recipient signing mode + wet-signature attestations

Phase 2 item 5 — RFP §4a "Hybrid flexibility": e-signature and wet signature in one unbroken
digital trail. Government counterparties will not sign electronically; they need a printed
pack, a wet signature and a stamp, and the executed paper scanned back.

  signature_recipients.signing_mode   `electronic` (default) or `wet` — which path THIS party
                                      takes. A hybrid envelope has both, so one paper
                                      counterparty does not force everyone off the e-flow.
  wet_signature_attestations          the evidence. A scan proves nothing on its own; what
                                      carries weight is a named employee asserting, in the
                                      append-only audit chain, that this file (by SHA-256) is
                                      the executed copy, received on this date, optionally
                                      witnessed.

Portable across PostgreSQL / MSSQL / Oracle / SQLite. Re-runnable.

Revision ID: 0019_wet_signature
Revises: 0018_visitor_esign
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0019_wet_signature"
down_revision = "0018_visitor_esign"
branch_labels = None
depends_on = None

_RECIPIENT_COLUMNS = [
    ("signing_mode", sa.Column("signing_mode", sa.String(20), nullable=False,
                               server_default="electronic")),
]


def _columns(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _drop_indexes_covering(bind, table: str, columns: set[str]) -> None:
    """Drop every index touching `columns`, whatever it is named — see the note in 0017."""
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return
    for ix in insp.get_indexes(table):
        name = ix.get("name")
        if name and columns.intersection(ix.get("column_names") or []):
            try:
                op.drop_index(name, table_name=table)
            except Exception:  # noqa: BLE001
                pass


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    existing = _columns(bind, "signature_recipients")
    if existing:
        for name, column in _RECIPIENT_COLUMNS:
            if name not in existing:
                op.add_column("signature_recipients", column)

    if "wet_signature_attestations" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "wet_signature_attestations",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("envelope_id", sa.String(32), nullable=False),
            sa.Column("recipient_id", sa.String(32), nullable=True),
            sa.Column("file_id", sa.String(32), nullable=False),
            sa.Column("file_sha256", sa.String(64), nullable=False, server_default=""),
            sa.Column("declared_execution_date", sa.Date(), nullable=True),
            sa.Column("signatory_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("signatory_designation", sa.String(200), nullable=False, server_default=""),
            sa.Column("witness_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("witness_designation", sa.String(200), nullable=False, server_default=""),
            sa.Column("notes", sa.String(1000), nullable=False, server_default=""),
            sa.Column("attested_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("attested_by_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("attested_at", sa.DateTime(), nullable=False),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        )
        op.create_index("ix_wet_attest_tenant", "wet_signature_attestations", ["tenant_id"])
        op.create_index("ix_wet_attest_envelope", "wet_signature_attestations", ["envelope_id"])
        op.create_index("ix_wet_attest_recipient", "wet_signature_attestations", ["recipient_id"])
        op.create_index("ix_wet_attest_file", "wet_signature_attestations", ["file_id"])

        if settings.enforce_db_isolation:
            for stmt in db_dialect.enable_row_security(dialect, ["wet_signature_attestations"]):
                try:
                    op.execute(stmt)
                except Exception:  # noqa: BLE001
                    pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if "wet_signature_attestations" in sa.inspect(bind).get_table_names():
        if settings.enforce_db_isolation:
            for stmt in db_dialect.disable_row_security(dialect, ["wet_signature_attestations"]):
                try:
                    op.execute(stmt)
                except Exception:  # noqa: BLE001
                    pass
        op.drop_table("wet_signature_attestations")

    _drop_indexes_covering(bind, "signature_recipients", {n for n, _ in _RECIPIENT_COLUMNS})
    cols = _columns(bind, "signature_recipients")
    with op.batch_alter_table("signature_recipients") as batch:
        for name, _ in reversed(_RECIPIENT_COLUMNS):
            if name in cols:
                batch.drop_column(name)
