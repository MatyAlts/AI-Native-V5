"""Aceptación HU-007 · la pasiva por sobreuso no esconde pasivas confirmadas.

Escrita por el orquestador ANTES de construir; el constructor no la modifica.

El PR #139 muestra como "uso intensivo" (y saca del progreso) toda pasiva con
subgrupo `dependiente_sobreuso`. Pero el subgrupo se conserva cuando un docente
revisa el episodio (review.py copia `features`) y cuando el juez v2/v3 decide la
pasiva: en esos casos la pasiva está CONFIRMADA y no puede esconderse.

C01  La regla vive en un solo lugar: `platform_ops.pasiva_por_sobreuso(appropriation, features)`.
C02  Las filas de los datasources y las respuestas de la API (analytics y
     classifier) traen el booleano `pasiva_por_sobreuso` ya calculado.
C03  El progreso saltea solo las que cumplen C01.
N01  Una pasiva confirmada por revisión humana no se esconde ni sale del progreso.
N02  Una pasiva decidida por el juez (veredicto `ok`) tampoco.
N03  No cambian la etiqueta guardada, el export académico, el kappa ni el clasificador.
"""

from __future__ import annotations

import contextlib
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "apps/ctr-service/src"))
sys.path.insert(0, str(ROOT / "apps/classifier-service/src"))
sys.path.insert(0, str(ROOT / "apps/analytics-service/src"))


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):
    return "JSON"


TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOBREUSO = {"key": "dependiente_sobreuso"}
REVISION = {"reviewer_id": "d0c3e7e0-0000-0000-0000-000000000001", "verdict": "delegacion_pasiva"}
JUEZ_OK = {"estado": "ok", "regimen": "PASIVA", "juez_version": "v3"}
JUEZ_NO_OK = {"estado": "baja_confianza", "regimen": None, "juez_version": "v3"}

# Las tres formas de una pasiva con subgrupo de sobreuso.
F_REGLA = {"subgrupo": SOBREUSO}
F_DOCENTE = {"subgrupo": SOBREUSO, "revision_humana": REVISION}
F_JUEZ = {"subgrupo": SOBREUSO, "regimen_llm": JUEZ_OK}


# ── C01 · la regla, en un solo lugar ─────────────────────────────────────


@pytest.mark.parametrize(
    ("appropriation", "features", "esperado"),
    [
        ("delegacion_pasiva", F_REGLA, True),
        # N01: un docente confirmó la pasiva.
        ("delegacion_pasiva", F_DOCENTE, False),
        # N02: el juez decidió la pasiva.
        ("delegacion_pasiva", F_JUEZ, False),
        # El juez corrió pero no gobernó: la etiqueta sigue siendo la de la regla.
        ("delegacion_pasiva", {"subgrupo": SOBREUSO, "regimen_llm": JUEZ_NO_OK}, True),
        ("delegacion_pasiva", {"subgrupo": {"key": "dependiente_delegador"}}, False),
        ("delegacion_pasiva", {}, False),
        ("delegacion_pasiva", None, False),
        ("apropiacion_reflexiva", F_REGLA, False),
        (None, F_REGLA, False),
    ],
)
def test_c01_regla(appropriation, features, esperado):
    from platform_ops import pasiva_por_sobreuso

    assert pasiva_por_sobreuso(appropriation, features) is esperado


# ── C02 + C03 · datasources y progreso ───────────────────────────────────


@pytest_asyncio.fixture
async def ctr_session() -> AsyncSession:
    from ctr_service.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def classifier_session() -> AsyncSession:
    from classifier_service.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def academic_session() -> AsyncSession:
    from sqlalchemy import text

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE tareas_practicas (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                "template_id TEXT, unidad_id TEXT, codigo TEXT, titulo TEXT)"
            )
        )
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def _episodio(session, comision_id, student, opened_at) -> UUID:
    from ctr_service.models import Episode

    ep = Episode(
        id=uuid4(),
        tenant_id=TENANT,
        comision_id=comision_id,
        student_pseudonym=student,
        problema_id=uuid4(),
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=30),
        estado="closed",
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
        curso_config_hash="d" * 64,
        events_count=0,
        last_chain_hash="0" * 64,
    )
    session.add(ep)
    await session.commit()
    return ep.id


