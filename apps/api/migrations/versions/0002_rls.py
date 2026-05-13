"""row-level security for multi-tenant isolation (PostgreSQL only)

For every tenant-scoped table this enables (and FORCEs) RLS with a `tenant_isolation` policy
keyed off the session GUC `app.cm_tenant` (set per-request from the JWT — see app/database.py).
The policy is permissive when the GUC is unset (so unauthenticated auth endpoints still work)
and strict when it's set. On SQLite this migration is a no-op.

Revision ID: 0002_rls
Revises: 0001_initial
Create Date: 2026-05-12
"""
from alembic import op

revision = "0002_rls"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

# tenant-scoped tables (the `tenants` registry table is intentionally excluded)
TENANT_TABLES = ["users", "contracts", "contract_versions", "comments", "audit_log", "notifications", "ocr_jobs"]

_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for t in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation ON "{t}" '
            f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for t in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}"')
        op.execute(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY')
