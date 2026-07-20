"""Test end-to-end de `new_version()` contra un Postgres real.

Reproduce y blinda el bug **MissingGreenlet** (PLAN A5): `new_version()`
clonaba la composición de ejercicios iterando la relación lazy
`parent.tp_ejercicios`. `parent` viene de `repo.get_or_404` sin eager-load,
así que ese acceso disparaba IO implícito fuera del contexto greenlet del
driver asyncpg → `sqlalchemy.exc.MissingGreenlet`.

Los tests mock-based (`test_tareas_practicas_crud.py`) NO cubren esto: un
`MagicMock(spec=TareaPractica).tp_ejercicios` devuelve un iterable vacío sin
tocar la DB, así que la lazy-load nunca se ejercita. Este test corre el flujo
real (crear TP → componer un ejercicio → publish → new_version) sobre una
`AsyncSession` real, forzando el boundary de request con `expire_all()` para
que la relación quede unloaded al versionar.

Requiere Docker (testcontainers). Se skippea con el marker `integration`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import (
    Base,
    Carrera,
    Comision,
    Ejercicio,
    Facultad,
    Materia,
    Periodo,
    PlanEstudios,
    TareaPractica,
    TpEjercicio,
    Universidad,
)
from academic_service.schemas.tarea_practica import (
    TareaPracticaCreate,
    TareaPracticaUpdate,
)
from academic_service.services.tarea_practica_service import TareaPracticaService
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def session(pg_container):
    dsn = pg_container.get_connection_url().replace("+psycopg2", "+asyncpg")
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        # Los defaults `uuid_generate_v4()` de los uuid_pk exigen uuid-ossp.
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(Base.metadata.create_all)
    # expire_on_commit=False para que el plumbing del test (leer ids de las
    # entidades sembradas tras un commit) no dispare lazy-loads propios. La
    # condición que reproduce el bug (relación `tp_ejercicios` unloaded al
    # versionar) se fuerza explícitamente con `session.expire_all()` antes de
    # llamar a new_version — no depende de este flag.
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            yield s
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _seed_hierarchy(session, tenant_id, created_by):
    """Siembra la jerarquía mínima (universidad → … → comisión) + un ejercicio
    reusable. Devuelve `(comision, ejercicio)`."""
    uni = Universidad(
        id=uuid4(),
        tenant_id=tenant_id,
        nombre="UTN",
        codigo=f"UTN-{uuid4().hex[:6]}",
        keycloak_realm=str(tenant_id),
    )
    fac = Facultad(
        id=uuid4(), tenant_id=tenant_id, universidad_id=uni.id, nombre="FRM", codigo="FRM"
    )
    car = Carrera(
        id=uuid4(),
        tenant_id=tenant_id,
        universidad_id=uni.id,
        facultad_id=fac.id,
        nombre="Ing. en Sistemas",
        codigo="ISI",
    )
    plan = PlanEstudios(
        id=uuid4(), tenant_id=tenant_id, carrera_id=car.id, version="2023", año_inicio=2023
    )
    mat = Materia(
        id=uuid4(), tenant_id=tenant_id, plan_id=plan.id, nombre="Programación 1", codigo="P1"
    )
    per = Periodo(
        id=uuid4(),
        tenant_id=tenant_id,
        codigo="2026S1",
        nombre="2026 - Cuatri 1",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 7, 1),
    )
    com = Comision(
        id=uuid4(),
        tenant_id=tenant_id,
        materia_id=mat.id,
        periodo_id=per.id,
        codigo="A-MANANA",
        nombre="A Mañana",
    )
    ej = Ejercicio(
        id=uuid4(),
        tenant_id=tenant_id,
        titulo="Suma de dos números",
        enunciado_md="Escribí una función que sume dos números.",
        unidad_tematica="secuenciales",
        created_by=created_by,
    )
    session.add_all([uni, fac, car, plan, mat, per, com, ej])
    await session.commit()
    return com, ej


async def test_new_version_end_to_end_no_missing_greenlet(session) -> None:
    """crear TP → componer ejercicio → publish → new_version, sin MissingGreenlet.

    Verifica además el invariante de versionado inmutable: la nueva versión
    clona la composición y linkea por `parent_tarea_id`; el TP original queda
    intacto (mismo estado, título y ejercicios).
    """
    tenant_id = uuid4()
    user = User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="docente@utn.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm=str(tenant_id),
    )

    comision, ejercicio = await _seed_hierarchy(session, tenant_id, user.id)
    # Capturamos los ids en locals: el `expire_all()` de más abajo expira
    # también estas entidades, y releerlas dispararía lazy-load.
    comision_id = comision.id
    ejercicio_id = ejercicio.id

    svc = TareaPracticaService(session)

    # 1) crear TP (draft)
    tp = await svc.create(
        TareaPracticaCreate(
            comision_id=comision_id,
            codigo="TP1",
            titulo="Trabajo Práctico 1",
            enunciado="Resolver los ejercicios de la unidad.",
            peso=Decimal("1.0"),
        ),
        user,
    )
    parent_id = tp.id
    await session.commit()

    # 2) componer un ejercicio en la TP (tabla intermedia tp_ejercicios)
    session.add(
        TpEjercicio(
            id=uuid4(),
            tenant_id=tenant_id,
            tarea_practica_id=parent_id,
            ejercicio_id=ejercicio_id,
            orden=1,
            peso_en_tp=Decimal("1.0"),
        )
    )
    await session.commit()

    # 3) publish
    await svc.publish(parent_id, user)
    await session.commit()

    # Boundary de request: expira la identity map. `parent.tp_ejercicios`
    # queda unloaded → sin el fix, iterarlo dispara MissingGreenlet.
    session.expire_all()

    # 4) new_version — el path que rompía
    new_tp = await svc.new_version(
        parent_id, TareaPracticaUpdate(titulo="Trabajo Práctico 1 (v2)"), user
    )
    await session.commit()

    # ── Versionado correcto ────────────────────────────────────────────
    assert new_tp.id != parent_id
    assert new_tp.version == 2
    assert new_tp.parent_tarea_id == parent_id
    assert new_tp.estado == "draft"
    assert new_tp.titulo == "Trabajo Práctico 1 (v2)"
    assert new_tp.comision_id == comision_id

    # ── La composición se clonó al nuevo TP ────────────────────────────
    clones = (
        (
            await session.execute(
                select(TpEjercicio).where(TpEjercicio.tarea_practica_id == new_tp.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(clones) == 1
    assert clones[0].ejercicio_id == ejercicio_id
    assert clones[0].orden == 1
    assert clones[0].peso_en_tp == Decimal("1.0")

    # ── Invariante inmutable: el original NO se mutó ───────────────────
    original = (
        await session.execute(select(TareaPractica).where(TareaPractica.id == parent_id))
    ).scalar_one()
    assert original.estado == "published"
    assert original.titulo == "Trabajo Práctico 1"
    assert original.version == 1
    assert original.parent_tarea_id is None

    original_ejs = (
        (
            await session.execute(
                select(TpEjercicio).where(TpEjercicio.tarea_practica_id == parent_id)
            )
        )
        .scalars()
        .all()
    )
    # el ejercicio del original sigue ahí (se clonó, no se movió)
    assert len(original_ejs) == 1
    assert original_ejs[0].id != clones[0].id
