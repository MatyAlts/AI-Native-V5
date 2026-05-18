"""Configuración del servicio evaluation-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings leídas de env + .env con validación."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service
    service_name: str = "evaluation-service"
    service_port: int = 8004
    environment: str = Field(default="development")
    log_level: str = Field(default="info")
    log_format: str = Field(default="json")

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Observability
    otel_endpoint: str = Field(default="http://127.0.0.1:4317")
    sentry_dsn: str = Field(default="")

    # Keycloak (la mayoría de servicios valida JWT)
    keycloak_url: str = Field(default="http://127.0.0.1:8180")
    keycloak_realm: str = Field(default="demo_uni")

    # Database
    academic_db_url: str = Field(
        default="postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main"
    )

    # Servicios internos
    ctr_service_url: str = Field(default="http://127.0.0.1:8007")
    academic_service_url: str = Field(default="http://127.0.0.1:8002")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
