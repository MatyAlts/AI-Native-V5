"""BUG-10: `POST /entregas/{id}/submit` tampoco validaba la comision.

`submit_entrega` solo llamaba a `_assert_can_write`, que frena al ESTUDIANTE
sobre entregas ajenas pero para cualquier rol docente devuelve sin mirar la
comision. Un docente de otra comision podia re-enviar la entrega de un alumno
que no es suyo.

El impacto no es solo "tocar algo ajeno": una entrega en `returned` esta
esperando que el alumno la rehaga. Forzarle el `submit` la saca de `returned` y
le tapa la devolucion del docente que si la corrigio — es la misma perdida de
datos de BUG-1 (re-envio automatico que borra la devolucion), pero disparada a
proposito y contra una comision ajena.

Cuidado al leer estos tests: `submit` lo llama el ALUMNO en el flujo normal, no
solo el docente. El guard de comision se aplica UNICAMENTE cuando el caller es
docente; el alumno sigue gobernado por la propiedad de su entrega
(`_assert_can_write`), que es su scope correcto — los alumnos no viven en
`usuarios_comision`, viven en `inscripciones`.

Escenario y limpieza: ver la fixture `scope_setup` en `conftest.py`.
"""

from __future__ import annotations

import uuid

from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient

# ── PoC del leak ──────────────────────────────────────────────────────────


async def test_docente_ajeno_no_puede_re_enviar_entrega(scope_setup: dict) -> None:
    """POST /submit sobre una entrega 'returned' de otra comision → rechazo."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_returned']}/submit",
            headers=scope_setup["docente"],
        )
    scope_setup["rechazo_ajeno"](resp)


async def test_docente_ajeno_no_borra_la_devolucion(scope_setup: dict) -> None:
    """El rechazo protege el dato: la entrega ajena sigue en 'returned'.

    Este es el sintoma que importa. Sin el guard el `submit` la dejaba en
    'submitted' y el alumno perdia la devolucion que tenia pendiente de rehacer.
    """
    entrega_id = scope_setup["ajena_returned"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(f"/api/v1/entregas/{entrega_id}/submit", headers=scope_setup["docente"])
        resp = await client.get(f"/api/v1/entregas/{entrega_id}", headers=scope_setup["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "returned"


async def test_docente_ajeno_no_puede_re_enviar_draft(scope_setup: dict) -> None:
    """Tampoco puede empujar a `submitted` un borrador ajeno a medio hacer."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_submitted']}/submit",
            headers=scope_setup["docente"],
        )
    # Rechazo, NO el 200 idempotente de "ya estaba en submitted": la autorizacion
    # corre antes que cualquier atajo por estado.
    scope_setup["rechazo_ajeno"](resp)


async def test_docente_sin_ninguna_comision_no_puede_re_enviar(scope_setup: dict) -> None:
    """Un docente sin filas en `usuarios_comision` no re-envia en ningun lado."""
    huerfano = scope_setup["headers"](uuid.uuid4(), "docente")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['propia_returned']}/submit", headers=huerfano
        )
    scope_setup["rechazo_ajeno"](resp)


# ── El guard NO puede romper al alumno ni al docente propio ───────────────


async def test_alumno_sigue_pudiendo_enviar_su_draft(scope_setup: dict) -> None:
    """Regresion critica: el alumno no esta en `usuarios_comision`.

    Si el guard se aplicara a todos los callers, el flujo normal de entrega
    moriria para TODOS los alumnos de la plataforma.
    """
    entrega_id = scope_setup["propia_draft"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{entrega_id}/submit",
            headers=scope_setup["alumno_de"]("propia_draft"),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "submitted"


async def test_alumno_sigue_pudiendo_re_enviar_lo_devuelto(scope_setup: dict) -> None:
    """El alumno de una entrega 'returned' la rehace y la re-envia."""
    entrega_id = scope_setup["propia_returned"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{entrega_id}/submit",
            headers=scope_setup["alumno_de"]("propia_returned"),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "submitted"


async def test_alumno_ajeno_sigue_bloqueado(scope_setup: dict) -> None:
    """`_assert_can_write` sigue vivo: un alumno no envia la entrega de otro."""
    otro_alumno = scope_setup["headers"](uuid.uuid4(), "estudiante")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['propia_draft']}/submit", headers=otro_alumno
        )
    assert resp.status_code == 403, resp.text


async def test_docente_propio_si_puede_re_enviar(scope_setup: dict) -> None:
    """El docente asignado conserva el re-envio (reapertura docente 2026-06-19)."""
    entrega_id = scope_setup["propia_returned"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{entrega_id}/submit", headers=scope_setup["docente"]
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "submitted"


async def test_oversight_puede_re_enviar_cualquier_comision(scope_setup: dict) -> None:
    """`docente_admin` sigue siendo oversight del tenant."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/entregas/{scope_setup['ajena_returned']}/submit",
            headers=scope_setup["admin"],
        )
    assert resp.status_code == 200, resp.text
