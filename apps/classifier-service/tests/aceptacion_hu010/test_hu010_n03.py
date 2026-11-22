"""Aceptacion HU-010, N03 (orquestador, agregada el 22/11 al verificar la
construccion; el constructor no la modifica).

La excepcion de "poco trabajo" para quien resuelve de una vale SOLO cuando el
ultimo Probar paso todo: es lo unico que compara contra lo esperado. Una sola
ejecucion que imprime algo sin error (por ejemplo `print("hola")` en el
ejercicio de Celsius) no prueba que resolvio.

N03  Un solo Ejecutar limpio, sin Probar y con pocas ediciones, sigue siendo
     poco trabajo: `autonomo_desenganchado` sin tutor, `desenganchado` con tutor.
"""

from __future__ import annotations

from classifier_service.services.subgrupo import clasificar_subgrupo


def _ev(seq: int, tipo: str, payload: dict | None = None) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-22T10:{seq:02d}:00Z",
        "payload": payload or {},
    }


def _ejecutar_limpio(seq: int) -> dict:
    return _ev(
        seq,
        "codigo_ejecutado",
        {
            "code": "print('hola')",
            "stdout": "hola\n",
            "stderr": "",
            "duration_ms": 5,
            "runtime": "pyodide",
        },
    )


def _edicion(seq: int) -> dict:
    return _ev(seq, "edicion_codigo", {"snapshot": "print('hola')", "origin": "student_typed"})


def test_n03_sin_tutor_un_ejecutar_limpio_no_es_resolver() -> None:
    ev = [_ev(1, "episodio_abierto"), _ev(2, "lectura_enunciado"), _edicion(3), _ejecutar_limpio(4)]
    assert clasificar_subgrupo(ev).key == "autonomo_desenganchado"


def test_n03_con_tutor_un_ejecutar_limpio_no_es_resolver() -> None:
    ev = [
        _ev(1, "episodio_abierto"),
        _ev(2, "prompt_enviado", {"content": "x", "prompt_kind": "aclaracion_enunciado"}),
        _edicion(3),
        _ejecutar_limpio(4),
    ]
    assert clasificar_subgrupo(ev).key == "desenganchado"
