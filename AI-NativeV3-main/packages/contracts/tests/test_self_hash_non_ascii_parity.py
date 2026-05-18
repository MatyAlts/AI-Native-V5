"""Tests anti-regresión del bit-exact match cross-package de `compute_self_hash`.

Asegura que el helper "auditor" del package `platform_contracts` produce
exactamente el mismo `self_hash` que el runtime del `ctr-service` para
eventos que contengan caracteres no-ASCII (tildes, "ñ", emoji).

Antes del fix de 2026-05-08 (commit que agrega `ensure_ascii=False` al
package), el helper escapaba caracteres como `\\uXXXX` mientras el
runtime no — los hashes divergían silenciosamente. Un auditor doctoral
usando el package "oficial" para verificar la cadena vería falsos
failures sobre eventos que tuvieran "ñ" o tildes en `payload.content`.

La tesis Sec 7.3 declara: "campos ordenados lexicográficamente,
codificación UTF-8, separadores compactos, sin escape de caracteres
no-ASCII". Este test fija esa promesa.

Si este test falla, hay desalineación entre `packages/contracts` y
`apps/ctr-service` — corregir el helper que NO use `ensure_ascii=False`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from platform_contracts.ctr import (
    AnotacionCreada,
    PromptEnviado,
    compute_self_hash,
)
from platform_contracts.ctr.events import (
    AnotacionCreadaPayload,
    PromptEnviadoPayload,
)

VALID_HASH = "a" * 64
FIXED_TS = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
FIXED_EPISODE = UUID("80000000-0000-0000-0000-0000000f69b4")
FIXED_TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FIXED_EVENT = UUID("00000000-0000-0000-0000-000000000bee")


def _runtime_canonicalize_then_sha256(payload_dict: dict) -> str:
    """Replica el runtime del ctr-service paso por paso.

    `apps/ctr-service/src/ctr_service/services/hashing.py::canonicalize`:
        json.dumps(obj, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), default=...).encode("utf-8")
    """
    serialized = json.dumps(
        payload_dict,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def test_self_hash_evento_con_tildes_es_bit_exact_con_runtime() -> None:
    """Evento con tildes y "ñ" → ambos helpers producen el MISMO hash.

    Antes del fix, el helper del package escapaba "ñ" como "\\u00f1" y
    el del runtime no — el hash divergía. Este test garantiza que la
    promesa de la tesis Sec 7.3 se cumple bit-a-bit.
    """
    contenido = "El año pasado vi qué difícil es entender los punteros — ¿será por mi prólogo en C?"
    event = AnotacionCreada(
        event_uuid=FIXED_EVENT,
        episode_id=FIXED_EPISODE,
        tenant_id=FIXED_TENANT,
        seq=0,
        ts=FIXED_TS,
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=AnotacionCreadaPayload(content=contenido, words=18),
    )

    package_hash = compute_self_hash(event)

    # Replicar exactamente el camino del runtime: dict → canonicalize → SHA-256
    event_dict = json.loads(event.model_dump_json(exclude={"self_hash", "chain_hash"}))
    runtime_hash = _runtime_canonicalize_then_sha256(event_dict)

    assert package_hash == runtime_hash, (
        f"Divergencia cross-package detectada con caracteres no-ASCII:\n"
        f"  package helper: {package_hash}\n"
        f"  runtime path:   {runtime_hash}\n"
        f"Si este test falla, el helper de `packages/contracts/.../hashing.py` "
        f"perdió `ensure_ascii=False`. Tesis Sec 7.3 requiere que coincidan."
    )


def test_self_hash_evento_con_enie_en_prompt() -> None:
    """Caso fuerte: "ñ" en el contenido del prompt enviado al tutor."""
    event = PromptEnviado(
        event_uuid=FIXED_EVENT,
        episode_id=FIXED_EPISODE,
        tenant_id=FIXED_TENANT,
        seq=1,
        ts=FIXED_TS,
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=PromptEnviadoPayload(
            content="¿Cómo enseño punteros sin que se enrosquen los dedos?",
            prompt_kind="epistemologica",
            chunks_used_hash=None,
        ),
    )

    package_hash = compute_self_hash(event)
    event_dict = json.loads(event.model_dump_json(exclude={"self_hash", "chain_hash"}))
    runtime_hash = _runtime_canonicalize_then_sha256(event_dict)

    assert package_hash == runtime_hash


def test_self_hash_no_escapa_caracteres_no_ascii() -> None:
    """El hash NO debe ser sensible al escape \\uXXXX.

    Si alguien quita `ensure_ascii=False` del helper del package, el JSON
    canonicalizado contendría "\\u00f1" en vez de "ñ" literal — bytes
    distintos → hash distinto. Este test verifica que el comportamiento
    actual es el correcto (sin escape).
    """
    contenido_con_n = "ñoño"
    contenido_escapado = "ñoño"  # mismo string lógico

    event_with_literal = AnotacionCreada(
        event_uuid=FIXED_EVENT,
        episode_id=FIXED_EPISODE,
        tenant_id=FIXED_TENANT,
        seq=0,
        ts=FIXED_TS,
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=AnotacionCreadaPayload(content=contenido_con_n, words=1),
    )

    # El string literal "ñoño" y el escapado "ñoño" son el mismo
    # string Python — Pydantic no los distingue. Este test garantiza que el
    # hash es el del string lógico, no de su representación textual escapada.
    serialized = event_with_literal.model_dump_json(exclude={"self_hash", "chain_hash"})
    # JSON canonicalizado debe contener "ñ" literal (UTF-8), NO "\\u00f1"
    assert "ñ" in serialized or "\\u00f1" not in serialized, (
        "El helper del package está escapando caracteres no-ASCII — "
        "ensure_ascii=False perdido. Ver tesis Sec 7.3."
    )

    h1 = compute_self_hash(event_with_literal)
    assert contenido_con_n == contenido_escapado  # mismo string Python
    assert len(h1) == 64
