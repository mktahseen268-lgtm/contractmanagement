from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


_DEV_SECRET_KEY = "dev-only-change-me-please-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Contract Management API"
    env: Literal["dev", "test", "uat", "staging", "production"] = "dev"

    # --- Database (PostgreSQL is the target stack). SQLite is accepted for a zero-setup quick look. MSSQL is portable. ---
    database_url: str = "postgresql+psycopg2://cm:cm@localhost:5432/cm"

    # --- Auth / JWT ---
    secret_key: str = _DEV_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30          # short-lived; refreshed via the rotating refresh cookie
    refresh_token_expire_days: int = 14            # opaque server-side token (rotated on use)
    mfa_token_expire_minutes: int = 5              # the short token between the password step and the 2FA step
    otp_expire_minutes: int = 10                   # email OTP validity
    otp_max_attempts: int = 5

    # --- Refresh cookie ---
    refresh_cookie_name: str = "cm_refresh"
    cookie_secure: bool = False                    # MUST be true in prod (https); false for local http
    cookie_samesite: str = "lax"                   # lax | strict | none

    # --- Login lockout (RFI §A.7) ---
    login_max_failures: int = 5                    # consecutive failures before lockout
    login_failure_window_minutes: int = 10         # rolling window the failures are counted in
    login_lockout_minutes: int = 15                # how long the user stays locked out

    # --- Encryption-at-rest for sensitive columns (MFA secret + signing-link secret +
    # webhook HMAC secret). Same key chain so one rotation rotates everything. ---
    # Newline-separated Fernet keys; the first is the current encryption key, the rest are kept
    # for read-side rotation. Empty in dev — the EncryptedString type then passes values through.
    mfa_encryption_keys: str = ""

    # --- Audit-log tamper-evidence chain (RFI §A.16 / docs/19) ---
    # HMAC key for the per-tenant hash chain on `audit_log`. Defaults to deriving from
    # `secret_key` when empty (still useful — every row is HMAC'd; an attacker needs *both*
    # the DB and this key to forge a consistent chain). In production set explicitly so JWT
    # signing-key rotation doesn't invalidate historical verification.
    audit_chain_key: str = ""

    # --- Password policy (RFI §A.7) ---
    password_min_length: int = 12                  # production minimum; dev override below
    password_min_length_dev: int = 8               # used when env=dev for ergonomics
    password_require_classes: int = 3              # require >= N of {lower, upper, digit, symbol}
    password_max_length: int = 128                 # bcrypt truncates at 72 bytes anyway; cap at 128

    # --- Signing-link tokens ---
    signing_token_ttl_days: int = 14               # expiry for /sign/{token} URLs

    # --- Rate limit (RFI §A.7) ---
    rate_limit_enabled: bool = True
    rate_limit_store: Literal["memory", "redis"] = "memory"  # redis recommended in prod
    rate_limit_redis_url: str = ""                 # falls back to `redis_url` when empty

    # --- Security headers (CSP can be loosened via env if frontend hosts elsewhere) ---
    security_headers_enabled: bool = True
    csp_extra_connect: str = ""                    # extra `connect-src` origins (comma-separated)
    csp_report_only: bool = False

    # --- Logging ---
    log_format: Literal["json", "text"] = "json"   # text in dev for human readability, json in prod
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Observability (RFI T-1 / docs/26) ---
    # `/metrics` (Prometheus) is always on. OpenTelemetry tracing is opt-in: set otel_enabled
    # AND point otel_exporter_otlp_endpoint at a collector (OTLP/HTTP, e.g. http://otel:4318).
    # Requires the optional extras in `requirements-otel.txt`; degrades to a no-op otherwise.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""          # e.g. http://otel-collector:4318
    otel_service_name: str = "cm-api"

    # --- Retention policy (RFI §C.8-C.11) ---
    retention_audit_hot_days: int = 365            # 1 year in DB
    retention_audit_archive_days: int = 3650       # 10 years total
    retention_webhook_delivery_days: int = 90
    retention_background_job_days: int = 90
    retention_email_outbox_days: int = 30

    # --- Email (for OTP / notifications). console = log it (dev); smtp = real send. ---
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "no-reply@contract-management.local"
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # --- CORS (frontend origins, comma-separated) ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # public URL of the frontend (used in emails — e.g. signing links)
    frontend_url: str = "http://localhost:3000"

    # --- Startup behaviour ---
    run_migrations_on_startup: bool = True
    auto_seed: bool = True

    # --- Background jobs (Celery + Redis) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""                     # empty -> falls back to redis_url
    celery_result_backend: str = ""
    celery_task_always_eager: bool = True

    # --- Object storage (S3-compatible). Empty s3_bucket -> local-filesystem fallback. ---
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    # Per-object server-side encryption — empty disables (e.g. for MinIO without KMS in dev).
    # "AES256" = SSE-S3 (default AWS-managed key). "aws:kms" = SSE-KMS (requires `s3_sse_kms_key_id`).
    s3_sse: Literal["", "AES256", "aws:kms"] = ""
    s3_sse_kms_key_id: str = ""
    local_storage_dir: str = "./storage"
    max_upload_mb: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def csp_extra_connect_list(self) -> list[str]:
        return [o.strip() for o in self.csp_extra_connect.split(",") if o.strip()]

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def db_dialect(self) -> str:
        """`postgresql`, `mssql`, `sqlite`, … — first segment of the URL up to `+` or `://`."""
        url = self.database_url.lower()
        # postgresql+psycopg2://…  -> postgresql
        head = url.split("://", 1)[0].split("+", 1)[0]
        return head

    @property
    def is_postgres(self) -> bool:
        return self.db_dialect == "postgresql"

    @property
    def is_mssql(self) -> bool:
        return self.db_dialect == "mssql"

    @property
    def is_sqlite(self) -> bool:
        return self.db_dialect == "sqlite"

    @property
    def use_s3(self) -> bool:
        return bool(self.s3_bucket)

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def is_production(self) -> bool:
        return self.env in ("production", "staging", "uat")

    @property
    def effective_password_min_length(self) -> int:
        return self.password_min_length_dev if self.is_dev else self.password_min_length

    @property
    def effective_audit_chain_key(self) -> str:
        """Use the explicit `audit_chain_key` when set; otherwise derive a stable key from
        `secret_key` so chaining still works without operator config (with the caveat that a
        rotation of `secret_key` invalidates historical verification)."""
        if self.audit_chain_key:
            return self.audit_chain_key
        return f"audit-chain::{self.secret_key}"

    def validate_for_production(self) -> list[str]:
        """Return a list of fatal misconfigurations when running outside dev. The app raises on
        these at startup so the operator can't accidentally launch with dev defaults."""
        errors: list[str] = []
        if not self.is_dev:
            if self.secret_key == _DEV_SECRET_KEY:
                errors.append("SECRET_KEY is still the dev default — set a 32+ byte secret from a CSPRNG.")
            if len(self.secret_key) < 32:
                errors.append("SECRET_KEY must be at least 32 bytes.")
            if not self.cookie_secure:
                errors.append("COOKIE_SECURE must be true outside of dev (https).")
            if not self.mfa_encryption_keys:
                errors.append("MFA_ENCRYPTION_KEYS must be set (one or more Fernet keys, newline-separated).")
            if self.cors_origins.startswith("http://localhost") and "localhost" in self.cors_origins:
                errors.append("CORS_ORIGINS still contains localhost — narrow to the real frontend domain(s).")
            if self.is_sqlite:
                errors.append("SQLite is not supported outside dev — switch to PostgreSQL (or MSSQL).")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
