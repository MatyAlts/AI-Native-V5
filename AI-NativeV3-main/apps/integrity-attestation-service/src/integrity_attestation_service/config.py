"""Config del integrity-attestation-service.

ADR-021 — registro externo auditable. La separacion dev/produccion es central:
- Dev: clave Ed25519 de juguete commiteada al repo en `dev-keys/`. Permite que
  `make test` y el dev loop funcionen sin claves reales ni red.
- Produccion (piloto UTN): clave generada por director de informatica UTN,
  vive en infraestructura institucional separada del cluster del piloto. Si la
  pubkey activa coincide con la dev key Y `environment=production`, el servicio
  rechaza arrancar (failsafe contra deploy accidental con clave de juguete).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "integrity-attestation-service"
    service_port: int = 8012
    environment: str = "development"
    log_level: str = "info"
    log_format: str = "json"

    # CORS — default vacio: solo el api-gateway llama server-to-server
    # (sin Origin header). Para exposicion publica, setear CORS_ORIGINS
    # explicito via env. Wildcard "*" prohibido por audit de seguridad.
    cors_origins: list[str] = Field(default_factory=list)
    otel_endpoint: str = "http://127.0.0.1:4317"
    sentry_dsn: str = ""

    # Bus (consumer del stream `attestation.requests`, PR 3 de G5).
    # IMPORTANTE: debe apuntar a la MISMA DB que el ctr-service (default 0)
    # para compartir el stream. En piloto, es la misma instancia Redis.
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Clave Ed25519 (paths). En dev, defaults a las dev-keys del repo.
    # En piloto, override por env var ATTESTATION_PRIVATE_KEY_PATH apuntando al
    # PEM del VPS institucional.
    attestation_private_key_path: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent / "dev-keys" / "dev-private.pem"
    )
    attestation_public_key_path: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent / "dev-keys" / "dev-public.pem"
    )

    # Directorio donde se appendean los JSONL `attestations-YYYY-MM-DD.jsonl`.
    # Dev: ./attestations/ (gitignored). Piloto: filesystem del VPS o mount a
    # bucket institucional MinIO.
    attestation_log_dir: Path = Path("./attestations")

    # ── Auth cross-service (A0.1) ────────────────────────────────────────────
    # integrity-attestation-service es infra institucional interna (NO está en
    # el ROUTE_MAP del api-gateway), pero expone endpoints HTTP. Sin verificar
    # la *procedencia* de los headers de identidad, cualquiera con acceso de red
    # puede forjar `X-User-Roles`/`X-Tenant-Id` y — vía el POST — hacer que la
    # clave Ed25519 institucional firme y appendee al journal attestations
    # arbitrarias (episodios fabricados con firma legítima de la institución).
    #
    # require_gateway_signature=False (default) => comportamiento actual: no se
    # exige nada. El flag es un no-op total: el runtime es idéntico al de hoy.
    #
    # Con el flag ON, el POST /api/v1/attestations debe probar procedencia por
    # UNO de dos caminos:
    #   (a) firma HMAC del gateway (X-Gateway-Signature + X-Gateway-Ts sobre los
    #       headers X-User-*), verificada con gateway_shared_secret; o
    #   (b) token de service-account (X-Internal-Service-Token) que coincide con
    #       internal_service_token — para callers internos directos que no pasan
    #       por el gateway. Ausencia de ambos => 401.
    #
    # Los GET (/pubkey, /{date}) quedan ABIERTOS incluso con el flag ON: son
    # públicos por diseño (ADR-021) — la pubkey y los JSONL de hashes+firmas
    # deben ser verificables por auditores externos SIN credenciales del
    # gateway. Gatearlos rompería la verificación de terceros. El /health
    # también queda abierto (probes).
    #
    # ORDEN DE ACTIVACIÓN (prod): primero setear el secreto/token compartido y
    # configurar a los callers legítimos del POST (gateway firmando, o el caller
    # interno mandando el token) y RECIÉN DESPUÉS prender este flag.
    require_gateway_signature: bool = Field(default=False)
    gateway_shared_secret: str = Field(default="")
    internal_service_token: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
