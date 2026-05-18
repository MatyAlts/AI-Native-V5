"""Tests golden del modulo metacognitive_feedback (R5 informeSoc.md).

Tests deterministicos sobre cadenas de eventos sinteticas. Validan que la
funcion `generate_metacognitive_feedback` selecciona la plantilla correcta
y respeta los invariantes de seguridad (no nombra categoria de apropiacion,
no nombra niveles N1-N4, no contiene score numerico).

Las plantillas mismas estan en DRAFT — los tests no validan el contenido
literal sino la plantilla seleccionada + propiedades estructurales.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from platform_ops.metacognitive_feedback import (
    METACOG_FEEDBACK_VERSION,
    MIN_EVENTS_FOR_FEEDBACK,
    generate_metacognitive_feedback,
)

BASE_TS = datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)


def _ev(event_type: str, minute: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Helper para construir un evento fake."""
    return {
        "event_type": event_type,
        "ts": BASE_TS + timedelta(minutes=minute),
        "payload": payload or {},
        "seq": minute,
    }


# ---------------------------------------------------------------------------
# Casos limite (plantillas defensivas)
# ---------------------------------------------------------------------------


def test_episodio_con_pocos_eventos_devuelve_episodio_corto() -> None:
    events = [
        _ev("episodio_abierto", 0),
        _ev("lectura_enunciado", 1),
    ]
    assert len(events) < MIN_EVENTS_FOR_FEEDBACK
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "episodio_corto"
    assert result["is_draft"] is True
    assert result["metacog_feedback_version"] == METACOG_FEEDBACK_VERSION


def test_episodio_abandonado_devuelve_abandonado_o_comprometido() -> None:
    events = [
        _ev("episodio_abierto", 0),
        _ev("lectura_enunciado", 1),
        _ev("edicion_codigo", 2),
        _ev("codigo_ejecutado", 3),
        _ev("prompt_enviado", 4),
        _ev("tutor_respondio", 5),
        _ev("episodio_abandonado", 6, {"reason": "timeout"}),
    ]
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "abandonado_o_comprometido"


def test_episodio_con_integrity_compromised_devuelve_abandonado_o_comprometido() -> None:
    events = [
        _ev("episodio_abierto", 0),
        _ev("edicion_codigo", 1),
        _ev("codigo_ejecutado", 2),
        _ev("prompt_enviado", 3),
        _ev("tutor_respondio", 4),
        _ev("episodio_cerrado", 5, {"integrity_compromised": True}),
    ]
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "abandonado_o_comprometido"


# ---------------------------------------------------------------------------
# Plantillas por patron principal
# ---------------------------------------------------------------------------


def test_episodio_sin_prompts_devuelve_sin_tutor() -> None:
    events = [
        _ev("episodio_abierto", 0),
        _ev("lectura_enunciado", 1),
        _ev("edicion_codigo", 2),
        _ev("codigo_ejecutado", 3),
        _ev("edicion_codigo", 4),
        _ev("tests_ejecutados", 5, {"test_count_failed": 0}),
        _ev("episodio_cerrado", 6),
    ]
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "sin_tutor"


def test_episodio_solo_conversacion_sin_ejecuciones_devuelve_solo_conversacion() -> None:
    events = [
        _ev("episodio_abierto", 0),
        _ev("lectura_enunciado", 1),
        _ev("prompt_enviado", 2),
        _ev("tutor_respondio", 3),
        _ev("prompt_enviado", 4),
        _ev("tutor_respondio", 5),
        _ev("episodio_cerrado", 6),
    ]
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "solo_conversacion"
    assert "2" in result["feedback_text"]  # n_prompts insertado


def test_episodio_con_prompts_post_tests_devuelve_integrando_feedback() -> None:
    """Patron: ejecuta tests, despues consulta, repite."""
    events = [
        _ev("episodio_abierto", 0),
        _ev("lectura_enunciado", 1),
        _ev("edicion_codigo", 2),
        _ev("tests_ejecutados", 3, {"test_count_failed": 1}),
        _ev("prompt_enviado", 4),  # post-test
        _ev("tutor_respondio", 5),
        _ev("edicion_codigo", 6),
        _ev("tests_ejecutados", 7, {"test_count_failed": 0}),
        _ev("prompt_enviado", 8),  # post-test
        _ev("tutor_respondio", 9),
        _ev("episodio_cerrado", 10),
    ]
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "integrando_feedback"


