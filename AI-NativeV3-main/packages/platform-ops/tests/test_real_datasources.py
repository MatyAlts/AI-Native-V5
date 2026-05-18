"""Tests de los adaptadores reales de DB.

Usan SQLite in-memory con dos engines separados (para imitar el patrón
multi-DB productivo). RLS no se testea aquí (Postgres-only); se testea
que los filtros aplicativos por tenant funcionan correctamente.

Compat hack: SQLite no entiende JSONB/UUID de Postgres. Usamos @compiles
para que JSONB se compile como JSON en SQLite.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Path para importar ctr_service.models y classifier_service.models
ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "apps/ctr-service/src"))
sys.path.insert(0, str(ROOT / "apps/classifier-service/src"))


# Compat: JSONB → JSON en SQLite
@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):
    return "JSON"


from platform_ops.real_datasources import (
    RealCohortDataSource,
    RealLongitudinalDataSource,
)

TENANT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def ctr_session() -> AsyncSession:
    from ctr_service.models import Base as CtrBase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CtrBase.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def classifier_session() -> AsyncSession:
    from classifier_service.models import Base as ClsBase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ClsBase.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


# ── Helpers para insertar data ────────────────────────────────────────


async def _add_episode(
    session: AsyncSession,
    tenant_id: UUID,
    comision_id: UUID,
    student_pseudonym: UUID,
    problema_id: UUID | None = None,
    opened_at: datetime | None = None,
) -> UUID:
    from ctr_service.models import Episode

    ep_id = uuid4()
    ep = Episode(
        id=ep_id,
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=student_pseudonym,
        problema_id=problema_id or uuid4(),
        opened_at=opened_at or datetime.now(UTC),
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
        curso_config_hash="d" * 64,
        events_count=0,
        last_chain_hash="0" * 64,
    )
    session.add(ep)
    await session.commit()
    return ep_id


async def _add_event(
    session: AsyncSession,
    tenant_id: UUID,
    episode_id: UUID,
    seq: int,
    event_type: str,
    payload: dict | None = None,
) -> None:
    from ctr_service.models import Event
    from sqlalchemy import func

    # SQLite no autoincrementa BigInteger PKs como Postgres; asignamos id manual
    from sqlalchemy import select as _select

    max_id_result = await session.execute(_select(func.max(Event.id)))
    max_id = max_id_result.scalar() or 0

    ev = Event(
        id=max_id + 1,
        event_uuid=uuid4(),
        episode_id=episode_id,
        tenant_id=tenant_id,
        seq=seq,
        event_type=event_type,
        ts=datetime.now(UTC),
        payload=payload or {},
        self_hash="a" * 64,
        chain_hash="b" * 64,
        prev_chain_hash="0" * 64,
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
    )
    session.add(ev)
    await session.commit()


async def _add_classification(
    session: AsyncSession,
    tenant_id: UUID,
    episode_id: UUID,
    comision_id: UUID,
    appropriation: str,
    is_current: bool = True,
    classified_at: datetime | None = None,
    coherences: dict | None = None,
    config_hash: str = "c" * 64,
) -> None:
    from classifier_service.models import Classification
    from sqlalchemy import func

    # SQLite: id manual
    from sqlalchemy import select as _select

    max_id_result = await session.execute(_select(func.max(Classification.id)))
    max_id = max_id_result.scalar() or 0

    cls = Classification(
        id=max_id + 1,
        episode_id=episode_id,
        tenant_id=tenant_id,
        comision_id=comision_id,
        classifier_config_hash=config_hash,
        appropriation=appropriation,
        appropriation_reason="test reason",
        classified_at=classified_at or datetime.now(UTC),
        is_current=is_current,
        features={},
        **(coherences or {}),
    )
    session.add(cls)
    await session.commit()


# ── RealCohortDataSource ──────────────────────────────────────────────


async def test_list_episodes_filtra_por_comision(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    comision_a = uuid4()
    comision_b = uuid4()
    student = uuid4()

    await _add_episode(ctr_session, TENANT_A, comision_a, student)
    await _add_episode(ctr_session, TENANT_A, comision_b, student)

    ds = RealCohortDataSource(ctr_session, classifier_session, TENANT_A)
    episodes = await ds.list_episodes_in_comision(
        comision_a, since=datetime(2020, 1, 1, tzinfo=UTC)
    )
    # Solo 1 episodio de la comisión A
    assert len(episodes) == 1
    assert episodes[0]["comision_id"] == comision_a


async def test_list_episodes_filtra_por_tenant(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    comision_id = uuid4()

    # 2 episodios en la misma comisión, distintos tenants
    await _add_episode(ctr_session, TENANT_A, comision_id, uuid4())
    await _add_episode(ctr_session, TENANT_B, comision_id, uuid4())

    # Data source de TENANT_A solo ve el de TENANT_A
    ds_a = RealCohortDataSource(ctr_session, classifier_session, TENANT_A)
    eps_a = await ds_a.list_episodes_in_comision(
        comision_id, since=datetime(2020, 1, 1, tzinfo=UTC)
    )
    assert len(eps_a) == 1

    # Data source de TENANT_B ve solo el de TENANT_B
    ds_b = RealCohortDataSource(ctr_session, classifier_session, TENANT_B)
    eps_b = await ds_b.list_episodes_in_comision(
        comision_id, since=datetime(2020, 1, 1, tzinfo=UTC)
    )
    assert len(eps_b) == 1


async def test_list_episodes_aplica_filtro_de_tiempo(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    comision_id = uuid4()

    old_date = datetime.now(UTC) - timedelta(days=200)
    recent_date = datetime.now(UTC) - timedelta(days=5)

    await _add_episode(ctr_session, TENANT_A, comision_id, uuid4(), opened_at=old_date)
    await _add_episode(ctr_session, TENANT_A, comision_id, uuid4(), opened_at=recent_date)

    ds = RealCohortDataSource(ctr_session, classifier_session, TENANT_A)
    cutoff = datetime.now(UTC) - timedelta(days=90)
    episodes = await ds.list_episodes_in_comision(comision_id, since=cutoff)
    assert len(episodes) == 1  # solo el reciente


async def test_list_events_ordena_por_seq(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    ep_id = await _add_episode(ctr_session, TENANT_A, uuid4(), uuid4())

    # Insertar eventos fuera de orden
    await _add_event(ctr_session, TENANT_A, ep_id, 2, "codigo_ejecutado")
    await _add_event(ctr_session, TENANT_A, ep_id, 0, "episodio_abierto")
    await _add_event(ctr_session, TENANT_A, ep_id, 1, "prompt_enviado")

    ds = RealCohortDataSource(ctr_session, classifier_session, TENANT_A)
    events = await ds.list_events_for_episode(ep_id)

    # Vienen ordenados por seq
    seqs = [e["seq"] for e in events]
    assert seqs == [0, 1, 2]
    types = [e["event_type"] for e in events]
    assert types == ["episodio_abierto", "prompt_enviado", "codigo_ejecutado"]


async def test_get_current_classification_devuelve_is_current(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    comision_id = uuid4()
    ep_id = await _add_episode(ctr_session, TENANT_A, comision_id, uuid4())

    # Vieja clasificación (no current) con hash antiguo
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_id,
        comision_id,
        "apropiacion_superficial",
        is_current=False,
        classified_at=datetime.now(UTC) - timedelta(hours=2),
        config_hash="old_" + "c" * 60,
    )
    # Nueva clasificación (current) con hash nuevo (reflejando ADR-010:
    # reclasificar con config nuevo → hash distinto)
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_id,
        comision_id,
        "apropiacion_reflexiva",
        is_current=True,
        coherences={"ct_summary": 0.85, "ccd_mean": 0.80},
        config_hash="new_" + "c" * 60,
    )

    ds = RealCohortDataSource(ctr_session, classifier_session, TENANT_A)
    cls = await ds.get_current_classification(ep_id)
    assert cls is not None
    assert cls["appropriation"] == "apropiacion_reflexiva"
    assert cls["ct_summary"] == 0.85


async def test_get_current_classification_devuelve_none_si_no_clasificado(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    ep_id = await _add_episode(ctr_session, TENANT_A, uuid4(), uuid4())

    ds = RealCohortDataSource(ctr_session, classifier_session, TENANT_A)
    cls = await ds.get_current_classification(ep_id)
    assert cls is None


# ── RealLongitudinalDataSource ────────────────────────────────────────


async def test_longitudinal_agrupa_por_estudiante(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    comision_id = uuid4()
    student_a = uuid4()
    student_b = uuid4()

    # Alice: 3 episodios con progresión
    ep_a1 = await _add_episode(ctr_session, TENANT_A, comision_id, student_a)
    ep_a2 = await _add_episode(ctr_session, TENANT_A, comision_id, student_a)
    ep_a3 = await _add_episode(ctr_session, TENANT_A, comision_id, student_a)
    # Bob: 1 episodio
    ep_b1 = await _add_episode(ctr_session, TENANT_A, comision_id, student_b)

    base_time = datetime(2026, 3, 1, tzinfo=UTC)
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_a1,
        comision_id,
        "delegacion_pasiva",
        classified_at=base_time,
    )
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_a2,
        comision_id,
        "apropiacion_superficial",
        classified_at=base_time + timedelta(days=10),
    )
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_a3,
        comision_id,
        "apropiacion_reflexiva",
        classified_at=base_time + timedelta(days=20),
    )
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_b1,
        comision_id,
        "apropiacion_reflexiva",
        classified_at=base_time,
    )

    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT_A)
    grouped = await ds.list_classifications_grouped_by_student(comision_id)
    assert len(grouped) == 2

    # Alice tiene 3 puntos, Bob 1
    alice_points = grouped[str(student_a)]
    bob_points = grouped[str(student_b)]
    assert len(alice_points) == 3
    assert len(bob_points) == 1

    # Orden cronológico
    alice_labels = [p["appropriation"] for p in alice_points]
    assert alice_labels == [
        "delegacion_pasiva",
        "apropiacion_superficial",
        "apropiacion_reflexiva",
    ]


async def test_longitudinal_respeta_is_current(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    """Solo considera las clasificaciones con is_current=true."""
    comision_id = uuid4()
    student = uuid4()
    ep_id = await _add_episode(ctr_session, TENANT_A, comision_id, student)

    # Vieja (no current, hash antiguo) + current (hash nuevo) → solo current
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_id,
        comision_id,
        "delegacion_pasiva",
        is_current=False,
        config_hash="old_" + "c" * 60,
    )
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_id,
        comision_id,
        "apropiacion_reflexiva",
        is_current=True,
        config_hash="new_" + "c" * 60,
    )

    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT_A)
    grouped = await ds.list_classifications_grouped_by_student(comision_id)
    assert len(grouped[str(student)]) == 1
    assert grouped[str(student)][0]["appropriation"] == "apropiacion_reflexiva"


async def test_longitudinal_con_pseudonymize_fn(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    """Si se pasa pseudonymize_fn, los aliases se aplican."""
    comision_id = uuid4()
    student = uuid4()
    ep_id = await _add_episode(ctr_session, TENANT_A, comision_id, student)
    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_id,
        comision_id,
        "apropiacion_reflexiva",
    )

    ds = RealLongitudinalDataSource(
        ctr_session,
        classifier_session,
        TENANT_A,
        pseudonymize_fn=lambda u: f"alias_{str(u)[:8]}",
    )
    grouped = await ds.list_classifications_grouped_by_student(comision_id)
    # La key ya NO es el UUID del estudiante
    assert str(student) not in grouped
    expected_alias = f"alias_{str(student)[:8]}"
    assert expected_alias in grouped


async def test_longitudinal_respeta_tenant_isolation(
    ctr_session: AsyncSession, classifier_session: AsyncSession
) -> None:
    """Un data source de TENANT_A no ve estudiantes de TENANT_B."""
    comision_id = uuid4()
    student_a = uuid4()
    student_b = uuid4()

    ep_a = await _add_episode(ctr_session, TENANT_A, comision_id, student_a)
    ep_b = await _add_episode(ctr_session, TENANT_B, comision_id, student_b)

    await _add_classification(
        classifier_session,
        TENANT_A,
        ep_a,
        comision_id,
        "apropiacion_reflexiva",
    )
    await _add_classification(
        classifier_session,
        TENANT_B,
        ep_b,
        comision_id,
        "delegacion_pasiva",
    )

    ds_a = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT_A)
    grouped_a = await ds_a.list_classifications_grouped_by_student(comision_id)

    assert len(grouped_a) == 1
    assert str(student_a) in grouped_a
    assert str(student_b) not in grouped_a
