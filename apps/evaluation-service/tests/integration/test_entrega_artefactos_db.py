"""Tests del artefacto contra Postgres REAL.

Existen porque los unitarios con sesion mockeada NO pueden ver dos clases de
bug que este cambio introdujo y que un revisor encontro corriendo contra la
base:

1. `ejercicio_estados` es JSONB plano (sin `MutableList`). Copiarlo con
   `list(...)` comparte los dicts, asi que mutarlos y reasignar deja el valor
   viejo igual al nuevo y SQLAlchemy NO emite el UPDATE. Con `db.flush()`
   mockeado el assert pasa sobre el dict en memoria y el bug es invisible.

2. `Entrega.artefactos` es una relacion lazy. Tocarla desde una corrutina sin
   haberla cargado tira `MissingGreenlet`. Un `MagicMock` con
   `entrega.artefactos = []` nunca lo reproduce.

Ambas clases de bug se ven SOLO contra una sesion de verdad. Por eso estos
tests no son opcionales aunque haga falta una base para correrlos.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration -v

Sin esa env var se SKIPEAN (no se inventa una base ni se cae el CI).
Cada test limpia lo que crea.
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
    get_entrega_artefacto,
    mark_ejercicio_completado,
    submit_entrega,
)
from evaluation_service.schemas.entrega import (
    ArtefactoItem,
    EntregaSubmitBody,
    MarkEjercicioBody,
)
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real",
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# `entregas` tiene FK a `comisiones` y `tp_ejercicios` a `tareas_practicas` y
# `ejercicios`: no se pueden inventar UUIDs. Se descubren de la base en la que
# corre el test en vez de hardcodearlos, para que esto ande contra cualquier
# base migrada y sembrada, no sólo contra la de esta máquina.
COMISION: UUID
EJ1: UUID
EJ2: UUID


def _student(sid: UUID) -> User:
    return User(
        id=sid,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Sesion real con el tenant RLS seteado, que revierte todo al terminar."""
    global COMISION, EJ1, EJ2
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(TENANT)},
        )
        com = (
            await session.execute(
                text("SELECT id FROM comisiones WHERE tenant_id = :t LIMIT 1"), {"t": str(TENANT)}
            )
        ).scalar_one_or_none()
        ejs = (
            (
                await session.execute(
                    text("SELECT id FROM ejercicios WHERE tenant_id = :t LIMIT 2"),
                    {"t": str(TENANT)},
                )
            )
            .scalars()
            .all()
        )
        if com is None or len(ejs) < 2:
            pytest.skip("la base no tiene comisiones/ejercicios sembrados")
        COMISION, (EJ1, EJ2) = com, (ejs[0], ejs[1])
        try:
            yield session
        finally:
            # Rollback y no commit: los tests no dejan basura en la base del
            # piloto. Lo que se quiere probar es lo que la DB HIZO durante la
            # transaccion, no que sobreviva.
            await session.rollback()
    await engine.dispose()


async def _tp_con_ejercicios(db: AsyncSession, n: int) -> tuple[UUID, list[UUID]]:
    """Crea una TP real con `n` filas en `tp_ejercicios`."""
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
            "cod": f"TEST-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
        },
    )
    ids = [EJ1, EJ2][:n]
    for orden, ej_id in enumerate(ids, start=1):
        await db.execute(
            text(
                "INSERT INTO tp_ejercicios "
                "(id, tenant_id, tarea_practica_id, ejercicio_id, orden, peso_en_tp) "
                "VALUES (:id, :t, :tp, :ej, :o, 0.5)"
            ),
            {
                "id": str(uuid.uuid4()),
                "t": str(TENANT),
                "tp": str(tp_id),
                "ej": str(ej_id),
                "o": orden,
            },
        )
    return tp_id, ids


async def _entrega_sembrada(
    db: AsyncSession, tp_id: UUID, ids: list[UUID], student_id: UUID
) -> Entrega:
    """Entrega en draft con los ejercicios sembrados incompletos — el estado
    en el que la deja `create_entrega` desde la tarea 1.4."""
    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tp_id,
        student_pseudonym=student_id,
        comision_id=COMISION,
        estado="draft",
        ejercicio_estados=[
            {
                "ejercicio_id": str(ej),
                "orden": i,
                "episode_id": None,
                "completado": False,
                "completed_at": None,
            }
            for i, ej in enumerate(ids, start=1)
        ],
    )
    db.add(entrega)
    await db.flush()
    return entrega


