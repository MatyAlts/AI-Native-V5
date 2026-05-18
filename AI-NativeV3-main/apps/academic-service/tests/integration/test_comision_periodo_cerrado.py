"""Test de regla de negocio: no se puede crear comisión si el período está cerrado."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from academic_service.models import Comision, Materia, Periodo
from academic_service.schemas.comision import ComisionCreate
from academic_service.services.comision_service import ComisionService
from fastapi import HTTPException


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


async def test_no_puede_crear_comision_en_periodo_cerrado(
    mock_session, user_docente_admin_a
) -> None:
    svc = ComisionService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()

    # Mock: materia existe
    fake_materia = MagicMock(spec=Materia)
    fake_materia.id = materia_id
    fake_materia.tenant_id = user_docente_admin_a.tenant_id
    svc.materias.get_or_404 = AsyncMock(return_value=fake_materia)

    # Mock: periodo CERRADO
    fake_periodo = MagicMock(spec=Periodo)
    fake_periodo.id = periodo_id
    fake_periodo.tenant_id = user_docente_admin_a.tenant_id
    fake_periodo.codigo = "2025-S2"
    fake_periodo.estado = "cerrado"
    svc.periodos.get_or_404 = AsyncMock(return_value=fake_periodo)

    data = ComisionCreate(
        materia_id=materia_id,
        periodo_id=periodo_id,
        codigo="A",
        nombre="A-Manana",
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 400
    assert "cerrado" in exc_info.value.detail.lower()


async def test_puede_crear_comision_en_periodo_abierto(mock_session, user_docente_admin_a) -> None:
    svc = ComisionService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()

    fake_materia = MagicMock(spec=Materia)
    fake_materia.id = materia_id
    fake_materia.tenant_id = user_docente_admin_a.tenant_id
    svc.materias.get_or_404 = AsyncMock(return_value=fake_materia)

    fake_periodo = MagicMock(spec=Periodo)
    fake_periodo.id = periodo_id
    fake_periodo.tenant_id = user_docente_admin_a.tenant_id
    fake_periodo.estado = "abierto"
    svc.periodos.get_or_404 = AsyncMock(return_value=fake_periodo)

    # Mock del create del repo
    fake_comision = MagicMock(spec=Comision)
    svc.repo.create = AsyncMock(return_value=fake_comision)

    data = ComisionCreate(
        materia_id=materia_id,
        periodo_id=periodo_id,
        codigo="A",
        nombre="A-Manana",
    )

    result = await svc.create(data, user_docente_admin_a)
    assert result is fake_comision
    svc.repo.create.assert_called_once()
