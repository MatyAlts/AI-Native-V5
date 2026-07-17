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

    # CORS — default vacio: solo el api-gateway llama server-to-server
    # (sin Origin header). Para exposicion publica, setear CORS_ORIGINS
    # explicito via env. Wildcard "*" prohibido por audit de seguridad.
    cors_origins: list[str] = Field(default_factory=list)
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    # Repo de prompts. En F5 se pulla automáticamente del origen Git con
    # verificación de GPG. Por ahora asumimos que está clonado en disco.
    prompts_repo_path: str = "/var/lib/platform/prompts"

    # ── Auth cross-service (A0.4) ────────────────────────────────────────────
    # governance-service es interno (NO está en el ROUTE_MAP del api-gateway),
    # pero vive en la misma red que el resto de los servicios. Sin auth,
    # cualquiera con acceso de red lee todos los prompts y configs.
    #
    # require_gateway_signature=False (default) => comportamiento actual: no se
    # exige nada. Necesario porque el tutor-service llama a governance
    # DIRECTO (service-to-service, sin pasar por el gateway y sin firmar) al
    # abrir cada episodio — encender enforcement por default rompería el
    # arranque de episodios.
    #
    # Con el flag ON, cada request a los endpoints de prompts/configs debe
    # probar procedencia por UNO de dos caminos:
    #   (a) firma HMAC del gateway (X-Gateway-Signature + X-Gateway-Ts sobre los
    #       headers X-User-*), verificada con gateway_shared_secret; o
    #   (b) token de service-account (X-Internal-Service-Token) que coincide con
    #       internal_service_token — el camino del tutor-service, que NO pasa por
    #       el gateway. Ausencia de ambos => 401.
    #
    # ORDEN DE ACTIVACIÓN (prod): primero setear el secreto/token compartido y
    # configurar a los callers legítimos (gateway firmando + tutor mandando el
    # token) y RECIÉN DESPUÉS prender este flag, o se cae el arranque de
    # episodios.
    require_gateway_signature: bool = Field(default=False)
    gateway_shared_secret: str = Field(default="")
    internal_service_token: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
