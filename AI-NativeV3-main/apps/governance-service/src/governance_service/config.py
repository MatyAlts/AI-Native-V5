"""Config del governance-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "governance-service"
    service_port: int = 8010
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    # Repo de prompts. En F5 se pulla automáticamente del origen Git con
    # verificación de GPG. Por ahora asumimos que está clonado en disco.
    prompts_repo_path: str = "/var/lib/platform/prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
