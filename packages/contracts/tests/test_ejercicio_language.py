"""Lenguaje del ejercicio y tipo de test case por lenguaje.

El banco del piloto es integramente Python (169 ejercicios), asi que el default
del contrato tiene que preservar esa semantica sin pedir backfill.
"""

from __future__ import annotations

import pytest
from platform_contracts.academic import (
    DEFAULT_LANGUAGE,
    EjercicioCreate,
    EjercicioUpdate,
    TestCaseSchema,
)
from pydantic import ValidationError


def _ejercicio(**extra) -> dict:
    base = {
        "titulo": "Suma de dos numeros",
        "enunciado_md": "Escribi un programa que sume dos numeros.",
        "unidad_tematica": "secuenciales",
    }
    return {**base, **extra}


# ─── Default y valores admitidos ────────────────────────────────────


def test_default_es_python() -> None:
    """Sin declarar lenguaje, el ejercicio es Python — como todo el banco actual."""
    ej = EjercicioCreate(**_ejercicio())
    assert ej.language == "python"
    assert ej.language == DEFAULT_LANGUAGE


def test_java_es_valido() -> None:
    ej = EjercicioCreate(**_ejercicio(language="java"))
    assert ej.language == "java"


def test_lenguaje_no_soportado_rechazado() -> None:
    with pytest.raises(ValidationError):
        EjercicioCreate(**_ejercicio(language="cobol"))


def test_update_parcial_sin_lenguaje_no_lo_pisa() -> None:
    """PATCH sin `language` deja el campo intacto, no lo vuelve al default."""
    upd = EjercicioUpdate(titulo="Titulo nuevo")
    assert upd.language is None
    assert "language" not in upd.model_dump(exclude_unset=True)


def test_update_puede_cambiar_el_lenguaje() -> None:
    upd = EjercicioUpdate(language="java")
    assert upd.model_dump(exclude_unset=True) == {"language": "java"}


# ─── Tipos de test case ─────────────────────────────────────────────


def _test_case(tipo: str) -> dict:
    return {
        "id": "tc1",
        "name": "caso basico",
        "type": tipo,
        "code": "assert True",
        "weight": 1.0,
    }


@pytest.mark.parametrize("tipo", ["stdin_stdout", "pytest_assert", "junit_assert"])
def test_tipos_de_test_case_admitidos(tipo: str) -> None:
    assert TestCaseSchema(**_test_case(tipo)).type == tipo


def test_tipo_de_test_case_inexistente_rechazado() -> None:
    with pytest.raises(ValidationError):
        TestCaseSchema(**_test_case("mocha_assert"))


def test_ejercicio_java_con_junit_assert() -> None:
    ej = EjercicioCreate(**_ejercicio(language="java", test_cases=[_test_case("junit_assert")]))
    assert ej.test_cases[0].type == "junit_assert"


def test_el_tipo_de_test_case_no_se_valida_contra_el_lenguaje() -> None:
    """A proposito: el test case no conoce a su ejercicio.

    Un `pytest_assert` dentro de un ejercicio Java es incoherente, pero el
    contrato no lo rechaza — validarlo aca obligaria al schema del test case a
    conocer el del ejercicio. La coherencia la garantiza el servicio.
    """
    ej = EjercicioCreate(**_ejercicio(language="java", test_cases=[_test_case("pytest_assert")]))
    assert ej.language == "java"
    assert ej.test_cases[0].type == "pytest_assert"
