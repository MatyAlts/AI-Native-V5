"""Smoke #7 — recompute SHA-256 chain de un episodio live con el helper de
`packages/contracts`.

Atrapa exactamente la clase de bug que el agente anterior cerró: orden
invertido en la concatenación de chain_hash, exclusiones distintas en el
self_hash, sort_keys olvidado, separators desalineados.

Estrategia:
  1. Lee la cadena de events del episodio seedeado directo de Postgres
     (`ctr_store.events`).
  2. Por cada event, reconstruye el dict canónico que el ctr-service usa al
     verificar (mismo schema que el legacy `verify_episode_chain`).
  3. Ejecuta `compute_self_hash` y `compute_chain_hash` del helper de
     `packages/contracts/src/platform_contracts/ctr/hashing.py`.
  4. Compara contra los hashes persistidos en DB.

Si UN solo evento diverge, falla con detalle (qué seq, qué hash recomputado
vs persistido). El éxito de este test es la prueba de que la integridad
criptográfica del CTR es bit-exact reproducible — invariante central de la
tesis.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from platform_contracts.ctr.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
)
from pydantic import BaseModel

from _helpers import fetch_pg  # type: ignore[import-not-found]


class _CanonicalEvent(BaseModel):
    """Vista mínima del event que el ctr-service usa al recomputar self_hash.

    Espejo exacto del dict construido en
    `apps/ctr-service/src/ctr_service/routes/events.py::verify_episode_chain`
    (líneas ~166-178). Si ese mapping cambia, este modelo debe acompañar.
    """

    event_uuid: str
    episode_id: str
    tenant_id: str
    seq: int
    event_type: str
    ts: str  # ISO-8601 con sufijo Z (no +00:00)
    payload: dict[str, Any]
    prompt_system_hash: str
    prompt_system_version: str
    classifier_config_hash: str


def _build_canonical_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convierte una row de events en el dict canónico que se hashea.

    Importante: el ts debe tener sufijo `Z` (no `+00:00`) — invariante
    declarado en RN-128 y en la implementación del verify legacy.
    """
    (
        event_uuid,
        episode_id,
        tenant_id,
        seq,
        event_type,
        ts,
        payload,
        prompt_system_hash,
        prompt_system_version,
        classifier_config_hash,
    ) = row
    return {
        "event_uuid": str(event_uuid),
        "episode_id": str(episode_id),
        "tenant_id": str(tenant_id),
        "seq": seq,
        "event_type": event_type,
        "ts": ts.isoformat().replace("+00:00", "Z"),
        "payload": payload if isinstance(payload, dict) else json.loads(payload),
        "prompt_system_hash": prompt_system_hash,
        "prompt_system_version": prompt_system_version,
        "classifier_config_hash": classifier_config_hash,
    }


@pytest.mark.smoke
def test_recompute_chain_of_seeded_episode(seeded_episode_id: str) -> None:
    """Recomputa la cadena completa del episodio del seed con el helper de
    contracts. Si UN solo hash diverge, falla con el detalle exacto.
    """
    rows = fetch_pg(
        "ctr_store",
        """
        SELECT event_uuid, episode_id, tenant_id, seq, event_type, ts,
               payload, prompt_system_hash, prompt_system_version,
               classifier_config_hash
        FROM events
        WHERE episode_id = %s
        ORDER BY seq
        """,
        (seeded_episode_id,),
    )
    assert rows, f"esperaba events para episode_id={seeded_episode_id} (seed roto?)"
    assert len(rows) >= 5, f"esperaba >=5 events, got {len(rows)}"

    # Levantar los hashes persistidos por separado (no van al canonical dict)
    stored_rows = fetch_pg(
        "ctr_store",
        "SELECT seq, self_hash, prev_chain_hash, chain_hash FROM events "
        "WHERE episode_id = %s ORDER BY seq",
        (seeded_episode_id,),
    )
    stored = {seq: (sh, pch, ch) for (seq, sh, pch, ch) in stored_rows}

    prev_chain: str | None = None
    failures: list[str] = []

    for row in rows:
        event_dict = _build_canonical_dict(row)
        seq = event_dict["seq"]
        stored_self, stored_prev_chain, stored_chain = stored[seq]

        # 1. Recomputar self_hash via el contracts helper. Necesitamos un
        #    pydantic model porque `compute_self_hash` espera CTRBaseEvent.
        event_obj = _CanonicalEvent.model_validate(event_dict)
        recomputed_self = compute_self_hash(event_obj)

        if recomputed_self != stored_self:
            failures.append(
                f"seq={seq} ({event_dict['event_type']}): "
                f"self_hash recomputado={recomputed_self[:16]}... "
                f"persistido={stored_self[:16]}... — DIVERGE"
            )
            # No abortar todavía — agarramos todos los failures para el report.

        # 2. Recomputar chain_hash usando el self_hash PERSISTIDO (no el
        #    recomputado, para aislar bugs de chain vs self).
        recomputed_chain = compute_chain_hash(stored_self, prev_chain)
        if recomputed_chain != stored_chain:
            failures.append(
                f"seq={seq}: chain_hash recomputado={recomputed_chain[:16]}... "
                f"persistido={stored_chain[:16]}... prev_chain_used={prev_chain[:16] if prev_chain else 'GENESIS'}... — DIVERGE"
            )

        # 3. prev_chain_hash en DB debe matchear con el chain anterior (defensa)
        expected_prev = prev_chain if prev_chain is not None else GENESIS_HASH
        if stored_prev_chain != expected_prev:
            failures.append(
                f"seq={seq}: prev_chain_hash en DB ({stored_prev_chain[:16]}...) "
                f"!= chain_hash del seq anterior ({expected_prev[:16]}...) — cadena rota"
            )

        prev_chain = stored_chain

    if failures:
        pytest.fail(
            "Cadena criptografica del episodio seed NO es reproducible bit-a-bit. "
            "Esto invalida la reproducibilidad declarada en CLAUDE.md (Constantes "
            "que NO deben inventarse). Detalle:\n  " + "\n  ".join(failures)
        )
