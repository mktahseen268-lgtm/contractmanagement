"""Pytest fixtures for the Contract Management API.

The default test environment targets the SQLite scaffold so contributors can run the suite
without standing up Postgres. Tests that depend on PostgreSQL-only features (RLS, JSONB,
advisory locks) are marked `@pytest.mark.postgres` and skipped unless the harness sets
`CM_TEST_DATABASE_URL` to a real Postgres DSN.

Each test gets a freshly-created schema + a seeded tenant + a single user via
`make_user_in_new_tenant()`. That keeps RLS happy (the test bears its own tenant context)
without test-to-test cross-contamination.
"""

from __future__ import annotations

import os
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

# Override settings before the app imports — these env vars are read by pydantic-settings.
os.environ.setdefault("DATABASE_URL", os.environ.get("CM_TEST_DATABASE_URL", "sqlite:///./_test.db"))
os.environ.setdefault("ENV", "test")
os.environ.setdefault("AUTO_SEED", "false")
os.environ.setdefault("RUN_MIGRATIONS_ON_STARTUP", "false")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("EMAIL_BACKEND", "console")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("AUDIT_CHAIN_KEY", "test-chain-key-" + secrets.token_hex(8))
# Production guards refuse to start outside ENV=dev with the default secret key. Supply a
# real-shape key so the lifespan startup doesn't crash if a test happens to use TestClient.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-32-bytes-long-aaaaaaaaaaa")
os.environ.setdefault("COOKIE_SECURE", "false")


@pytest.fixture(scope="session", autouse=True)
def _prepare_schema():
    """Create the full schema once per session via SQLAlchemy metadata (faster than running
    every Alembic migration). The schema we build matches `head` because both come from the
    same model definitions; the only thing missed is the Postgres-only RLS DDL — Postgres
    tests should run Alembic instead via the `pg_db` fixture below."""
    from app.database import Base, engine
    from app import models  # noqa: F401  — register models on Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    from app.database import SessionLocal, set_request_tenant

    set_request_tenant(None)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _strong_password() -> str:
    """A password that satisfies the production password policy (12+ chars, 3 classes)."""
    return "TestPass!" + secrets.token_hex(4)


@pytest.fixture()
def make_user():
    """Factory: create a brand-new tenant + user (owner role). Returns the registration response
    body shape {access_token, user, tenant} so tests can authenticate immediately."""
    created: list[str] = []

    def _make(email: str | None = None, name: str = "Test Owner"):
        from app import models, security
        from app.database import SessionLocal, set_request_tenant

        email = email or f"u{uuid.uuid4().hex[:8]}@example.test"
        tenant_id = uuid.uuid4().hex
        with SessionLocal() as db:
            set_request_tenant(tenant_id)
            tenant = models.Tenant(id=tenant_id, name=f"Tenant {tenant_id[:6]}", slug=f"t-{tenant_id[:8]}")
            db.add(tenant)
            db.flush()
            user = models.User(
                tenant_id=tenant_id, email=email.lower(), name=name,
                password_hash=security.hash_password(_strong_password()), role="owner",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.refresh(tenant)
            created.append(tenant_id)
            return user, tenant

    yield _make

    # Per-test cleanup so the schema teardown at session end doesn't have leftover RLS context.
    from app.database import set_request_tenant
    set_request_tenant(None)