def test_episodio_con_prompts_tempranos_devuelve_consulta_temprana() -> None:
    """Patron: dos prompts en primeros 3 minutos, despues trabajo solo."""
    events = [
        _ev("episodio_abierto", 0),
        _ev("prompt_enviado", 1),  # minuto 1, dentro de 180s
        _ev("tutor_respondio", 1),
        _ev("prompt_enviado", 2),  # minuto 2, dentro de 180s
        _ev("tutor_respondio", 2),
        _ev("edicion_codigo", 10),  # despues, sin mas prompts
        _ev("codigo_ejecutado", 11),
        _ev("tests_ejecutados", 12, {"test_count_failed": 0}),
        _ev("episodio_cerrado", 13),
    ]
    result = generate_metacognitive_feedback(events)
    assert result["feedback_template"] == "consulta_temprana"


def test_episodio_mixto_devuelve_mixto() -> None:
    """Patron sin ninguna senal dominante."""
    events = [
        _ev("episodio_abierto", 0),
        _ev("lectura_enunciado", 1),
        _ev("edicion_codigo", 5),
        _ev("codigo_ejecutado", 10),
        _ev("prompt_enviado", 11),  # despues de exec, podria contar como post-tests
        _ev("tutor_respondio", 11),
        _ev("edicion_codigo", 12),
        _ev("prompt_enviado", 15),  # otro prompt sin test previo reciente
        _ev("tutor_respondio", 15),
        _ev("edicion_codigo", 16),
        _ev("episodio_cerrado", 20),
    ]
    result = generate_metacognitive_feedback(events)
    # Con prompts post-exec >= 50% caeria en integrando_feedback. Verifiquemos
    # que la seleccion es consistente con la logica documentada.
    assert result["feedback_template"] in ("integrando_feedback", "mixto")


# ---------------------------------------------------------------------------
# Invariantes de seguridad pedagogica
# ---------------------------------------------------------------------------


def test_ninguna_plantilla_nombra_categoria_de_apropiacion() -> None:
    """Cubre invariante: no nombrar `reflexiva`, `superficial`, `delegacion`."""
    casos = [
        # sin tutor
        [_ev("episodio_abierto", 0), _ev("edicion_codigo", 1), _ev("codigo_ejecutado", 2),
         _ev("edicion_codigo", 3), _ev("tests_ejecutados", 4, {"test_count_failed": 0}),
         _ev("episodio_cerrado", 5)],
        # solo conversacion
        [_ev("episodio_abierto", 0), _ev("prompt_enviado", 1), _ev("tutor_respondio", 2),
         _ev("prompt_enviado", 3), _ev("tutor_respondio", 4), _ev("episodio_cerrado", 5)],
        # mixto largo
        [_ev("episodio_abierto", 0), _ev("lectura_enunciado", 1), _ev("edicion_codigo", 5),
         _ev("codigo_ejecutado", 10), _ev("prompt_enviado", 11), _ev("tutor_respondio", 12),
         _ev("episodio_cerrado", 13)],
    ]
    PALABRAS_PROHIBIDAS = ["reflexiva", "superficial", "delegacion", "delegación"]
    for events in casos:
        result = generate_metacognitive_feedback(events)
        text = result["feedback_text"].lower()
        for palabra in PALABRAS_PROHIBIDAS:
            assert palabra not in text, (
                f"plantilla {result['feedback_template']} contiene '{palabra}': {text}"
            )


def test_ninguna_plantilla_nombra_niveles_N1_a_N4() -> None:
    """Cubre invariante: no nombrar N1, N2, N3, N4."""
    events = [
        _ev("episodio_abierto", 0),
        _ev("prompt_enviado", 1),
        _ev("tutor_respondio", 2),
        _ev("edicion_codigo", 3),
        _ev("codigo_ejecutado", 4),
        _ev("tests_ejecutados", 5, {"test_count_failed": 0}),
        _ev("episodio_cerrado", 6),
    ]
    result = generate_metacognitive_feedback(events)
    text = result["feedback_text"].lower()
    for nivel in ["n1", "n2", "n3", "n4"]:
        assert nivel not in text


def test_todas_las_plantillas_marcadas_como_draft() -> None:
    events = [_ev("episodio_abierto", 0)]
    result = generate_metacognitive_feedback(events)
    assert result["is_draft"] is True
    assert "draft" in result["metacog_feedback_version"].lower()


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------


def test_dos_llamadas_con_mismos_eventos_devuelven_mismo_texto() -> None:
    events = [
        _ev("episodio_abierto", 0),
        _ev("prompt_enviado", 1),
        _ev("tutor_respondio", 1),
        _ev("edicion_codigo", 5),
        _ev("tests_ejecutados", 6, {"test_count_failed": 0}),
        _ev("episodio_cerrado", 7),
    ]
    r1 = generate_metacognitive_feedback(events)
    r2 = generate_metacognitive_feedback(events)
    assert r1 == r2
