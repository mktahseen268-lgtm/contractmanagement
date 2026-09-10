"""Single-tenant deployment profile (`DEPLOYMENT_MODE=single_tenant`).

The MMBL install is one bank, on-prem. Multi-tenancy buys nothing there and its Postgres-only
RLS is exactly what makes MSSQL/Oracle painful. So this profile provisions exactly one tenant
at install, resolves its id once at startup, and disables self-service registration.

Deliberately **not** a fork in the code path: `get_current_user` still sets the tenant
ContextVar, repositories still filter by `tenant_id`, and row security still works the same
way (optionally disabled via `ENFORCE_DB_ISOLATION`, since with one tenant the predicate is a
tautology). One less code path is one less place for a tenant leak to hide.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from . import models
from .config import settings
from .database import SessionLocal

log = logging.getLogger("uvicorn.error")

_resolved_tenant_id: str | None = None


def single_tenant_id() -> str | None:
    """The sole tenant's id, or None outside the single-tenant profile."""
    return _resolved_tenant_id if settings.is_single_tenant else None


def provision() -> str:
    """Resolve — creating if necessary — the one tenant this deployment serves.

    Order of precedence:
      1. `SINGLE_TENANT_ID` names an existing row → use it.
      2. Exactly one tenant row exists → adopt it (the usual upgrade-from-demo path).
      3. No tenant rows → create one from `SINGLE_TENANT_NAME` / `SINGLE_TENANT_SLUG`.
      4. More than one tenant row and no `SINGLE_TENANT_ID` → refuse to guess.
    """
    global _resolved_tenant_id

    with SessionLocal() as db:
        if settings.single_tenant_id:
            found = db.get(models.Tenant, settings.single_tenant_id)
            if found is None:
                raise RuntimeError(
                    f"SINGLE_TENANT_ID={settings.single_tenant_id} does not exist in `tenants`. "
                    "Leave it empty to provision a new one, or correct it."
                )
            _resolved_tenant_id = found.id
            log.info("single-tenant mode: using tenant %s (%s)", found.id, found.name)
            return found.id

        count = db.scalar(select(func.count()).select_from(models.Tenant)) or 0
        if count > 1:
            raise RuntimeError(
                f"DEPLOYMENT_MODE=single_tenant but the database holds {count} tenants. "
                "Set SINGLE_TENANT_ID to the one this deployment serves."
            )
        if count == 1:
            found = db.scalars(select(models.Tenant)).one()
            _resolved_tenant_id = found.id
            log.info("single-tenant mode: adopted existing tenant %s (%s)", found.id, found.name)
            return found.id

        tenant = models.Tenant(name=settings.single_tenant_name, slug=settings.single_tenant_slug)
        db.add(tenant)
        db.commit()
        _resolved_tenant_id = tenant.id
        log.info("single-tenant mode: provisioned tenant %s (%s)", tenant.id, tenant.name)
        return tenant.id
