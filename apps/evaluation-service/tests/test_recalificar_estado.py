"""BUG-10 (defecto secundario): recalificar no debe pisar el estado 'returned'.

`PATCH /entregas/{id}/calificacion` normalizaba el estado a `graded` de forma
incondicional para cubrir el caso NB-4 (entrega re-enviada que quedo en
`submitted` con la calificacion vieja adherida). Pero `submit_entrega` solo
acepta `draft` y `returned`: si el docente corregia un typo en la nota de una
entrega ya devuelta, esa entrega pasaba a `graded` y el alumno que iba a
re-entregar recibia `409 No se puede enviar una entrega en estado 'graded'`.

Los dos primeros tests son el PoC del bloqueo; el tercero es la anti-regresion
de la normalizacion NB-4, que sigue viva para `submitted`.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

CAL_BODY = {"nota_final": 8.0, "feedback_general": "ok", "detalle_criterios": []}


async def test_recalificar_conserva_returned(scope_setup: dict) -> None:
    """Corregir la nota de una entrega devuelta NO la vuelve 'graded'."""
    entrega_id = scope_setup["propia_returned"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{entrega_id}/calificacion",
            json={"nota_final": 7.25},
            headers=scope_setup["docente"],
        )
        assert resp.status_code == 200, resp.text
        assert float(resp.json()["nota_final"]) == 7.25

        detalle = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["docente"])
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["estado"] == "returned"


async def test_recalificar_returned_deja_re_entregar_al_alumno(scope_setup: dict) -> None:
    """Cierre del loop: tras la re-calificacion el alumno todavia puede enviar.

    Este es el sintoma que le pega al usuario final — sin el fix, el submit
    devuelve 409 y la re-entrega queda trabada.
    """
    entrega_id = scope_setup["propia_returned"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/api/v1/entregas/{entrega_id}/calificacion",
            json={"nota_final": 7.25},
            headers=scope_setup["docente"],
        )
        detalle = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["docente"])
        alumno = scope_setup["headers"](
            uuid.UUID(detalle.json()["student_pseudonym"]), "estudiante"
        )
        resp = await client.post(f"/api/v1/entregas/{entrega_id}/submit", headers=alumno)

    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "submitted"


async def test_recalificar_sigue_normalizando_submitted_a_graded(scope_setup: dict) -> None:
    """Anti-regresion NB-4: sobre 'submitted' la normalizacion sigue aplicando.

    Recorre el ciclo real (calificar -> devolver -> el alumno re-entrega) para
    llegar a una entrega en `submitted` con la calificacion vieja adherida, que
    es exactamente el caso que NB-4 vino a normalizar.
    """
    entrega_id = scope_setup["propia_submitted"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/entregas/{entrega_id}/calificar",
            json=CAL_BODY,
            headers=scope_setup["docente"],
        )
        await client.post(f"/api/v1/entregas/{entrega_id}/return", headers=scope_setup["docente"])
        detalle = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["docente"])
        alumno = scope_setup["headers"](
            uuid.UUID(detalle.json()["student_pseudonym"]), "estudiante"
        )
        reenvio = await client.post(f"/api/v1/entregas/{entrega_id}/submit", headers=alumno)
        assert reenvio.json()["estado"] == "submitted", reenvio.text

        resp = await client.patch(
            f"/api/v1/entregas/{entrega_id}/calificacion",
            json={"nota_final": 9.0},
            headers=scope_setup["docente"],
        )
        assert resp.status_code == 200, resp.text
        detalle = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["docente"])
    assert detalle.json()["estado"] == "graded"
