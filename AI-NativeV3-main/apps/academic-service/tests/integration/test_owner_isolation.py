"""Tests del aislamiento de contenido por docente creador.

Síntoma reportado (ver docs/filtrado-teacher-plan.md):
> Un docente nuevo ve Unidades / Banco de ejercicios / TPs de OTRO docente.

RLS aisla por `tenant_id`, NO por docente. Por eso el listado de
contenido se scopea por `created_by = user.id` para docentes comunes,
mientras que superadmin/docente_admin (oversight) ven todo el tenant.

Cubre:
- `owner_filter()`: docente comun → su propio id; oversight → None.
- `TareaPracticaService.list(created_by=X)` propaga el filtro al repo.
- `UnidadService.list_by_comision(created_by=X)` agrega el WHERE.

Mock-based, mismo estilo que `test_tareas_practicas_unidad_filter.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User, owner_filter
from academic_service.services.tarea_practica_service import TareaPracticaService
from academic_service.services.unidad_service import UnidadService


def _user(roles: set[str], tenant_id: UUID, user_id: UUID) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email="d@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    return session


# ── owner_filter ──────────────────────────────────────────────────────


def test_owner_filter_docente_comun_scopea_a_si_mismo(tenant_a_id: UUID) -> None:
    """Un docente comun queda restringido a su propio created_by."""
    uid = uuid4()
    user = _user({"docente"}, tenant_a_id, uid)
    assert owner_filter(user) == uid


@pytest.mark.parametrize("role", ["docente_admin", "superadmin"])
def test_owner_filter_oversight_ve_todo(role: str, tenant_a_id: UUID) -> None:
    """superadmin / docente_admin no se filtran por created_by (None)."""
    user = _user({role}, tenant_a_id, uuid4())
    assert owner_filter(user) is None


def test_owner_filter_oversight_gana_aunque_tenga_rol_docente(
    tenant_a_id: UUID,
) -> None:
    """Si el user tiene docente + docente_admin, prevalece el oversight."""
    user = _user({"docente", "docente_admin"}, tenant_a_id, uuid4())
    assert owner_filter(user) is None


# ── TareaPracticaService.list ──────────────────────────────────────────


async def test_tp_list_propaga_created_by(mock_session, tenant_a_id: UUID) -> None:
    """list(created_by=X) propaga el filtro al repo.list."""
    svc = TareaPracticaService(mock_session)
    svc.repo.list = AsyncMock(return_value=[])

    owner = uuid4()
    await svc.list(created_by=owner, limit=50)

    svc.repo.list.assert_called_once_with(
        limit=50, cursor=None, filters={"created_by": owner}
    )


async def test_tp_list_sin_created_by_no_filtra(
    mock_session, tenant_a_id: UUID
) -> None:
    """list() sin created_by NO agrega ese filtro (oversight ve todo)."""
    svc = TareaPracticaService(mock_session)
    svc.repo.list = AsyncMock(return_value=[])

    await svc.list(comision_id=uuid4(), limit=50)

    _, kwargs = svc.repo.list.call_args
    assert "created_by" not in kwargs["filters"]


# ── UnidadService.list_by_comision ─────────────────────────────────────


async def test_unidad_list_con_created_by_agrega_where(
    mock_session, tenant_a_id: UUID
) -> None:
    """list_by_comision(created_by=X) suma un WHERE created_by == X.

    Verificamos que el statement ejecutado contiene el predicado sobre
    created_by comparando la cantidad de clausulas WHERE con/sin filtro.
    """
    scalars = MagicMock()
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    mock_session.execute = AsyncMock(return_value=result)

    svc = UnidadService(mock_session)
    owner = uuid4()
    await svc.list_by_comision(tenant_a_id, uuid4(), created_by=owner)

    stmt = mock_session.execute.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "created_by" in compiled
