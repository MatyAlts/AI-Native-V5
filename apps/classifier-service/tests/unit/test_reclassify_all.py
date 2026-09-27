"""`reclassify_all.py::_classify_response` — el conteo del backfill tiene que
distinguir "quedó vigente" de "se registró sin gobernar" (hallazgo de QA,
2026-09-27, ronda 5, punto 3).

`ClassificationOut.is_current` (`routes/classify_ep.py:69`) ya viaja en la
respuesta HTTP de `POST /classify_episode/{id}` — no es un cambio de
contrato, es leer un campo que ya está ahí. Sin esto, `nuevos(201)` en el
resumen final del script confunde dos cosas: una reclasificación que
efectivamente cambió la etiqueta oficial, y una que se registró pero una
anulación humana previa sigue gobernando (bloque 6 va a correr este script
después del bump de `tree_version` — es exactamente el escenario donde ese
número importa).

Función pura, sin HTTP: se prueba sin mockear `httpx.AsyncClient`.
"""

from __future__ import annotations

from classifier_service.reclassify_all import _classify_response


def test_201_con_is_current_true_es_nuevo_vigente() -> None:
    assert _classify_response(201, {"is_current": True}) == "nuevos_vigentes"


def test_201_con_is_current_false_es_nuevo_no_vigente() -> None:
    """El caso que motivó el hallazgo: se insertó una fila nueva (201) pero
    una anulación humana previa sigue siendo la etiqueta oficial."""
    assert _classify_response(201, {"is_current": False}) == "nuevos_no_vigentes"


def test_200_es_sin_cambio_independientemente_de_is_current() -> None:
    assert _classify_response(200, {"is_current": True}) == "sin_cambio"


def test_status_code_de_error_es_error() -> None:
    assert _classify_response(500, {}) == "error"
