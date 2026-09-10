"""esignature depth: per-signatory PKI binding, execution reliability, authority matrix

Phase 2 — RFP §4a "Advanced eSignature" and §4a(ii) 4.1–4.4.

`signature_recipients` gains the identity binding the sealer needs to find *which* certificate
to sign with:
  - `signer_user_id` / `party_ref` — internal user or external signatory
  - `certificate_id`               — the certificate actually used
  - `identity_method` / `identity_verified_at` / `identity_evidence` — how the identity was
    bound (SSO, email OTP, SMS OTP), carried onto the Certificate of Completion

Without these the sealer would have to guess which certificate belongs to a signatory, and
guessing means falling back to one shared certificate — the arrangement the RFP forbids.

`signature_envelopes` gains execution-reliability state (§4.4 asks for a signing process "free
from execution/signature failures", which requires being able to *see* failures):
  - `seal_status` / `seal_attempts` / `seal_error` / `seal_last_attempt_at`
  - `lock_version` — optimistic locking so two concurrent signers cannot both advance the
    envelope from the same starting state
  - `execution_mode` — electronic | hybrid | wet

New table `signatory_authorities` — the delegation-of-authority matrix (§4.1–4.2).

Portable across PostgreSQL / MSSQL / Oracle / SQLite: plain column adds, B-tree indexes and
one new table. Re-runnable — every add is inspected first.

Revision ID: 0017_esignature_depth
Revises: 0016_pki
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0017_esignature_depth"
down_revision = "0016_pki"
branch_labels = None
depends_on = None

_RECIPIENT_COLUMNS = [
    ("signer_user_id", sa.Column("signer_user_id", sa.String(32), nullable=True)),
    ("party_ref", sa.Column("party_ref", sa.String(64), nullable=True)),
    ("certificate_id", sa.Column("certificate_id", sa.String(32), nullable=True)),
    ("identity_method", sa.Column("identity_method", sa.String(30), nullable=False, server_default="")),
    ("identity_verified_at", sa.Column("identity_verified_at", sa.DateTime(), nullable=True)),
    ("identity_evidence", sa.Column("identity_evidence", sa.JSON(), nullable=True)),
]

_ENVELOPE_COLUMNS = [
    ("seal_status", sa.Column("seal_status", sa.String(20), nullable=False, server_default="pending")),
    ("seal_attempts", sa.Column("seal_attempts", sa.Integer(), nullable=False, server_default="0")),
    ("seal_error", sa.Column("seal_error", sa.String(1000), nullable=False, server_default="")),
    ("seal_last_attempt_at", sa.Column("seal_last_attempt_at", sa.DateTime(), nullable=True)),
    ("lock_version", sa.Column("lock_version", sa.Integer(), nullable=False, server_default="0")),
    ("execution_mode", sa.Column("execution_mode", sa.String(20), nullable=False, server_default="electronic")),
]


def _columns(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    existing = _columns(bind, "signature_recipients")
    if existing:
        for name, column in _RECIPIENT_COLUMNS:
            if name not in existing:
                op.add_column("signature_recipients", column)
        idx = _indexes(bind, "signature_recipients")
        for name, cols in (
            ("ix_sig_recip_signer_user", ["signer_user_id"]),
            ("ix_sig_recip_party_ref", ["party_ref"]),
            ("ix_sig_recip_certificate", ["certificate_id"]),
        ):
            if name not in idx:
                op.create_index(name, "signature_recipients", cols)

    existing = _columns(bind, "signature_envelopes")
    if existing:
        for name, column in _ENVELOPE_COLUMNS:
            if name not in existing:
                op.add_column("signature_envelopes", column)
        if "ix_sig_env_seal_status" not in _indexes(bind, "signature_envelopes"):
            # The dead-letter view queries this: "show me everything that failed to seal".
            op.create_index("ix_sig_env_seal_status", "signature_envelopes",
                            ["tenant_id", "seal_status"])
        # Envelopes that completed before this migration were sealed by the old path; marking
        # them `pending` would make the dead-letter view scream about historical documents.
        op.execute(
            "UPDATE signature_envelopes SET seal_status = 'sealed' "
            "WHERE status = 'completed' AND sealed_pdf_file_id IS NOT NULL"
        )

    if "signatory_authorities" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "signatory_authorities",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("department", sa.String(100), nullable=False, server_default=""),
            sa.Column("contract_type", sa.String(50), nullable=False, server_default=""),
            sa.Column("currency", sa.String(3), nullable=False, server_default=""),
            sa.Column("min_value", sa.Float(), nullable=False, server_default="0"),
            sa.Column("max_value", sa.Float(), nullable=True),
            sa.Column("required_role", sa.String(40), nullable=False, server_default=""),
            sa.Column("required_user_id", sa.String(32), nullable=True),
            sa.Column("signatories_required", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("escalation_user_id", sa.String(32), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes", sa.String(500), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_sigauth_tenant", "signatory_authorities", ["tenant_id"])
        op.create_index("ix_sigauth_lookup", "signatory_authorities",
                        ["tenant_id", "is_active", "contract_type"])

        if settings.enforce_db_isolation:
            for stmt in db_dialect.enable_row_security(dialect, ["signatory_authorities"]):
                op.execute(stmt)


def _drop_indexes_covering(bind, table: str, columns: set[str]) -> None:
    """Drop every index that touches any of `columns`, whatever it is called.

    Necessary because `0001_initial` materialises the schema with
    `Base.metadata.create_all()`, so a column carrying `index=True` on the model already has
    an auto-named index (`ix_<table>_<column>`) before this migration runs — separate from any
    index the migration itself creates. On SQLite, `batch_alter_table` recreates the table and
    faithfully restores every reflected index, including ones on the columns being dropped,
    which then fails. Dropping by *coverage* rather than by name handles both origins.
    """
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


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if "signatory_authorities" in sa.inspect(bind).get_table_names():
        if settings.enforce_db_isolation:
            for stmt in db_dialect.disable_row_security(dialect, ["signatory_authorities"]):
                try:
                    op.execute(stmt)
                except Exception:  # noqa: BLE001
                    pass
        op.drop_table("signatory_authorities")

    env_columns = {name for name, _ in _ENVELOPE_COLUMNS}
    _drop_indexes_covering(bind, "signature_envelopes", env_columns)
    cols = _columns(bind, "signature_envelopes")
    with op.batch_alter_table("signature_envelopes") as batch:
        for name, _ in reversed(_ENVELOPE_COLUMNS):
            if name in cols:
                batch.drop_column(name)

    recip_columns = {name for name, _ in _RECIPIENT_COLUMNS}
    _drop_indexes_covering(bind, "signature_recipients", recip_columns)
    cols = _columns(bind, "signature_recipients")
    with op.batch_alter_table("signature_recipients") as batch:
        for name, _ in reversed(_RECIPIENT_COLUMNS):
            if name in cols:
                batch.drop_column(name)
