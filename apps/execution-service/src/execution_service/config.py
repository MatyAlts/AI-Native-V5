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

    # ── Sandbox (ADR-060) ────────────────────────────────────────────────────
    # El motor es un contenedor Docker efimero SIN privilegios. Judge0 quedo
    # superado por el ADR-060: exigia contenedor privilegiado y cgroups v1, que
    # es lo que obligaba a sacarlo del VPS y pagar cloud.
    #
    # Imagen con JDK. En produccion se pinea por DIGEST, no por tag: un tag
    # mutable permite que cambie el JDK bajo los pies (control C1).
    java_image: str = Field(default="eclipse-temurin:21-jdk")

    # ── Runner (gate D3 del ADR-060) ─────────────────────────────────────────
    # Este servicio NO monta `/var/run/docker.sock`: ese socket es equivalente a
    # root en el host, y con el se puede crear un contenedor privilegiado que
    # monte `/`. El acceso a Docker vive en un proceso aparte —el runner— que
    # solo acepta `{source_code, stdin}` y arma el comando el mismo.
    #
    # Un socket-proxy NO resuelve esto: filtra por ruta, no por payload, y
    # permitir `POST /containers/create` es permitir crear uno privilegiado.
    runner_url: str = Field(default="http://127.0.0.1:8015")
    # Secreto compartido con el runner. Vacio => sin verificacion (solo dev).
    runner_token: str = Field(default="")

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

    # ── Habilitacion progresiva y apagado (tareas 9.2 y 9.3) ─────────────────
    # Lista de comisiones habilitadas, separadas por coma. VACIA = habilitado
    # para todas. Sirve para la puesta en produccion: se prende para UNA comision
    # antes que para todas, y si algo sale mal se saca esa sola sin tocar al
    # resto del piloto.
    execution_enabled_comisiones: str = Field(default="")
    # Interruptor general. En `false` el servicio responde 503 a toda ejecucion y
    # el editor vuelve solo al estado "ejecucion no disponible" — sin desplegar
    # nada y sin romper los episodios en curso, porque ejecutar es un agregado y
    # no un bloqueante. Es el procedimiento de apagado.
    execution_enabled: bool = Field(default=True)

    def comision_habilitada(self, comision_id: str | None) -> bool:
        """True si esa comision puede ejecutar.

        Sin lista configurada, todas pueden. Con lista, solo las que estan.
        """
        if not self.execution_enabled:
            return False
        permitidas = {c.strip() for c in self.execution_enabled_comisiones.split(",") if c.strip()}
        if not permitidas:
            return True
        return bool(comision_id) and comision_id in permitidas

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
