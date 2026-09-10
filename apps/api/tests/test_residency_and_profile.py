"""Data residency enforcement + the single-tenant deployment profile (Phase 0).

Residency is the control behind the RFP's "Hosting & data residency statement": the deployment
must keep all data inside the country. We assert the actual property enforced — that no
configured endpoint egresses to a public address unless an operator allowlisted it — rather
than mocking a geo-lookup we deliberately do not perform.

Requirements: SEC-22.
"""

from __future__ import annotations

import pytest

from app import residency
from app.config import settings


@pytest.fixture()
def restore_settings():
    """Settings is a cached singleton; snapshot and restore the fields each test mutates."""
    fields = [
        "s3_endpoint_url", "smtp_host", "otel_exporter_otlp_endpoint", "signing_tsa_url",
        "oidc_issuer", "database_url", "redis_url", "celery_broker_url", "ocr_provider",
        "data_residency_allow_hosts", "data_residency_enforced", "deployment_mode",
        "single_tenant_id", "auto_seed", "enforce_db_isolation", "env",
    ]
    saved = {f: getattr(settings, f) for f in fields}
    yield settings
    for f, v in saved.items():
        setattr(settings, f, v)


def _quiet(s):
    """Blank out every endpoint so a test only sees the one it sets."""
    for f in ("s3_endpoint_url", "otel_exporter_otlp_endpoint", "signing_tsa_url",
              "oidc_issuer", "celery_broker_url"):
        setattr(s, f, "")
    s.smtp_host = "localhost"
    s.database_url = "postgresql+psycopg2://cm:cm@127.0.0.1:5432/cm"
    s.redis_url = "redis://127.0.0.1:6379/0"
    s.ocr_provider = "stub"
    s.data_residency_allow_hosts = ""
    s.data_residency_enforced = True


# ------------------------------------------------------------------ host parsing


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://minio.internal:9000", "minio.internal"),
        ("postgresql+psycopg2://cm:pw@db.internal:5432/cm", "db.internal"),
        ("redis://cache.internal:6379/0", "cache.internal"),
        ("smtp.internal:587", "smtp.internal"),
        ("mail.internal", "mail.internal"),
        ("", ""),
    ],
)
def test_host_extraction(raw, expected):
    assert residency._host_of(raw) == expected


# ------------------------------------------------------------------ enforcement


def test_private_endpoints_pass(restore_settings):
    s = restore_settings
    _quiet(s)
    s.s3_endpoint_url = "http://10.0.0.5:9000"

    findings = residency.enforce()
    assert all(f.ok for f in findings)


def test_public_endpoint_blocks_boot(restore_settings):
    """A managed cloud database is the most likely way contract data leaves the country."""
    s = restore_settings
    _quiet(s)
    s.database_url = "postgresql+psycopg2://cm:pw@1.1.1.1:5432/cm"

    with pytest.raises(RuntimeError, match="[Dd]ata residency"):
        residency.enforce()


def test_allowlist_permits_a_reviewed_exception(restore_settings):
    """A TSA or sanctions-list feed may legitimately be external — but only when the operator
    has named it, where config review and the residency statement can see it."""
    s = restore_settings
    _quiet(s)
    s.database_url = "postgresql+psycopg2://cm:pw@1.1.1.1:5432/cm"
    s.data_residency_allow_hosts = "1.1.1.1"

    findings = residency.enforce()
    assert all(f.ok for f in findings)
    assert any("allowlisted" in f.reason for f in findings)


def test_allowlist_accepts_cidr(restore_settings):
    s = restore_settings
    _quiet(s)
    s.database_url = "postgresql+psycopg2://cm:pw@1.1.1.1:5432/cm"
    s.data_residency_allow_hosts = "1.1.0.0/16"

    assert all(f.ok for f in residency.enforce())


def test_enforcement_can_be_reported_without_blocking(restore_settings):
    """`DATA_RESIDENCY_ENFORCED=false` still records findings — useful for a staged rollout,
    but it must never silently pass a violation off as compliant."""
    s = restore_settings
    _quiet(s)
    s.database_url = "postgresql+psycopg2://cm:pw@1.1.1.1:5432/cm"
    s.data_residency_enforced = False

    findings = residency.enforce()  # does not raise
    assert any(not f.ok for f in findings)


def test_anthropic_ocr_counts_as_egress(restore_settings):
    """The stub OCR provider is local; the Anthropic one is a foreign API. Switching provider
    must move the residency needle, or the check is theatre."""
    s = restore_settings
    _quiet(s)
    assert not any(e.label == "ocr provider" for e in residency.collect_endpoints())
    s.ocr_provider = "anthropic"
    assert any(e.label == "ocr provider" for e in residency.collect_endpoints())


def test_unresolvable_host_is_not_a_violation(restore_settings):
    """A host that is simply down, or DNS that is not up yet in a compose start order, must
    not wedge the deployment."""
    s = restore_settings
    _quiet(s)
    s.smtp_host = "no-such-host.invalid"

    findings = residency.enforce()
    smtp = [f for f in findings if f.endpoint.label == "smtp"][0]
    assert smtp.ok and "unresolvable" in smtp.reason


# ------------------------------------------------------------------ single-tenant profile


def test_registration_disabled_in_single_tenant(restore_settings):
    s = restore_settings
    s.deployment_mode = "single_tenant"
    assert s.registration_enabled is False
    s.deployment_mode = "saas"
    assert s.registration_enabled is True


def test_register_endpoint_is_gated(client, restore_settings):
    s = restore_settings
    s.deployment_mode = "single_tenant"

    r = client.post("/auth/register", json={
        "email": "intruder@example.com", "password": "Str0ng!Passw0rd", "name": "X",
        "workspace_name": "New Workspace",
    })
    assert r.status_code == 403


def test_sso_config_advertises_the_profile(client, restore_settings):
    s = restore_settings
    s.deployment_mode = "single_tenant"

    body = client.get("/auth/sso/config").json()
    assert body["registration_enabled"] is False
    assert body["deployment_mode"] == "single_tenant"


def test_saas_profile_cannot_disable_db_isolation(restore_settings):
    """Turning off row security is only defensible when there is one tenant."""
    s = restore_settings
    s.deployment_mode = "saas"
    s.enforce_db_isolation = False

    errors = s.validate_for_production()
    assert any("ENFORCE_DB_ISOLATION" in e for e in errors)


def test_single_tenant_rejects_saas_shaped_config(restore_settings):
    s = restore_settings
    s.deployment_mode = "single_tenant"
    s.env = "production"
    s.auto_seed = True

    errors = s.validate_for_production()
    assert any("AUTO_SEED" in e for e in errors)
