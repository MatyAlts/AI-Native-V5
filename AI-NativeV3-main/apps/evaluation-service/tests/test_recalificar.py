"""Test de integracion del PATCH /entregas/{id}/calificacion (NB-4).

Cubre el bug NB-4: antes no habia forma de corregir una nota ya puesta
(no existia PATCH y el UNIQUE(entrega_id) bloqueaba insertar una segunda
calificacion). El PATCH actualiza la fila existente in-place.

Pega contra el Postgres local (academic_main) como superuser `postgres`
(bypasa RLS). Si la DB no esta disponible o no hay seed para las FKs de
`entregas` (tareas_practicas / comisiones), el test se skippea.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from evaluation_service.auth import get_db
from evaluation_service.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get(
    "EVAL_TEST_DB_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main",
)

DOCENTE_ID = uuid.uuid4()
DOCENTE_HEADERS = {
    "X-User-Id": str(DOCENTE_ID),
    "X-User-Email": "docente@test.local",
    "X-User-Roles": "docente",
}


async def _fetch_fk_triple(engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None:
    """Busca un (tenant_id, tarea_practica_id, comision_id) valido del seed."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT tp.tenant_id, tp.id, c.id "
                    "FROM tareas_practicas tp "
                    "JOIN comisiones c ON c.tenant_id = tp.tenant_id "
                    "LIMIT 1"
                )
            )
        ).first()
    if row is None:
        return None
    return (row[0], row[1], row[2])


@pytest.fixture
async def recalificar_setup() -> AsyncIterator[dict]:
    """Crea una entrega + calificacion (nota 5.00) y overridea get_db.

    Limpia la entrega/calificacion creadas al final. Skippea si no hay DB
    o no hay seed para las FKs.
    """
    engine = create_async_engine(DB_URL)
    try:
        triple = await _fetch_fk_triple(engine)
    except Exception as exc:  # DB no disponible
        await engine.dispose()
        pytest.skip(f"Postgres local no disponible: {exc}")

    if triple is None:
        await engine.dispose()
        pytest.skip("Sin seed de tareas_practicas/comisiones para las FKs")

    tenant_id, tarea_id, comision_id = triple
    student_id = uuid.uuid4()
    entrega_id = uuid.uuid4()
    calificacion_id = uuid.uuid4()

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Seed: entrega submitted + calificacion (nota 5.00)
    async with factory() as s:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        await s.execute(
            text(
                "INSERT INTO entregas (id, tenant_id, tarea_practica_id, "
                "student_pseudonym, comision_id, estado, ejercicio_estados) "
                "VALUES (:id, :t, :tp, :st, :c, 'submitted', '[]'::jsonb)"
            ),
            {
                "id": str(entrega_id),
                "t": str(tenant_id),
                "tp": str(tarea_id),
                "st": str(student_id),
                "c": str(comision_id),
            },
        )
        await s.execute(
            text(
                "INSERT INTO calificaciones (id, tenant_id, entrega_id, "
                "graded_by, nota_final, detalle_criterios) "
                "VALUES (:id, :t, :e, :g, 5.00, '[]'::jsonb)"
            ),
            {
                "id": str(calificacion_id),
                "t": str(tenant_id),
                "e": str(entrega_id),
                "g": str(uuid.uuid4()),
            },
        )
        await s.commit()

    # Override get_db: sesion superuser con el tenant seteado (bypasa RLS).
    async def _override_get_db() -> AsyncIterator:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    DOCENTE_HEADERS["X-Tenant-Id"] = str(tenant_id)

    try:
        yield {"entrega_id": entrega_id, "tenant_id": tenant_id}
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with factory() as s:
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            await s.execute(
                text("DELETE FROM calificaciones WHERE entrega_id = :e"),
                {"e": str(entrega_id)},
            )
            await s.execute(
                text("DELETE FROM entregas WHERE id = :e"),
                {"e": str(entrega_id)},
            )
            await s.commit()
        await engine.dispose()


async def test_recalificar_actualiza_nota_in_place(recalificar_setup: dict) -> None:
    """PATCH re-califica in-place: 200 con la nota nueva, sin violar el UNIQUE."""
    entrega_id = recalificar_setup["entrega_id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{entrega_id}/calificacion",
            json={"nota_final": 9.5, "feedback_general": "Corregido: mejor de lo evaluado"},
            headers=DOCENTE_HEADERS,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nota_final"] == 9.5
    assert body["feedback_general"] == "Corregido: mejor de lo evaluado"
    assert body["graded_by"] == str(DOCENTE_ID)
    assert body["updated_at"] is not None


async def test_recalificar_sin_calificacion_previa_404(
    recalificar_setup: dict,
) -> None:
    """PATCH sobre una entrega sin calificacion → 404 (usar POST /calificar)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/entregas/{uuid.uuid4()}/calificacion",
            json={"nota_final": 7.0},
            headers=DOCENTE_HEADERS,
        )
    assert resp.status_code == 404
