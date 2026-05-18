"""Configuración del servicio analytics-service."""

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
    service_name: str = "analytics-service"
    service_port: int = 8005
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

    # DBs externas que analytics-service LEE (no es dueño).
    # Vacío → factory cae a _StubDataSource (dev sin DBs reales).
    # Populado → usa adaptadores reales con RLS por tenant.
    ctr_store_url: str = Field(default="")
    classifier_db_url: str = Field(default="")
    # ADR-018: requerido para resolver Episode.problema_id → TareaPractica.template_id
    # en /student/{id}/cii-evolution-longitudinal. Modo dev (vacío) salta la query.
    academic_db_url: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
