"""HU-009 (tree_version v4.2.0): Probar cuenta como ejecución en el subgrupo.

Apoyo de la aceptación (`tests/aceptacion_hu009`): fija los bordes que ella no
cubre. Probar pasa todo y después un Ejecutar sin datos de entrada termina con
error de `input()`; un Probar sin casos; y que el conteo de CII llegue a
`features` y al armado de la respuesta.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from classifier_service.routes.classify_ep import _salida
from classifier_service.services.pipeline import classify_episode_from_events
from classifier_service.services.subgrupo import _resolvio, clasificar_subgrupo


def _ev(seq: int, tipo: str, payload: dict | None = None) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-20T10:{seq:02d}:00Z",
        "payload": payload or {},
    }


def _probar(seq: int, total: int, passed: int) -> dict:
    return _ev(
        seq,
        "tests_ejecutados",
        {
            "test_count_total": total,
            "test_count_passed": passed,
            "test_count_failed": total - passed,
        },
    )


def _ediciones(desde: int, n: int) -> list[dict]:
    return [
        _ev(desde + i, "edicion_codigo", {"snapshot": f"x = {i}", "origin": "student_typed"})
        for i in range(n)
    ]


def test_probar_que_pasa_todo_resuelve_aunque_despues_ejecutar_falle() -> None:
    ev = [
        _probar(1, 2, 2),
        _ev(2, "codigo_ejecutado", {"stdout": "", "stderr": "EOFError: EOF when reading a line"}),
    ]
    assert _resolvio(ev) is True


def test_probar_sin_casos_no_resuelve() -> None:
    assert _resolvio([_probar(1, 0, 0)]) is False


def test_cuenta_el_ultimo_probar_no_alguno() -> None:
    assert _resolvio([_probar(1, 2, 2), _probar(2, 2, 1)]) is False


def test_solo_probar_que_falla_es_trabado_y_no_escribe_sin_validar() -> None:
    # Probó dos veces: validó, aunque no le salió. Antes del bump no contaba y
    # salía `autonomo_desenganchado`.
    ev = [_ev(0, "episodio_abierto"), *_ediciones(1, 4), _probar(5, 2, 1), _probar(6, 2, 1)]
    assert clasificar_subgrupo(ev).key == "autonomo_trabado"


def test_features_lleva_las_iteraciones_de_cii() -> None:
    ev = [
        _ev(0, "episodio_abierto"),
        _ev(1, "prompt_enviado", {"content": "hola", "prompt_kind": "x"}),
        _ev(2, "tutor_respondio", {"content": "r"}),
        _ev(3, "prompt_enviado", {"content": "chau", "prompt_kind": "x"}),
        _ev(4, "episodio_cerrado"),
    ]
    assert classify_episode_from_events(ev).features["cii"] == {"iterations": 2}


def _fila(features: dict) -> SimpleNamespace:
    return SimpleNamespace(
        episode_id=uuid4(),
        comision_id=uuid4(),
        classifier_config_hash="h",
        appropriation="apropiacion_superficial",
        appropriation_reason="x",
        ct_summary=None,
        ccd_mean=None,
        ccd_orphan_ratio=None,
        cii_stability=None,
        cii_evolution=None,
        is_current=True,
        features=features,
    )


def test_salida_expone_cii_iteraciones() -> None:
    assert _salida(_fila({"cii": {"iterations": 4}})).cii_iteraciones == 4


def test_clasificacion_vieja_sin_el_dato_da_none() -> None:
    assert _salida(_fila({"subgrupo": None})).cii_iteraciones is None
