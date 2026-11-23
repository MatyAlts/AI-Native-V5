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

    ctr_db_url: str = Field(
        default="postgresql+asyncpg://ctr_user:ctr_pass@127.0.0.1:5432/ctr_store"
    )
    db_echo: bool = False

    # ── Aislamiento por comisión de las LECTURAS del CTR (A0.6) ─────────────
    # Un docente solo puede leer/verificar episodios de comisiones a las que
    # está asignado (`usuarios_comision` en academic_main). superadmin /
    # docente_admin (oversight) y los service-accounts internos
    # (tutor_service / classifier_worker) siguen viendo todo. El CTR vive en su
    # propia base (`ctr_store`) y NO hace joins cross-base — esta conexión de
    # solo-lectura a academic_main existe únicamente para resolver la membresía
    # docente↔comisión, replicando el patrón de analytics-service.
    #
    # `enforce_comision_access=True` (default prod) prende el gate. HU-017: sin
    # `academic_db_url` el gate falla CERRADO (503 a todo el que no sea
    # oversight ni dueño del episodio) — antes era no-op, y producción no tenía
    # la variable. En dev sin base académica, opt-out explícito con
    # `ENFORCE_COMISION_ACCESS=false`.
    academic_db_url: str = Field(default="")
    enforce_comision_access: bool = Field(default=True)

    redis_url: str = "redis://127.0.0.1:6379/0"

    num_partitions: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
