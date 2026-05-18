"""Tests del CRUD de PlanEstudios.

Cubre el happy path + reglas de negocio principales (FK carrera obligatoria,
filtrado por carrera, soft-delete, audit log) usando mocks de session/repos
en línea con `test_comision_periodo_cerrado.py`. El test de aislamiento RLS
levanta un Postgres real con testcontainers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Carrera, PlanEstudios
from academic_service.schemas.plan import PlanCreate, PlanUpdate
from academic_service.services.plan_service import PlanService
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def user_docente_admin() -> User:
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="admin@unsl.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm="unsl",
    )


def _fake_carrera(tenant_id: UUID, carrera_id: UUID | None = None) -> MagicMock:
    c = MagicMock(spec=Carrera)
    c.id = carrera_id or uuid4()
    c.tenant_id = tenant_id
    return c


def _fake_plan(tenant_id: UUID, carrera_id: UUID, plan_id: UUID | None = None) -> MagicMock:
    p = MagicMock(spec=PlanEstudios)
    p.id = plan_id or uuid4()
    p.tenant_id = tenant_id
    p.carrera_id = carrera_id
    p.version = "2025"
    p.año_inicio = 2025
    p.ordenanza = "ORD-001/25"
    p.vigente = True
    return p


async def test_plan_create_happy_path(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)

    carrera_id = uuid4()
    fake_carrera = _fake_carrera(user_docente_admin.tenant_id, carrera_id)
    svc.carreras.get_or_404 = AsyncMock(return_value=fake_carrera)

    fake_plan = _fake_plan(user_docente_admin.tenant_id, carrera_id)
    svc.repo.create = AsyncMock(return_value=fake_plan)

    data = PlanCreate(
        carrera_id=carrera_id,
        version="2025",
        año_inicio=2025,
        ordenanza="ORD-001/25",
    )

    result = await svc.create(data, user_docente_admin)

    assert result is fake_plan
    svc.repo.create.assert_called_once()
    create_args = svc.repo.create.call_args[0][0]
    assert create_args["carrera_id"] == carrera_id
    assert create_args["tenant_id"] == user_docente_admin.tenant_id
    assert create_args["version"] == "2025"
    assert create_args["año_inicio"] == 2025

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "plan.create"
    assert audit_calls[0].resource_type == "plan"
    assert audit_calls[0].user_id == user_docente_admin.id


async def test_plan_create_carrera_inexistente_404(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)

    svc.carreras.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Carrera no encontrada")
    )

    data = PlanCreate(
        carrera_id=uuid4(),
        version="2025",
        año_inicio=2025,
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin)

    assert exc_info.value.status_code == 404
    mock_session.add.assert_not_called()


async def test_plan_list_filtra_por_carrera(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)
    carrera_id = uuid4()

    fake_planes = [
        _fake_plan(user_docente_admin.tenant_id, carrera_id),
        _fake_plan(user_docente_admin.tenant_id, carrera_id),
    ]
    svc.repo.list = AsyncMock(return_value=fake_planes)

    result = await svc.list(limit=50, cursor=None, carrera_id=carrera_id)

    assert result == fake_planes
    svc.repo.list.assert_called_once_with(limit=50, cursor=None, filters={"carrera_id": carrera_id})


async def test_plan_list_sin_filtros(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)
    svc.repo.list = AsyncMock(return_value=[])

    await svc.list(limit=50, cursor=None, carrera_id=None)

    svc.repo.list.assert_called_once_with(limit=50, cursor=None, filters={})


async def test_plan_get_one_404(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)
    svc.repo.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="PlanEstudios no encontrado")
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.get(uuid4())

    assert exc_info.value.status_code == 404


async def test_plan_update_happy_path(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)

    plan_id = uuid4()
    carrera_id = uuid4()
    fake_plan = _fake_plan(user_docente_admin.tenant_id, carrera_id, plan_id)
    svc.repo.get_or_404 = AsyncMock(return_value=fake_plan)

    data = PlanUpdate(vigente=False, ordenanza="ORD-DEROG/26")

    result = await svc.update(plan_id, data, user_docente_admin)

    assert result is fake_plan
    assert fake_plan.vigente is False
    assert fake_plan.ordenanza == "ORD-DEROG/26"

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "plan.update"
    assert audit_calls[0].resource_id == plan_id
    assert audit_calls[0].changes == {"after": {"ordenanza": "ORD-DEROG/26", "vigente": False}}


async def test_plan_soft_delete(mock_session, user_docente_admin) -> None:
    svc = PlanService(mock_session)

    plan_id = uuid4()
    carrera_id = uuid4()
    fake_plan = _fake_plan(user_docente_admin.tenant_id, carrera_id, plan_id)
    svc.repo.soft_delete = AsyncMock(return_value=fake_plan)

    result = await svc.soft_delete(plan_id, user_docente_admin)

    assert result is fake_plan
    svc.repo.soft_delete.assert_called_once_with(plan_id)

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "plan.delete"
    assert audit_calls[0].changes == {"soft_delete": True}


# RLS isolation usa Postgres real para validar que un tenant no ve planes
# de otro. Se marca como integration y solo corre cuando hay docker.
pytestmark_rls = pytest.mark.integration


RLS_INIT_SQL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE planes_estudio (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    carrera_id UUID NOT NULL,
    version TEXT NOT NULL,
    año_inicio INT NOT NULL,
    vigente BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMPTZ
);
CREATE INDEX ix_planes_tenant ON planes_estudio (tenant_id);

ALTER TABLE planes_estudio ENABLE ROW LEVEL SECURITY;
ALTER TABLE planes_estudio FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON planes_estudio
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE ROLE app_user WITH LOGIN PASSWORD 'app';
GRANT ALL ON planes_estudio TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
"""


@pytest.fixture(scope="module")
def pg_container_planes():
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        import psycopg2

        conn = psycopg2.connect(pg.get_connection_url().replace("+psycopg2", ""))
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(RLS_INIT_SQL)
        conn.close()
        yield pg


@pytest.fixture
async def planes_engine(pg_container_planes):
    base = pg_container_planes.get_connection_url().replace("+psycopg2", "+asyncpg")
    from urllib.parse import urlparse

    parsed = urlparse(base)
    dsn = f"postgresql+asyncpg://app_user:app@{parsed.hostname}:{parsed.port}{parsed.path}"

    engine = create_async_engine(dsn)
    yield engine
    await engine.dispose()


@pytest.mark.integration
async def test_plan_rls_isolation(planes_engine) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    carrera_a = uuid4()
    carrera_b = uuid4()

    async with planes_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        await conn.execute(
            text(
                "INSERT INTO planes_estudio (tenant_id, carrera_id, version, año_inicio) "
                "VALUES (:t, :c, '2025', 2025)"
            ),
            {"t": tenant_a, "c": carrera_a},
        )

    async with planes_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_b)},
        )
        await conn.execute(
            text(
                "INSERT INTO planes_estudio (tenant_id, carrera_id, version, año_inicio) "
                "VALUES (:t, :c, '2025', 2025)"
            ),
            {"t": tenant_b, "c": carrera_b},
        )

    async with planes_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        result = await conn.execute(text("SELECT carrera_id FROM planes_estudio"))
        rows = [r[0] for r in result]

    assert rows == [carrera_a], f"Tenant A vio planes de B: {rows}"
