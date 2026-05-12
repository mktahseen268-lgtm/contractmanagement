"""Database engine, session, Base — and the multi-tenant Row-Level-Security plumbing.

How tenant isolation works (PostgreSQL):
 - every tenant-scoped row carries `tenant_id`;
 - migration `0002_rls` enables (FORCE) RLS on those tables with a `tenant_isolation` policy
   keyed off the session GUC `app.cm_tenant`;
 - this module keeps the active tenant in a `ContextVar` and an engine `begin` event listener
   re-applies it (`SET LOCAL`) on every transaction — so even post-commit queries stay scoped;
 - `get_current_user` sets the ContextVar from the JWT *before* its first query;
 - the policies are "permissive when the GUC is unset" so unauthenticated auth endpoints
   (login/refresh) still work; the repository layer *also* filters by `tenant_id` (defence in depth).
On SQLite the listener is a no-op and the RLS migration is skipped.
"""

import contextvars
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


# ---------- tenant context (for RLS) ----------

_current_tenant: contextvars.ContextVar[str | None] = contextvars.ContextVar("cm_tenant", default=None)


def set_request_tenant(tenant_id: str | None) -> None:
    """Set the active tenant for the current execution context (request / Celery task)."""
    _current_tenant.set(tenant_id)


def get_request_tenant() -> str | None:
    return _current_tenant.get()


if settings.is_postgres:

    @event.listens_for(engine, "begin")
    def _apply_tenant_guc(conn) -> None:  # type: ignore[no-untyped-def]
        tid = _current_tenant.get()
        if tid:
            # set_config(name, value, is_local=true) — transaction-scoped, never leaks across pooled conns
            conn.exec_driver_sql("SELECT set_config('app.cm_tenant', %s, true)", (tid,))


# ---------- session dependency ----------


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Used by the initial Alembic migration to materialise the current model state."""
    from . import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
