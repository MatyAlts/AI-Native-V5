"""Fixtures compartidas de los tests de entregas del evaluation-service.

`scope_setup` siembra el escenario minimo de BUG-10: un docente asignado a UNA
comision y entregas en esa comision y en otra ajena. Lo usan los tests del
scope de correccion (`test_scope_comision_calificacion.py`) y los del estado de
la re-calificacion (`test_recalificar_estado.py`).

Pega contra el Postgres local (academic_main) como superuser `postgres`
(bypasa RLS). Los ids academicos (tenant, comisiones, tareas_practicas) salen
del seed real, no se inventan; solo los actores efimeros (docente / alumnos /
entregas) se crean por test y se limpian al final. La membresia del docente se
inserta con la misma forma que emite `scripts/seed-demo-data.py:363`
(`rol='titular'`, `fecha_desde`).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta

import pytest
from evaluation_service.auth import get_db
from evaluation_service.main import app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get(
    "EVAL_TEST_DB_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main",
)

# Docente asignado SOLO a la comision "propia". El leak de BUG-10 era que
# tambien podia escribir sobre la "ajena".
DOCENTE_ID = uuid.UUID("d0ced0ce-0001-0001-0001-000000000001")
# Oversight academico del tenant: escribe en cualquier comision a proposito.
ADMIN_ID = uuid.UUID("d0ced0ce-0002-0002-0002-000000000002")


def build_headers(user_id: uuid.UUID, tenant_id: uuid.UUID, roles: str) -> dict[str, str]:
    """Headers X-* que el api-gateway inyecta a los servicios internos."""
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": f"{user_id}@test.local",
        "X-User-Roles": roles,
    }


async def _fetch_dos_comisiones(engine) -> tuple[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]]:
    """(tenant_id, [(tarea_practica_id, comision_id), ...]) de DOS comisiones del seed."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT DISTINCT ON (tp.comision_id) tp.tenant_id, tp.id, tp.comision_id "
                    "FROM tareas_practicas tp "
                    "WHERE tp.deleted_at IS NULL "
                    "ORDER BY tp.comision_id, tp.id"
                )
            )
        ).all()
    if len(rows) < 2:
        return (uuid.uuid4(), [])
    tenant_id = rows[0][0]
    del_mismo_tenant = [(r[1], r[2]) for r in rows if r[0] == tenant_id]
    return (tenant_id, del_mismo_tenant[:2])


@pytest.fixture
async def scope_setup() -> AsyncIterator[dict]:
    """Docente de la comision A + entregas en A (propia) y B (ajena).

    Entregas creadas (claves del dict devuelto):
      - `propia_submitted`  (comision A, 'submitted', sin calificacion)
      - `propia_returned`   (comision A, 'returned', con calificacion 5.00)
      - `ajena_submitted`   (comision B, 'submitted', sin calificacion)
      - `ajena_graded`      (comision B, 'graded', con calificacion 5.00)

    Ademas: `tenant_id`, `docente` / `admin` (headers listos) y `headers`
    (callable para armar los de un alumno concreto).
    """
    engine = create_async_engine(DB_URL)
    try:
        tenant_id, pares = await _fetch_dos_comisiones(engine)
    except Exception as exc:  # DB no disponible
        await engine.dispose()
        pytest.skip(f"Postgres local no disponible: {exc}")

    if len(pares) < 2:
        await engine.dispose()
        pytest.skip("El seed no tiene tareas_practicas en dos comisiones distintas")

    (tp_propia, comision_propia), (tp_ajena, comision_ajena) = pares
    membresia_id = uuid.uuid4()

    entregas = {
        "propia_submitted": (tp_propia, comision_propia, "submitted", None),
        "propia_returned": (tp_propia, comision_propia, "returned", uuid.uuid4()),
        "ajena_submitted": (tp_ajena, comision_ajena, "submitted", None),
        "ajena_graded": (tp_ajena, comision_ajena, "graded", uuid.uuid4()),
    }
    ids = {k: uuid.uuid4() for k in entregas}

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _set_tenant(s) -> None:
        await s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )

    async with factory() as s:
        await _set_tenant(s)
        # Membresia del docente: SOLO la comision propia.
        await s.execute(
            text(
                "INSERT INTO usuarios_comision "
                "(id, tenant_id, comision_id, user_id, rol, fecha_desde) "
                "VALUES (:id, :t, :c, :u, 'titular', :fd)"
            ),
            {
                "id": str(membresia_id),
                "t": str(tenant_id),
                "c": str(comision_propia),
                "u": str(DOCENTE_ID),
                "fd": date.today() - timedelta(days=60),
            },
        )
        for key, (tp_id, comision_id, estado, cal_id) in entregas.items():
            await s.execute(
                text(
                    "INSERT INTO entregas (id, tenant_id, tarea_practica_id, "
                    "student_pseudonym, comision_id, estado, ejercicio_estados) "
                    "VALUES (:id, :t, :tp, :st, :c, :e, '[]'::jsonb)"
                ),
                {
                    "id": str(ids[key]),
                    "t": str(tenant_id),
                    "tp": str(tp_id),
                    "st": str(uuid.uuid4()),
                    "c": str(comision_id),
                    "e": estado,
                },
            )
            if cal_id is not None:
                await s.execute(
                    text(
                        "INSERT INTO calificaciones (id, tenant_id, entrega_id, "
                        "graded_by, nota_final, detalle_criterios) "
                        "VALUES (:id, :t, :e, :g, 5.00, '[]'::jsonb)"
                    ),
                    {
                        "id": str(cal_id),
                        "t": str(tenant_id),
                        "e": str(ids[key]),
                        "g": str(uuid.uuid4()),
                    },
                )
        await s.commit()

    async def _override_get_db() -> AsyncIterator:
        async with factory() as session:
            await _set_tenant(session)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    try:
        yield {
            "tenant_id": tenant_id,
            "comision_propia": comision_propia,
            "comision_ajena": comision_ajena,
            "docente": build_headers(DOCENTE_ID, tenant_id, "docente"),
            "admin": build_headers(ADMIN_ID, tenant_id, "docente_admin"),
            "headers": lambda uid, roles: build_headers(uid, tenant_id, roles),
            **ids,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with factory() as s:
            await _set_tenant(s)
            for entrega_id in ids.values():
                await s.execute(
                    text("DELETE FROM calificaciones WHERE entrega_id = :e"),
                    {"e": str(entrega_id)},
                )
                await s.execute(text("DELETE FROM entregas WHERE id = :e"), {"e": str(entrega_id)})
            await s.execute(
                text("DELETE FROM usuarios_comision WHERE id = :id"),
                {"id": str(membresia_id)},
            )
            await s.commit()
        await engine.dispose()
