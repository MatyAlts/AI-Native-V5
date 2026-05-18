"""Tests de Coherencia Inter-Iteración."""

from __future__ import annotations

from classifier_service.services.cii import compute_cii


def _prompt(seq: int, content: str) -> dict:
    return {
        "seq": seq,
        "event_type": "prompt_enviado",
        "ts": "2026-09-01T10:00:00Z",
        "payload": {"content": content},
    }


def test_un_solo_prompt_datos_insuficientes() -> None:
    r = compute_cii([_prompt(0, "qué es recursión")])
    assert r["insufficient_data"] is True


def test_prompts_sobre_mismo_tema_alta_estabilidad() -> None:
    events = [
        _prompt(0, "qué es la recursión en python"),
        _prompt(1, "cómo funciona la recursión para factorial"),
        _prompt(2, "ejemplo de recursión con fibonacci en python"),
    ]
    r = compute_cii(events)
    # Comparten tokens centrales (recursión/recursion, python). Jaccard ronda 0.1-0.2.
    # Lo importante: > que prompts totalmente distintos.
    assert r["cii_stability"] > 0.1


def test_estabilidad_mayor_con_overlap_que_sin() -> None:
    """El test real: overlap produce estabilidad mayor que no-overlap."""
    with_overlap = [
        _prompt(0, "recursión python factorial"),
        _prompt(1, "recursión python fibonacci"),
    ]
    without_overlap = [
        _prompt(0, "alpha beta gamma"),
        _prompt(1, "delta epsilon zeta"),
    ]
    assert (
        compute_cii(with_overlap)["cii_stability"] > compute_cii(without_overlap)["cii_stability"]
    )


def test_prompts_cambiantes_baja_estabilidad() -> None:
    events = [
        _prompt(0, "alpha beta gamma"),
        _prompt(1, "delta epsilon zeta"),
        _prompt(2, "eta theta iota"),
    ]
    r = compute_cii(events)
    # Sin overlap → jaccard ~0
    assert r["cii_stability"] == 0.0


def test_prompts_que_crecen_en_longitud_evolution_alta() -> None:
    events = [
        _prompt(0, "qué"),
        _prompt(1, "qué es recursión"),
        _prompt(2, "qué es recursión y cómo la uso con factorial"),
    ]
    r = compute_cii(events)
    assert r["cii_evolution"] > 0.5


def test_prompts_que_decrecen_evolution_baja() -> None:
    events = [
        _prompt(0, "puedo explicarte este concepto largo y detallado con ejemplos"),
        _prompt(1, "eso sirve"),
        _prompt(2, "ok"),
    ]
    r = compute_cii(events)
    assert r["cii_evolution"] < 0.5


def test_cii_es_determinista() -> None:
    events = [_prompt(0, "uno dos"), _prompt(1, "uno tres")]
    r1 = compute_cii(events)
    r2 = compute_cii(events)
    assert r1["cii_stability"] == r2["cii_stability"]
    assert r1["cii_evolution"] == r2["cii_evolution"]
