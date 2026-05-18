"""Config del integrity-attestation-service.

ADR-021 — registro externo auditable. La separacion dev/produccion es central:
- Dev: clave Ed25519 de juguete commiteada al repo en `dev-keys/`. Permite que
  `make test` y el dev loop funcionen sin claves reales ni red.
- Produccion (piloto UNSL): clave generada por director de informatica UNSL,
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

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
