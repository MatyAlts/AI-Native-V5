"""Config del execution-service (ADR-059)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "execution-service"
    # Puerto reservado para el sandbox desde ADR-033 (que difirio la ejecucion
    # server-side pero ya le habia apartado el numero).
    service_port: int = 8013
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    # CORS — default vacio: solo el api-gateway llama server-to-server
    # (sin Origin header). Wildcard "*" prohibido por audit de seguridad.
    cors_origins: list[str] = Field(default_factory=list)
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    # ── Sandbox (ADR-059) ────────────────────────────────────────────────────
    # La direccion va por env A PROPOSITO: la decision de infraestructura
    # (gestionado vs servidor propio) NO debe bloquear el desarrollo, y migrar
    # de uno a otro no tiene que tocar codigo. Ver D2/D3 del ADR-059.
    judge0_base_url: str = Field(default="http://127.0.0.1:2358")
    # Token de la API del proveedor gestionado. NUNCA en disco ni en logs
    # (control C3 del ADR-059). Vacio => se asume Judge0 local sin auth.
    judge0_auth_token: str = Field(default="")
    judge0_timeout_seconds: float = Field(default=20.0, gt=0)

    # ── Limites POR CORRIDA ──────────────────────────────────────────────────
    # Explicitos, sin depender de los defaults del sandbox (tarea 3.3): los
    # defaults de Judge0 son generosos y cambian entre versiones. Es la primera
    # de las dos capas de limite del ADR-059; la segunda son las cuotas por
    # alumno, que fallan cerradas.
    execution_cpu_time_limit_seconds: float = Field(default=5.0, gt=0)
    execution_wall_time_limit_seconds: float = Field(default=10.0, gt=0)
    execution_memory_limit_kb: int = Field(default=256_000, gt=0)
    execution_max_processes: int = Field(default=60, gt=0)
    # Control C2 del ADR-059: el codigo del alumno NO tiene salida de red.
    # Se fija acá, del lado del servidor — el cliente no lo elige.
    execution_enable_network: bool = Field(default=False)

    # ── Cuotas por alumno (D5 del design) ────────────────────────────────────
    # FALLAN CERRADAS, al reves que el resto de los limites del sistema. Si el
    # contador no responde, se rechaza: la consecuencia acá es costo real sin
    # techo, no un mensaje de chat de menos.
    redis_url: str = Field(default="redis://127.0.0.1:6379/0")
    execution_quota_max_per_window: int = Field(default=30, gt=0)
    execution_quota_window_seconds: int = Field(default=600, gt=0)

    # ── Auth cross-service (A0.4) ────────────────────────────────────────────
    # Mismo patron y mismo default OFF que el resto de los servicios: encender
    # enforcement por default rompe a los callers que todavia no firman.
    require_gateway_signature: bool = Field(default=False)
    gateway_shared_secret: str = Field(default="")
    internal_service_token: str = Field(default="")

    # Origen de la definicion COMPLETA del ejercicio, con los casos ocultos.
    # El execution-service los lee sin el filtrado por visibilidad que aplica
    # el endpoint publico (tarea 3.4) — por eso pega al academic-service
    # directo y no via gateway.
    academic_service_url: str = Field(default="http://127.0.0.1:8002")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
