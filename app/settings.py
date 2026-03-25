from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    app_name: str = "nesting-saas-mvp"
    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/nesting_mvp"
    redis_url: str = "redis://redis:6379/0"
    cors_allowed_origins: str = "*"
    job_queue_name: str = "nesting:jobs"
    storage_dir: Path = BASE_DIR / "storage"
    geometry_tolerance: float = 0.5
    startup_timeout_seconds: int = 30
    queue_block_timeout_seconds: int = 5
    worker_idle_sleep_seconds: float = 0.5

    model_config = SettingsConfigDict(
        env_prefix="NESTING_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @computed_field
    @property
    def imports_dir(self) -> Path:
        return self.storage_dir / "imports"

    @computed_field
    @property
    def results_dir(self) -> Path:
        return self.storage_dir / "results"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @computed_field
    @property
    def normalized_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @computed_field
    @property
    def cors_allowed_origin_list(self) -> list[str]:
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
