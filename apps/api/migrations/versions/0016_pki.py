"""pki: certificate authorities, certificates, RA requests, trust anchors, key storage

Phase 1 — the in-platform PKI required by RFP §4a ("PKI Depth & Advanced eSignature", 11% of
the technical score and an eligibility gate). See docs/PKI-ARCHITECTURE.md.

Tables:
  pki_keys                private key material for the *software* keystore only, encrypted at
                          rest via `EncryptedString`. Empty when KEYSTORE_PROVIDER=pkcs11.
  certificate_authorities root / issuing / OCSP-responder CA certificates. A CA's identity is
                          its (key_id, subject_dn); multiple rows may share those when the CA
                          is cross-certified under a second parent (the ECAC path).
  trust_anchors           roots trusted when validating third-party certificates. A table, not
                          a file, so the chain can be extended at runtime.
  certificate_requests    the Registration Authority queue. Nothing is issued without one.
  certificates            the issued register.

The load-bearing constraint here is the pair of **partial unique indexes** on `certificates`:
at most one row with status='active' per (tenant_id, subject_user_id) and per
(tenant_id, subject_party_id). That is the database-level enforcement of the RFP's "one
certificate per signatory, uniquely bound private key, no shared or role-based certificates".
The DDL is dialect-specific (Oracle has no filtered indexes) and comes from
`app/db_dialect.partial_unique_index`.

RLS: the new tenant-scoped tables get the same isolation policy as the rest of the schema,
via the Phase 0 seam. `pki_keys` is deliberately *not* tenant-scoped — its ids are opaque
keystore handles and it is never queried by tenant.

Revision ID: 0016_pki
Revises: 0015_retention_tiering
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import db_dialect
from app.config import settings

revision = "0016_pki"
down_revision = "0015_retention_tiering"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["certificate_authorities", "trust_anchors", "certificate_requests", "certificates"]


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)
    existing = _tables(bind)

    if "pki_keys" not in existing:
        op.create_table(
            "pki_keys",
            sa.Column("id", sa.String(200), primary_key=True),
            sa.Column("algorithm", sa.String(30), nullable=False, server_default="ec-p256"),
            sa.Column("provider", sa.String(20), nullable=False, server_default="soft"),
            # Fernet ciphertext of a PKCS#8 PEM. 8192 covers RSA-4096 plus the envelope.
            sa.Column("material", sa.String(8192), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "certificate_authorities" not in existing:
        op.create_table(
            "certificate_authorities",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False, server_default="issuing"),
            sa.Column("subject_dn", sa.String(500), nullable=False),
            sa.Column("issuer_dn", sa.String(500), nullable=False, server_default=""),
            sa.Column("parent_ca_id", sa.String(32), nullable=True),
            sa.Column("key_id", sa.String(200), nullable=False),
            sa.Column("key_algorithm", sa.String(30), nullable=False, server_default="ec-p384"),
            sa.Column("serial_number", sa.String(64), nullable=False),
            sa.Column("pem", sa.Text(), nullable=False, server_default=""),
            sa.Column("not_before", sa.DateTime(), nullable=False),
            sa.Column("not_after", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("is_offline", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("crl_number", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("base_crl_number", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_ca_tenant", "certificate_authorities", ["tenant_id"])
        op.create_index("ix_ca_tenant_kind_status", "certificate_authorities",
                        ["tenant_id", "kind", "status"])
        op.create_index("ix_ca_subject_dn", "certificate_authorities", ["subject_dn"])
        op.create_index("ix_ca_key_id", "certificate_authorities", ["key_id"])
        op.create_index("ix_ca_serial", "certificate_authorities", ["serial_number"])
        op.create_index("ix_ca_parent", "certificate_authorities", ["parent_ca_id"])

    if "trust_anchors" not in existing:
        op.create_table(
            "trust_anchors",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("subject_dn", sa.String(500), nullable=False, server_default=""),
            sa.Column("fingerprint_sha256", sa.String(64), nullable=False),
            sa.Column("pem", sa.Text(), nullable=False),
            sa.Column("source", sa.String(20), nullable=False, server_default="external"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("added_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_trust_anchor_tenant", "trust_anchors", ["tenant_id"])
        # One row per root per tenant — re-adding the same PEM must update, not duplicate.
        op.create_index("ix_trust_anchor_tenant_fp", "trust_anchors",
                        ["tenant_id", "fingerprint_sha256"], unique=True)

    if "certificate_requests" not in existing:
        op.create_table(
            "certificate_requests",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("subject_dn", sa.String(500), nullable=False),
            sa.Column("subject_user_id", sa.String(32), nullable=True),
            sa.Column("subject_party_id", sa.String(32), nullable=True),
            sa.Column("subject_email", sa.String(320), nullable=False, server_default=""),
            sa.Column("profile", sa.String(30), nullable=False, server_default="internal"),
            sa.Column("csr_pem", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("evidence", sa.JSON(), nullable=True),
            sa.Column("requested_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("reviewed_by", sa.String(32), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("second_reviewed_by", sa.String(32), nullable=True),
            sa.Column("second_reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("review_note", sa.String(1000), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_certreq_tenant", "certificate_requests", ["tenant_id"])
        op.create_index("ix_certreq_tenant_status", "certificate_requests", ["tenant_id", "status"])
        op.create_index("ix_certreq_subject_user", "certificate_requests", ["subject_user_id"])
        op.create_index("ix_certreq_subject_party", "certificate_requests", ["subject_party_id"])

    if "certificates" not in existing:
        op.create_table(
            "certificates",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(32), nullable=False),
            sa.Column("ca_id", sa.String(32), nullable=False),
            sa.Column("request_id", sa.String(32), nullable=True),
            sa.Column("subject_dn", sa.String(500), nullable=False),
            sa.Column("subject_user_id", sa.String(32), nullable=True),
            sa.Column("subject_party_id", sa.String(32), nullable=True),
            sa.Column("subject_email", sa.String(320), nullable=False, server_default=""),
            sa.Column("profile", sa.String(30), nullable=False, server_default="internal"),
            sa.Column("serial_number", sa.String(64), nullable=False),
            sa.Column("key_id", sa.String(200), nullable=False, server_default=""),
            sa.Column("key_algorithm", sa.String(30), nullable=False, server_default="ec-p256"),
            sa.Column("pem", sa.Text(), nullable=False, server_default=""),
            sa.Column("not_before", sa.DateTime(), nullable=False),
            sa.Column("not_after", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("revocation_reason", sa.String(40), nullable=False, server_default=""),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("renewed_from_id", sa.String(32), nullable=True),
            sa.Column("issued_by", sa.String(32), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_cert_tenant", "certificates", ["tenant_id"])
        op.create_index("ix_cert_ca", "certificates", ["ca_id"])
        op.create_index("ix_cert_request", "certificates", ["request_id"])
        op.create_index("ix_cert_subject_dn", "certificates", ["subject_dn"])
        op.create_index("ix_cert_subject_user", "certificates", ["subject_user_id"])
        op.create_index("ix_cert_subject_party", "certificates", ["subject_party_id"])
        op.create_index("ix_cert_renewed_from", "certificates", ["renewed_from_id"])
        op.create_index("ix_cert_not_after", "certificates", ["not_after"])
        op.create_index("ix_cert_status", "certificates", ["status"])
        # The OCSP responder's hot path: (tenant, ca, serial).
        op.create_index("ix_cert_tenant_ca_serial", "certificates",
                        ["tenant_id", "ca_id", "serial_number"])

        # ---- the no-shared-certificates rule, enforced by the database ----
        for name, column in (
            ("uq_cert_active_per_user", "subject_user_id"),
            ("uq_cert_active_per_party", "subject_party_id"),
        ):
            for stmt in db_dialect.partial_unique_index(
                dialect, name, "certificates", ["tenant_id", column],
                where=f"status = 'active' AND {db_dialect.quote(dialect, column)} IS NOT NULL",
            ):
                op.execute(stmt)

    # ---- row security on the new tenant-scoped tables ----
    if settings.enforce_db_isolation:
        for stmt in db_dialect.enable_row_security(dialect, _TENANT_TABLES):
            op.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = db_dialect.dialect_of(bind)

    if settings.enforce_db_isolation:
        for stmt in db_dialect.disable_row_security(dialect, _TENANT_TABLES):
            try:
                op.execute(stmt)
            except Exception:  # noqa: BLE001
                pass

    existing = _tables(bind)
    for table in ("certificates", "certificate_requests", "trust_anchors",
                  "certificate_authorities", "pki_keys"):
        if table in existing:
            op.drop_table(table)
