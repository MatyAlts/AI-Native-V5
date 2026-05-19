"""Configuración del api-gateway."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    service_port: int = 8000
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    # CORS: default = solo frontends de dev local. Producción DEBE override via
    # env var CORS_ORIGINS con la lista explícita de dominios del piloto.
    # Nunca usar ["*"] junto con allow_credentials=True (bypass de origin check).
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
        ]
    )
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    keycloak_url: str = "http://127.0.0.1:8180"
    keycloak_realm: str = "demo_uni"

    # Service discovery (URLs de servicios downstream).
    # identity-service (ADR-041) y enrollment-service (ADR-030) deprecated y borrados.
    academic_service_url: str = "http://127.0.0.1:8002"
    evaluation_service_url: str = "http://127.0.0.1:8004"
    analytics_service_url: str = "http://127.0.0.1:8005"
    tutor_service_url: str = "http://127.0.0.1:8006"
    ctr_service_url: str = "http://127.0.0.1:8007"
    classifier_service_url: str = "http://127.0.0.1:8008"
    content_service_url: str = "http://127.0.0.1:8009"
    governance_service_url: str = "http://127.0.0.1:8010"
    ai_gateway_url: str = "http://127.0.0.1:8011"

    # Rate limiting (Redis-backed, por principal+path — middleware preexistente)
    rate_limit_redis_url: str = "redis://127.0.0.1:6379/4"

    # User-bucket rate limit (slowapi, in-memory) — protege contra runaway
    # clients (ej. useEffect en loop). Por `X-User-Id`, fallback IP. Aplica
    # solo a `/api/v1/*`. Desactivar (`rate_limit_enabled=False`) en tests.
    rate_limit_default: str = "100/minute"
    rate_limit_enabled: bool = True

    # JWT validation (F5). Si jwt_issuer está vacío, el gateway cae en
    # modo dev y acepta headers X-* tal cual vienen (solo para local).
    jwt_issuer: str = ""  # ej "http://keycloak:8080/realms/demo_uni"
    jwt_audience: str = "platform-backend"
    jwt_jwks_uri: str = (
        ""  # ej "http://keycloak:8080/realms/demo_uni/protocol/openid-connect/certs"
    )
    jwt_jwks_cache_ttl: int = 300
    # SAFETY: default False — auth via JWT obligatorio. Para dev local sin
    # Keycloak setear DEV_TRUST_HEADERS=true explicito en .env (los frontends
    # mandan X-User-Id / X-Tenant-Id / X-User-Roles via Vite proxy). En piloto-2
    # PROD esto NUNCA debe ir a True — habilitaria impersonacion sin credenciales.
    dev_trust_headers: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
