"""Filtro `reentrega` de `list_entregas` contra Postgres real (change
`reentregas-marcadas-en-pendientes`, D2).

El filtro tiene que ser SQL (EXISTS sobre `calificaciones`) y no un recorte en
Python: la lista pagina con cursor, y un recorte posterior devolveria paginas
incompletas. Por eso se prueba contra la base y con `limit` chico.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_listado_reentregas_db.py -v
Sin esa env var se SKIPEAN. Cada test revierte lo que crea.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import get_entrega, list_entregas
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real"
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION: UUID


def _user(roles: set[str], uid: UUID | None = None) -> User:
    return User(
        id=uid or uuid.uuid4(),
        tenant_id=TENANT,
        email="d@utn.edu.ar",
        roles=frozenset(roles),
        realm="utn",
    )


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    global COMISION
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(TENANT)}
        )
        com = (
            await session.execute(
                text("SELECT id FROM comisiones WHERE tenant_id = :t LIMIT 1"), {"t": str(TENANT)}
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
            "(id, tenant_id, comision_id, codigo, titulo, enunciado, created_by) "
            "VALUES (:id, :t, :c, :cod, 'Reentregas', 'Test', :u)"
        ),
        {
            "id": str(tp_id),
            "t": str(TENANT),
            "c": str(COMISION),
            "cod": f"RE-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
        },
    )
    return tp_id


async def _entrega(
    db: AsyncSession, tp: UUID, estado: str, *, nota: float | None = None, borrada: bool = False
) -> UUID:
    e = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tp,
        student_pseudonym=uuid.uuid4(),
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[],
    )
    db.add(e)
    await db.flush()
    if nota is not None:
        await db.execute(
            text(
                "INSERT INTO calificaciones "
                "(id, tenant_id, entrega_id, nota_final, graded_by, deleted_at) "
                "VALUES (:id, :t, :e, :n, :u, CASE WHEN :b THEN now() ELSE NULL END)"
            ),
            {
                "id": str(uuid.uuid4()),
                "t": str(TENANT),
                "e": str(e.id),
                "n": nota,
                "u": str(uuid.uuid4()),
                "b": borrada,
            },
        )
        await db.flush()
    return e.id


async def _escenario(db: AsyncSession) -> tuple[UUID, dict[str, set[UUID]]]:
    tp = await _tp(db)
    nuevas = {await _entrega(db, tp, "submitted") for _ in range(3)}
    reentregas = {await _entrega(db, tp, "submitted", nota=6) for _ in range(2)}
    otras = {
        await _entrega(db, tp, "graded", nota=8),
        await _entrega(db, tp, "returned", nota=5),
    }
    # calificacion borrada: ya no cuenta como re-entrega
    borrada = {await _entrega(db, tp, "submitted", nota=4, borrada=True)}
    return tp, {
        "nuevas": nuevas,
        "reentregas": reentregas,
        "otras": otras,
        "borrada": borrada,
    }


async def _listar(db: AsyncSession, tp: UUID, user: User, **kw: Any) -> list[Any]:
    params: dict[str, Any] = {
        "tarea_practica_id": tp,
        "comision_id": None,
        "estado": None,
        "student_pseudonym": None,
        "cursor": None,
        "limit": 50,
        "user": user,
        "db": db,
    }
    params.update(kw)
    return list((await list_entregas(**params)).data)


_ADMIN = {"docente_admin"}


class TestFiltroReentrega:
    async def test_true_devuelve_solo_las_reentregas(self, db: AsyncSession) -> None:
        tp, g = await _escenario(db)
        data = await _listar(db, tp, _user(_ADMIN), reentrega=True)
        assert {e.id for e in data} == g["reentregas"]
        assert all(e.es_reentrega and e.nota_final == 6.0 for e in data)

    async def test_false_devuelve_todo_lo_que_no_es_reentrega(self, db: AsyncSession) -> None:
        tp, g = await _escenario(db)
        data = await _listar(db, tp, _user(_ADMIN), reentrega=False)
        assert {e.id for e in data} == g["nuevas"] | g["otras"] | g["borrada"]
        assert not any(e.es_reentrega for e in data)

    async def test_sin_parametro_es_igual_que_antes(self, db: AsyncSession) -> None:
        tp, g = await _escenario(db)
        data = await _listar(db, tp, _user(_ADMIN))
        assert {e.id for e in data} == (g["nuevas"] | g["reentregas"] | g["otras"] | g["borrada"])

    async def test_la_calificacion_borrada_no_cuenta(self, db: AsyncSession) -> None:
        tp, g = await _escenario(db)
        data = await _listar(db, tp, _user(_ADMIN), reentrega=True)
        assert not ({e.id for e in data} & g["borrada"])

    async def test_estado_graded_con_reentrega_true_es_vacio(self, db: AsyncSession) -> None:
        tp, _ = await _escenario(db)
        assert await _listar(db, tp, _user(_ADMIN), estado="graded", reentrega=True) == []

    async def test_paginacion_devuelve_paginas_completas(self, db: AsyncSession) -> None:
        tp, g = await _escenario(db)
        vistos: list[UUID] = []
        cursor = None
        while True:
            resp = await list_entregas(
                tarea_practica_id=tp,
                comision_id=None,
                estado=None,
                student_pseudonym=None,
                cursor=cursor,
                limit=1,
                reentrega=True,
                user=_user(_ADMIN),
                db=db,
            )
            vistos += [e.id for e in resp.data]
            if resp.meta.cursor_next is None:
                break
            cursor = UUID(resp.meta.cursor_next)
        assert set(vistos) == g["reentregas"]
        assert len(vistos) == 2


class TestAislamientoPorComision:
    async def test_docente_ajeno_con_reentrega_true_no_recibe_nada(self, db: AsyncSession) -> None:
        tp, _ = await _escenario(db)
        assert await _listar(db, tp, _user({"docente"}), reentrega=True) == []

    async def test_docente_asignado_recibe_las_de_su_comision(self, db: AsyncSession) -> None:
        tp, g = await _escenario(db)
        yo = _user({"docente"})
        await db.execute(
            text(
                "INSERT INTO usuarios_comision "
                "(id, tenant_id, user_id, comision_id, rol, fecha_desde) "
                "VALUES (:id, :t, :u, :c, 'docente', CURRENT_DATE)"
            ),
            {"id": str(uuid.uuid4()), "t": str(TENANT), "u": str(yo.id), "c": str(COMISION)},
        )
        data = await _listar(db, tp, yo, reentrega=True)
        assert {e.id for e in data} == g["reentregas"]


class TestGetEntregaIndividual:
    async def test_get_entrega_informa_es_reentrega(self, db: AsyncSession) -> None:
        _, g = await _escenario(db)
        una = next(iter(g["reentregas"]))
        assert (await get_entrega(una, user=_user(_ADMIN), db=db)).es_reentrega is True
        nueva = next(iter(g["nuevas"]))
        assert (await get_entrega(nueva, user=_user(_ADMIN), db=db)).es_reentrega is False
