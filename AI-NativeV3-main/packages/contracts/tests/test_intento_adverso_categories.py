"""Tests del contrato `intento_adverso_detectado` (ADR-019 + ADR-043).

Bug de contrato runtime: el detector de guardrails define SEIS categorías
(incluyendo `overuse`, severidad 1, ADR-043) pero el Literal del payload
`IntentoAdversoDetectadoPayload.category` listaba solo CINCO. Como
`CTRBaseEvent` usa `extra="forbid"` y los modelos son frozen, emitir un evento
con `category="overuse"` desde `tutor_core` fallaba la validación Pydantic en
runtime.

Estos tests blindan que:
1. Las 6 categorías del detector validan (incluyendo `overuse`).
2. El `self_hash` se computa para un evento `overuse` (la cadena no se rompe).
3. Una categoría inventada sigue siendo rechazada (el Literal no se aflojó).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from platform_contracts.ctr import IntentoAdversoDetectado, compute_self_hash
from platform_contracts.ctr.events import IntentoAdversoDetectadoPayload
from pydantic import ValidationError

VALID_HASH = "a" * 64

# Las 6 categorías canónicas del detector
# (`apps/tutor-service/.../guardrails.py::Category`). El contrato del evento
# DEBE aceptar exactamente estas seis — ni más ni menos.
GUARDRAILS_CATEGORIES = (
    "jailbreak_indirect",
    "jailbreak_substitution",
    "jailbreak_fiction",
    "persuasion_urgency",
    "prompt_injection",
    "overuse",
)


def _make_event(category: str, severity: int = 1) -> IntentoAdversoDetectado:
    return IntentoAdversoDetectado(
        event_uuid=uuid4(),
        episode_id=uuid4(),
        tenant_id=uuid4(),
        seq=3,
        ts=datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC),
        prompt_system_hash=VALID_HASH,
        prompt_system_version="1.0.0",
        classifier_config_hash=VALID_HASH,
        payload=IntentoAdversoDetectadoPayload(
            pattern_id="overuse_burst_v1",
            category=category,  # type: ignore[arg-type]
            severity=severity,
            matched_text="(ventana temporal cross-prompt)",
            guardrails_corpus_hash=VALID_HASH,
        ),
    )


@pytest.mark.parametrize("category", GUARDRAILS_CATEGORIES)
def test_all_six_guardrails_categories_validate(category: str) -> None:
    """Las 6 categorías del detector deben construir el payload sin error."""
    event = _make_event(category)
    assert event.payload.category == category


def test_overuse_event_validates_and_hashes() -> None:
    """`category='overuse'` (ADR-043) valida y su self_hash se computa.

    Este es el caso exacto que `tutor_core` emite desde `overuse_match` y que
    antes del fix rompía la validación Pydantic en runtime.
    """
    event = _make_event("overuse", severity=1)
    assert event.payload.category == "overuse"

    h = compute_self_hash(event)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    # Determinista
    assert compute_self_hash(event) == h


def test_bogus_category_still_rejected() -> None:
    """Una categoría fuera del Literal sigue siendo rechazada (no se aflojó)."""
    with pytest.raises(ValidationError):
        _make_event("definitely_not_a_real_category")