async def _estados_en_db(db: AsyncSession, entrega_id: UUID) -> list[dict]:
    """Lee `ejercicio_estados` SALTEANDO la identity map de SQLAlchemy.

    Leer `entrega.ejercicio_estados` devolveria el objeto en memoria, que
    esta mutado aunque el UPDATE nunca se haya emitido — que es exactamente
    el bug que este test tiene que poder ver.
    """
    row = await db.execute(
        text("SELECT ejercicio_estados FROM entregas WHERE id = :i"), {"i": str(entrega_id)}
    )
    return row.scalar_one()


class TestMarcarEjercicioPersiste:
    async def test_el_patch_sobre_un_estado_sembrado_llega_a_la_db(self, db: AsyncSession) -> None:
        """El bug: `list(estados)` comparte los dicts, mutarlos y reasignar
        deja viejo == nuevo y SQLAlchemy no emite UPDATE. Con la entrega
        sembrada TODOS los PATCH caen en esa rama, asi que la TP
        multi-ejercicio quedaba inentregable."""
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 2)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)
        episode = uuid.uuid4()

        await mark_ejercicio_completado(
            entrega.id,
            1,
            MarkEjercicioBody(completado=True, episode_id=episode, ejercicio_id=EJ1),
            _student(sid),
            db,
        )
        await db.flush()

        en_db = await _estados_en_db(db, entrega.id)
        ej1 = next(e for e in en_db if e["orden"] == 1)
        assert ej1["completado"] is True, "el UPDATE no se emitio: el cambio se perdio"
        assert ej1["episode_id"] == str(episode)
        # El otro sigue incompleto: marcar uno no marca todos.
        assert next(e for e in en_db if e["orden"] == 2)["completado"] is False

    async def test_marcar_los_dos_permite_entregar(self, db: AsyncSession) -> None:
        """El camino completo del alumno, extremo a extremo contra la base."""
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 2)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)

        for orden, ej in enumerate(ids, start=1):
            await mark_ejercicio_completado(
                entrega.id,
                orden,
                MarkEjercicioBody(completado=True, episode_id=uuid.uuid4(), ejercicio_id=ej),
                _student(sid),
                db,
            )

        await submit_entrega(
            entrega.id,
            EntregaSubmitBody(
                artefactos=[
                    ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="class A {}", language="java"),
                    ArtefactoItem(orden=2, ejercicio_id=EJ2, codigo="class B {}", language="java"),
                ]
            ),
            _student(sid),
            db,
        )
        await db.flush()

        assert entrega.estado == "submitted"
        n = await db.execute(
            text("SELECT count(*) FROM entrega_artefactos WHERE entrega_id = :i"),
            {"i": str(entrega.id)},
        )
        assert n.scalar_one() == 2, "el submit no persistio los artefactos"


