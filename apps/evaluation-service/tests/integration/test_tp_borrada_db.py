"""No se entrega ni se califica sobre un trabajo practico BORRADO.

`tareas_practicas` tiene `deleted_at` (soft-delete, `SoftDeleteMixin` del
academic-service) y NADIE del lado de entregas lo miraba. `_comision_de_la_tp`
—el guard que decide si la TP es "visible"— hacía
`SELECT comision_id FROM tareas_practicas WHERE id = :tp` a secas, así que una
TP borrada seguía devolviendo su comisión y el ciclo entero pasaba:

    1. `_comision_de_la_tp` sobre una TP con `deleted_at` seteado -> la devuelve
    2. `create_entrega` -> CREADA, con `ejercicio_estados` sembrados desde la
       TP muerta
    3. `mark_ejercicio_completado` -> OK
    4. `submit_entrega` -> OK, estado `submitted`
    5. `calificar_entrega` -> OK, nota 10.0

Y como `list_entregas` filtra `estado != "draft"`, la entrega aparece en la
**cola de corrección del docente**: le pone nota a un TP que él mismo borró.

**Por qué no alcanzaba con arreglar `_comision_de_la_tp`.** Es la puerta de
entrada de UN endpoint (`create_entrega`). Los otros tres —`submit`,
`mark_ejercicio_completado`, `calificar`— ni siquiera pasan por ahí: arrancan
en `_get_or_404(entrega_id)`, que filtra `Entrega.deleted_at` pero nunca mira
la TP. Y el camino realista **no necesita el bug de la puerta**: el alumno que
ya tenía su entrega abierta cuando el docente borró la TP puede enviarla igual.
`TareaPracticaService.soft_delete` tiene un `# DEFERRED` explícito y cero
guards, así que del otro lado tampoco hay nada.

Matiz que corrige una pista vieja: el vecino `_assert_tp_de_mi_comision` de
`activeia.py` SÍ filtra `deleted_at`, pero de `usuarios_comision` — no de
`tareas_practicas`. Nadie filtraba el de la TP.

**Contra Postgres real y no con la sesión mockeada**, por el mismo motivo que
`test_entrega_comision_de_la_tp_db.py`: el guard es SQL crudo sobre una tabla
de otro servicio. Con `db.execute` mockeado el test pasa con el filtro puesto
Y sacado.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest \
        apps/evaluation-service/tests/integration/test_tp_borrada_db.py -v

Sin esa env var se SKIPEAN. Cada test revierte lo que crea.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import (
    _comision_de_la_tp,
    calificar_entrega,
    create_entrega,
    mark_ejercicio_completado,
    submit_entrega,
)
from evaluation_service.schemas.entrega import (
    CalificacionCreate,
    EntregaCreate,
    EntregaSubmitBody,
    MarkEjercicioBody,
)
from fastapi import HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real",
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

COMISION: UUID


def _alumno(uid: UUID) -> User:
    return User(
        id=uid,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


def _docente() -> User:
    # `docente_admin` entra en `_OVERSIGHT_ROLES`, así que `_assert_comision_visible`
    # lo deja pasar sin necesitar una fila en `usuarios_comision`. Lo que estos
    # tests miden es el guard de la TP borrada, no el de comisión.
    return User(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        email="d@utn.edu.ar",
        roles=frozenset({"docente_admin"}),
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
                text("SELECT id FROM comisiones WHERE tenant_id = :t ORDER BY id LIMIT 1"),
                {"t": str(TENANT)},
            )
        ).scalar_one_or_none()
        if com is None:
            pytest.skip("la base necesita al menos una comision sembrada")
        COMISION = com
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _tp(db: AsyncSession, *, borrada: bool = False) -> UUID:
    """Siembra una TP monolítica (sin `tp_ejercicios`), opcionalmente borrada.

    `language` va omitida a propósito — mismo criterio que el archivo vecino:
    la columna tiene `server_default`, así que nombrarla rompe contra una base
    sin la migración `20260723_0001`.
    """
    tp_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tareas_practicas "
            "(id, tenant_id, comision_id, codigo, titulo, enunciado, created_by, deleted_at) "
            "VALUES (:id, :t, :c, :cod, 'Test', 'Test', :u, :d)"
        ),
        {
            "id": str(tp_id),
            "t": str(TENANT),
            "c": str(COMISION),
            "cod": f"DEL-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
            # `datetime` y no un ISO string: asyncpg tipa el bind por el
            # `timestamptz` de la columna y rechaza el str con `DataError`.
            "d": datetime(2026, 8, 27, 10, 0, tzinfo=UTC) if borrada else None,
        },
    )
    return tp_id


async def _borrar(db: AsyncSession, tp: UUID) -> None:
    """El soft-delete tal cual lo hace `TareaPracticaService.soft_delete`."""
    await db.execute(
        text("UPDATE tareas_practicas SET deleted_at = now() WHERE id = :tp"),
        {"tp": str(tp)},
    )


async def _entrega_en_curso(db: AsyncSession, *, tp: UUID, alumno: UUID) -> Entrega:
    """El caso REALISTA: la entrega ya existía cuando el docente borró la TP.

    No necesita el agujero de `_comision_de_la_tp` — la entrega se creó cuando
    la TP estaba viva. Es el camino por el que el docente termina calificando
    algo que ya no existe.
    """
    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tp,
        student_pseudonym=alumno,
        comision_id=COMISION,
        estado="draft",
        ejercicio_estados=[],
    )
    db.add(entrega)
    await db.flush()
    return entrega


async def _crear(db: AsyncSession, *, tp: UUID, alumno: UUID):
    response = Response()
    response.status_code = None  # type: ignore[assignment]
    return await create_entrega(
        EntregaCreate(tarea_practica_id=tp, comision_id=COMISION),
        response,
        user=_alumno(alumno),
        db=db,
    )


# ── La puerta de entrada ──────────────────────────────────────────────────


class TestElLectorNoVeLaTPBorrada:
    async def test_comision_de_la_tp_borrada_es_none(self, db: AsyncSession) -> None:
        """La mitad de abajo del guard: una TP borrada no es visible.

        `None` es el mismo valor que ya devuelve para una TP inexistente, así
        que el caller la trata igual y contesta 422 "Trabajo practico no
        existe" — sin distinguir borrada de inexistente, que además evita el
        oráculo.
        """
        tp = await _tp(db, borrada=True)
        assert await _comision_de_la_tp(db, tp) is None

    async def test_la_tp_viva_se_sigue_viendo(self, db: AsyncSession) -> None:
        """La otra mitad: un filtro que devuelva siempre `None` pasaría el de
        arriba y rompería todas las entregas del piloto."""
        tp = await _tp(db)
        assert await _comision_de_la_tp(db, tp) == COMISION

    async def test_create_entrega_sobre_tp_borrada_es_422(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        tp = await _tp(db, borrada=True)
        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=tp, alumno=alumno)
        assert e.value.status_code == 422
        assert e.value.detail == "Trabajo practico no existe"

        cuantas = (
            await db.execute(
                text("SELECT count(*) FROM entregas WHERE tarea_practica_id = :tp"),
                {"tp": str(tp)},
            )
        ).scalar_one()
        assert cuantas == 0, "el 422 salió pero la entrega ya estaba escrita"


# ── El resto del ciclo, que no pasa por la puerta ─────────────────────────


class TestElCicloEnteroSobreUnaTPBorrada:
    """El camino realista: la entrega estaba abierta cuando borraron la TP.

    Estos tres endpoints arrancan en `_get_or_404(entrega_id)` y nunca tocan
    `_comision_de_la_tp`. Arreglar sólo la puerta de entrada los dejaba
    abiertos, y son justo los que llegan hasta la nota.
    """

    async def test_mark_ejercicio_completado_es_409(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega_en_curso(db, tp=tp, alumno=alumno)
        await _borrar(db, tp)

        with pytest.raises(HTTPException) as e:
            await mark_ejercicio_completado(
                entrega.id,
                1,
                MarkEjercicioBody(completado=True),
                user=_alumno(alumno),
                db=db,
            )
        assert e.value.status_code == 409

    async def test_submit_entrega_es_409(self, db: AsyncSession) -> None:
        """El que más duele: sin esto la entrega entra a la cola de corrección.

        `list_entregas` filtra `estado != "draft"`, así que un `submitted`
        sobre una TP borrada le aparece al docente como trabajo pendiente.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega_en_curso(db, tp=tp, alumno=alumno)
        await _borrar(db, tp)

        with pytest.raises(HTTPException) as e:
            await submit_entrega(
                entrega.id,
                EntregaSubmitBody(artefactos=[]),
                user=_alumno(alumno),
                db=db,
            )
        assert e.value.status_code == 409

        estado = (
            await db.execute(
                text("SELECT estado FROM entregas WHERE id = :e"), {"e": str(entrega.id)}
            )
        ).scalar_one()
        assert estado == "draft", "la entrega pasó a submitted igual"

    async def test_calificar_entrega_es_409(self, db: AsyncSession) -> None:
        """Poner nota a un TP que no existe.

        La entrega llega a `submitted` con la TP viva; el docente la borra
        después y califica. Sin el guard salía 201 con la calificación
        persistida.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega_en_curso(db, tp=tp, alumno=alumno)
        entrega.estado = "submitted"
        await db.flush()
        await _borrar(db, tp)

        with pytest.raises(HTTPException) as e:
            await calificar_entrega(
                entrega.id,
                CalificacionCreate(nota_final=Decimal("10.00"), detalle_criterios=[]),
                user=_docente(),
                db=db,
            )
        assert e.value.status_code == 409

        cuantas = (
            await db.execute(
                text("SELECT count(*) FROM calificaciones WHERE entrega_id = :e"),
                {"e": str(entrega.id)},
            )
        ).scalar_one()
        assert cuantas == 0, "quedó una calificación colgada de un TP borrado"


# ── Controles: el camino legítimo sigue funcionando ───────────────────────


class TestLaTPVivaSigueFuncionando:
    """Sin esto, un guard que rechace siempre pasaría todos los de arriba y
    rompería el piloto entero."""

    async def test_el_ciclo_completo_sobre_una_tp_viva(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        tp = await _tp(db)

        entrega = await _crear(db, tp=tp, alumno=alumno)
        assert entrega.estado == "draft"

        # TP monolítica (sin `tp_ejercicios`): `esperados` viene vacío, así que
        # el submit no exige artefactos.
        enviada = await submit_entrega(
            entrega.id,
            EntregaSubmitBody(artefactos=[]),
            user=_alumno(alumno),
            db=db,
        )
        assert enviada.estado == "submitted"

        cal = await calificar_entrega(
            entrega.id,
            CalificacionCreate(nota_final=Decimal("8.50"), detalle_criterios=[]),
            user=_docente(),
            db=db,
        )
        assert float(cal.nota_final) == 8.5

    async def test_leer_una_entrega_de_tp_borrada_sigue_permitido(self, db: AsyncSession) -> None:
        """Los guards son de ESCRITURA, no de lectura.

        Cerrar también la lectura le borraría al docente el trabajo histórico
        del alumno de la vista, y eso es evidencia legítima: la entrega existió
        y la TP existió cuando se hizo. Lo que no puede es seguir avanzando.
        """
        from evaluation_service.routes.entregas import get_entrega

        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega_en_curso(db, tp=tp, alumno=alumno)
        await _borrar(db, tp)

        leida = await get_entrega(entrega.id, user=_docente(), db=db)
        assert leida.id == entrega.id
