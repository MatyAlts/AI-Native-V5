"""Config del ai-gateway."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "ai-gateway"
    service_port: int = 8011
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    # Default vacio: este servicio solo se llama server-to-server desde el
    # api-gateway (sin Origin header). Si se necesita exposicion publica,
    # setear CORS_ORIGINS explicito por env. Wildcard "*" prohibido por audit.
    cors_origins: list[str] = Field(default_factory=list)
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    redis_url: str = "redis://127.0.0.1:6379/1"  # DB 1 separada del CTR

    # Provider de LLM activo. CLAUDE.md exige `mock` como default dev para que el
    # test suite y los smoke locales no requieran API keys reales. Override via
    # env var `LLM_PROVIDER=anthropic` (o el provider real que corresponda) cuando
    # haya keys configuradas.
    llm_provider: str = "mock"

    # Resiliencia del streaming del tutor. El modelo (ej. Gemini) puede tirar
    # 503 "model overloaded" en picos AUNQUE sea tier pago. Reintentamos la
    # llamada entera (buffereada) ante errores transitorios; si se configura un
    # `llm_fallback_model`, se prueba ese modelo después de agotar los reintentos.
    llm_stream_max_attempts: int = 3
    llm_fallback_model: str = ""  # ej. "gemini-2.0-flash" — vacío = sin fallback

    # Budgets default por tenant/feature/mes (USD)
    default_monthly_budget_usd: float = 100.0

    # Secrets (no commitear al repo; setear por env var o secret manager)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    mistral_api_key: str = ""

    # ── BYOK (Sec 5+7 epic ai-native-completion / ADR-038-039) ──────────
    # Master key (32 bytes base64) para encriptacion AES-GCM at-rest de las
    # API keys de tenants. Generar con: `openssl rand -base64 32`. Rotacion
    # via runbook (5 steps, downtime ~30s). NO commitear al repo.
    byok_master_key: str = ""
    # Feature flag: si False, el resolver salta directo a env fallback
    # (modo dev legacy o degradado). Si True y no hay key configurada para
    # el scope, el resolver intenta env tambien.
    byok_enabled: bool = True
    # DB de academic_main donde viven byok_keys + byok_keys_usage. El
    # resolver necesita session SQLA con tenant RLS aplicado.
    academic_db_url: str = (
        "postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
