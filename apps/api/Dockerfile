FROM python:3.12-slim AS base

# Minimal OS hardening: no cache, no extras, non-root user, deterministic build.
ARG APP_UID=10001
ARG APP_GID=10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Security: install minimal runtime + create the non-root user
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid ${APP_GID} app \
    && useradd  --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /sbin/nologin app

WORKDIR /app

# Install Python deps first (cache-friendly)
COPY --chown=app:app requirements.txt .
RUN pip install -r requirements.txt

# Then the application
COPY --chown=app:app alembic.ini .
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app app ./app

# Make /app read-only at runtime (containers also enable ReadOnlyRootFilesystem in k8s)
USER app:app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Default = the API; the worker / beat services override the CMD.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
