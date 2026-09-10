"""FIDO2 / WebAuthn credentials (Phase 8, item 1).

Only public keys are stored. There is no private key here and never can be — which is what
makes a passkey phishing-resistant, and also means a database breach yields nothing an
attacker can authenticate with.

Revision ID: 0029_webauthn
Revises: 0028_access_control
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0029_webauthn"
down_revision = "0028_access_control"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if "webauthn_credentials" not in _tables(bind):
        op.create_table(
            "webauthn_credentials",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("user_id", sa.String(32), nullable=False),
            sa.Column("credential_id", sa.String(400), nullable=False),
            sa.Column("public_key", sa.Text(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("label", sa.String(120), nullable=False,
                      server_default="Security key"),
            sa.Column("transports", sa.String(120), nullable=False, server_default=""),
            sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("aaguid", sa.String(64), nullable=False, server_default=""),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_webauthn_credentials_tenant_id", "webauthn_credentials",
                        ["tenant_id"])
        op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials",
                        ["user_id"])
        # Globally unique: a credential id identifies one authenticator, and the same key
        # registered under two accounts would make the counter check meaningless.
        op.create_index("ix_webauthn_credential", "webauthn_credentials",
                        ["credential_id"], unique=True)
        op.create_index("ix_webauthn_user", "webauthn_credentials",
                        ["tenant_id", "user_id"])

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, ["webauthn_credentials"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, ["webauthn_credentials"]):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass
    if "webauthn_credentials" in _tables(bind):
        op.drop_table("webauthn_credentials")
