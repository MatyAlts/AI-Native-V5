"""Config del tutor-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "tutor-service"
    service_port: int = 8006
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    redis_url: str = "redis://127.0.0.1:6379/2"

    # URLs de los servicios dependientes
    governance_service_url: str = "http://127.0.0.1:8010"
    content_service_url: str = "http://127.0.0.1:8009"
    ai_gateway_url: str = "http://127.0.0.1:8011"
    ctr_service_url: str = "http://127.0.0.1:8007"
    academic_service_url: str = "http://127.0.0.1:8002"
    # tp-entregas-correccion: evaluation-service para validar secuencialidad de ejercicios
    evaluation_service_url: str = "http://127.0.0.1:8004"

    # Prompt y modelo default (override por tenant vía active_configs)
    # v1.1.0 activado 2026-05-06 (epic tutor-context-rag-rubrica): agrega
    # instrucciones para uso del contexto RAG y rubrica de evaluacion. El
    # tutor ahora usa la rubrica como mapa privado de navegacion pedagogica
    # (orienta preguntas socraticas sin revelar criterios ni puntajes).
    # ai-native-prompts/manifest.yaml expone esta version via /active_configs.
    default_prompt_name: str = "tutor"
    default_prompt_version: str = "v1.1.0"
    default_model: str = "mistral-small-latest"
    opus_model: str = "claude-opus-4-7"

    # Feature flags por tenant (F6)
    feature_flags_path: str = "/etc/platform/feature_flags.yaml"
    feature_flags_reload_seconds: int = 60

    # ADR-025 (G10-A): worker de abandono por timeout. Detecta sesiones
    # inactivas y emite EpisodioAbandonado(reason="timeout"). El frontend
    # cubre el caso normal con beforeunload + reason="beforeunload"; el
    # worker cubre mobile, crashes, conexion caida, etc.
    episode_idle_timeout_seconds: int = 30 * 60  # 30 min de inactividad
    abandonment_check_interval_seconds: int = 60  # sweep cada 1 min
    enable_abandonment_worker: bool = True  # apagable para tests / dev

    # ADR-027 / ADR-044 (Mejora 4 plan post-piloto-1): Fase B de guardrails —
    # postprocesamiento de respuestas del tutor + cálculo de socratic_compliance.
    # OFF por default. Mientras esté False, el campo
    # `TutorRespondioPayload.socratic_compliance` persiste como None y
    # `violations` como lista vacía, preservando la garantía de ADR-027 ("el
    # campo queda None hasta que la calibración con docentes valide el cálculo").
    # Activación bloqueada hasta validación intercoder κ ≥ 0.6 sobre 50+
    # respuestas etiquetadas por 2 docentes independientes. El esqueleto
    # técnico (detector + score + tests) vive en
    # `tutor_service.services.postprocess_socratic`.
    socratic_compliance_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
