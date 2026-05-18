"""Tests de soft-delete con validación de cascadas para los 4 entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.services.comision_service import (
    ComisionService,
    PeriodoService,
)
from academic_service.services.materia_service import MateriaService
from academic_service.services.universidad_service import UniversidadService
from fastapi import HTTPException


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def superadmin_user():
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="root@unsl.edu.ar",
        roles=frozenset({"superadmin"}),
        realm="unsl",
    )


@pytest.fixture
def docente_admin_user():
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="admin@unsl.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm="unsl",
    )


# ── Universidad ──────────────────────────────────────────────────


async def test_universidad_soft_delete_happy_path(mock_session, superadmin_user) -> None:
    svc = UniversidadService(mock_session)
    universidad_id = uuid4()

    svc.carreras.count = AsyncMock(return_value=0)

    fake_universidad = MagicMock(spec=["id", "tenant_id"])
    fake_universidad.id = universidad_id
    fake_universidad.tenant_id = universidad_id
    svc.repo.soft_delete = AsyncMock(return_value=fake_universidad)

    result = await svc.soft_delete(universidad_id, superadmin_user)
    assert result is fake_universidad
    svc.repo.soft_delete.assert_called_once_with(universidad_id)
    mock_session.add.assert_called_once()


async def test_universidad_soft_delete_rejects_with_active_children(
    mock_session, superadmin_user
) -> None:
    svc = UniversidadService(mock_session)
    universidad_id = uuid4()

    svc.carreras.count = AsyncMock(return_value=3)

    with pytest.raises(HTTPException) as exc_info:
        await svc.soft_delete(universidad_id, superadmin_user)

    assert exc_info.value.status_code == 409
    assert "3 carreras activas" in exc_info.value.detail


# ── Materia ──────────────────────────────────────────────────────


async def test_materia_soft_delete_happy_path(mock_session, docente_admin_user) -> None:
    svc = MateriaService(mock_session)
    materia_id = uuid4()

    svc.comisiones.count = AsyncMock(return_value=0)

    fake_materia = MagicMock(spec=["id", "tenant_id"])
    fake_materia.id = materia_id
    fake_materia.tenant_id = docente_admin_user.tenant_id
    svc.repo.soft_delete = AsyncMock(return_value=fake_materia)

    result = await svc.soft_delete(materia_id, docente_admin_user)
    assert result is fake_materia
    svc.repo.soft_delete.assert_called_once_with(materia_id)
    mock_session.add.assert_called_once()


async def test_materia_soft_delete_rejects_with_active_children(
    mock_session, docente_admin_user
) -> None:
    svc = MateriaService(mock_session)
    materia_id = uuid4()

    svc.comisiones.count = AsyncMock(return_value=2)

    with pytest.raises(HTTPException) as exc_info:
        await svc.soft_delete(materia_id, docente_admin_user)

    assert exc_info.value.status_code == 409
    assert "2 comisiones activas" in exc_info.value.detail


# ── Comisión ─────────────────────────────────────────────────────


async def test_comision_soft_delete_happy_path(mock_session, docente_admin_user) -> None:
    svc = ComisionService(mock_session)
    comision_id = uuid4()

    svc.inscripciones.count = AsyncMock(return_value=0)

    fake_comision = MagicMock(spec=["id", "tenant_id"])
    fake_comision.id = comision_id
    fake_comision.tenant_id = docente_admin_user.tenant_id
    svc.repo.soft_delete = AsyncMock(return_value=fake_comision)

    result = await svc.soft_delete(comision_id, docente_admin_user)
    assert result is fake_comision
    svc.repo.soft_delete.assert_called_once_with(comision_id)
    mock_session.add.assert_called_once()


async def test_comision_soft_delete_rejects_with_active_children(
    mock_session, docente_admin_user
) -> None:
    svc = ComisionService(mock_session)
    comision_id = uuid4()

    svc.inscripciones.count = AsyncMock(return_value=15)

    with pytest.raises(HTTPException) as exc_info:
        await svc.soft_delete(comision_id, docente_admin_user)

    assert exc_info.value.status_code == 409
    assert "15 inscripciones activas" in exc_info.value.detail


# ── Periodo ──────────────────────────────────────────────────────


async def test_periodo_soft_delete_happy_path(mock_session, docente_admin_user) -> None:
    svc = PeriodoService(mock_session)
    periodo_id = uuid4()

    svc.comisiones.count = AsyncMock(return_value=0)

    fake_periodo = MagicMock(spec=["id", "tenant_id"])
    fake_periodo.id = periodo_id
    fake_periodo.tenant_id = docente_admin_user.tenant_id
    svc.repo.soft_delete = AsyncMock(return_value=fake_periodo)

    result = await svc.soft_delete(periodo_id, docente_admin_user)
    assert result is fake_periodo
    svc.repo.soft_delete.assert_called_once_with(periodo_id)
    mock_session.add.assert_called_once()


async def test_periodo_soft_delete_rejects_with_active_children(
    mock_session, docente_admin_user
) -> None:
    svc = PeriodoService(mock_session)
    periodo_id = uuid4()

    svc.comisiones.count = AsyncMock(return_value=4)

    with pytest.raises(HTTPException) as exc_info:
        await svc.soft_delete(periodo_id, docente_admin_user)

    assert exc_info.value.status_code == 409
    assert "4 comisiones activas" in exc_info.value.detail


# ── Universidad RBAC ─────────────────────────────────────────────


async def test_universidad_soft_delete_rejects_non_superadmin(
    mock_session, docente_admin_user
) -> None:
    svc = UniversidadService(mock_session)
    universidad_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await svc.soft_delete(universidad_id, docente_admin_user)

    assert exc_info.value.status_code == 403
