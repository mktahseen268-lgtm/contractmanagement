import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal
from .routers import audit, auth, contracts, dashboard, files, inbox, misc, reports, signatures, workflows

log = logging.getLogger("uvicorn.error")

_API_ROOT = Path(__file__).resolve().parent.parent  # apps/api/ — where alembic.ini lives


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_ROOT / "migrations"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
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


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(contracts.router)
app.include_router(dashboard.router)
app.include_router(audit.router)
app.include_router(files.router)
app.include_router(workflows.router)
app.include_router(signatures.router)
app.include_router(reports.router)
app.include_router(inbox.router)
app.include_router(misc.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"name": settings.app_name, "version": "0.2.0", "docs": "/docs", "db": "postgresql" if settings.is_postgres else "sqlite"}


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
