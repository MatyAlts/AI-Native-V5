"""Tests del aislamiento por membresía de comisión (Capa 1).

Síntoma (docs/filtrado-teacher-plan.md): un docente ve datos de OTRA
comisión/docente. En prod todos los docentes comparten un tenant fijo,
así que la RLS no los separa — el aislamiento lo da `usuarios_comision`.

`assert_comision_member`:
- oversight (superadmin/docente_admin) → pasa sin consultar.
- docente miembro de la comisión → pasa.
- docente NO miembro → 403.

Mock-based, mismo estilo que `test_tareas_practicas_unidad_filter.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.services.comision_service import assert_comision_member
from fastapi import HTTPException


def _user(roles: set[str], tenant_id: UUID, user_id: UUID) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email="d@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


def _session_returning(comision_ids: list[UUID]) -> MagicMock:
    """Mock de sesión cuyo execute devuelve esas comisiones para el SELECT."""
    rows = MagicMock()
    rows.all.return_value = [(cid,) for cid in comision_ids]
    session = MagicMock()
    session.execute = AsyncMock(return_value=rows)
    return session


@pytest.mark.parametrize("role", ["superadmin", "docente_admin"])
async def test_oversight_pasa_sin_consultar(role: str, tenant_a_id: UUID) -> None:
    """Oversight no necesita ser miembro: pasa sin tocar la DB."""
    session = _session_returning([])
    user = _user({role}, tenant_a_id, uuid4())

    await assert_comision_member(session, user, uuid4())

    session.execute.assert_not_called()


async def test_docente_miembro_pasa(tenant_a_id: UUID) -> None:
    """Un docente asignado a la comisión pasa el guard."""
    comision = uuid4()
    session = _session_returning([comision, uuid4()])
    user = _user({"docente"}, tenant_a_id, uuid4())

    await assert_comision_member(session, user, comision)  # no levanta


async def test_docente_no_miembro_403(tenant_a_id: UUID) -> None:
    """Un docente que pide una comisión ajena recibe 403."""
    session = _session_returning([uuid4(), uuid4()])  # otras comisiones
    user = _user({"docente"}, tenant_a_id, uuid4())

    with pytest.raises(HTTPException) as exc:
        await assert_comision_member(session, user, uuid4())
    assert exc.value.status_code == 403


async def test_docente_sin_comisiones_403(tenant_a_id: UUID) -> None:
    """Un docente sin ninguna asignación no accede a ninguna comisión."""
    session = _session_returning([])
    user = _user({"docente"}, tenant_a_id, uuid4())

    with pytest.raises(HTTPException) as exc:
        await assert_comision_member(session, user, uuid4())
    assert exc.value.status_code == 403
