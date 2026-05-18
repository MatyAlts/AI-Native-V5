"""Tests del filtro `unidad_id` en `GET /tareas-practicas` (fix QA A13).

CLAUDE.md reportaba:
> Filtro `unidad_id` en `GET /tareas-practicas` no filtra (devuelve todas).

Cubre que:
- `list()` sin `unidad_id` NO agrega ese filtro al repo (compat).
- `list(unidad_id=X)` propaga el filtro al `repo.list(filters=...)`.
- Los demás filtros (comision_id, estado) coexisten con unidad_id.

Mock-based, mismo estilo que `test_tareas_practicas_crud.py`.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.models import TareaPractica
from academic_service.services.tarea_practica_service import TareaPracticaService


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _fake_tarea(
    tid: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    unidad_id: UUID | None = None,
) -> MagicMock:
    t = MagicMock(spec=TareaPractica)
    t.id = tid
    t.tenant_id = tenant_id
    t.comision_id = comision_id
    t.unidad_id = unidad_id
    t.estado = "draft"
    t.version = 1
    t.peso = Decimal("1.0")
    t.deleted_at = None
    return t


async def test_list_sin_unidad_id_no_agrega_filtro(
    mock_session, tenant_a_id: UUID
) -> None:
    """list() sin unidad_id → repo NO recibe ese filter (comportamiento actual)."""
    svc = TareaPracticaService(mock_session)

    fake = [_fake_tarea(uuid4(), tenant_a_id, uuid4())]
    svc.repo.list = AsyncMock(return_value=fake)

    result = await svc.list(limit=50)

    assert result == fake
    svc.repo.list.assert_called_once_with(limit=50, cursor=None, filters={})


async def test_list_filtra_por_unidad_id(
    mock_session, tenant_a_id: UUID
) -> None:
    """list(unidad_id=X) propaga el filtro al repo (fix A13)."""
    svc = TareaPracticaService(mock_session)

    target_unidad = uuid4()
    fake = [_fake_tarea(uuid4(), tenant_a_id, uuid4(), unidad_id=target_unidad)]
    svc.repo.list = AsyncMock(return_value=fake)

    result = await svc.list(unidad_id=target_unidad, limit=50)

    assert result == fake
    svc.repo.list.assert_called_once_with(
        limit=50, cursor=None, filters={"unidad_id": target_unidad}
    )


async def test_list_combina_unidad_id_con_comision_y_estado(
    mock_session, tenant_a_id: UUID
) -> None:
    """unidad_id coexiste con los filtros previos (comision_id, estado)."""
    svc = TareaPracticaService(mock_session)

    target_comision = uuid4()
    target_unidad = uuid4()
    fake = [
        _fake_tarea(uuid4(), tenant_a_id, target_comision, unidad_id=target_unidad)
    ]
    svc.repo.list = AsyncMock(return_value=fake)

    result = await svc.list(
        comision_id=target_comision,
        estado="published",
        unidad_id=target_unidad,
        limit=50,
    )

    assert result == fake
    svc.repo.list.assert_called_once_with(
        limit=50,
        cursor=None,
        filters={
            "comision_id": target_comision,
            "estado": "published",
            "unidad_id": target_unidad,
        },
    )
