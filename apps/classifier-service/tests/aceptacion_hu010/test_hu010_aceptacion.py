"""Aceptacion HU-010 (orquestador, antes de construir; el constructor no la
modifica).

Sale de la prueba como alumno en produccion del 21/11/2026 (TP SEC2027, ej2):
el alumno escribio la solucion de una, toco Probar una sola vez, paso todo, y
el cierre le dijo "Quedo a mitad de camino" (`desenganchado`). La regla de
"poco trabajo" pide 2 ejecuciones o 10 ediciones y no mira si resolvio.

C01  Con tutor, sin pedir la solucion, ultimo Probar que pasa todo, una sola
     edicion y un solo Probar: NO sale `desenganchado`; sale un colaborador.
C02  Sin tutor, mismo caso: sale `autonomo_competente`.
C04  Cambia una regla del arbol: `tree_version` sube a v4.3.0 y el hash del
     classifier cambia (las clasificaciones nuevas llevan otra marca).
N01  Sin un Probar que pase todo, el que trabajo poco sigue siendo
     `desenganchado` (con tutor) o `autonomo_desenganchado` (sin tutor).
N02  El que le pide la solucion al tutor sigue saliendo `dependiente_delegador`
     aunque despues Probar pase todo.
"""

from __future__ import annotations

from classifier_service.routes import health
from classifier_service.services.pipeline import compute_classifier_config_hash
from classifier_service.services.subgrupo import clasificar_subgrupo


def _ev(seq: int, tipo: str, payload: dict | None = None) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-21T10:{seq:02d}:00Z",
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


def _prompt(seq: int, kind: str) -> dict:
    return _ev(seq, "prompt_enviado", {"content": "x", "prompt_kind": kind})


def _edicion(seq: int) -> dict:
    return _ev(seq, "edicion_codigo", {"snapshot": "print('hola')", "origin": "student_typed"})


def _de_una_con_tutor(passed: int) -> list[dict]:
    # Como el ej2 del 21/11: abre, pregunta dos veces, escribe de una, Probar una vez.
    return [
        _ev(1, "episodio_abierto"),
        _prompt(2, "aclaracion_enunciado"),
        _prompt(3, "aclaracion_enunciado"),
        _edicion(4),
        _probar(5, 1, passed),
    ]


def _de_una_sin_tutor(passed: int) -> list[dict]:
    return [
        _ev(1, "episodio_abierto"),
        _ev(2, "lectura_enunciado"),
        _edicion(3),
        _probar(4, 2, passed),
    ]


def test_c01_con_tutor_resuelve_de_una_no_es_desenganchado() -> None:
    sg = clasificar_subgrupo(_de_una_con_tutor(passed=1))
    assert sg.key != "desenganchado"
    assert sg.key in {"colaborador_funcional", "colaborador_reflexivo"}


def test_c02_sin_tutor_resuelve_de_una_es_autonomo_competente() -> None:
    assert clasificar_subgrupo(_de_una_sin_tutor(passed=2)).key == "autonomo_competente"


def test_n01_con_tutor_sin_resolver_sigue_desenganchado() -> None:
    assert clasificar_subgrupo(_de_una_con_tutor(passed=0)).key == "desenganchado"


def test_n01_sin_tutor_sin_resolver_sigue_autonomo_desenganchado() -> None:
    assert clasificar_subgrupo(_de_una_sin_tutor(passed=1)).key == "autonomo_desenganchado"


def test_n01_sin_probar_sigue_desenganchado() -> None:
    ev = [_ev(1, "episodio_abierto"), _prompt(2, "aclaracion_enunciado"), _edicion(3), _edicion(4)]
    assert clasificar_subgrupo(ev).key == "desenganchado"


def test_n02_el_que_pide_la_solucion_sigue_delegador() -> None:
    ev = [
        _ev(1, "episodio_abierto"),
        _prompt(2, "solicitud_directa"),
        _prompt(3, "solicitud_directa"),
        _edicion(4),
        _probar(5, 1, 1),
    ]
    assert clasificar_subgrupo(ev).key == "dependiente_delegador"


def test_c04_tree_version_sube_y_cambia_el_hash() -> None:
    assert health._TREE_VERSION == "v4.3.0"
    perfil = health.DEFAULT_REFERENCE_PROFILE
    assert compute_classifier_config_hash(perfil) == compute_classifier_config_hash(
        perfil, "v4.3.0"
    )
    assert compute_classifier_config_hash(perfil, "v4.3.0") != compute_classifier_config_hash(
        perfil, "v4.2.0"
    )
