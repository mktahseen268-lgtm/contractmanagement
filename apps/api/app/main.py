import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal
from .middleware import LoggingMiddleware, MetricsMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from .routers import api_keys, audit, auth, contracts, dashboard, files, inbox, misc, obligations, reports, signatures, templates, webhooks, workflows

log = logging.getLogger("uvicorn.error")

_API_ROOT = Path(__file__).resolve().parent.parent  # apps/api/ — where alembic.ini lives


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_ROOT / "migrations"))
    command.upgrade(cfg, "head")


def _enforce_production_safety() -> None:
    """Refuse to start outside dev if SECRET_KEY is the default, MFA keys missing, cookies
    insecure, etc. See `config.validate_for_production` for the full list (RFI §A.18 / §A.5)."""
    errors = settings.validate_for_production()
    if errors:
        for err in errors:
            log.critical("CONFIG ERROR: %s", err)
        raise RuntimeError(
            f"Refusing to start with insecure configuration (env={settings.env}). "
            "Fix the errors above and re-deploy. See docs/20-security-compliance.md §12."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _enforce_production_safety()
    # Observability: /metrics is always on (mounted below); tracing is opt-in + graceful.
    try:
        from .tracing import init_tracing

        init_tracing(app)
    except Exception:  # noqa: BLE001
        log.exception("tracing init failed (continuing)")
    if settings.run_migrations_on_startup:
        try:
            _run_migrations()
            log.info("Database migrations applied (alembic upgrade head).")
        except Exception:  # noqa: BLE001
            log.exception("Failed to run migrations on startup")
            raise
    try:
        from .storage import get_storage

        get_storage().ensure_ready()
        log.info("Object storage ready (%s).", get_storage().name)
    except Exception:  # noqa: BLE001
        log.exception("Could not prepare object storage")
    if settings.auto_seed:
        from .seed import seed_if_empty

        with SessionLocal() as db:
            if seed_if_empty(db):
                log.info("Seeded demo workspace. Login: demo@acme.io / Password: demo1234")
    yield


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)

# Middleware order matters: Starlette runs them in reverse-add order, so the LAST added is the
# OUTERMOST. We want: Metrics (outermost — times the whole request incl. rate-limit 429s) →
# Logging → RateLimit → CORS → SecurityHeaders (innermost, closest to response so it always tags).
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(MetricsMiddleware)

app.include_router(auth.router)
app.include_router(contracts.router)
app.include_router(dashboard.router)
app.include_router(audit.router)
app.include_router(files.router)
app.include_router(workflows.router)
app.include_router(signatures.router)
app.include_router(reports.router)
app.include_router(inbox.router)
app.include_router(obligations.router)
app.include_router(templates.router)
app.include_router(webhooks.router)
app.include_router(api_keys.router)
app.include_router(misc.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"name": settings.app_name, "version": "0.3.0", "docs": "/docs", "db": settings.db_dialect, "env": settings.env}


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe — always 200 as long as the process is up."""
    return {"status": "ok"}


@app.get("/metrics", tags=["meta"], include_in_schema=False)
def metrics():
    """Prometheus exposition endpoint (RFI T-1). Scraped per-pod; see K8s deployment
    `prometheus.io/scrape` annotation. Not rate-limited (skip list) and not in the OpenAPI."""
    from fastapi import Response

    from .metrics import render

    payload, content_type = render()
    return Response(content=payload, media_type=content_type)


@app.get("/healthz/ready", tags=["meta"])
def readiness() -> dict:
    """Readiness probe — validates DB round-trip + storage. K8s readinessProbe targets this."""
    from sqlalchemy import text

    checks: dict[str, str] = {}
    overall = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"failed: {e.__class__.__name__}"
        overall = "fail"
    try:
        from .storage import get_storage

        get_storage().ensure_ready()
        checks["storage"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["storage"] = f"failed: {e.__class__.__name__}"
        overall = "fail"
    return {"status": overall, "checks": checks}
