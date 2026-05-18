"""Test directo del invariante central de la tesis: chain integrity.

Verifica que `verify_chain_integrity()` (función pura en
`apps/ctr-service/src/ctr_service/services/hashing.py`) detecta tampering
de `self_hash` o `chain_hash` en una cadena de eventos.

Cubre RN-039 / RN-040 + ADR-010 (CTR append-only) y la propiedad central
declarada en Sección 7.3 de la tesis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ctr_service.models.base import GENESIS_HASH
from ctr_service.services.hashing import (
    compute_chain_hash,
    compute_self_hash,
    verify_chain_integrity,
)


def _build_chain(
    n: int = 5,
) -> list[tuple[dict[str, Any], str, str]]:
    """Construye una cadena de N eventos correctamente encadenados."""
    episode_id = uuid4()
    tenant_id = uuid4()
    base_ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
    events: list[tuple[dict[str, Any], str, str]] = []
    prev_chain = GENESIS_HASH
    for i in range(n):
        event = {
            "event_uuid": str(uuid4()),
            "episode_id": str(episode_id),
            "tenant_id": str(tenant_id),
            "seq": i,
            "event_type": "tutor_respondio" if i % 2 else "prompt_enviado",
            "ts": (base_ts + timedelta(seconds=i)).isoformat().replace(
                "+00:00", "Z"
            ),
            "payload": {"step": i, "msg": f"event-{i}"},
            "prompt_system_hash": "sha256-prompt-v1",
            "prompt_system_version": "v1.0.1",
            "classifier_config_hash": "sha256-classifier-v1",
        }
        self_h = compute_self_hash(event)
        chain_h = compute_chain_hash(self_h, prev_chain)
        events.append((event, self_h, chain_h))
        prev_chain = chain_h
    return events


def test_intact_chain_passes_verification() -> None:
    """N=5 eventos correctamente encadenados → valid=True."""
    events = _build_chain(n=5)
    valid, failing_index = verify_chain_integrity(events)
    assert valid is True
    assert failing_index is None


def test_mutated_self_hash_is_detected() -> None:
    """Mutar un byte del self_hash de un evento intermedio → detectado."""
    events = _build_chain(n=5)
    # Mutar self_hash del evento en index=2
    event, self_h, chain_h = events[2]
    # Elegir un char distinto del primero — el test era flaky 1/16 cuando
    # self_h[0] casualmente era "0" y la mutacion no cambiaba nada.
    new_first = "a" if self_h[0] != "a" else "b"
    mutated_self = new_first + self_h[1:]
    assert mutated_self != self_h
    events[2] = (event, mutated_self, chain_h)

    valid, failing_index = verify_chain_integrity(events)

    assert valid is False
    assert failing_index == 2


def test_mutated_chain_hash_is_detected() -> None:
    """Mutar un byte del chain_hash de un evento intermedio → detectado."""
    events = _build_chain(n=5)
    event, self_h, chain_h = events[1]
    # Elegir un char distinto del primero — el test era flaky 1/16 cuando
    # chain_h[0] casualmente era "f" y la mutación no cambiaba nada.
    new_first = "a" if chain_h[0] != "a" else "b"
    mutated_chain = new_first + chain_h[1:]
    assert mutated_chain != chain_h
    events[1] = (event, self_h, mutated_chain)

    valid, failing_index = verify_chain_integrity(events)

    assert valid is False
    assert failing_index == 1


def test_mutated_payload_breaks_self_hash_consistency() -> None:
    """Mutar el payload (sin recomputar hash) → detectado en self_hash."""
    events = _build_chain(n=3)
    event, self_h, chain_h = events[1]
    # Mutar el payload pero NO recomputar self_hash
    mutated_event = {**event, "payload": {"step": 1, "msg": "tampered"}}
    events[1] = (mutated_event, self_h, chain_h)

    valid, failing_index = verify_chain_integrity(events)

    assert valid is False
    assert failing_index == 1


def test_break_at_first_event_detected() -> None:
    """Tampering en el primer evento (vs GENESIS) detectado en index=0."""
    events = _build_chain(n=3)
    event, self_h, chain_h = events[0]
    mutated_chain = "f" * 64  # totally bogus chain_hash
    events[0] = (event, self_h, mutated_chain)

    valid, failing_index = verify_chain_integrity(events)

    assert valid is False
    assert failing_index == 0


def test_empty_chain_is_valid() -> None:
    """Cadena vacía → trivialmente íntegra."""
    valid, failing_index = verify_chain_integrity([])
    assert valid is True
    assert failing_index is None
