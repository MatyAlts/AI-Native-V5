"""Tests de Coherencia Temporal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from classifier_service.services.ct import (
    compute_windows,
    ct_features,
)


def _ev(seq: int, event_type: str, minutes_offset: int, payload: dict | None = None) -> dict:
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": (base + timedelta(minutes=minutes_offset)).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


def test_sin_eventos_devuelve_neutral() -> None:
    f = ct_features([])
    assert f["ct_summary"] == 0.5
    assert f["insufficient_data"] is True


def test_eventos_continuos_forman_una_ventana() -> None:
    """Eventos separados por <5min deben estar en la misma ventana."""
    events = [
        _ev(0, "episodio_abierto", 0),
        _ev(1, "prompt_enviado", 2),
        _ev(2, "codigo_ejecutado", 4),
        _ev(3, "prompt_enviado", 4),
    ]
    windows = compute_windows(events)
    assert len(windows) == 1
    assert windows[0].event_count == 4


def test_pausa_larga_divide_en_ventanas() -> None:
    """Pausa >5min divide en dos ventanas."""
    events = [
        _ev(0, "prompt_enviado", 0),
        _ev(1, "codigo_ejecutado", 3),
        _ev(2, "prompt_enviado", 10),  # salto de 7 min → nueva ventana
        _ev(3, "codigo_ejecutado", 12),
    ]
    windows = compute_windows(events)
    assert len(windows) == 2
    assert windows[0].event_count == 2
    assert windows[1].event_count == 2


def test_ct_summary_esta_en_rango_0_1() -> None:
    events = [
        _ev(0, "prompt_enviado", 0),
        _ev(1, "codigo_ejecutado", 1),
        _ev(2, "prompt_enviado", 2),
        _ev(3, "codigo_ejecutado", 3),
    ]
    ct = ct_features(events)
    assert 0.0 <= ct["ct_summary"] <= 1.0


def test_ct_es_determinista() -> None:
    """Mismos eventos → misma ct_summary."""
    events = [
        _ev(0, "prompt_enviado", 0),
        _ev(1, "codigo_ejecutado", 2),
        _ev(2, "prompt_enviado", 4),
    ]
    f1 = ct_features(events)
    f2 = ct_features(events)
    assert f1["ct_summary"] == f2["ct_summary"]


def test_ventana_cuenta_prompts_y_ejecuciones() -> None:
    events = [
        _ev(0, "prompt_enviado", 0),
        _ev(1, "codigo_ejecutado", 1),
        _ev(2, "prompt_enviado", 2),
        _ev(3, "anotacion_creada", 3),
    ]
    w = compute_windows(events)[0]
    assert w.prompt_count == 2
    assert w.execution_count == 1
    assert w.reflection_count == 1