class TestSubmitPersisteArtefactos:
    async def test_submit_no_explota_por_la_relacion_lazy(self, db: AsyncSession) -> None:
        """El bug: `entrega.artefactos` sin cargar, tocado desde una
        corrutina, tira `MissingGreenlet` y el submit devolvia 500 SIEMPRE."""
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 1)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)
        await mark_ejercicio_completado(
            entrega.id,
            1,
            MarkEjercicioBody(completado=True, episode_id=uuid.uuid4(), ejercicio_id=EJ1),
            _student(sid),
            db,
        )

        await submit_entrega(
            entrega.id,
            EntregaSubmitBody(
                artefactos=[ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="x", language="java")]
            ),
            _student(sid),
            db,
        )
        await db.flush()

        row = await db.execute(
            text("SELECT codigo, sha256, language FROM entrega_artefactos WHERE entrega_id = :i"),
            {"i": str(entrega.id)},
        )
        codigo, sha, lang = row.one()
        assert codigo == "x"
        assert len(sha) == 64
        assert lang == "java"

    async def test_submit_monolitico_sin_artefactos_no_explota(self, db: AsyncSession) -> None:
        """Regresion: la TP monolitica no manda artefactos, pero el log del
        endpoint tocaba la relacion igual y rompia un camino que ANDABA."""
        sid = uuid.uuid4()
        tp_id, _ = await _tp_con_ejercicios(db, 0)  # TP real, SIN tp_ejercicios
        entrega = Entrega(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            tarea_practica_id=tp_id,
            student_pseudonym=sid,
            comision_id=COMISION,
            estado="draft",
            ejercicio_estados=[],
        )
        db.add(entrega)
        await db.flush()

        await submit_entrega(entrega.id, EntregaSubmitBody(), _student(sid), db)
        assert entrega.estado == "submitted"

    async def test_resubmit_reemplaza_las_filas_en_la_db(self, db: AsyncSession) -> None:
        """`artefactos.clear()` tiene que traducirse en DELETE real via
        `delete-orphan`, no dejar la fila vieja conviviendo con la nueva."""
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 1)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)
        await mark_ejercicio_completado(
            entrega.id,
            1,
            MarkEjercicioBody(completado=True, episode_id=uuid.uuid4(), ejercicio_id=EJ1),
            _student(sid),
            db,
        )
        body_v1 = EntregaSubmitBody(
            artefactos=[ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="v1", language="java")]
        )
        await submit_entrega(entrega.id, body_v1, _student(sid), db)
        await db.flush()

        # El docente devuelve la entrega y el alumno re-entrega con otro codigo.
        entrega.estado = "returned"
        await db.flush()
        body_v2 = EntregaSubmitBody(
            artefactos=[ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="v2", language="java")]
        )
        await submit_entrega(entrega.id, body_v2, _student(sid), db)
        await db.flush()

        rows = await db.execute(
            text("SELECT codigo FROM entrega_artefactos WHERE entrega_id = :i"),
            {"i": str(entrega.id)},
        )
        codigos = [r[0] for r in rows.all()]
        assert codigos == ["v2"], f"quedaron filas viejas conviviendo: {codigos}"

    async def test_orden_que_la_tp_no_declara_da_422(self, db: AsyncSession) -> None:
        """Un `orden` colado se persistia igual y entraba al hash del
        conjunto: el docente veia un ejercicio inexistente y la constancia de
        lo entregado dependia de una fila sin respaldo en `tp_ejercicios`."""
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 1)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)
        await mark_ejercicio_completado(
            entrega.id,
            1,
            MarkEjercicioBody(completado=True, episode_id=uuid.uuid4(), ejercicio_id=EJ1),
            _student(sid),
            db,
        )

        body = EntregaSubmitBody(
            artefactos=[
                ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="legit"),
                ArtefactoItem(orden=9, codigo="colado"),
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, body, _student(sid), db)
        assert exc.value.status_code == 422
        assert "9" in str(exc.value.detail)

    async def test_reentrega_monolitica_sin_codigo_da_422(self, db: AsyncSession) -> None:
        """Dejarla pasar moveria `submitted_at` conservando el artefacto del
        envio anterior: el hash dejaria de certificar el momento que la
        entrega declara."""
        sid = uuid.uuid4()
        tp_id, _ = await _tp_con_ejercicios(db, 0)  # monolitica
        entrega = Entrega(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            tarea_practica_id=tp_id,
            student_pseudonym=sid,
            comision_id=COMISION,
            estado="draft",
            ejercicio_estados=[],
        )
        db.add(entrega)
        await db.flush()

        await submit_entrega(
            entrega.id,
            EntregaSubmitBody(artefactos=[ArtefactoItem(orden=1, codigo="version-vieja")]),
            _student(sid),
            db,
        )
        await db.flush()
        sha_1 = entrega.artefacto_sha256

        entrega.estado = "returned"
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, EntregaSubmitBody(), _student(sid), db)
        assert exc.value.status_code == 422
        assert entrega.artefacto_sha256 == sha_1

    async def test_orden_duplicado_da_422_y_no_500(self, db: AsyncSession) -> None:
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 1)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)
        await mark_ejercicio_completado(
            entrega.id,
            1,
            MarkEjercicioBody(completado=True, episode_id=uuid.uuid4(), ejercicio_id=EJ1),
            _student(sid),
            db,
        )

        body = EntregaSubmitBody(
            artefactos=[
                ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="x"),
                ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="y"),
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await submit_entrega(entrega.id, body, _student(sid), db)
        assert exc.value.status_code == 422


class TestLeerArtefacto:
    async def test_el_duenio_lee_lo_que_entrego(self, db: AsyncSession) -> None:
        sid = uuid.uuid4()
        tp_id, ids = await _tp_con_ejercicios(db, 1)
        entrega = await _entrega_sembrada(db, tp_id, ids, sid)
        await mark_ejercicio_completado(
            entrega.id,
            1,
            MarkEjercicioBody(completado=True, episode_id=uuid.uuid4(), ejercicio_id=EJ1),
            _student(sid),
            db,
        )
        await submit_entrega(
            entrega.id,
            EntregaSubmitBody(
                artefactos=[
                    ArtefactoItem(orden=1, ejercicio_id=EJ1, codigo="hola", language="java")
                ]
            ),
            _student(sid),
            db,
        )
        await db.flush()

        out = await get_entrega_artefacto(entrega.id, _student(sid), db)
        assert len(out.artefactos) == 1
        assert out.artefactos[0].codigo == "hola"
        assert out.artefacto_sha256 is not None
        assert out.legacy is False
