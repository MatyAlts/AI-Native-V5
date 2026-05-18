"""Configuración del ctr-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "ctr-service"
    service_port: int = 8007
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    keycloak_url: str = "http://127.0.0.1:8180"
    keycloak_realm: str = "demo_uni"

    ctr_db_url: str = Field(
        default="postgresql+asyncpg://ctr_user:ctr_pass@127.0.0.1:5432/ctr_store"
    )
    db_echo: bool = False

    redis_url: str = "redis://127.0.0.1:6379/0"

    num_partitions: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
