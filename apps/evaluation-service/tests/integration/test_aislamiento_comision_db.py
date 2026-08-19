"""El docente sólo opera sobre entregas de SUS comisiones (tarea 6.5).

Existe por un agujero de autorización real: el filtro por comisión estaba en
`GET /entregas` (el listado) y en `GET /{id}/artefacto`, pero NO en los cuatro
endpoints que operan sobre una entrega puntual. `_assert_can_read` sólo cubre
al ESTUDIANTE — deja pasar a cualquier docente sobre cualquier entrega.

O sea que un docente de otra comisión podía:

    GET    /entregas/{id}                 leer la entrega ajena
    POST   /entregas/{id}/calificar       ponerle nota
    PATCH  /entregas/{id}/calificacion    cambiársela
    POST   /entregas/{id}/return          devolvérsela al alumno

El `entrega_id` era la única credencial. Y como el listado SÍ filtraba, el
agujero no se veía navegando la UI: había que llegar con un id en la mano.

**Por qué contra Postgres real y no con la sesión mockeada.** El guard resuelve
la pertenencia con SQL crudo contra `usuarios_comision` (tabla de
academic-service, misma DB). Con una sesión mockeada, `db.execute` devuelve lo
que le digamos: el test pasaría con el guard puesto Y con el guard sacado, que
es exactamente la clase de test vacuo que ya nos mordió cinco veces en este
epic. Acá la fila existe o no existe, y el 404 sale o no sale.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_aislamiento_comision_db.py -v

Sin esa env var se SKIPEAN. Cada test revierte lo que crea.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import (
    calificar_entrega,
    get_entrega,
    get_entrega_artefacto,
    recalificar_entrega,
    return_entrega,
)
from evaluation_service.schemas.entrega import CalificacionCreate, CalificacionUpdate
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real",
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# Se descubren de la base: `entregas` tiene FK a `comisiones`, no se pueden
# inventar UUIDs.
COMISION: UUID


def _docente(uid: UUID) -> User:
    return User(
        id=uid,
        tenant_id=TENANT,
        email="d@utn.edu.ar",
        roles=frozenset({"docente"}),
        realm="utn",
    )


def _superadmin(uid: UUID) -> User:
    return User(
        id=uid,
        tenant_id=TENANT,
        email="admin@utn.edu.ar",
        roles=frozenset({"superadmin"}),
        realm="utn",
    )


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    global COMISION
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(TENANT)},
        )
        com = (
            await session.execute(
                text("SELECT id FROM comisiones WHERE tenant_id = :t LIMIT 1"),
                {"t": str(TENANT)},
            )
        ).scalar_one_or_none()
        if com is None:
            pytest.skip("la base no tiene comisiones sembradas")
        COMISION = com
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _tp(db: AsyncSession) -> UUID:
    tp_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tareas_practicas "
            "(id, tenant_id, comision_id, codigo, titulo, enunciado, created_by, language) "
            "VALUES (:id, :t, :c, :cod, 'Test', 'Test', :u, 'java')"
        ),
        {
            "id": str(tp_id),
            "t": str(TENANT),
            "c": str(COMISION),
            "cod": f"AISL-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
        },
    )
    return tp_id


async def _entrega(db: AsyncSession, estado: str = "submitted") -> Entrega:
    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=await _tp(db),
        student_pseudonym=uuid.uuid4(),
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[],
    )
    db.add(entrega)
    await db.flush()
    return entrega


async def _con_calificacion(db: AsyncSession, entrega: Entrega) -> None:
    """Siembra la calificación de la entrega.

    Sin esto, `recalificar_entrega` devuelve 404 por "no hay calificación" y el
    test pasa con el guard puesto Y con el guard sacado — el 404 correcto por
    el motivo equivocado. Lo detectó la corrida de mutación: era el único de
    los cinco que sobrevivía a matar el guard.
    """
    await db.execute(
        text(
            "INSERT INTO calificaciones (id, tenant_id, entrega_id, nota_final, graded_by) "
            "VALUES (:id, :t, :e, 7.00, :u)"
        ),
        {
            "id": str(uuid.uuid4()),
            "t": str(TENANT),
            "e": str(entrega.id),
            "u": str(uuid.uuid4()),
        },
    )
    await db.flush()


async def _asignar_a_comision(db: AsyncSession, uid: UUID) -> None:
    """Mete al docente en `usuarios_comision` — lo que el guard consulta."""
    await db.execute(
        text(
            "INSERT INTO usuarios_comision "
            "(id, tenant_id, user_id, comision_id, rol, fecha_desde) "
            "VALUES (:id, :t, :u, :c, 'docente', CURRENT_DATE)"
        ),
        {
            "id": str(uuid.uuid4()),
            "t": str(TENANT),
            "u": str(uid),
            "c": str(COMISION),
        },
    )
    await db.flush()


class TestDocenteAjenoNoLlega:
    """El docente que no está en la comisión recibe 404 en los cuatro."""

    async def test_get_entrega(self, db: AsyncSession) -> None:
        entrega = await _entrega(db)
        with pytest.raises(HTTPException) as e:
            await get_entrega(entrega.id, user=_docente(uuid.uuid4()), db=db)
        assert e.value.status_code == 404

    async def test_calificar(self, db: AsyncSession) -> None:
        entrega = await _entrega(db)
        with pytest.raises(HTTPException) as e:
            await calificar_entrega(
                entrega.id,
                CalificacionCreate(nota_final=10),
                user=_docente(uuid.uuid4()),
                db=db,
            )
        assert e.value.status_code == 404

    async def test_recalificar(self, db: AsyncSession) -> None:
        entrega = await _entrega(db, estado="graded")
        await _con_calificacion(db, entrega)  # si no, el 404 sale por otro motivo
        with pytest.raises(HTTPException) as e:
            await recalificar_entrega(
                entrega.id,
                CalificacionUpdate(nota_final=1),
                user=_docente(uuid.uuid4()),
                db=db,
            )
        assert e.value.status_code == 404

    async def test_return(self, db: AsyncSession) -> None:
        entrega = await _entrega(db, estado="graded")
        with pytest.raises(HTTPException) as e:
            await return_entrega(entrega.id, user=_docente(uuid.uuid4()), db=db)
        assert e.value.status_code == 404

    async def test_artefacto_sigue_cerrado(self, db: AsyncSession) -> None:
        """El endpoint que YA tenía el guard no se rompió al centralizarlo."""
        entrega = await _entrega(db)
        with pytest.raises(HTTPException) as e:
            await get_entrega_artefacto(entrega.id, user=_docente(uuid.uuid4()), db=db)
        assert e.value.status_code == 404


class TestElRechazoNoDelataQueLaEntregaExiste:
    def test_404_y_no_403(self, db: AsyncSession) -> None:
        """Un 403 diría 'existe pero no podés'. El id ajeno se volvería un
        oráculo de existencia: probando ids se mapea la base."""
        # Cubierto por los asserts de arriba (todos 404). Este test documenta
        # la decisión para que un refactor futuro no la afloje a 403.

    async def test_entrega_inexistente_da_el_mismo_404(self, db: AsyncSession) -> None:
        """Y el mensaje tiene que ser indistinguible del de una entrega ajena."""
        entrega = await _entrega(db)
        ajeno = _docente(uuid.uuid4())

        with pytest.raises(HTTPException) as e_ajena:
            await get_entrega(entrega.id, user=ajeno, db=db)
        with pytest.raises(HTTPException) as e_inexistente:
            await get_entrega(uuid.uuid4(), user=ajeno, db=db)

        assert e_ajena.value.status_code == e_inexistente.value.status_code == 404
        assert e_ajena.value.detail == e_inexistente.value.detail


class TestQuienSiTienePasoLoConserva:
    async def test_docente_asignado_lee(self, db: AsyncSession) -> None:
        entrega = await _entrega(db)
        docente = _docente(uuid.uuid4())
        await _asignar_a_comision(db, docente.id)

        out = await get_entrega(entrega.id, user=docente, db=db)
        assert out.id == entrega.id

    async def test_superadmin_lee_sin_estar_asignado(self, db: AsyncSession) -> None:
        """Oversight ve todo: es el rol que audita comisiones ajenas."""
        entrega = await _entrega(db)

        out = await get_entrega(entrega.id, user=_superadmin(uuid.uuid4()), db=db)
        assert out.id == entrega.id

    async def test_el_alumno_duenio_lee_lo_suyo(self, db: AsyncSession) -> None:
        """El dueño no pasa por el guard de comisión: su `student_pseudonym`
        ya es un filtro más estrecho."""
        entrega = await _entrega(db)
        alumno = User(
            id=entrega.student_pseudonym,
            tenant_id=TENANT,
            email="a@utn.edu.ar",
            roles=frozenset({"estudiante"}),
            realm="utn",
        )

        out = await get_entrega(entrega.id, user=alumno, db=db)
        assert out.id == entrega.id
