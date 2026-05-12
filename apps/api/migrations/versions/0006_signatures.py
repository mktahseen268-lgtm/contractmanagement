"""e-signature: signature_envelopes, signature_recipients, signature_events (+ RLS on PostgreSQL)

Idempotent (create_all checkfirst; drop-then-create policies). RLS skipped on SQLite.

Revision ID: 0006_signatures
Revises: 0005_workflows
Create Date: 2026-05-13
"""
from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0006_signatures"
down_revision = "0005_workflows"
branch_labels = None
depends_on = None

_NEW_TABLES = ["signature_envelopes", "signature_recipients", "signature_events"]
_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[models.SignatureEnvelope.__table__, models.SignatureRecipient.__table__, models.SignatureEvent.__table__],
        checkfirst=True,
    )
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
