"""background_jobs + email_outbox (+ RLS on PostgreSQL)

Revision ID: 0009_jobs_outbox
Revises: 0008_obligations
Create Date: 2026-05-13
"""
from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0009_jobs_outbox"
down_revision = "0008_obligations"
branch_labels = None
depends_on = None

_NEW_TABLES = ["background_jobs", "email_outbox"]
# Permissive when GUC unset (Celery beat & auth-less sends need it), strict when set.
_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[models.BackgroundJob.__table__, models.EmailOutbox.__table__], checkfirst=True)
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
