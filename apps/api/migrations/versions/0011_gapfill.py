"""contract_templates + api_keys + webhook_endpoints + webhook_deliveries (+ RLS on PostgreSQL)

Closes a few gaps from the original spec: a templates library, programmatic API keys for
headless integrations, and outbound webhooks for events.

Revision ID: 0011_gapfill
Revises: 0010_signature_tabs
Create Date: 2026-05-13
"""
from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0011_gapfill"
down_revision = "0010_signature_tabs"
branch_labels = None
depends_on = None

_NEW_TABLES = ["contract_templates", "api_keys", "webhook_endpoints", "webhook_deliveries"]
_POLICY_EXPR = "coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id)"


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[
            models.ContractTemplate.__table__,
            models.ApiKey.__table__,
            models.WebhookEndpoint.__table__,
            models.WebhookDelivery.__table__,
        ],
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
