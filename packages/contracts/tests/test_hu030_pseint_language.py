"""Aceptacion HU-030 (orquestador, antes de construir; el constructor no la
modifica). Criterios acordados con Juani el 24/11/2026.

C01  PSeInt es un lenguaje del contrato: un ejercicio y una TP lo aceptan.
N01  Python sigue siendo el default y un lenguaje desconocido sigue siendo 422.
"""

from __future__ import annotations

import typing

import pytest
from platform_contracts.academic import DEFAULT_LANGUAGE, EjercicioCreate
from platform_contracts.academic.ejercicio import Language
from pydantic import ValidationError


def _ejercicio(**extra) -> dict:
    base = {
        "titulo": "Doble de un numero",
        "enunciado_md": "Lee un numero y escribi el doble.",
        "unidad_tematica": "secuenciales",
    }
    return {**base, **extra}


def test_c01_pseint_esta_en_el_literal() -> None:
    assert set(typing.get_args(Language)) == {"python", "java", "pseint"}


def test_c01_un_ejercicio_pseint_es_valido() -> None:
    ej = EjercicioCreate(**_ejercicio(language="pseint"))
    assert ej.language == "pseint"


def test_n01_python_sigue_siendo_el_default() -> None:
    assert DEFAULT_LANGUAGE == "python"
    assert EjercicioCreate(**_ejercicio()).language == "python"


def test_n01_un_lenguaje_desconocido_sigue_rechazado() -> None:
    with pytest.raises(ValidationError):
        EjercicioCreate(**_ejercicio(language="cobol"))
