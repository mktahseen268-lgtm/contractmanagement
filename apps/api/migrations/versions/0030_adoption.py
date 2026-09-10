"""Adoption: contextual help, knowledge base, training hub (Phase 9, items 1-3).

Help copy lives in the database rather than the front-end bundle so Legal can correct wording
without a deploy — which is the requirement, and also the reason a wrong tooltip does not have
to wait a fortnight for a release train.

Revision ID: 0030_adoption
Revises: 0029_webauthn
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0030_adoption"
down_revision = "0029_webauthn"
branch_labels = None
depends_on = None

TABLES = ("help_topics", "knowledge_articles", "training_courses",
          "training_progress", "training_sessions")


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    existing = _tables(bind)
    json_type = db_dialect.json_column(dialect)

    if "help_topics" not in existing:
        op.create_table(
            "help_topics",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("key", sa.String(120), nullable=False),
            sa.Column("locale", sa.String(8), nullable=False, server_default="en"),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("surface", sa.String(80), nullable=False, server_default=""),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_help_topics_tenant_id", "help_topics", ["tenant_id"])
        op.create_index("ix_help_topics_key", "help_topics", ["key"])
        # One row per (tenant, key, locale). Without this a second seed run on a race would
        # duplicate every topic and the editor would show each one twice.
        op.create_index("ix_help_key", "help_topics", ["tenant_id", "key", "locale"],
                        unique=True)

    if "knowledge_articles" not in existing:
        op.create_table(
            "knowledge_articles",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("slug", sa.String(120), nullable=False),
            sa.Column("locale", sa.String(8), nullable=False, server_default="en"),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("summary", sa.String(500), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("category", sa.String(40), nullable=False, server_default="faq"),
            sa.Column("tags", json_type, nullable=True),
            sa.Column("video_file_id", sa.String(32), nullable=True),
            sa.Column("video_duration_s", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("audience_roles", json_type, nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_knowledge_articles_tenant_id", "knowledge_articles", ["tenant_id"])
        op.create_index("ix_knowledge_articles_slug", "knowledge_articles", ["slug"])
        op.create_index("ix_knowledge_articles_category", "knowledge_articles", ["category"])
        op.create_index("ix_kb_slug", "knowledge_articles",
                        ["tenant_id", "slug", "locale"], unique=True)
        op.create_index("ix_kb_category", "knowledge_articles", ["tenant_id", "category"])

    if "training_courses" not in existing:
        op.create_table(
            "training_courses",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("slug", sa.String(120), nullable=False),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("summary", sa.String(500), nullable=False, server_default=""),
            sa.Column("for_roles", json_type, nullable=True),
            sa.Column("modules", json_type, nullable=True),
            # Holds the answer key. Never served to a client — `training_service.quiz_for`
            # strips it, and a quiz whose answers reach the browser certifies nothing.
            sa.Column("quiz", json_type, nullable=True),
            sa.Column("pass_mark", sa.Integer(), nullable=False, server_default="80"),
            sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("certificate_valid_months", sa.Integer(), nullable=False,
                      server_default="12"),
            sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_training_courses_tenant_id", "training_courses", ["tenant_id"])
        op.create_index("ix_training_courses_slug", "training_courses", ["slug"])
        op.create_index("ix_course_slug", "training_courses", ["tenant_id", "slug"], unique=True)

    if "training_progress" not in existing:
        op.create_table(
            "training_progress",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("user_id", sa.String(32), nullable=False),
            sa.Column("course_id", sa.String(32), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="not_started"),
            sa.Column("completed_modules", json_type, nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("best_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("passed_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("certificate_no", sa.String(40), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_training_progress_tenant_id", "training_progress", ["tenant_id"])
        op.create_index("ix_training_progress_user_id", "training_progress", ["user_id"])
        op.create_index("ix_training_progress_course_id", "training_progress", ["course_id"])
        # One row per person per course. The unique index is what makes `progress_for`'s
        # get-or-create safe when two tabs open the same course at once.
        op.create_index("ix_progress_user_course", "training_progress",
                        ["tenant_id", "user_id", "course_id"], unique=True)
        op.create_index("ix_progress_status", "training_progress", ["tenant_id", "status"])

    if "training_sessions" not in existing:
        op.create_table(
            "training_sessions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("kind", sa.String(20), nullable=False, server_default="webinar"),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("location", sa.String(300), nullable=False, server_default=""),
            sa.Column("trainer", sa.String(200), nullable=False, server_default=""),
            sa.Column("capacity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("registered_user_ids", json_type, nullable=True),
            # Kept apart from registration: "have fifteen resources been trained" is a question
            # about who turned up, and a list of who intended to cannot answer it.
            sa.Column("attended_user_ids", json_type, nullable=True),
            sa.Column("recording_file_id", sa.String(32), nullable=True),
            sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_training_sessions_tenant_id", "training_sessions", ["tenant_id"])
        op.create_index("ix_training_sessions_starts_at", "training_sessions", ["starts_at"])
        op.create_index("ix_session_start", "training_sessions", ["tenant_id", "starts_at"])

    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, list(TABLES)):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, list(TABLES)):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass

    existing = _tables(bind)
    for table in reversed(TABLES):
        if table in existing:
            op.drop_table(table)
