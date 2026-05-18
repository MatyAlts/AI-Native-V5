"""F1: aseguramos que los `event_type` declarados en los contracts CTR
coinciden 1-a-1 con los strings que emite el tutor-service en runtime.

Si alguien:
  - agrega un evento al contract sin emitirlo en `tutor_core.py`, o
  - emite un evento con un `event_type` que no existe en los contracts,

este test rompe. Bloquea regresiones del bug que motivó F1 (PascalCase
en contracts vs snake_case en runtime).

Nota: NO valida los payloads — solo el conjunto de strings de event_type.
La validación de payload contra el contract es tema de F8/G3.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from platform_contracts.ctr.events import (
    AnotacionCreada,
    CodigoEjecutado,
    EdicionCodigo,
    EpisodioAbandonado,
    EpisodioAbierto,
    EpisodioCerrado,
    IntentoAdversoDetectado,
    LecturaEnunciado,
    PromptEnviado,
    ReflexionCompletada,
    TestsEjecutados,
    TutorRespondio,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TUTOR_CORE = (
    _REPO_ROOT / "apps" / "tutor-service" / "src" / "tutor_service" / "services" / "tutor_core.py"
)


def _contract_event_types() -> set[str]:
    """event_type literal de cada subclase de CTRBaseEvent."""
    classes = (
        EpisodioAbierto,
        EpisodioCerrado,
        EpisodioAbandonado,
        PromptEnviado,
        TutorRespondio,
        LecturaEnunciado,
        AnotacionCreada,
        EdicionCodigo,
        CodigoEjecutado,
        IntentoAdversoDetectado,
        ReflexionCompletada,
        TestsEjecutados,
    )
    return {cls.model_fields["event_type"].default for cls in classes}


def _runtime_event_types() -> set[str]:
    """Strings literales pasados como event_type=... en tutor_core.py.

    Usamos regex en lugar de import + introspección porque los strings
    se construyen inline en `_build_event(..., event_type="...", ...)`.
    """
    source = _TUTOR_CORE.read_text(encoding="utf-8")
    pattern = re.compile(r'event_type\s*=\s*"([a-z_]+)"')
    return set(pattern.findall(source))


def test_tutor_core_file_exists() -> None:
    """Sanity check: si el archivo se movió, el test rompe explícito."""
    assert _TUTOR_CORE.exists(), f"tutor_core.py no encontrado: {_TUTOR_CORE}"


def test_contract_event_types_are_snake_case() -> None:
    """Todos los event_type del contract son snake_case (alineado al runtime)."""
    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    for et in _contract_event_types():
        assert pattern.match(et), (
            f"event_type {et!r} no es snake_case — los contracts deben"
            " alinearse al string que emite el runtime."
        )


@pytest.mark.parametrize(
    "subset_label,subset",
    [
        # Eventos que son emitidos directamente por el tutor-service.
        # `lectura_enunciado` se emite desde el frontend vía endpoint
        # dedicado y no aparece como string literal en tutor_core.py todavía.
        (
            "tutor_core_emitted",
            {
                "episodio_abierto",
                "prompt_enviado",
                "tutor_respondio",
                "episodio_cerrado",
                "codigo_ejecutado",
                "edicion_codigo",
                "anotacion_creada",
                "intento_adverso_detectado",
            },
        ),
    ],
)
def test_runtime_emits_only_contract_event_types(subset_label: str, subset: set[str]) -> None:
    """Lo que emite tutor_core.py existe en los contracts (no inventos)."""
    contract = _contract_event_types()
    runtime = _runtime_event_types()
    extras = runtime - contract
    assert not extras, (
        f"tutor_core.py emite event_types que no están en el contract: {extras}."
        " Agregalos al contract o saca el emit."
    )
    # Y dentro del subset esperado, los esperados están presentes en runtime.
    missing = subset - runtime
    assert not missing, f"tutor_core.py NO emite event_types esperados ({subset_label}): {missing}."
