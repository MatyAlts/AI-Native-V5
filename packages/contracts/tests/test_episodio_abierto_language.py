"""`language` en `EpisodioAbiertoPayload` (multi-language-research-integrity,
capability episode-language-provenance).

El piloto vigente tiene ~87 alumnos generando eventos `episodio_abierto` sin
este campo. Agregarlo con default `None` tiene que ser retrocompatible por
construcción: un evento histórico (dict tal cual se persistió, sin la key
"language") debe seguir deserializando sin cambios (task 2.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from platform_contracts.ctr.events import EpisodioAbierto, EpisodioAbiertoPayload

VALID_HASH = "a" * 64


def _historic_event_dict() -> dict:
    """Payload crudo tal como lo emitía el tutor-service ANTES de este
    cambio: sin la key `language` en absoluto (no `None` explícito — la key
    ni existe)."""
    return {
        "event_uuid": str(uuid4()),
        "episode_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "seq": 0,
        "ts": datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC).isoformat(),
        "event_type": "episodio_abierto",
        "prompt_system_hash": VALID_HASH,
        "prompt_system_version": "v1.0.0",
        "classifier_config_hash": VALID_HASH,
        "payload": {
            "student_pseudonym": str(uuid4()),
            "problema_id": str(uuid4()),
            "comision_id": str(uuid4()),
            "curso_config_hash": VALID_HASH,
        },
    }


def test_payload_sin_language_deserializa_con_default_none() -> None:
    """`EpisodioAbiertoPayload` sin la key `language` sigue construyéndose,
    con el campo nuevo en `None` (interpretar como 'python' — ver spec)."""
    payload = EpisodioAbiertoPayload(
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        comision_id=uuid4(),
        curso_config_hash=VALID_HASH,
    )
    assert payload.language is None


def test_evento_historico_completo_deserializa_sin_el_campo() -> None:
    """Un evento `episodio_abierto` completo, persistido antes de este
    cambio (sin `language` en ningún nivel), sigue parseando vía
    `EpisodioAbierto.model_validate(...)` sin error."""
    event = EpisodioAbierto.model_validate(_historic_event_dict())
    assert event.payload.language is None


def test_language_explicito_se_preserva() -> None:
    """Un episodio nuevo con `language="java"` lo conserva tal cual."""
    payload = EpisodioAbiertoPayload(
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        comision_id=uuid4(),
        curso_config_hash=VALID_HASH,
        language="java",
    )
    assert payload.language == "java"
