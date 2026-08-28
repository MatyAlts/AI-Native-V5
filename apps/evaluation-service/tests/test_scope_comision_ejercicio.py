"""BUG-10: `PATCH /entregas/{id}/ejercicio/{orden}` tampoco validaba la comision.

Mismo agujero que `submit`: solo `_assert_can_write`, que para cualquier rol
docente devuelve sin mirar la comision. Un docente ajeno podia escribir en el
`ejercicio_estados` de una entrega que no es de su comision — marcando o
des-marcando ejercicios del alumno de otro.

Este es ademas el endpoint de la reapertura docente del 2026-06-19
(`completado: false` para que el alumno retome un ejercicio), asi que el abuso
tiene una forma util: des-marcarle ejercicios a un alumno ajeno lo deja sin
poder entregar, porque `submit_entrega` exige todos los ejercicios completados.

Igual que en `submit`, el caller puede ser el ALUMNO: el guard de comision se
aplica solo cuando es docente.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

MARCAR = {"completado": True, "orden": 1}
DESMARCAR = {"completado": False}


# ── PoC del leak ──────────────────────────────────────────────────────────


async def test_docente_ajeno_no_puede_marcar_ejercicio(scope_setup: dict) -> None:
    """PATCH /ejercicio sobre una entrega de otra comision → rechazo (era 200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['ajena_returned']}/ejercicio/1",
            json=MARCAR,
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_docente_ajeno_no_escribe_ejercicio_estados(scope_setup: dict) -> None:
    """El rechazo protege el dato: `ejercicio_estados` de la ajena queda vacio.

    Sin el guard el PATCH devolvia 200 con el estado ya escrito adentro.
    """
    entrega_id = scope_setup["ajena_returned"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/api/v1/entregas/{entrega_id}/ejercicio/1",
            json=MARCAR,
            headers=scope_setup["docente"],
        )
        resp = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["ejercicio_estados"] == []


async def test_docente_ajeno_no_puede_desmarcar_ejercicio(scope_setup: dict) -> None:
    """Tampoco puede usar la reapertura docente contra una comision ajena.

    Des-marcar ejercicios de un alumno ajeno lo deja sin poder entregar:
    `submit_entrega` rechaza con 422 si queda alguno incompleto.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['ajena_returned']}/ejercicio/1",
            json=DESMARCAR,
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_docente_sin_ninguna_comision_no_puede_marcar(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no escribe en ningun lado."""
    huerfano = scope_setup["headers"](uuid.uuid4(), "docente")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['propia_draft']}/ejercicio/1",
            json=MARCAR,
            headers=huerfano,
        )
    scope_setup["rechazo_ajeno"](resp)


# ── El guard NO puede romper al alumno ni al docente propio ───────────────


async def test_alumno_sigue_pudiendo_marcar_su_ejercicio(scope_setup: dict) -> None:
    """Regresion critica: es el flujo normal del alumno al cerrar un ejercicio.

    Si el guard se aplicara a todos los callers, ningun alumno podria volver a
    marcar un ejercicio como completado.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['propia_draft']}/ejercicio/1",
            json=MARCAR,
            headers=scope_setup["alumno_de"]("propia_draft"),
        )
    assert resp.status_code == 200, resp.text
    estados = resp.json()["ejercicio_estados"]
    assert len(estados) == 1
    assert estados[0]["completado"] is True


async def test_alumno_ajeno_sigue_bloqueado(scope_setup: dict) -> None:
    """`_assert_can_write` sigue vivo: un alumno no toca la entrega de otro."""
    otro_alumno = scope_setup["headers"](uuid.uuid4(), "estudiante")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['propia_draft']}/ejercicio/1",
            json=MARCAR,
            headers=otro_alumno,
        )
    assert resp.status_code == 403, resp.text


async def test_docente_propio_conserva_la_reapertura(scope_setup: dict) -> None:
    """La reapertura docente (2026-06-19) NO se rechaza en su propia comision.

    Solo se afirma la autorizacion (200, no rechazo) — que es lo que este guard
    gobierna. El efecto del des-marcado NO se puede afirmar todavia: hay un bug
    pre-existente e independiente por el cual toda actualizacion in-place de un
    ejercicio YA existente se pierde (solo persiste el `append` de uno nuevo).
    `estados = list(...)` es una copia superficial, asi que mutar `est[...]`
    tambien muta el valor cargado en el atributo: SQLAlchemy no ve cambio neto,
    no emite UPDATE, y el `db.refresh(entrega)` de despues devuelve la fila
    vieja. Verificado contra Postgres real el 2026-08-27; reportado aparte.
    """
    entrega_id = scope_setup["propia_draft"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        marcado = await client.patch(
            f"/api/v1/entregas/{entrega_id}/ejercicio/1",
            json=MARCAR,
            headers=scope_setup["alumno_de"]("propia_draft"),
        )
        assert marcado.status_code == 200, marcado.text

        resp = await client.patch(
            f"/api/v1/entregas/{entrega_id}/ejercicio/1",
            json=DESMARCAR,
            headers=scope_setup["docente"],
        )
    assert resp.status_code == 200, resp.text


async def test_oversight_puede_marcar_cualquier_comision(scope_setup: dict) -> None:
    """`docente_admin` sigue siendo oversight del tenant."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{scope_setup['ajena_returned']}/ejercicio/1",
            json=MARCAR,
            headers=scope_setup["admin"],
        )
    assert resp.status_code == 200, resp.text
