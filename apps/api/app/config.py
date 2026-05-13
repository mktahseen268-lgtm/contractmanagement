from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Contract Management API"
    env: str = "dev"

    # --- Database (PostgreSQL is the target stack). SQLite is accepted for a zero-setup quick look. ---
    database_url: str = "postgresql+psycopg2://cm:cm@localhost:5432/cm"

    # --- Auth / JWT ---
    secret_key: str = "dev-only-change-me-please-0123456789abcdef"
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

    # --- Email (for OTP / notifications). console = log it (dev); smtp = real send. ---
    email_backend: str = "console"                 # console | smtp
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
    local_storage_dir: str = "./storage"
    max_upload_mb: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    @property
    def use_s3(self) -> bool:
        return bool(self.s3_bucket)

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
