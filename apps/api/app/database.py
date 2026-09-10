"""Database engine, session, Base — and the Row-Level-Security plumbing.

How tenant isolation works (PostgreSQL, MSSQL and Oracle — see `db_dialect.py`):
 - every tenant-scoped row carries `tenant_id`;
 - migration `0002_rls` enables row security on those tables: a `tenant_isolation` policy on
   Postgres, a Security Policy with an inline table-valued predicate on MSSQL, a VPD policy
   via `DBMS_RLS.ADD_POLICY` on Oracle — all keyed off a per-session tenant value;
 - this module keeps the active tenant in a `ContextVar` and an engine `begin` event listener
   re-applies it on every transaction — so even post-commit queries stay scoped;
 - `get_current_user` sets the ContextVar from the JWT *before* its first query;
 - the policies are "permissive when the tenant is unset" so unauthenticated auth endpoints
   (login/refresh) still work; the repository layer *also* filters by `tenant_id` (defence in depth).
On SQLite the listener is a no-op and the RLS migration is skipped — dev only.

In `DEPLOYMENT_MODE=single_tenant` the policies are optional (`ENFORCE_DB_ISOLATION`): with one
tenant the predicate is a tautology. The ContextVar and the repository filters stay in place
regardless, so the code path never forks.
"""

import contextvars
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import db_dialect
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


_DIALECT = settings.db_dialect

if _DIALECT in (db_dialect.PG, db_dialect.MSSQL, db_dialect.ORACLE):

    @event.listens_for(engine, "begin")
    def _apply_tenant_context(conn) -> None:  # type: ignore[no-untyped-def]
        # Written on EVERY transaction, including when the tenant is unset: MSSQL/Oracle hold
        # this on the connection, so a pooled connection would otherwise inherit the previous
        # request's tenant. See db_dialect.set_tenant_context.
        db_dialect.set_tenant_context(conn, _DIALECT, _current_tenant.get())


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
