"""auth hardening: users.mfa_*, sessions, otp_codes, recovery_codes (+ RLS on PostgreSQL)

`0001_initial` materialised the model state via create_all, so on a brand-new DB the new
columns/tables may already exist; everything here is therefore done idempotently
(check-then-add for columns, create_all(checkfirst=True) for tables, drop-then-create for policies).
RLS DDL is skipped on SQLite.

Revision ID: 0004_auth
Revises: 0003_files
Create Date: 2026-05-12
"""
import sqlalchemy as sa
from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0004_auth"
down_revision = "0003_files"
branch_labels = None
depends_on = None

_NEW_TABLES = ["sessions", "otp_codes", "recovery_codes"]
_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def _existing_columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # 1) new columns on users (add only if missing)
    user_cols = _existing_columns(bind, "users")
    if "mfa_enabled" not in user_cols:
        op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "mfa_secret" not in user_cols:
        op.add_column("users", sa.Column("mfa_secret", sa.String(length=64), nullable=True))

    # 2) new tables (create only the missing ones)
    Base.metadata.create_all(
        bind=bind,
        tables=[models.Session.__table__, models.OtpCode.__table__, models.RecoveryCode.__table__],
        checkfirst=True,
    )

    # 3) RLS on the new tenant-scoped tables (PostgreSQL only)
    if bind.dialect.name == "postgresql":
        for t in _NEW_TABLES:
            op.execute(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY')
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}"')
            op.execute(f'CREATE POLICY tenant_isolation ON "{t}" USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for t in _NEW_TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}"')
    for t in _NEW_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{t}"')
    cols = _existing_columns(bind, "users")
    if "mfa_secret" in cols:
        op.drop_column("users", "mfa_secret")
    if "mfa_enabled" in cols:
        op.drop_column("users", "mfa_enabled")
