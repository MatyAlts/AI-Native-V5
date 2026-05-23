"""Configuración del api-gateway."""

from functools import cached_property, lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CORS_ORIGINS_CSV = (
    "http://localhost:5173,http://localhost:5174,http://localhost:5175"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    service_port: int = 8000
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    # CORS — STRING (CSV), no list. Razon: pydantic-settings hace json.loads()
    # automatico sobre fields con tipo list/dict/tuple. Con env var vacia o
    # mal-formada (caso real en prod EasyPanel), eso explota con:
    #   SettingsError: error parsing value for field "cors_origins"
    #   json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
    # Workarounds via NoDecode/field_validator dependen de la version de
    # pydantic-settings y son fragiles. Solucion robusta: dejar el field como
    # str y parsearlo a list en runtime via `cors_origins_list`.
    cors_origins: str = _DEFAULT_CORS_ORIGINS_CSV

    @cached_property
    def cors_origins_list(self) -> list[str]:
        """Parse cors_origins (CSV o JSON array) a list[str]."""
        raw = (self.cors_origins or "").strip()
        if not raw:
            return [o.strip() for o in _DEFAULT_CORS_ORIGINS_CSV.split(",")]
        # Tolerar JSON array si alguien lo pone asi
        if raw.startswith("["):
            import json

            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(o) for o in parsed]
            except json.JSONDecodeError:
                pass
        # CSV (formato default y recomendado)
        return [o.strip() for o in raw.split(",") if o.strip()]

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
