"""Configuración del servicio evaluation-service."""

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
    service_name: str = "evaluation-service"
    service_port: int = 8004
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

    # Keycloak (la mayoría de servicios valida JWT)
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

    # Database
    academic_db_url: str = Field(
        default="postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main"
    )

    # Servicios internos
    ctr_service_url: str = Field(default="http://127.0.0.1:8007")

    # ── Corrección con IA: qué motor la resuelve ────────────────────────────
    #
    # `activeia` es lo de siempre y es el DEFAULT: prender un motor nuevo por
    # omisión cambiaría notas de alumnos sin que nadie lo decida.
    #
    # `nativo` corrige contra `Ejercicio.rubrica` —la que el docente escribió—
    # pasando por el ai-gateway. Ver `correccion_nativa.py` para el porqué.
    correccion_motor: str = Field(default="activeia")
    ai_gateway_url: str = Field(default="http://127.0.0.1:8011")
    # Namespaced a proposito: la regla del gateway es que un modelo con "/" se
    # rutea por OpenRouter. Sin namespace se va al proveedor nativo.
    correccion_model: str = Field(default="google/gemini-2.5-flash-lite")
    # El prompt de correccion NO vive como string en el codigo: se pide
    # versionado, con su hash, igual que los del tutor.
    governance_service_url: str = Field(default="http://127.0.0.1:8010")
    execution_service_url: str = Field(default="http://127.0.0.1:8013")
    academic_service_url: str = Field(default="http://127.0.0.1:8002")

    # ── Active-IA (correccion asistida) ───────────────────────────────────
    #
    # FALLA CERRADO (default `false`), mismo criterio que `execution_enabled`
    # del execution-service: prendido, esto manda codigo de alumnos a un
    # servicio externo y gasta cuota. Un default `true` encenderia eso para el
    # piloto entero en el primer deploy que no tocara el flag. Un doc no frena
    # un deploy; un default si. Es tambien el procedimiento de apagado.
    activeia_enabled: bool = Field(default=False)

    activeia_url: str = Field(default="https://api.active-ia.com/api/v1")

    # 90s y no 30: medido contra la API en vivo, `GET /pendientes/moodle` tardo
    # 25, 40 y 24 segundos en tres corridas. Con 30 fallaba una de cada tres.
    activeia_timeout_seconds: float = Field(default=90.0)

    # Master key PROPIA, no `BYOK_MASTER_KEY`: cifra passwords de cuentas de
    # terceros y no queremos ampliar el blast radius de la key de BYOK a un
    # segundo pod (design D5). 32 bytes en base64 — `openssl rand -base64 32`.
    # Vacia = las credenciales no se pueden guardar ni leer, y el endpoint lo
    # dice explicitamente en vez de fallar con un error de cifrado.
    activeia_master_key: str = Field(default="")

    # Correcciones por docente y por dia. La cuota FALLA CERRADA (503 si no se
    # puede leer el contador): cada corrida cuesta computo y dinero.
    activeia_cuota_diaria_por_docente: int = Field(default=100)

    # El sincronizador de rubricas depende de endpoints de escritura que
    # Active-IA todavia NO expone (`POST/PUT /rubricas/`), y de poder leerlas
    # de vuelta para comparar el hash — hoy `GET /rubricas/{id}` devuelve 403
    # con rol tutor.
    activeia_sync_rubricas_enabled: bool = Field(default=False)

    # Simula SOLO la escritura de rubricas, para poder construir y probar el
    # circuito entero antes de que el endpoint exista. Lo que devuelve va
    # marcado (`simulado: true`, `rubrica_id` con prefijo `MOCK-`) y cada
    # llamada se loguea en WARNING: un mock silencioso en produccion es
    # indistinguible de una integracion que anda.
    #
    # Default `false` y ademas la app se NIEGA a arrancar si esto esta
    # prendido con `environment=production` (ver `main.py`). Un flag de
    # simulacion que se puede dejar prendido en prod termina con una rubrica
    # inexistente corrigiendo entregas reales.
    activeia_mock_escritura: bool = Field(default=False)

    # Cada cuánto reconcilia correcciones huérfanas, además de la pasada del
    # arranque. Existe porque sólo con la del arranque, un deploy que reinicie
    # en menos de 6 minutos (el umbral de "huérfana") deja colgadas todas las
    # correcciones de esa ventana, sin nadie que las levante nunca.
    # 300s: la mitad del umbral, para que ninguna espere más de un ciclo largo.
    activeia_reconciliador_intervalo_s: float = Field(default=300.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
