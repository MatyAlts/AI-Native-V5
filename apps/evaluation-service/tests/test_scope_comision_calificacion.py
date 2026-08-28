"""BUG-10: las escrituras de correccion deben respetar el scope de comision.

`list_entregas` filtra la cola de correccion por `usuarios_comision`
(entregas.py) porque en prod todos los docentes comparten un tenant fijo y la
RLS por tenant NO los separa. Los endpoints de escritura (`POST /calificar`,
`PATCH /calificacion`, `POST /return`) chequeaban solo el permiso por rol: con
un `entrega_id` en la mano — que ni es secreto, viaja en las URLs del
web-teacher — un docente podia calificar, recalificar y devolver entregas de
una comision ajena.

Los tres `test_docente_ajeno_*` son el PoC: revirtiendo el guard vuelven a dar
201/200 en vez del rechazo.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

CAL_BODY = {"nota_final": 8.0, "feedback_general": "ok", "detalle_criterios": []}


# ── PoC del leak: el docente ajeno NO puede escribir ──────────────────────


async def test_docente_ajeno_no_puede_calificar(scope_setup: dict) -> None:
    """POST /calificar sobre una entrega de otra comision → rechazo (era 201)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_submitted']}/calificar",
            json=CAL_BODY,
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_docente_ajeno_no_puede_recalificar(scope_setup: dict) -> None:
    """PATCH /calificacion sobre una entrega de otra comision → rechazo (era 200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            json={"nota_final": 1.0},
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_docente_ajeno_no_puede_devolver(scope_setup: dict) -> None:
    """POST /return sobre una entrega de otra comision → rechazo (era 200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/return",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_rechazo_no_dejo_efectos_en_la_comision_ajena(scope_setup: dict) -> None:
    """El rechazo corta ANTES de escribir: la entrega ajena sigue en 'submitted'.

    Sin este assert, un guard puesto despues del `flush` pasaria igual los
    tests de status code mientras la escritura ya ocurrio.
    """
    entrega_id = scope_setup["ajena_submitted"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/entregas/{entrega_id}/calificar",
            json=CAL_BODY,
            headers=scope_setup["docente"],
        )
        resp = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "submitted"


async def test_el_rechazo_no_cambia_aunque_el_estado_no_sea_calificable(scope_setup: dict) -> None:
    """La autorizacion corre ANTES de la logica de negocio.

    `ajena_graded` no esta en 'submitted', asi que el chequeo de estado daria
    422. Si el guard quedara despues, el docente ajeno distinguiria por el
    status code en que estado esta una entrega que no deberia ni ver.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificar",
            json=CAL_BODY,
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


# ── El guard no rompe el flujo legitimo ───────────────────────────────────


async def test_docente_propio_si_puede_calificar(scope_setup: dict) -> None:
    """El docente asignado a la comision califica normalmente → 201."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}/calificar",
            json=CAL_BODY,
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 201, resp.text
    assert float(resp.json()["nota_final"]) == 8.0


async def test_docente_propio_si_puede_devolver(scope_setup: dict) -> None:
    """El docente asignado devuelve su propia entrega → 200 y queda 'returned'."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}/calificar",
            json=CAL_BODY,
            headers=scope_setup["docente"],
        )
        assert resp.status_code == 201, resp.text
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}/return",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "returned"


async def test_oversight_puede_calificar_cualquier_comision(scope_setup: dict) -> None:
    """`docente_admin` es oversight del tenant: escribe fuera de su comision.

    Mismo bypass que aplica `list_entregas` (is_oversight), sin el cual el
    guard le sacaria a coordinacion la correccion cross-comision.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_submitted']}/calificar",
            json=CAL_BODY,
            headers=scope_setup["admin"],
        )
    assert resp.status_code == 201, resp.text


async def test_docente_sin_ninguna_comision_no_califica(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no escribe en ningun lado.

    Cierra el caso borde del `IN ()` vacio que `list_entregas` resuelve
    devolviendo la lista vacia: aca tiene que rechazar, no dar un pase libre.
    """
    huerfano = scope_setup["headers"](uuid.uuid4(), "docente")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}/calificar",
            json=CAL_BODY,
            headers=huerfano,
        )
    scope_setup["rechazo_ajeno"](resp)
