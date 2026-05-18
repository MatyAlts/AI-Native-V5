"""Tests de Coherencia Código-Discurso."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from classifier_service.services.ccd import compute_ccd


def _ev(seq: int, event_type: str, sec_offset: int, payload: dict | None = None) -> dict:
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": (base + timedelta(seconds=sec_offset)).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


def test_sin_eventos_devuelve_neutral() -> None:
    r = compute_ccd([])
    assert r["insufficient_data"] is True


def test_accion_seguida_de_reflexion_alinea() -> None:
    """Un prompt seguido de anotación en <2min es una alineación."""
    events = [
        _ev(0, "prompt_enviado", 0, {"content": "pregunta", "prompt_kind": "solicitud_directa"}),
        _ev(1, "anotacion_creada", 30, {"content": "ahora entiendo"}),
    ]
    r = compute_ccd(events)
    assert r["pairs"] == 1
    assert r["aligned"] == 1
    assert r["orphans"] == 0
    assert r["ccd_orphan_ratio"] == 0.0
    assert r["ccd_mean"] > 0.5  # gap pequeño = alta coherencia


def test_accion_sin_reflexion_es_huerfana() -> None:
    """Ejecución sin verbalización posterior cuenta como huérfana."""
    events = [
        _ev(0, "codigo_ejecutado", 0),
    ]
    r = compute_ccd(events)
    assert r["orphans"] == 1
    assert r["ccd_orphan_ratio"] == 1.0


def test_orphan_ratio_mixto() -> None:
    """2 acciones fuera de ventana + 1 acción con reflexión → orphan 2/3."""
    events = [
        _ev(0, "codigo_ejecutado", 0),  # huérfana (la reflexión a 200s está fuera)
        _ev(1, "codigo_ejecutado", 30),  # huérfana
        _ev(2, "codigo_ejecutado", 500),  # acción con reflexión cercana
        _ev(3, "anotacion_creada", 520),  # 20s tras la 3° acción
    ]
    r = compute_ccd(events)
    assert r["pairs"] == 3
    # La reflexión a 520s sólo alinea con la acción a 500s.
    # Las acciones a 0s y 30s tienen la reflexión a >2min → huérfanas.
    assert r["orphans"] == 2
    assert abs(r["ccd_orphan_ratio"] - 2 / 3) < 1e-6


def test_reflection_fuera_de_ventana_no_alinea() -> None:
    """Reflexión >2min después de la acción no cuenta."""
    events = [
        _ev(0, "codigo_ejecutado", 0),
        _ev(1, "anotacion_creada", 200),  # 3min 20s después
    ]
    r = compute_ccd(events)
    assert r["orphans"] == 1


def test_prompt_reflexion_cuenta_como_verbalizacion() -> None:
    """Un prompt con kind='reflexion' actúa como verbalización."""
    events = [
        _ev(0, "codigo_ejecutado", 0),
        _ev(1, "prompt_enviado", 30, {"prompt_kind": "reflexion", "content": "pensé que..."}),
    ]
    r = compute_ccd(events)
    assert r["aligned"] == 1
    assert r["orphans"] == 0


def test_prompt_solicitud_directa_es_accion() -> None:
    """Un prompt con kind='solicitud_directa' sin reflexión posterior es huérfano."""
    events = [
        _ev(
            0,
            "prompt_enviado",
            0,
            {"prompt_kind": "solicitud_directa", "content": "dame la respuesta"},
        ),
    ]
    r = compute_ccd(events)
    assert r["orphans"] == 1
