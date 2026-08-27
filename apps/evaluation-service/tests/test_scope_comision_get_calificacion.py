"""BUG-10: `GET /entregas/{id}/calificacion` filtraba por alumno, no por comision.

Ultimo endpoint del leak. Igual que `get_entrega`, solo llamaba a
`_assert_can_read`: un docente podia leer la NOTA y el feedback del alumno de
otra comision.

El guard va ANTES del lookup de la calificacion, no despues. Si fuera despues,
el docente ajeno distinguiria por el status code (403 vs 404) si la entrega
ajena tiene nota puesta o no — un oraculo sobre el avance de correccion de otra
comision. Es el mismo criterio que ya aplica
`test_rechazo_es_403_aunque_el_estado_no_sea_calificable`.

Consumidores auditados: en web-teacher solo `GradingFormView` lo llama, con el
`entrega_id` que viene de la lista ya filtrada por comision. El web-student lo
llama con el id de su propia entrega (rama de estudiante, intacta). Ambos
clientes tratan el 404 como `null`; el 403 nuevo es un error distinto y solo lo
puede ver un docente fuera de su comision, que hoy no tiene forma de llegar
ahi por la UI.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

# ── PoC del leak ──────────────────────────────────────────────────────────


async def test_docente_ajeno_no_puede_leer_la_nota(scope_setup: dict) -> None:
    """GET /calificacion sobre una entrega de otra comision → 403 (era 200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 403, resp.text
    assert "comision" in resp.json()["detail"].lower()


async def test_el_403_no_filtra_la_nota(scope_setup: dict) -> None:
    """El cuerpo del rechazo no puede traer la nota del alumno ajeno.

    La entrega ajena esta calificada con 5.00 en la fixture.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['ajena_graded']}/calificacion",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 403, resp.text
    assert "nota_final" not in resp.text


async def test_403_no_delata_si_la_entrega_ajena_tiene_nota(scope_setup: dict) -> None:
    """Con y sin calificacion, el docente ajeno ve el MISMO 403.

    Si el guard corriera despues del lookup, `ajena_submitted` (sin nota) daria
    404 y `ajena_graded` (con nota) daria 403 — un oraculo sobre el avance de
    correccion de otra comision.
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
    assert con_nota.status_code == 403, con_nota.text
    assert sin_nota.status_code == 403, sin_nota.text


async def test_docente_sin_ninguna_comision_no_lee_la_nota(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no lee notas en ningun lado."""
    huerfano = scope_setup["headers"](uuid.uuid4(), "docente")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_returned']}/calificacion",
            headers=huerfano,
        )
    assert resp.status_code == 403, resp.text


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
    """Regresion: el 404 de "todavia no hay nota" no se convirtio en 403.

    Los clientes (web-teacher y web-student) traducen ese 404 a `null` para
    mostrar el form vacio. Si el guard lo pisara, romperia la primera
    correccion de toda entrega.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/entregas/{scope_setup['propia_submitted']}/calificacion",
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 404, resp.text


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
