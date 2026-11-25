"""Apoyo HU-038 (constructor): el 422 del tutor nombra el orden REAL del primer
ejercicio anterior sin completar, no `ejercicio_orden - 1`."""

from __future__ import annotations

from tutor_service.services.orden_ejercicios import primer_anterior_sin_completar


def _estados(completos: set[int]) -> list[dict]:
    return [{"orden": o, "completado": o in completos} for o in (1, 2, 3, 101, 102, 110)]


def test_nombra_el_primer_anterior_que_existe_sin_completar() -> None:
    assert primer_anterior_sin_completar(110, _estados({1, 2, 3, 102})) == 101
    assert primer_anterior_sin_completar(101, _estados({1, 3})) == 2


def test_sin_anteriores_pendientes_es_none() -> None:
    assert primer_anterior_sin_completar(101, _estados({1, 2, 3})) is None
    assert primer_anterior_sin_completar(1, _estados(set())) is None


def test_ignora_entradas_sin_orden() -> None:
    assert (
        primer_anterior_sin_completar(3, [{"completado": False}, {"orden": 1, "completado": True}])
        is None
    )
