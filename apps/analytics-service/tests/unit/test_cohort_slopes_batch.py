"""Test de equivalencia del batch anti-N+1 de /alerts (P-4).

Verifica que `batch_classifications_with_templates_by_student` (una pasada,
3 queries para toda la cohorte) produce, por estudiante, EXACTAMENTE la misma
lista de dicts que la función per-alumno original
`RealLongitudinalDataSource.list_classifications_with_templates_for_student`
(3 queries × N alumnos). Si son idénticos, el `mean_slope` downstream es
idéntico y el resultado de /alerts no cambia.

Usa 3 engines SQLite in-memory (ctr + classifier + academic) imitando el
patrón multi-DB productivo — mismo enfoque que
`packages/platform-ops/tests/test_real_datasources.py`.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "apps/ctr-service/src"))
sys.path.insert(0, str(ROOT / "apps/classifier-service/src"))
sys.path.insert(0, str(ROOT / "apps/academic-service/src"))


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):
    return "JSON"


TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

_APPROPRIATIONS = [
    "delegacion_pasiva",
    "apropiacion_superficial",
    "apropiacion_reflexiva",
]


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
    # Tabla mínima: la query solo lee id/template_id/unidad_id/tenant_id de
    # tareas_practicas (evitamos las FKs y server_default JSONB del modelo real).
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE tareas_practicas ("
                "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                "template_id TEXT, unidad_id TEXT)"
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _add_open_event(
    session: AsyncSession, *, episode_id: UUID, payload: dict | None = None
) -> None:
    from ctr_service.models import Event
    from sqlalchemy import func
    from sqlalchemy import select as _select

    max_id_result = await session.execute(_select(func.max(Event.id)))
    max_id = max_id_result.scalar() or 0

    session.add(
        Event(
            id=max_id + 1,
            event_uuid=uuid4(),
            episode_id=episode_id,
            tenant_id=TENANT,
            seq=0,
            event_type="episodio_abierto",
            ts=datetime.now(UTC),
            payload=payload or {},
            self_hash="a" * 64,
            chain_hash="b" * 64,
            prev_chain_hash="0" * 64,
            prompt_system_hash="p" * 64,
            prompt_system_version="v1.0.0",
            classifier_config_hash="c" * 64,
        )
    )
    await session.commit()


async def _add_episode(session: AsyncSession, *, student: UUID, problema_id: UUID) -> UUID:
    from ctr_service.models import Episode

    ep_id = uuid4()
    ep = Episode(
        id=ep_id,
        tenant_id=TENANT,
        comision_id=COMISION,
        student_pseudonym=student,
        problema_id=problema_id,
        opened_at=datetime.now(UTC),
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


async def _add_tarea(session: AsyncSession, *, problema_id: UUID, template_id: UUID | None) -> None:
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO tareas_practicas (id, tenant_id, template_id, unidad_id) "
            "VALUES (:id, :tenant_id, :template_id, NULL)"
        ),
        {
            "id": str(problema_id),
            "tenant_id": str(TENANT),
            "template_id": str(template_id) if template_id else None,
        },
    )
    await session.commit()


_cls_id_counter = 0


async def _add_classification(
    session: AsyncSession,
    *,
    episode_id: UUID,
    appropriation: str,
    classified_at: datetime,
    is_current: bool = True,
) -> None:
    from classifier_service.models import Classification

    # SQLite no autoincrementa BigInteger PKs como Postgres — id manual.
    # El config_hash varía por id para no chocar el UNIQUE(episode_id, hash)
    # cuando un mismo episodio tiene una classification current + una stale.
    global _cls_id_counter
    _cls_id_counter += 1
    session.add(
        Classification(
            id=_cls_id_counter,
            episode_id=episode_id,
            comision_id=COMISION,
            tenant_id=TENANT,
            classifier_config_hash=f"{_cls_id_counter:064d}",
            appropriation=appropriation,
            appropriation_reason="test",
            classified_at=classified_at,
            is_current=is_current,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_batch_equivale_a_la_funcion_per_alumno(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
) -> None:
    """El batch por-cohorte devuelve, por estudiante, la MISMA lista que la
    función per-alumno de RealLongitudinalDataSource."""
    from analytics_service.services.cohort_slopes import (
        batch_classifications_with_templates_by_student,
    )
    from platform_ops.real_datasources import RealLongitudinalDataSource

    base_ts = datetime(2026, 1, 1, tzinfo=UTC)
    # 3 estudiantes: uno con template, uno con TP huérfana (template None),
    # uno con varios episodios sobre el mismo template (slope real).
    template_a = uuid4()
    students = [uuid4() for _ in range(3)]

    # Estudiante 0: 3 episodios sobre template_a (slope definido).
    for i in range(3):
        prob = uuid4()
        await _add_tarea(academic_session, problema_id=prob, template_id=template_a)
        ep = await _add_episode(ctr_session, student=students[0], problema_id=prob)
        await _add_classification(
            classifier_session,
            episode_id=ep,
            appropriation=_APPROPRIATIONS[i],
            classified_at=base_ts + timedelta(days=i),
        )

    # Estudiante 1: 1 episodio con TP huérfana (template_id None).
    prob1 = uuid4()
    await _add_tarea(academic_session, problema_id=prob1, template_id=None)
    ep1 = await _add_episode(ctr_session, student=students[1], problema_id=prob1)
    await _add_classification(
        classifier_session,
        episode_id=ep1,
        appropriation="apropiacion_superficial",
        classified_at=base_ts,
    )

    # Estudiante 2: 2 episodios sobre el mismo template + una classification
    # NO current (debe ignorarse por ambos caminos).
    for i in range(2):
        prob = uuid4()
        await _add_tarea(academic_session, problema_id=prob, template_id=template_a)
        ep = await _add_episode(ctr_session, student=students[2], problema_id=prob)
        await _add_classification(
            classifier_session,
            episode_id=ep,
            appropriation=_APPROPRIATIONS[i],
            classified_at=base_ts + timedelta(days=i),
        )
        if i == 0:
            # classification stale del mismo episodio → is_current=False
            await _add_classification(
                classifier_session,
                episode_id=ep,
                appropriation="delegacion_pasiva",
                classified_at=base_ts - timedelta(days=1),
                is_current=False,
            )

    # --- Batch (camino nuevo) ---
    grouped = await batch_classifications_with_templates_by_student(
        ctr_session=ctr_session,
        classifier_session=classifier_session,
        academic_session=academic_session,
        comision_id=COMISION,
        tenant_id=TENANT,
    )

    # --- Referencia per-alumno (camino original) ---
    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT)
    for student in students:
        reference = await ds.list_classifications_with_templates_for_student(
            student_pseudonym=student,
            comision_id=COMISION,
            academic_session=academic_session,
        )
        batched = grouped.get(student, [])
        # Orden independiente: comparamos como sets de tuplas de items clave.
        key = lambda d: (str(d["episode_id"]), str(d["classified_at"]))  # noqa: E731
        assert sorted(batched, key=key) == sorted(reference, key=key), (
            f"mismatch para estudiante {student}"
        )

    # Sanity: el estudiante 0 tiene 3 clasificaciones current, el 2 tiene 2.
    assert len(grouped[students[0]]) == 3
    assert len(grouped[students[2]]) == 2
    assert len(grouped[students[1]]) == 1


@pytest.mark.asyncio
async def test_batch_cohorte_vacia_devuelve_dict_vacio(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
) -> None:
    from analytics_service.services.cohort_slopes import (
        batch_classifications_with_templates_by_student,
    )

    grouped = await batch_classifications_with_templates_by_student(
        ctr_session=ctr_session,
        classifier_session=classifier_session,
        academic_session=academic_session,
        comision_id=COMISION,
        tenant_id=TENANT,
    )
    assert grouped == {}


# ── Filtro por lenguaje (multi-language-research-integrity sección 4.8) ──


@pytest.mark.asyncio
async def test_batch_filtra_por_lenguaje(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
) -> None:
    from analytics_service.services.cohort_slopes import (
        batch_classifications_with_templates_by_student,
    )

    base_ts = datetime(2026, 1, 1, tzinfo=UTC)
    student = uuid4()
    prob_py = uuid4()
    prob_java = uuid4()
    await _add_tarea(academic_session, problema_id=prob_py, template_id=None)
    await _add_tarea(academic_session, problema_id=prob_java, template_id=None)

    ep_py = await _add_episode(ctr_session, student=student, problema_id=prob_py)
    ep_java = await _add_episode(ctr_session, student=student, problema_id=prob_java)
    await _add_open_event(ctr_session, episode_id=ep_py, payload={"language": "python"})
    await _add_open_event(ctr_session, episode_id=ep_java, payload={"language": "java"})
    await _add_classification(
        classifier_session,
        episode_id=ep_py,
        appropriation="delegacion_pasiva",
        classified_at=base_ts,
    )
    await _add_classification(
        classifier_session,
        episode_id=ep_java,
        appropriation="apropiacion_reflexiva",
        classified_at=base_ts,
    )

    grouped = await batch_classifications_with_templates_by_student(
        ctr_session=ctr_session,
        classifier_session=classifier_session,
        academic_session=academic_session,
        comision_id=COMISION,
        tenant_id=TENANT,
        language="java",
    )

    assert len(grouped[student]) == 1
    assert grouped[student][0]["episode_id"] == ep_java


@pytest.mark.asyncio
async def test_batch_filtro_sin_resultados_devuelve_dict_vacio(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
) -> None:
    """4.9: cohorte 100% Python filtrada por `java` → dict vacío."""
    from analytics_service.services.cohort_slopes import (
        batch_classifications_with_templates_by_student,
    )

    base_ts = datetime(2026, 1, 1, tzinfo=UTC)
    student = uuid4()
    prob = uuid4()
    await _add_tarea(academic_session, problema_id=prob, template_id=None)
    ep = await _add_episode(ctr_session, student=student, problema_id=prob)
    await _add_open_event(ctr_session, episode_id=ep, payload={"language": "python"})
    await _add_classification(
        classifier_session, episode_id=ep, appropriation="delegacion_pasiva", classified_at=base_ts
    )

    grouped = await batch_classifications_with_templates_by_student(
        ctr_session=ctr_session,
        classifier_session=classifier_session,
        academic_session=academic_session,
        comision_id=COMISION,
        tenant_id=TENANT,
        language="java",
    )

    assert grouped == {}
