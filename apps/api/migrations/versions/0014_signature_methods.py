"""signature methods: capture drawn/uploaded signature images per recipient

Adds two columns to `signature_recipients`:
  - `signature_kind`  = 'typed' (default) | 'drawn' | 'uploaded' — how the signer adopted.
  - `signature_image` = base64 PNG/JPEG data URL for drawn/uploaded signatures (NULL for typed).

Backward-compatible: existing rows backfill to 'typed' with no image, so the executed PDF
keeps rendering '/s/ Name' exactly as before.

Revision ID: 0014_signature_methods
Revises: 0013_hardening
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_signature_methods"
down_revision = "0013_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "signature_recipients" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("signature_recipients")}
    if "signature_kind" not in cols:
        op.add_column(
            "signature_recipients",
            sa.Column("signature_kind", sa.String(20), nullable=False, server_default="typed"),
        )
    if "signature_image" not in cols:
        # Text holds a base64 data URL (~1.4 MB max after our 1 MB decoded cap).
        op.add_column(
            "signature_recipients",
            sa.Column("signature_image", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "signature_recipients" not in sa.inspect(bind).get_table_names():
        return
    cols = {c["name"] for c in sa.inspect(bind).get_columns("signature_recipients")}
    if "signature_image" in cols:
        op.drop_column("signature_recipients", "signature_image")
    if "signature_kind" in cols:
        op.drop_column("signature_recipients", "signature_kind")
