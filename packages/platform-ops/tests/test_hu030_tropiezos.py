"""Aceptacion HU-030 (orquestador, antes de construir; el constructor no la
modifica).

N03  Los errores de PSeInt no se cuentan como tropiezos de Python: un
     episodio PSeInt no tiene tropiezos (igual que Java, N06 de su historia),
     porque el regex de excepciones de Python los leeria como "OtroError".
"""

from __future__ import annotations

from platform_ops.tropiezos import tipo_de_error, tropiezos_de_episodio


def test_n03_un_error_pseint_no_es_tropiezo() -> None:
    stderr = "Linea 4: division por cero."
    assert tipo_de_error(stderr, "Algoritmo a\nFinAlgoritmo\n", language="pseint") is None


def test_n03_un_episodio_pseint_no_tiene_tropiezos() -> None:
    eventos = [
        {"seq": 1, "event_type": "codigo_ejecutado", "payload": {"stderr": "Linea 4: division por cero."}},
        {"seq": 2, "event_type": "codigo_ejecutado", "payload": {"stderr": "Linea 4: division por cero."}},
        {"seq": 3, "event_type": "codigo_ejecutado", "payload": {"stderr": ""}},
    ]
    assert tropiezos_de_episodio(eventos, language="pseint") == []


def test_n01_python_sigue_teniendo_tropiezos() -> None:
    assert tipo_de_error("Traceback...\nZeroDivisionError: division by zero", "", language="python") == (
        "ZeroDivisionError"
    )
