"""Helpers de cadena SHA-256 del CTR.

Dos funciones críticas:
- compute_self_hash: hash determinista de un evento (excluyendo los propios hashes)
- compute_chain_hash: hash que encadena con el evento anterior

GENESIS_HASH es una constante arbitraria de 64 hex chars usada como
prev_chain_hash del primer evento (seq=0) de cada episodio. NO es SHA-256("")
(que sería e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855).
La elección de "0"*64 es arbitraria pero estable: cualquier cambio invalida
toda cadena existente del piloto. Debe coincidir bit-a-bit con
`apps/ctr-service/src/ctr_service/models/base.py::GENESIS_HASH`.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_contracts.ctr.events import CTRBaseEvent


GENESIS_HASH = "0" * 64


def compute_self_hash(event: CTRBaseEvent) -> str:
    """SHA-256 del evento canonicalizado.

    Canonicalización: campos lex-ordenados, separadores compactos, codificación
    UTF-8, **sin escape de caracteres no-ASCII** (`ensure_ascii=False`).

    Bit-exact con el runtime
    -----------------------
    Debe producir el mismo hash que
    `apps/ctr-service/src/ctr_service/services/hashing.py::compute_self_hash`
    para todo evento — incluyendo los que contengan tildes, "ñ" o cualquier
    carácter no-ASCII en su payload. Sin `ensure_ascii=False` los dos helpers
    divergen silenciosamente y un auditor externo que use este package vería
    falsos failures sobre cadenas íntegras del piloto.

    Tesis Sec 7.3: "campos ordenados lexicográficamente, codificación UTF-8,
    separadores compactos, sin escape de caracteres no-ASCII".
    """
    canonical = event.model_dump_json(
        exclude={"self_hash", "chain_hash"},
    )
    # Forzar orden determinístico reparseando y re-serializando con sort_keys
    import json

    parsed = json.loads(canonical)
    canonical_sorted = json.dumps(
        parsed,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_sorted.encode("utf-8")).hexdigest()


def compute_chain_hash(self_hash: str, prev_chain_hash: str | None) -> str:
    """Hash que encadena con el evento anterior.

    Formula canonica: chain_hash_n = SHA-256(self_hash_n || prev_chain_hash_{n-1})
    self primero, prev despues — counterintuitivo, declarado en CLAUDE.md
    "Constantes que NO deben inventarse". Este orden matchea exactamente
    `apps/ctr-service/src/ctr_service/services/hashing.py::compute_chain_hash`
    y es el que produce la cadena criptografica vigente en la DB del piloto.

    Para el primer evento del episodio, prev_chain_hash debe ser None
    (se usa GENESIS_HASH).
    """
    prev = prev_chain_hash if prev_chain_hash is not None else GENESIS_HASH
    concatenated = f"{self_hash}{prev}"
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


def verify_chain_integrity(
    events_with_hashes: list[tuple[CTRBaseEvent, str, str]],
) -> tuple[bool, int | None]:
    """Verifica que la cadena de eventos sea íntegra.

    Args:
        events_with_hashes: lista de (evento, self_hash, chain_hash) en orden de seq.

    Returns:
        Tupla (is_valid, failing_seq). failing_seq es None si todo es íntegro,
        o el seq del primer evento donde la cadena se rompe.
    """
    prev_chain = None
    for event, stored_self_hash, stored_chain_hash in events_with_hashes:
        # Recalcular self_hash y comparar
        recomputed_self = compute_self_hash(event)
        if recomputed_self != stored_self_hash:
            return False, event.seq

        # Recalcular chain_hash y comparar
        recomputed_chain = compute_chain_hash(stored_self_hash, prev_chain)
        if recomputed_chain != stored_chain_hash:
            return False, event.seq

        prev_chain = stored_chain_hash

    return True, None
