"""file_objects table + its RLS policy (PostgreSQL)

`0001_initial` materialises the model state via create_all, so on a brand-new DB the
`file_objects` table already exists; `create_all(checkfirst=True)` here is a no-op then.
On a DB that pre-dates this revision it creates the table. The RLS policy is added
idempotently (drop-if-exists then create) and skipped on SQLite.

Revision ID: 0003_files
Revises: 0002_rls
Create Date: 2026-05-12
"""
from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0003_files"
down_revision = "0002_rls"
branch_labels = None
depends_on = None

_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def upgrade() -> None:
    bind = op.get_bind()
    # create the table if it doesn't already exist
    Base.metadata.create_all(bind=bind, tables=[models.FileObject.__table__], checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "file_objects" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "file_objects" FORCE ROW LEVEL SECURITY')
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "file_objects"')
        op.execute(f'CREATE POLICY tenant_isolation ON "file_objects" USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation ON "file_objects"')
    op.execute('DROP TABLE IF EXISTS "file_objects"')