async def _clasificacion(session, episode_id, comision_id, appropriation, features, when):
    from classifier_service.models import Classification
    from sqlalchemy import func, select

    max_id = (await session.execute(select(func.max(Classification.id)))).scalar() or 0
    session.add(
        Classification(
            id=max_id + 1,
            episode_id=episode_id,
            tenant_id=TENANT,
            comision_id=comision_id,
            classifier_config_hash="c" * 64,
            appropriation=appropriation,
            appropriation_reason="x",
            classified_at=when,
            is_current=True,
            features=features,
        )
    )
    await session.commit()


async def _tres_pasivas(ctr_session, classifier_session):
    """Un alumno con tres pasivas de sobreuso: por regla, por docente, por juez."""
    comision_id, student = uuid4(), uuid4()
    t0 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    for i, feats in enumerate((F_REGLA, F_DOCENTE, F_JUEZ)):
        ep = await _episodio(ctr_session, comision_id, student, t0 + timedelta(hours=i))
        await _clasificacion(
            classifier_session, ep, comision_id, "delegacion_pasiva", feats, t0 + timedelta(days=i)
        )
    return comision_id, student


async def test_c02_filas_agrupadas_traen_el_booleano(ctr_session, classifier_session):
    from platform_ops.real_datasources import RealLongitudinalDataSource

    comision_id, student = await _tres_pasivas(ctr_session, classifier_session)
    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT)
    filas = (await ds.list_classifications_grouped_by_student(comision_id))[str(student)]
    assert [f["pasiva_por_sobreuso"] for f in filas] == [True, False, False]
    # N03: la etiqueta guardada no cambia.
    assert {f["appropriation"] for f in filas} == {"delegacion_pasiva"}


async def test_c02_episodios_del_alumno_traen_el_booleano(
    ctr_session, classifier_session, academic_session
):
    from platform_ops.real_datasources import RealLongitudinalDataSource

    comision_id, student = await _tres_pasivas(ctr_session, classifier_session)
    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT)
    eps = await ds.list_episodes_with_classifications_for_student(
        student, comision_id, academic_session
    )
    assert sorted(e["pasiva_por_sobreuso"] for e in eps) == [False, False, True]


async def test_c02_c03_progreso_por_template_cuenta_las_confirmadas(
    ctr_session, classifier_session, academic_session
):
    from platform_ops.cii_longitudinal import compute_evolution_general
    from platform_ops.real_datasources import RealLongitudinalDataSource

    comision_id, student = await _tres_pasivas(ctr_session, classifier_session)
    ds = RealLongitudinalDataSource(ctr_session, classifier_session, TENANT)
    filas = await ds.list_classifications_with_templates_for_student(
        student, comision_id, academic_session
    )
    assert sorted(f["pasiva_por_sobreuso"] for f in filas) == [False, False, True]
    # La de la regla no participa; las dos confirmadas cuentan como 0.
    assert compute_evolution_general(filas)["scores_ordinal"] == [0, 0]


def test_c03_progreso_general_desde_dicts():
    from platform_ops.cii_longitudinal import compute_evolution_general

    t0 = datetime(2026, 3, 1, tzinfo=UTC)

    def fila(i, appr, pps):
        return {
            "classified_at": t0 + timedelta(days=i),
            "appropriation": appr,
            "pasiva_por_sobreuso": pps,
        }

    filas = [
        fila(0, "delegacion_pasiva", True),
        fila(1, "delegacion_pasiva", False),
        fila(2, "apropiacion_superficial", False),
        fila(3, "apropiacion_reflexiva", False),
    ]
    assert compute_evolution_general(filas)["scores_ordinal"] == [0, 1, 2]


