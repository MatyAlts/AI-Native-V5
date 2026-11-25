"""Aceptacion HU-038 (orquestador, antes de arreglar; el constructor no la
modifica). Bug que encontro Juani el 25/11 (previo: esta en `main`).

Al abrir un ejercicio, el tutor exigia que el de `orden - 1` estuviera
completado (`tutor_core.py`, chequeo del ejercicio anterior). Con un TP de
ordenes 1, 2, 3, 101, ... el 101 pedia "completa el ejercicio 100", que no
existe: aunque el frontend lo dejara abrir, el servidor respondia 422.

Contrato:
  - Funcion pura `ejercicio_anterior_completado(ejercicio_orden, estados) ->
    bool` en `tutor_service/services/orden_ejercicios.py`. `estados` es la
    lista `ejercicio_estados` de la entrega (dicts con `orden` y `completado`).
    Devuelve True si todos los ejercicios QUE EXISTEN con orden menor estan
    completados (sin anteriores, True).
  - El chequeo de `tutor_core.py` la usa en lugar de `ejercicio_orden - 1`, y
    el mensaje de error nombra el orden real del ejercicio que falta.

N13  Con huecos, el siguiente que existe se puede abrir.
N14  Si un anterior que existe no esta completo, no se puede abrir.
C13  Sin huecos, igual que antes.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _estados(completos: set[int]) -> list[dict]:
    return [{"orden": o, "completado": o in completos} for o in (1, 2, 3, 101, 102, 110)]


def test_n13_el_101_se_abre_con_1_2_y_3_completos() -> None:
    from tutor_service.services.orden_ejercicios import ejercicio_anterior_completado

    assert ejercicio_anterior_completado(101, _estados({1, 2, 3})) is True


def test_n14_el_102_no_se_abre_sin_el_101() -> None:
    from tutor_service.services.orden_ejercicios import ejercicio_anterior_completado

    assert ejercicio_anterior_completado(102, _estados({1, 2, 3})) is False


def test_n14_el_101_no_se_abre_si_falta_el_2() -> None:
    from tutor_service.services.orden_ejercicios import ejercicio_anterior_completado

    assert ejercicio_anterior_completado(101, _estados({1, 3})) is False


def test_n13_el_primero_que_existe_siempre_se_abre() -> None:
    from tutor_service.services.orden_ejercicios import ejercicio_anterior_completado

    assert ejercicio_anterior_completado(1, _estados(set())) is True
    assert ejercicio_anterior_completado(5, [{"orden": 5, "completado": False}]) is True


def test_c13_sin_huecos_igual_que_antes() -> None:
    from tutor_service.services.orden_ejercicios import ejercicio_anterior_completado

    seguidos = [{"orden": o, "completado": o == 1} for o in (1, 2, 3)]
    assert ejercicio_anterior_completado(2, seguidos) is True
    assert ejercicio_anterior_completado(3, seguidos) is False


def test_el_chequeo_del_tutor_usa_la_regla_nueva() -> None:
    fuente = (RAIZ / "src/tutor_service/services/tutor_core.py").read_text(encoding="utf-8")
    assert "ejercicio_anterior_completado(" in fuente
    assert "prev_orden = ejercicio_orden - 1" not in fuente
