"""Test de integracion ligera: el listado de episodios del drill-down docente
excluye los episodios marcados como fantasma (meta['superseded'] == True).

Usa 3 engines SQLite in-memory (ctr + classifier + academic) para imitar el
patron multi-DB. Verifica que `list_episodes_with_classifications_for_student`
NO devuelva episodios superseded, y SI devuelva los normales.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "apps/ctr-service/src"))
sys.path.insert(0, str(ROOT / "apps/classifier-service/src"))
sys.path.insert(0, str(ROOT / "apps/academic-service/src"))


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):
    return "JSON"


from platform_ops.real_datasources import RealLongitudinalDataSource

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest_asyncio.fixture
async def ctr_session() -> AsyncSession:
    from ctr_service.models import Base as CtrBase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CtrBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def classifier_session() -> AsyncSession:
    from classifier_service.models import Base as ClsBase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ClsBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def academic_session() -> AsyncSession:
    from sqlalchemy import text

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # La query solo lee id/template_id/codigo/titulo/tenant_id de
    # `tareas_practicas`. Creamos una tabla minima por SQL crudo para evitar
    # arrastrar las FKs (comisiones, templates, unidades) y los server_default
    # JSONB del modelo completo, que SQLite no entiende.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE tareas_practicas ("
                "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                "template_id TEXT, codigo TEXT, titulo TEXT)"
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _add_episode(
    session: AsyncSession,
    *,
    comision_id: UUID,
    student: UUID,
    problema_id: UUID,
    estado: str,
    meta: dict | None = None,
) -> UUID:
    from ctr_service.models import Episode

    ep_id = uuid4()
    ep = Episode(
        id=ep_id,
        tenant_id=TENANT,
        comision_id=comision_id,
        student_pseudonym=student,
        problema_id=problema_id,
        estado=estado,
        opened_at=datetime.now(UTC),
        closed_at=datetime.now(UTC) if estado == "closed" else None,
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
        curso_config_hash="d" * 64,
        events_count=3,
        last_chain_hash="0" * 64,
        meta=meta or {},
    )
    session.add(ep)
    await session.commit()
    return ep_id


async def _add_tarea(session: AsyncSession, problema_id: UUID) -> None:
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO tareas_practicas (id, tenant_id, template_id, codigo, titulo) "
            "VALUES (:id, :tenant_id, NULL, 'TP1', 'Tarea')"
        ),
        {"id": str(problema_id), "tenant_id": str(TENANT)},
    )
    await session.commit()


async def test_excluye_episodios_superseded(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
) -> None:
    comision = uuid4()
    student = uuid4()
    problema = uuid4()
    await _add_tarea(academic_session, problema)

    # Un episodio normal (paused, visible) + uno fantasma (superseded, oculto).
    normal_id = await _add_episode(
        ctr_session,
        comision_id=comision,
        student=student,
        problema_id=problema,
        estado="paused",
    )
    await _add_episode(
        ctr_session,
        comision_id=comision,
        student=student,
        problema_id=problema,
        estado="paused",
        meta={"superseded": True, "superseded_by": str(normal_id)},
    )

    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT)
    out = await ds.list_episodes_with_classifications_for_student(
        student, comision, academic_session
    )

    # Solo el normal aparece; el superseded queda fuera del conteo de sesiones.
    assert len(out) == 1
    assert out[0]["episode_id"] == str(normal_id)


async def test_no_excluye_episodios_normales(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
) -> None:
    comision = uuid4()
    student = uuid4()
    problema = uuid4()
    await _add_tarea(academic_session, problema)

    # Episodio con meta vacio y otro con meta sin superseded -> ambos visibles.
    await _add_episode(
        ctr_session,
        comision_id=comision,
        student=student,
        problema_id=problema,
        estado="closed",
    )
    await _add_episode(
        ctr_session,
        comision_id=comision,
        student=student,
        problema_id=problema,
        estado="paused",
        meta={"prompts": 4},
    )

    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT)
    out = await ds.list_episodes_with_classifications_for_student(
        student, comision, academic_session
    )

    assert len(out) == 2
