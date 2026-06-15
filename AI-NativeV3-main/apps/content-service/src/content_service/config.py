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

    # CORS — default vacio: solo el api-gateway llama server-to-server
    # (sin Origin header). Para exposicion publica, setear CORS_ORIGINS
    # explicito via env. Wildcard "*" prohibido por audit de seguridad.
    cors_origins: list[str] = Field(default_factory=list)
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    keycloak_url: str = "http://127.0.0.1:8180"
    keycloak_realm: str = "demo_uni"

    # Defensa en profundidad cross-service (firma HMAC del gateway).
    # require_gateway_signature=False (default) => comportamiento actual: se
    # confía en los headers X-* del gateway sin más. Cuando se prende, se exige
    # que el gateway haya firmado los headers de identidad (X-Gateway-Signature
    # + X-Gateway-Ts) con gateway_shared_secret; firma ausente/inválida => 401.
    # ORDEN DE ACTIVACIÓN: primero deployar el gateway firmando (con el secreto
    # compartido seteado) y RECIÉN DESPUÉS prender este flag, o se cae todo.
    require_gateway_signature: bool = False
    gateway_shared_secret: str = ""

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
