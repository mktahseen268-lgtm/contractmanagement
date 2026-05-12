from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Contract Management API"
    env: str = "dev"

    # --- Database (PostgreSQL is the target stack). ---
    # SQLite is still accepted for a zero-setup quick look (RLS migration is skipped on SQLite).
    database_url: str = "postgresql+psycopg2://cm:cm@localhost:5432/cm"

    # --- Auth ---
    secret_key: str = "dev-only-change-me-please-0123456789abcdef"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14

    # --- CORS (frontend origins, comma-separated) ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Startup behaviour ---
    run_migrations_on_startup: bool = True
    auto_seed: bool = True

    # --- Background jobs (Celery + Redis) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""  # empty -> falls back to redis_url
    celery_result_backend: str = ""  # empty -> falls back to redis_url
    celery_task_always_eager: bool = True

    # --- Object storage (S3-compatible: AWS S3 / MinIO / Wasabi / Ceph).
    # If s3_bucket is set -> S3 backend; otherwise -> local-filesystem fallback at local_storage_dir.
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # e.g. http://minio:9000 (MinIO) — leave empty for AWS
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
