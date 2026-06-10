"""Tests del modo sombra de subgrupos (B1 Fase 2).

Verifica el fix de la inversión + que el subgrupo es ADITIVO (no toca la
clasificación oficial ni el classifier_config_hash).
"""

from __future__ import annotations

from classifier_service.services.pipeline import (
    DEFAULT_REFERENCE_PROFILE,
    classify_episode_from_events,
    compute_classifier_config_hash,
)
from classifier_service.services.subgrupo import clasificar_subgrupo, compute_subgrupo


def _ev(seq: int, et: str, **payload: object) -> dict:
    return {"seq": seq, "event_type": et, "ts": f"2026-06-09T22:00:{seq % 60:02d}Z", "payload": payload}


def _autonomo_competente() -> list[dict]:
    """Programó solo (0 prompts), última ejecución limpia."""
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(6):
        ev.append(_ev(1 + 2 * k, "edicion_codigo", origin="student_typed"))
        ev.append(_ev(2 + 2 * k, "codigo_ejecutado", stdout="42\n", stderr=""))
    return ev


def test_autonomo_sin_prompts_NO_cae_en_delegacion() -> None:
    """El fix central: sin prompts, delegar es imposible → rama autónoma, NO delegación."""
    sg = clasificar_subgrupo(_autonomo_competente())
    assert sg.key == "autonomo_competente"
    assert sg.eje == "reflexiva"
    assert sg.eje != "delegacion_pasiva"


def test_delegador_real_por_solicitud_directa() -> None:
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(5):
        ev.append(_ev(1 + 2 * k, "prompt_enviado", prompt_kind="solicitud_directa", content="dame el codigo"))
        ev.append(_ev(2 + 2 * k, "edicion_codigo", origin="pasted_external"))
    ev.append(_ev(20, "codigo_ejecutado", stdout="", stderr="NameError"))
    assert clasificar_subgrupo(ev).key == "dependiente_delegador"


def test_escribe_sin_validar() -> None:
    """Escribió mucho (>=10 ediciones) pero casi no ejecutó."""
    ev = [_ev(0, "lectura_enunciado")]
    for k in range(15):
        ev.append(_ev(1 + k, "edicion_codigo", origin="student_typed"))
    assert clasificar_subgrupo(ev).key == "escribe_sin_validar"


def test_episodio_corto_indeterminado() -> None:
    ev = [_ev(0, "lectura_enunciado"), _ev(1, "edicion_codigo", origin="student_typed")]
    assert clasificar_subgrupo(ev).key == "indeterminado"


def test_compute_subgrupo_trae_dimensiones() -> None:
    sg = compute_subgrupo(_autonomo_competente())
    assert sg["key"] == "autonomo_competente"
    assert set(sg["dimensiones"]) == {"autonomia", "experimentacion", "persistencia", "foco"}
    assert sg["dimensiones"]["autonomia"] == 1.0  # sin prompts ni pegados


def test_subgrupo_es_aditivo_no_cambia_appropriation_oficial() -> None:
    """El subgrupo convive con la clasificación oficial sin alterarla."""
    result = classify_episode_from_events(_autonomo_competente())
    # el motor oficial sigue su lógica vieja (acá, de hecho, lo invierte a delegación)
    assert result.appropriation in ("delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva")
    # y el subgrupo additivo lo ubica bien en features
    assert result.features["subgrupo"]["eje"] == "reflexiva"


def test_subgrupo_no_afecta_el_classifier_config_hash() -> None:
    """features no entra al hash canónico → reproducibilidad intacta."""
    h1 = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    h2 = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    assert h1 == h2 and len(h1) == 64
