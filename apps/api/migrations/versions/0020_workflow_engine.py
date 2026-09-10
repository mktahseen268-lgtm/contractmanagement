"""workflow engine rebuild: parallel stages, SLA + escalation, approval matrix, delegation,
mentions, internal-only comments

Phase 4 — RFI §3. The v1 engine advanced one step at a time; the RFI is built entirely around
parallel multi-stakeholder review, where Legal, Finance, Compliance and IS look at an agreement
at the same time and each marks their own review complete independently.

  workflow_definitions  + stages / non_standard_stages (JSON). The legacy flat `steps` list is
                        kept and promotes to one-step-per-stage, so existing definitions and
                        in-flight runs keep working unchanged.
  workflow_runs         + stages (snapshotted at start — a definition edited mid-review must
                        not change the rules an in-flight approval is judged by),
                        current_stage, applied_rule_ids, routing_snapshot
  workflow_run_steps    + stage_index, sla_hours, due_at, reminded_at, escalated_at,
                        escalated_to, delegated_from, added_mid_flight, added_by, activated_at
  contracts             + is_non_standard / non_standard_reason / non_standard_at (RFI §3.1)
  comments              + internal_only (the privacy flag), department, kind, anchor range
  users                 + is_client_facing (RFI §3.5), department

  approval_rules        the dynamic approval matrix
  delegations           out-of-office proxies
  holidays              non-working days for the SLA clock
  mentions              @mentions, as rows so "mentions me" is an indexed query

Portable across PostgreSQL / MSSQL / Oracle / SQLite. Re-runnable.

Revision ID: 0020_workflow_engine
Revises: 0019_wet_signature
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0020_workflow_engine"
down_revision = "0019_wet_signature"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["approval_rules", "delegations", "holidays", "mentions"]

_ADDITIONS: dict[str, list[tuple[str, sa.Column]]] = {
    "workflow_definitions": [
        ("stages", sa.Column("stages", sa.JSON(), nullable=True)),
        ("non_standard_stages", sa.Column("non_standard_stages", sa.JSON(), nullable=True)),
    ],
    "workflow_runs": [
        ("stages", sa.Column("stages", sa.JSON(), nullable=True)),
        ("current_stage", sa.Column("current_stage", sa.Integer(), nullable=False, server_default="0")),
        ("applied_rule_ids", sa.Column("applied_rule_ids", sa.JSON(), nullable=True)),
        ("routing_snapshot", sa.Column("routing_snapshot", sa.JSON(), nullable=True)),
    ],
    "workflow_run_steps": [
        ("stage_index", sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0")),
        ("sla_hours", sa.Column("sla_hours", sa.Integer(), nullable=False, server_default="0")),
        ("due_at", sa.Column("due_at", sa.DateTime(), nullable=True)),
        ("reminded_at", sa.Column("reminded_at", sa.DateTime(), nullable=True)),
        ("escalated_at", sa.Column("escalated_at", sa.DateTime(), nullable=True)),
        ("escalated_to", sa.Column("escalated_to", sa.String(32), nullable=True)),
        ("delegated_from", sa.Column("delegated_from", sa.String(32), nullable=True)),
        ("added_mid_flight", sa.Column("added_mid_flight", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("added_by", sa.Column("added_by", sa.String(32), nullable=True)),
        ("activated_at", sa.Column("activated_at", sa.DateTime(), nullable=True)),
    ],
    "contracts": [
        ("is_non_standard", sa.Column("is_non_standard", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("non_standard_reason", sa.Column("non_standard_reason", sa.String(400), nullable=False, server_default="")),
        ("non_standard_at", sa.Column("non_standard_at", sa.DateTime(), nullable=True)),
    ],
    "comments": [
        ("internal_only", sa.Column("internal_only", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("department", sa.Column("department", sa.String(100), nullable=False, server_default="")),
        ("kind", sa.Column("kind", sa.String(20), nullable=False, server_default="comment")),
        ("anchor_start", sa.Column("anchor_start", sa.Integer(), nullable=True)),
        ("anchor_end", sa.Column("anchor_end", sa.Integer(), nullable=True)),
    ],
    "users": [
        ("is_client_facing", sa.Column("is_client_facing", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("department", sa.Column("department", sa.String(100), nullable=False, server_default="")),
    ],
}

_INDEXES = [
    ("ix_wf_step_stage", "workflow_run_steps", ["run_id", "stage_index"]),
    ("ix_wf_step_due", "workflow_run_steps", ["status", "due_at"]),
    ("ix_wf_step_escalated", "workflow_run_steps", ["tenant_id", "escalated_at"]),
    ("ix_wf_run_stage", "workflow_runs", ["tenant_id", "status", "current_stage"]),
    ("ix_contracts_non_standard", "contracts", ["tenant_id", "is_non_standard"]),
    ("ix_comments_internal", "comments", ["contract_id", "internal_only"]),
]


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

    for table, additions in _ADDITIONS.items():
        existing = _columns(bind, table)
        if not existing:
            continue
        for name, column in additions:
            if name not in existing:
                op.add_column(table, column)

    if "approval_rules" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "approval_rules",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("contract_type", sa.String(50), nullable=False, server_default=""),
            sa.Column("department", sa.String(100), nullable=False, server_default=""),
            sa.Column("currency", sa.String(3), nullable=False, server_default=""),
            sa.Column("min_value", sa.Float(), nullable=False, server_default="0"),
            sa.Column("max_value", sa.Float(), nullable=True),
            sa.Column("risk_level", sa.String(20), nullable=False, server_default=""),
            sa.Column("governing_law", sa.String(100), nullable=False, server_default=""),
            sa.Column("non_standard_only", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("min_playbook_deviations", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stage_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("stage_policy", sa.String(20), nullable=False, server_default="all"),
            sa.Column("stage_threshold", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stage_steps", sa.JSON(), nullable=True),
            sa.Column("sla_hours", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("escalate_to_user_id", sa.String(32), nullable=True),
            sa.Column("insert_after_stage", sa.Integer(), nullable=False, server_default="-1"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_approval_rule_tenant", "approval_rules", ["tenant_id"])
        op.create_index("ix_approval_rule_lookup", "approval_rules",
                        ["tenant_id", "is_active", "contract_type"])

    if "delegations" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "delegations",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("from_user_id", sa.String(32), nullable=False),
            sa.Column("to_user_id", sa.String(32), nullable=False),
            sa.Column("scope", sa.String(50), nullable=False, server_default="all"),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(400), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_delegation_tenant", "delegations", ["tenant_id"])
        # The hot path: "does anything route away from this user right now?"
        op.create_index("ix_delegation_window", "delegations",
                        ["tenant_id", "from_user_id", "is_active", "starts_at", "ends_at"])

    if "holidays" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "holidays",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_holiday_lookup", "holidays", ["tenant_id", "day"], unique=True)

    if "mentions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "mentions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("comment_id", sa.String(32), nullable=False),
            sa.Column("contract_id", sa.String(32), nullable=False),
            sa.Column("mentioned_user_id", sa.String(32), nullable=False),
            sa.Column("mentioned_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("mentioned_by_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("internal_only", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mention_comment", "mentions", ["comment_id"])
        op.create_index("ix_mention_contract", "mentions", ["contract_id"])
        # The "mentions me" inbox filter.
        op.create_index("ix_mention_inbox", "mentions",
                        ["tenant_id", "mentioned_user_id", "read_at"])

    for name, table, columns in _INDEXES:
        if table in sa.inspect(bind).get_table_names() and name not in _indexes(bind, table):
            try:
                op.create_index(name, table, columns)
            except Exception:  # noqa: BLE001
                pass

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, _TENANT_TABLES):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
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

    existing = set(sa.inspect(bind).get_table_names())
    for table in ("mentions", "holidays", "delegations", "approval_rules"):
        if table in existing:
            op.drop_table(table)

    for table, additions in _ADDITIONS.items():
        names = {n for n, _ in additions}
        _drop_indexes_covering(bind, table, names)
        cols = _columns(bind, table)
        if not cols:
            continue
        with op.batch_alter_table(table) as batch:
            for name, _ in reversed(additions):
                if name in cols:
                    batch.drop_column(name)
