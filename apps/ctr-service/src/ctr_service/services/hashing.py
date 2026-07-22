"""Canonicalización criptográfica y verificación de cadena.

La serialización canónica es la clave del hashing determinista. Usamos
JSON con `sort_keys=True`, `ensure_ascii=False`, `separators=(',', ':')`
para que el mismo objeto lógico produzca siempre los mismos bytes.

El módulo re-exporta primitivas de `platform_contracts` para tener una
API estable en el servicio.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from ctr_service.metrics import ctr_self_hash_compute_seconds
from ctr_service.models.base import GENESIS_HASH


def canonicalize(obj: Any) -> bytes:
    """Serialización canónica determinista del payload."""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _json_default(o: Any) -> str:
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, datetime):
        # ISO-8601 con Z para UTC explícito
        return o.isoformat().replace("+00:00", "Z")
    raise TypeError(f"No serializable: {type(o)}")


def compute_self_hash(event: dict[str, Any]) -> str:
    """SHA-256 del evento serializado canónicamente.

    Excluye los campos `self_hash`, `chain_hash`, `prev_chain_hash`,
    `persisted_at` e `id` (metadata de cadena calculados después).

    Relación con la Sección 7.3 de la tesis
    ----------------------------------------
    La tesis enuncia:
        hash_evento_n = SHA-256(contenido_n || hash_evento_{n-1} || hash_prompt_sistema)

    La implementación separa en dos pasos equivalentes en propiedad:
        self_hash_n  = SHA-256(canonicalize(evento_n))
        chain_hash_n = SHA-256(self_hash_n || chain_hash_{n-1})

    El `prompt_system_hash` no se concatena como tercer bloque literal: entra como
    campo del `evento_n` (ver Event.prompt_system_hash en models/event.py). Como
    `canonicalize()` incluye todos los campos del evento salvo metadatos de cadena
    (self_hash, chain_hash, prev_chain_hash, persisted_at, id), el hash del prompt
    vigente queda incorporado a self_hash y por ende a chain_hash. La propiedad
    auditada por la tesis — "si cambia el prompt entre dos eventos, se detecta en
    la cadena" — se preserva bit a bit.

    También se incluye `classifier_config_hash` en cada evento (no mencionado en
    7.3 pero requerido por el principio de reproducibilidad 7.1.4: permite
    reclasificar con otro profile y producir cadena distinguible).
    """
    start = time.perf_counter()
    clean = {
        k: v
        for k, v in event.items()
        if k not in {"self_hash", "chain_hash", "prev_chain_hash", "persisted_at", "id"}
    }
    digest = hashlib.sha256(canonicalize(clean)).hexdigest()
    # Métrica: latencia del compute. Sin labels — la cardinalidad por
    # event_type no aporta y agregaría 15+ buckets duplicados.
    ctr_self_hash_compute_seconds.record(time.perf_counter() - start)
    return digest


def compute_chain_hash(self_hash: str, prev_chain_hash: str | None) -> str:
    """chain_hash = SHA-256(self_hash || prev_chain_hash)

    El primer evento de un episodio usa GENESIS_HASH como prev.
    """
    prev = prev_chain_hash if prev_chain_hash is not None else GENESIS_HASH
    combined = f"{self_hash}{prev}".encode()
    return hashlib.sha256(combined).hexdigest()


def verify_chain_integrity(
    events: list[tuple[dict[str, Any], str, str]],
) -> tuple[bool, int | None]:
    """Verifica que la cadena de eventos sea íntegra.

    Args:
        events: lista de (event_payload, self_hash, chain_hash) en orden
                estricto por seq.

    Returns:
        (valid, failing_index).
        valid=True → cadena íntegra.
        valid=False → falla; failing_index apunta al evento que rompe.
    """
    prev_chain = GENESIS_HASH
    for i, (event, declared_self, declared_chain) in enumerate(events):
        # Re-computar self_hash del payload declarado
        computed_self = compute_self_hash(event)
        if computed_self != declared_self:
            return False, i
        # Re-computar chain_hash con el prev que venimos acarreando
        computed_chain = compute_chain_hash(declared_self, prev_chain)
        if computed_chain != declared_chain:
            return False, i
        prev_chain = declared_chain
    return True, None
