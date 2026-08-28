"""BUG-10: `GET /entregas/{id}` filtraba por alumno, no por comision.

`get_entrega` solo llamaba a `_assert_can_read`, que frena al ESTUDIANTE sobre
entregas ajenas pero para cualquier rol docente devuelve sin mirar la comision.
Un docente podia leer el detalle de la entrega de un alumno de otra comision
con solo tener el `entrega_id`.

Por que se cierra recien ahora: se audito el frontend antes de tocarlo. En
web-teacher el unico consumidor es `GradingFormView` (CorreccionesView), y el
`entrega_id` sale siempre de `entregasDocenteApi.list({comision_id})` — la
lista que YA filtra por `usuarios_comision`. No hay deep link ni parametro de
URL con `entrega_id`; web-admin no llama este endpoint; el tutor-service usa el
LIST impersonando al alumno. O sea: ningun consumidor legitimo lo usa
cross-comision, y coordinacion (`docente_admin`/`superadmin`) queda exenta por
`OVERSIGHT_ROLES`.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

# ── PoC del leak ──────────────────────────────────────────────────────────


async def test_docente_ajeno_no_puede_leer_entrega(scope_setup: dict) -> None:
    """GET /{id} sobre una entrega de otra comision → rechazo (era 200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_submitted']}",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_el_rechazo_no_filtra_el_student_pseudonym(scope_setup: dict) -> None:
    """El cuerpo del rechazo no puede traer datos del alumno ajeno.

    Lo que se filtraba no era solo el estado: el 200 devolvia
    `student_pseudonym`, `tarea_practica_id` y `comision_id` de un alumno de
    otra comision.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)
    assert "student_pseudonym" not in resp.text
    assert str(scope_setup["comision_ajena"]) not in resp.text


async def test_docente_sin_ninguna_comision_no_lee(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no lee en ningun lado."""
    huerfano = scope_setup["headers"](uuid.uuid4(), "docente")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}", headers=huerfano
        )
    scope_setup["rechazo_ajeno"](resp)


# ── El guard no rompe a ningun consumidor legitimo ────────────────────────


async def test_docente_propio_si_puede_leer(scope_setup: dict) -> None:
    """El camino real del web-teacher: la entrega viene de su propia cola."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["comision_id"] == str(scope_setup["comision_propia"])


async def test_alumno_sigue_leyendo_su_entrega(scope_setup: dict) -> None:
    """Regresion: el alumno no esta en `usuarios_comision` y debe seguir leyendo."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_draft']}",
            headers=scope_setup["alumno_de"]("propia_draft"),
        )
    assert resp.status_code == 200, resp.text


async def test_alumno_ajeno_sigue_bloqueado(scope_setup: dict) -> None:
    """`_assert_can_read` sigue vivo: un alumno no lee la entrega de otro."""
    otro_alumno = scope_setup["headers"](uuid.uuid4(), "estudiante")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_draft']}", headers=otro_alumno
        )
    assert resp.status_code == 403, resp.text


async def test_oversight_puede_leer_cualquier_comision(scope_setup: dict) -> None:
    """Coordinacion (`docente_admin`) conserva la vista cross-comision."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_submitted']}", headers=scope_setup["admin"]
        )
    assert resp.status_code == 200, resp.text
