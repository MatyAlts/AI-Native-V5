"""Configuración del content-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "content-service"
    service_port: int = 8009
    environment: str = Field(default="development")
    log_level: str = "info"
    log_format: str = "json"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    keycloak_url: str = "http://127.0.0.1:8180"
    keycloak_realm: str = "demo_uni"

    # Base dedicada: content_db (ADR-003). La tabla `materiales` + `chunks` viven acá,
    # NO en academic_main (el comentario anterior apuntaba a una decisión stale —
    # las migraciones de content-service efectivamente crean en content_db, verificable
    # con `docker exec platform-postgres psql -U postgres -d content_db -c "\dt"`).
    # El fallback default asume dev local con los users que crea setup-dev-permissions.sh.
    content_db_url: str = Field(
        default="postgresql+asyncpg://content_user:content_pass@127.0.0.1:5432/content_db"
    )
    db_echo: bool = False

    # Storage
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_materials: str = "materials"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
