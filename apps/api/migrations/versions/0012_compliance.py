"""compliance: login_attempts + lockout_states + mfa_secret column widened (encrypted at rest)

Adds two security tables required for the RFI:
  - login_attempts: every authentication attempt (success or failure) — drives lockout
    + serves as the security-audit "who tried to log in as me" data source.
  - lockout_states: O(1) per-user counter + locked-until timestamp for fast checks at login.

Also widens `users.mfa_secret` from VARCHAR(64) to VARCHAR(256) because the value is now
stored encrypted (Fernet ciphertext + `fr$` prefix ≈ 100 chars for short plaintexts).
Existing plaintext base32 secrets continue to round-trip through `EncryptedString` (legacy
unprefixed values are returned as-is).

Revision ID: 0012_compliance
Revises: 0011_gapfill
Create Date: 2026-05-14
"""
import sqlalchemy as sa
from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0012_compliance"
down_revision = "0011_gapfill"
branch_labels = None
depends_on = None

_NEW_TABLES = ["login_attempts", "lockout_states"]
_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def _existing_columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    # 1) New tables
    Base.metadata.create_all(
        bind=bind,
        tables=[models.LoginAttempt.__table__, models.LockoutState.__table__],
        checkfirst=True,
    )
    # 2) Widen users.mfa_secret to store the AES-256-GCM ciphertext + tag
    if "users" in sa.inspect(bind).get_table_names():
        cols = _existing_columns(bind, "users")
        if "mfa_secret" in cols:
            if bind.dialect.name == "postgresql":
                op.execute("ALTER TABLE users ALTER COLUMN mfa_secret TYPE VARCHAR(256)")
            elif bind.dialect.name == "mssql":
                op.execute("ALTER TABLE users ALTER COLUMN mfa_secret NVARCHAR(256) NULL")
            # SQLite: no-op (VARCHAR length not enforced)
    # 3) RLS on the new tables (Postgres only; the permissive-when-unset GUC keeps auth-less
    #    inserts of "unknown email" failures working — they carry tenant_id='').
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
    # Don't narrow mfa_secret back — would corrupt encrypted values.
