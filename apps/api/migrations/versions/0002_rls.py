"""row-level security for tenant isolation (PostgreSQL / MSSQL / Oracle)

For every tenant-scoped table this enables row security keyed off a per-session tenant value
(set per-request from the JWT — see app/database.py). The DDL is dialect-specific and lives in
`app/db_dialect.py`:

  postgresql — ENABLE + FORCE ROW LEVEL SECURITY with a `tenant_isolation` policy on the
               `app.cm_tenant` GUC.
  mssql      — a SECURITY POLICY with FILTER + BLOCK predicates over an inline table-valued
               function reading SESSION_CONTEXT(N'cm_tenant').
  oracle     — an application context (CM_CTX) plus a VPD policy per table via
               DBMS_RLS.ADD_POLICY.

All three are permissive when the tenant is unset (so unauthenticated /auth/login and
/auth/refresh still work) and strict when it is set. On SQLite this migration is a no-op.

`ENFORCE_DB_ISOLATION=false` skips the DDL entirely — supported only in
`DEPLOYMENT_MODE=single_tenant`, where one tenant makes the predicate a tautology and the
repository-layer `tenant_id` filter is the operative boundary. `validate_for_production`
rejects that combination in the SaaS profile.

Revision ID: 0002_rls
Revises: 0001_initial
Create Date: 2026-05-12
"""
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0002_rls"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

# tenant-scoped tables (the `tenants` registry table is intentionally excluded)
TENANT_TABLES = ["users", "contracts", "contract_versions", "comments", "audit_log", "notifications", "ocr_jobs"]


def upgrade() -> None:
    if not settings.enforce_db_isolation:
        return
    dialect = db_dialect.dialect_of(op.get_bind())
    for stmt in db_dialect.enable_row_security(dialect, TENANT_TABLES):
        op.execute(stmt)


def downgrade() -> None:
    dialect = db_dialect.dialect_of(op.get_bind())
    for stmt in db_dialect.disable_row_security(dialect, TENANT_TABLES):
        op.execute(stmt)
