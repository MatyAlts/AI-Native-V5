"""Configuración del servicio academic-service."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service
    service_name: str = "academic-service"
    service_port: int = 8002
    environment: str = Field(default="development")
    log_level: str = Field(default="info")
    log_format: str = Field(default="json")

    # CORS — default vacio: solo el api-gateway llama server-to-server
    # (sin Origin header). Para exposicion publica, setear CORS_ORIGINS
    # explicito via env. Wildcard "*" prohibido por audit de seguridad.
    cors_origins: list[str] = Field(default_factory=list)

    # Observability
    otel_endpoint: str = Field(default="http://127.0.0.1:4317")
    sentry_dsn: str = Field(default="")

    # Keycloak
    keycloak_url: str = Field(default="http://127.0.0.1:8180")
    keycloak_realm: str = Field(default="demo_uni")

    # Defensa en profundidad cross-service (firma HMAC del gateway).
    # require_gateway_signature=False (default) => comportamiento actual: se
    # confía en los headers X-* del gateway sin más. Cuando se prende, se exige
    # que el gateway haya firmado los headers de identidad (X-Gateway-Signature
    # + X-Gateway-Ts) con gateway_shared_secret; firma ausente/inválida => 401.
    # ORDEN DE ACTIVACIÓN: primero deployar el gateway firmando (con el secreto
    # compartido seteado) y RECIÉN DESPUÉS prender este flag, o se cae todo.
    require_gateway_signature: bool = Field(default=False)
    gateway_shared_secret: str = Field(default="")

    # Token compartido de plataforma para llamadas internas server-to-server
    # que NO pasan por el api-gateway (academic → classifier / ai-gateway
    # directo). Cuando esos servicios prenden `require_gateway_signature`,
    # aceptan procedencia via firma del gateway O via este token en el header
    # `X-Internal-Service-Token`. Default vacío => NO se manda el header
    # (backward-compat: comportamiento idéntico al actual). Setear el mismo
    # secreto en todos los servicios de la plataforma para activarlo.
    internal_service_token: str = Field(default="")

    # Database
    academic_db_url: str = Field(
        default="postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main"
    )
    db_echo: bool = Field(default=False)

    # Rate limiting del canje de invite_code (A0.7 — anti fuerza bruta).
    # Redis compartido con el resto del stack (misma db index que el gateway).
    rate_limit_redis_url: str = Field(default="redis://127.0.0.1:6379/4")
    # Bucket por actor (user_id | IP): tope de intentos de canje por ventana.
    invite_join_actor_max_attempts: int = Field(default=10, ge=1)
    invite_join_actor_window_seconds: int = Field(default=60, ge=1)
    # Bucket por código: tope de intentos FALLIDOS por ventana (fuerza bruta
    # distribuida sobre un mismo código). Los aciertos no cuentan.
    invite_join_code_max_failures: int = Field(default=20, ge=1)
    invite_join_code_window_seconds: int = Field(default=300, ge=1)

    # External services (Sec 11 epic ai-native-completion: TP-gen IA)
    governance_service_url: str = Field(default="http://127.0.0.1:8010")
    ai_gateway_url: str = Field(default="http://127.0.0.1:8011")
    content_service_url: str = Field(default="http://127.0.0.1:8009")
    # Bootstrap mínimo F9: el endpoint /comisiones/{id}/config-hashes pide
    # el hash vigente del classifier al servicio dueño de la fórmula
    # determinista (compute_classifier_config_hash). Si no responde, el
    # handler degrada al fallback hardcoded "d"*64 (warning en log).
    # Sin barra final: se concatena con "/api/v1/..." y una barra de mas produce
    # `//api/v1/...`, que da 404. El handler degrada al fallback "d"*64 con solo
    # un warning, y ese valor es hex valido: pasa cualquier validacion de formato
    # y se ve como un hash legitimo. Asi los 981 episodios del piloto quedaron
    # firmados con el placeholder sin que nadie lo notara (detectado 2026-08-06).
    # No se repara hacia atras: la cadena es append-only.
    classifier_service_url: str = Field(default="http://127.0.0.1:8008")

    @field_validator("classifier_service_url")
    @classmethod
    def _sin_barra_final(cls, v: str) -> str:
        return v.rstrip("/")

    tp_generator_prompt_version: str = Field(default="v1.0.0")
    # Default Gemini (namespaced → OpenRouter con fallback keyless a Gemini nativo).
    # Antes era "mistral-small-latest" (sin key de Mistral configurada → 502).
    # Override por env TP_GENERATOR_DEFAULT_MODEL.
    tp_generator_default_model: str = Field(default="google/gemini-2.0-flash")
    # Techo de tokens de SALIDA de la generación de TPs. Mismo problema y mismo
    # fix que `ejercicio_generator_max_tokens` (ver el comentario largo más
    # abajo): estaba hardcodeado en 8192 dentro de `routes/tareas_practicas.py`,
    # así que una TP con schema grande truncaba el JSON a mitad de string y el
    # error salía como "JSON inválido", culpando al prompt en vez del techo.
    # Rige el mismo tope del contrato del ai-gateway (`le=65536`).
    # Override por env TP_GENERATOR_MAX_TOKENS.
    tp_generator_max_tokens: int = Field(default=32768, gt=0)
    # ADR-047 + ADR-048: wizard IA standalone para generar Ejercicios
    # reusables del banco. Devuelve borrador con todos los campos
    # pedagógicos (banco N1-N4, misconceptions, tutor_rules, etc.).
    ejercicio_generator_prompt_version: str = Field(default="v1.0.0")
    # Default Gemini (namespaced → OpenRouter con fallback keyless a Gemini nativo).
    # Override por env EJERCICIO_GENERATOR_DEFAULT_MODEL.
    ejercicio_generator_default_model: str = Field(default="google/gemini-2.0-flash")
    # Techo de tokens de SALIDA de la generación. El valor viejo (8192) quedó
    # corto cuando el ADR-048 engordó el schema pedagógico: un ejercicio
    # completo lleva enunciado, banco socrático N1-N4, misconceptions con
    # probabilidad, anti-patrones, tutor_rules, pistas por nivel, tests y
    # rúbrica. A ~3,5 chars por token, 8192 topaba cerca de los 28.700
    # caracteres y el JSON volvía **truncado a mitad de string** — el parser
    # tiraba "Unterminated string" y el handler lo reportaba como "JSON
    # inválido", que apuntaba al prompt en vez de al techo real.
    # ⚠️ ACOTADO POR EL CONTRATO DEL AI-GATEWAY: `CompleteRequest.max_tokens`
    # valida `le=65536` (`apps/ai-gateway/.../routes/complete.py`). Pasarse de
    # ese techo NO da un error del modelo — da un **422 del ai-gateway** antes
    # de llegar al provider, y el caller lo ve como 502 tras agotar los
    # reintentos. Si hace falta subir esto, hay que subir ANTES el `le` de allá
    # y deployar el ai-gateway PRIMERO.
    # Override por env EJERCICIO_GENERATOR_MAX_TOKENS.
    ejercicio_generator_max_tokens: int = Field(default=32768, gt=0)
    # Presupuesto TOTAL de la generación IA contra el ai-gateway, reintentos
    # incluidos — no por intento. Con timeout por intento el peor caso era
    # `max_attempts × timeout + backoff` (3×90s = 271.5s), que ya excedía el
    # timeout del gateway: el gateway cortaba, el cliente veía un error opaco y
    # el backend seguía generando contra un caller que ya no estaba.
    #
    # La cascada va de MÁS a MENOS hacia adentro. Este es el número más chico:
    #
    #   cliente 300s  >  api-gateway 270s  >  este presupuesto 240s
    #
    # Al mover cualquiera de los tres, mover los tres.
    # Override por env EJERCICIO_GENERATOR_BUDGET_SECONDS.
    ejercicio_generator_budget_seconds: float = Field(default=240.0, gt=0)
    # P-9 / A2.4: límite de generaciones IA (TP/ejercicio) concurrentes. Cada
    # generación pega al LLM hasta agotar el presupuesto de arriba; sin tope, N
    # docentes disparando el wizard a la vez saturan al ai-gateway y (por el
    # patrón viejo) agotaban el pool de Postgres. Semáforo compartido por ambos
    # endpoints /generate.
    # Override por env AI_GENERATION_MAX_CONCURRENCY.
    ai_generation_max_concurrency: int = Field(default=4, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
