"""BUG-10: `GET /entregas/{id}/calificacion` filtraba por alumno, no por comision.

Ultimo endpoint del leak. Igual que `get_entrega`, solo llamaba a
`_assert_can_read`: un docente podia leer la NOTA y el feedback del alumno de
otra comision.

El guard va ANTES del lookup de la calificacion, no despues. Si fuera despues,
el docente ajeno distinguiria por el DETALLE del 404 si la entrega ajena tiene
nota puesta o no ("Entrega no existe" contra "No hay calificacion para la
entrega {id}") — un oraculo sobre el avance de correccion de otra comision. Es
el mismo criterio que aplica
`test_el_rechazo_no_cambia_aunque_el_estado_no_sea_calificable`.

Consumidores auditados: en web-teacher solo `GradingFormView` lo llama, con el
`entrega_id` que viene de la lista ya filtrada por comision. El web-student lo
llama con el id de su propia entrega (rama de estudiante, intacta). Ambos
clientes tratan el 404 como `null`, y el rechazo por comision ajena es tambien
un 404 — o sea que la UI no cambia de comportamiento, y ese 404 solo lo puede
ver un docente fuera de su comision, que hoy no tiene forma de llegar ahi.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

# ── PoC del leak ──────────────────────────────────────────────────────────


async def test_docente_ajeno_no_puede_leer_la_nota(scope_setup: dict) -> None:
    """GET /calificacion sobre una entrega de otra comision → rechazo (era 200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_el_rechazo_no_filtra_la_nota(scope_setup: dict) -> None:
    """El cuerpo del rechazo no puede traer la nota del alumno ajeno.

    La entrega ajena esta calificada con 5.00 en la fixture.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)
    assert "nota_final" not in resp.text


async def test_el_rechazo_no_delata_si_la_entrega_ajena_tiene_nota(scope_setup: dict) -> None:
    """Con y sin calificacion, el docente ajeno ve la MISMA respuesta.

    Con el guard despues del lookup, `ajena_graded` (con nota) daria el rechazo
    por comision y `ajena_submitted` (sin nota) daria el 404 de "no hay
    calificacion para la entrega {id}" — mismo status, DETALLE distinto, y ahi
    esta el oraculo sobre el avance de correccion de otra comision. Por eso se
    comparan los dos bodies enteros y no solo el status.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        con_nota = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            headers=scope_setup["docente"],
        )
        sin_nota = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_submitted']}/calificacion",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](con_nota)
    scope_setup["rechazo_ajeno"](sin_nota)
    assert con_nota.json() == sin_nota.json()


async def test_docente_sin_ninguna_comision_no_lee_la_nota(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no lee notas en ningun lado."""
    huerfano = scope_setup["headers"](uuid.uuid4(), "docente")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_returned']}/calificacion",
            headers=huerfano,
        )
    scope_setup["rechazo_ajeno"](resp)


# ── El guard no rompe a ningun consumidor legitimo ────────────────────────


async def test_docente_propio_si_puede_leer_la_nota(scope_setup: dict) -> None:
    """El camino real del web-teacher al precargar el form de correccion."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_returned']}/calificacion",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 200, resp.text
    assert float(resp.json()["nota_final"]) == 5.0


async def test_docente_propio_sin_nota_sigue_dando_404(scope_setup: dict) -> None:
    """Regresion: el 404 de "todavia no hay nota" sigue siendo el suyo.

    Los clientes (web-teacher y web-student) traducen ese 404 a `null` para
    mostrar el form vacio. Si el guard lo pisara, romperia la primera
    correccion de toda entrega.

    El DETALLE es lo que hace el test: desde que el rechazo por comision
    tambien es 404, comparar solo el status dejaria pasar un guard que rechaza
    al docente propio. Los dos 404 se distinguen unicamente por el body.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}/calificacion",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == (
        f"No hay calificacion para la entrega {scope_setup['propia_submitted']}"
    ), resp.text


async def test_alumno_sigue_leyendo_su_nota(scope_setup: dict) -> None:
    """Regresion: el web-student lee la nota de su propia entrega."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_returned']}/calificacion",
            headers=scope_setup["alumno_de"]("propia_returned"),
        )
    assert resp.status_code == 200, resp.text


async def test_alumno_ajeno_sigue_bloqueado(scope_setup: dict) -> None:
    """`_assert_can_read` sigue vivo: un alumno no lee la nota de otro."""
    otro_alumno = scope_setup["headers"](uuid.uuid4(), "estudiante")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_returned']}/calificacion",
            headers=otro_alumno,
        )
    assert resp.status_code == 403, resp.text


async def test_oversight_puede_leer_cualquier_nota(scope_setup: dict) -> None:
    """Coordinacion (`docente_admin`) conserva la vista cross-comision."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            headers=scope_setup["admin"],
        )
    assert resp.status_code == 200, resp.text
