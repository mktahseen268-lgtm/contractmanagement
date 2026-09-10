"""visitor esigning: public signing invitations, visitor sessions, SMS outbox channel

Phase 2 items 2-3 — RFP §4a "Visitor / merchant eSigning surface".

External signatories must be able to sign with **no per-visitor user provisioning**, reached by
web link, branch-tablet kiosk, mobile link or QR code, at 100,000 signatories a year.

  signing_invitations   a shareable, reusable, expiring public link per document. Only the
                        token HASH is stored (plus a Fernet-encrypted copy so the QR can be
                        re-rendered), so a database leak cannot reconstruct a working URL.
  visitor_sessions      one external signatory's journey: identity claim, OTP proof, the
                        certificate minted for them, and the consent evidence (did they
                        actually read it) that goes on the Certificate of Completion.

`email_outbox` gains `channel` + `provider_ref` so SMS and email share one delivery-audit
surface. **The SMTP flush beat now filters on `channel='email'`** — without that it would try
to email a phone number.

Portable across PostgreSQL / MSSQL / Oracle / SQLite. Re-runnable.

Revision ID: 0018_visitor_esign
Revises: 0017_esignature_depth
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0018_visitor_esign"
down_revision = "0017_esignature_depth"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["signing_invitations", "visitor_sessions"]

_OUTBOX_COLUMNS = [
    ("channel", sa.Column("channel", sa.String(10), nullable=False, server_default="email")),
    ("provider_ref", sa.Column("provider_ref", sa.String(200), nullable=False, server_default="")),
]


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


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
    existing = _tables(bind)

    if "signing_invitations" not in existing:
        op.create_table(
            "signing_invitations",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("contract_id", sa.String(32), nullable=False),
            sa.Column("label", sa.String(200), nullable=False, server_default=""),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("token_secret", sa.String(512), nullable=True),
            sa.Column("otp_channel", sa.String(10), nullable=False, server_default="any"),
            sa.Column("require_otp", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("collect_cnic", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("max_signatures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("signature_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_invitation_tenant", "signing_invitations", ["tenant_id"])
        op.create_index("ix_invitation_contract", "signing_invitations", ["contract_id"])
        # The public landing page hits this on every request — it is the hot path of the
        # whole visitor surface.
        op.create_index("ix_invitation_token_hash", "signing_invitations", ["token_hash"])
        op.create_index("ix_invitation_active", "signing_invitations", ["is_active", "expires_at"])

    if "visitor_sessions" not in existing:
        op.create_table(
            "visitor_sessions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("invitation_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("email", sa.String(320), nullable=False, server_default=""),
            sa.Column("phone", sa.String(32), nullable=False, server_default=""),
            sa.Column("cnic_last4", sa.String(4), nullable=False, server_default=""),
            sa.Column("otp_channel", sa.String(10), nullable=False, server_default="email"),
            sa.Column("otp_code_hash", sa.String(64), nullable=True),
            sa.Column("otp_expires_at", sa.DateTime(), nullable=True),
            sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("otp_sent_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("party_ref", sa.String(64), nullable=False, server_default=""),
            sa.Column("recipient_id", sa.String(32), nullable=True),
            sa.Column("certificate_id", sa.String(32), nullable=True),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("scroll_completed_at", sa.DateTime(), nullable=True),
            sa.Column("pages_viewed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("entry_point", sa.String(20), nullable=False, server_default="web"),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("user_agent", sa.String(400), nullable=False, server_default=""),
            sa.Column("device_fingerprint", sa.String(64), nullable=False, server_default=""),
            sa.Column("geo", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="started"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_visitor_tenant", "visitor_sessions", ["tenant_id"])
        op.create_index("ix_visitor_invitation", "visitor_sessions", ["invitation_id"])
        op.create_index("ix_visitor_party_ref", "visitor_sessions", ["party_ref"])
        op.create_index("ix_visitor_recipient", "visitor_sessions", ["recipient_id"])
        op.create_index("ix_visitor_status", "visitor_sessions", ["status"])
        # The per-invitation-per-IP rate limit query.
        op.create_index("ix_visitor_rate_limit", "visitor_sessions",
                        ["invitation_id", "ip", "created_at"])

    outbox = _columns(bind, "email_outbox")
    if outbox:
        for name, column in _OUTBOX_COLUMNS:
            if name not in outbox:
                op.add_column("email_outbox", column)
        if "ix_email_outbox_channel" not in _indexes(bind, "email_outbox"):
            op.create_index("ix_email_outbox_channel", "email_outbox", ["channel", "status"])

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, _TENANT_TABLES):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                # The tables may already carry a policy from a partial run.
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

    existing = _tables(bind)
    for table in ("visitor_sessions", "signing_invitations"):
        if table in existing:
            op.drop_table(table)

    _drop_indexes_covering(bind, "email_outbox", {name for name, _ in _OUTBOX_COLUMNS})
    outbox = _columns(bind, "email_outbox")
    with op.batch_alter_table("email_outbox") as batch:
        for name, _ in reversed(_OUTBOX_COLUMNS):
            if name in outbox:
                batch.drop_column(name)
