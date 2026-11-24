"""Aceptacion HU-030 (orquestador, antes de construir; el constructor no la
modifica).

C01  Una entrega guarda artefactos de PSeInt (antes, 422).
N01  Un lenguaje desconocido sigue siendo 422.
"""

from __future__ import annotations

import pytest
from evaluation_service.schemas.entrega import ArtefactoItem
from pydantic import ValidationError


def test_c01_artefacto_pseint_es_valido() -> None:
    a = ArtefactoItem(orden=1, codigo="Algoritmo a\nFinAlgoritmo\n", language="pseint")
    assert a.language == "pseint"


def test_n01_python_y_java_siguen() -> None:
    assert ArtefactoItem(orden=1, codigo="print(1)").language == "python"
    assert ArtefactoItem(orden=1, codigo="class Main {}", language="java").language == "java"


def test_n01_lenguaje_desconocido_rechazado() -> None:
    with pytest.raises(ValidationError):
        ArtefactoItem(orden=1, codigo="x", language="cobol")
