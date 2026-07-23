"""Reglas de composicion de una TP y del lenguaje de sus ejercicios.

Cubre `TpEjerciciosValidator` y los dos helpers que lo acompanan
(`validar_tp_no_vacia`, `validar_lenguaje_unico`), que juntos son lo que
`publish()` invoca antes de exponer una TP al alumno.

Contexto de por que estos tests importan: el validator existia desde ADR-047 y
NUNCA se invoco desde ningun servicio. Al medir la base del piloto antes de
engancharlo (2026-07-23) aparecio el motivo — con su regla de pesos original
habria rechazado 25 de las 27 TPs publicadas.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from platform_contracts.academic import (
    TpEjercicioCreate,
    TpEjerciciosValidator,
    validar_lenguaje_unico,
    validar_tp_no_vacia,
)


def _par(orden: int, peso: str = "1.0", ejercicio_id=None) -> TpEjercicioCreate:
    return TpEjercicioCreate(
        ejercicio_id=ejercicio_id or uuid4(),
        orden=orden,
        peso_en_tp=Decimal(peso),
    )


# ─── TpEjerciciosValidator: orden y unicidad ────────────────────────


def test_composicion_valida_pasa() -> None:
    TpEjerciciosValidator(tp_ejercicios=[_par(1), _par(2), _par(3)])


def test_ordenes_duplicados_rechazados() -> None:
    with pytest.raises(ValueError, match="ordenes"):
        TpEjerciciosValidator(tp_ejercicios=[_par(1), _par(1)])


def test_ejercicio_repetido_rechazado() -> None:
    mismo = uuid4()
    with pytest.raises(ValueError, match="dos veces"):
        TpEjerciciosValidator(
            tp_ejercicios=[_par(1, ejercicio_id=mismo), _par(2, ejercicio_id=mismo)]
        )


def test_lista_vacia_no_rompe_el_validator() -> None:
    """El caso vacio es legitimo aca: una TP monolitica no tiene pares.

    Que este validator lo acepte es correcto — quien decide si una TP vacia se
    puede publicar es `validar_tp_no_vacia`, que ademas mira los test cases
    propios.
    """
    TpEjerciciosValidator(tp_ejercicios=[])


# ─── La regla de pesos NO existe (anti-regresion) ───────────────────


def test_pesos_que_no_suman_uno_no_bloquean() -> None:
    """Regla retirada a proposito. Este test existe para que no vuelva sola.

    Las 169 asociaciones del piloto tienen peso 1.0000 cada una, asi que toda TP
    de mas de un ejercicio suma > 1.0. Ningun calculo de calificacion consume el
    campo. Ver el docstring de `TpEjerciciosValidator`.
    """
    TpEjerciciosValidator(tp_ejercicios=[_par(1), _par(2), _par(3)])  # suma 3.0


def test_peso_fraccionario_tampoco_bloquea() -> None:
    """El otro extremo: si alguien SI usa fracciones, tampoco se le exige 1.0."""
    TpEjerciciosValidator(tp_ejercicios=[_par(1, "0.25"), _par(2, "0.25")])  # suma 0.5


# ─── validar_tp_no_vacia ────────────────────────────────────────────


def test_tp_sin_ejercicios_ni_test_cases_rechazada() -> None:
    with pytest.raises(ValueError, match="vacia"):
        validar_tp_no_vacia(cantidad_ejercicios=0, cantidad_test_cases=0)


def test_tp_monolitica_con_test_cases_propios_aceptada() -> None:
    validar_tp_no_vacia(cantidad_ejercicios=0, cantidad_test_cases=3)


def test_tp_con_ejercicios_de_banco_aceptada() -> None:
    validar_tp_no_vacia(cantidad_ejercicios=5, cantidad_test_cases=0)


def test_tp_de_un_solo_ejercicio_aceptada() -> None:
    """Dos TPs del piloto tienen exactamente un ejercicio. No son un error."""
    validar_tp_no_vacia(cantidad_ejercicios=1, cantidad_test_cases=0)


# ─── validar_lenguaje_unico ─────────────────────────────────────────


def test_lenguaje_homogeneo_aceptado() -> None:
    validar_lenguaje_unico(language_tp="java", languages_ejercicios=["java", "java", "java"])


def test_mezcla_de_lenguajes_rechazada() -> None:
    with pytest.raises(ValueError, match="un solo lenguaje"):
        validar_lenguaje_unico(language_tp="python", languages_ejercicios=["python", "java"])


def test_mezcla_nombra_los_dos_lenguajes() -> None:
    """El mensaje tiene que decirle al docente QUE mezclo, no solo que fallo."""
    with pytest.raises(ValueError) as exc:
        validar_lenguaje_unico(language_tp="python", languages_ejercicios=["python", "java"])
    assert "java" in str(exc.value)
    assert "python" in str(exc.value)


def test_ejercicios_que_no_coinciden_con_la_tp_rechazados() -> None:
    with pytest.raises(ValueError, match="declara"):
        validar_lenguaje_unico(language_tp="java", languages_ejercicios=["python"])


def test_tp_sin_ejercicios_no_valida_lenguaje() -> None:
    """Una TP monolitica no tiene ejercicios contra los cuales comparar."""
    validar_lenguaje_unico(language_tp="java", languages_ejercicios=[])


def test_python_sigue_siendo_valido() -> None:
    """Anti-regresion del piloto: las 27 TPs publicadas son Python."""
    validar_lenguaje_unico(language_tp="python", languages_ejercicios=["python"] * 10)