def test_c03_trayectoria_saltea_solo_la_de_la_regla():
    from platform_ops.longitudinal import ClassificationPoint, StudentTrajectory

    t0 = datetime(2026, 3, 1, tzinfo=UTC)
    puntos = [
        ClassificationPoint(uuid4(), t0, "apropiacion_reflexiva"),
        ClassificationPoint(
            uuid4(), t0 + timedelta(days=1), "delegacion_pasiva", pasiva_por_sobreuso=True
        ),
        ClassificationPoint(
            uuid4(), t0 + timedelta(days=2), "delegacion_pasiva", pasiva_por_sobreuso=False
        ),
    ]
    tray = StudentTrajectory(student_pseudonym="a", points=puntos)
    # La confirmada (False) cuenta y es la más baja; la de la regla no.
    assert tray.max_appropriation_reached() == "apropiacion_reflexiva"
    solo_regla = StudentTrajectory(student_pseudonym="b", points=puntos[1:2])
    assert solo_regla.max_appropriation_reached() is None
    solo_confirmada = StudentTrajectory(student_pseudonym="c", points=puntos[2:3])
    assert solo_confirmada.max_appropriation_reached() == "delegacion_pasiva"


# ── C02 · la API ─────────────────────────────────────────────────────────


def test_c02_schemas_de_analytics():
    from analytics_service.routes.analytics import StudentEpisodeOut, TrajectoryPoint

    for modelo in (TrajectoryPoint, StudentEpisodeOut):
        campo = modelo.model_fields.get("pasiva_por_sobreuso")
        assert campo is not None, modelo.__name__
        assert campo.default is False, modelo.__name__


async def test_c02_get_classification_del_classifier(monkeypatch):
    from classifier_service.main import app
    from classifier_service.models import Classification
    from httpx import ASGITransport, AsyncClient

    def _cls(features):
        return Classification(
            id=1,
            episode_id=uuid4(),
            tenant_id=TENANT,
            comision_id=uuid4(),
            classifier_config_hash="c" * 64,
            appropriation="delegacion_pasiva",
            appropriation_reason="x",
            classified_at=datetime(2026, 3, 1, tzinfo=UTC),
            is_current=True,
            features=features,
        )

    async def pedir(features):
        fila = _cls(features)

        @contextlib.asynccontextmanager
        async def fake_session(_tenant_id):
            async def execute(_stmt):
                return SimpleNamespace(scalar_one_or_none=lambda: fila)

            yield SimpleNamespace(execute=execute)

        monkeypatch.setattr("classifier_service.routes.classify_ep.tenant_session", fake_session)
        headers = {
            "X-User-Id": str(uuid4()),
            "X-Tenant-Id": str(TENANT),
            "X-User-Email": "d@utn.test",
            "X-User-Roles": "docente",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/api/v1/classifications/{fila.episode_id}", headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    assert (await pedir(F_REGLA))["pasiva_por_sobreuso"] is True
    assert (await pedir(F_DOCENTE))["pasiva_por_sobreuso"] is False
    assert (await pedir(F_JUEZ))["pasiva_por_sobreuso"] is False
    # N03: la etiqueta que devuelve es la guardada.
    assert (await pedir(F_JUEZ))["appropriation"] == "delegacion_pasiva"


# ── N03 · lo que no se toca ──────────────────────────────────────────────
# HU-009 (20/11) cambia a proposito `subgrupo.py` (Probar cuenta como ejecucion,
# tree_version v4.2.0) y `pipeline.py` (`cii_iteraciones` en features): salen de
# esta lista. Lo que HU-007 protegia de esos dos archivos, que la regla de
# sobreuso no cambie, lo sigue afirmando test_hu009 N02 y la suite de subgrupo.

_INTACTOS = {
    "packages/platform-ops/src/platform_ops/academic_export.py": "611fb20669759553525239df19d9b9c10b8545723d966f3e995907bae819d741",
    "packages/platform-ops/src/platform_ops/kappa_analysis.py": "4b91c9927d79270748e049d7638b2acb3fbb554d2dddbca6f9587decda2ea2fe",
    "apps/classifier-service/src/classifier_service/services/review.py": "c0571aadc382361aec6bf72f7d58bc9326d46351d97b03663aefd40d8e0e3cb3",
}


@pytest.mark.parametrize("ruta", sorted(_INTACTOS))
def test_n03_intactos(ruta):
    assert hashlib.sha256((ROOT / ruta).read_bytes()).hexdigest() == _INTACTOS[ruta]
