"""Journal append-only de attestations en JSONL (ADR-021).

Estructura del archivo:
    {log_dir}/attestations-YYYY-MM-DD.jsonl
        donde YYYY-MM-DD es el dia UTC del `ts_attested` (no del `ts_episode_closed`,
        para evitar ambiguedad cross-day).

Cada linea es un attestation completo serializado como JSON. El archivo es
**append-only**: nunca se hace seek/truncate. Se rota diariamente.

POSIX/Windows write con `O_APPEND` flag es atomico para writes < PIPE_BUF (~4KB).
Cada attestation serializado es ~500 bytes, por lo que NO se necesita lock
explicito siempre y cuando solo escriba un consumer (single-consumer del stream
Redis). Si en el futuro se introduce paralelismo, agregar `filelock` package.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Attestation(BaseModel):
    """Una linea del journal — el registro completo y firmado de un episode close."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    episode_id: str = Field(description="UUID lowercase con dashes")
    tenant_id: str = Field(description="UUID lowercase con dashes")
    final_chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    total_events: int = Field(ge=1)
    ts_episode_closed: str = Field(description="ISO-8601 UTC con sufijo Z")
    ts_attested: str = Field(description="ISO-8601 UTC con sufijo Z; momento del firmado")
    signer_pubkey_id: str = Field(min_length=12, max_length=12)
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")
    schema_version: str = "1.0.0"


def now_utc_z() -> str:
    """Timestamp UTC en ISO-8601 con sufijo Z (formato canonico del piloto)."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def attestation_log_path(log_dir: Path, day: datetime | str) -> Path:
    """Path del JSONL del dia. `day` es datetime UTC o string YYYY-MM-DD."""
    day_str = day.strftime("%Y-%m-%d") if isinstance(day, datetime) else day
    return log_dir / f"attestations-{day_str}.jsonl"


def append_attestation(log_dir: Path, attestation: Attestation) -> Path:
    """Appendea la attestation al JSONL del dia (UTC del `ts_attested`).

    Devuelve el path del archivo escrito. Crea `log_dir` si no existe.
    Levanta ValueError si `ts_attested` no es ISO-8601 valido.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # `ts_attested` ya viene formateado con `Z`; lo parseamos para extraer la fecha
    # de manera robusta sin asumir longitud del string.
    iso = attestation.ts_attested.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    day = dt.astimezone(UTC).strftime("%Y-%m-%d")

    path = log_dir / f"attestations-{day}.jsonl"
    line = json.dumps(attestation.model_dump(), separators=(",", ":")) + "\n"

    # Append atomico (O_APPEND). Single-consumer => no race.
    with path.open("a", encoding="utf-8") as f:
        f.write(line)

    return path


def read_attestations_for_date(log_dir: Path, day: str) -> list[Attestation]:
    """Lee y parsea el JSONL del dia `YYYY-MM-DD`. Devuelve [] si no existe."""
    path = log_dir / f"attestations-{day}.jsonl"
    if not path.exists():
        return []
    return [
        Attestation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def raw_jsonl_for_date(log_dir: Path, day: str) -> str | None:
    """Devuelve el JSONL crudo del dia (para `GET /attestations/{date}`).

    None si no existe. Util para que el endpoint sirva el log textual sin
    re-serializar — preserva bit-exact lo escrito.
    """
    path = log_dir / f"attestations-{day}.jsonl"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
