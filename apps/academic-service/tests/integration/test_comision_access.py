"""Tests de `assert_comision_access` (gate de LECTURA docente O alumno).

A diferencia de `assert_comision_member` (solo staff docente), este guard
habilita además a los alumnos inscriptos — es el que usan los endpoints de
lectura que consume el web-student (GET /unidades, GET /tareas-practicas y los
detalles por id). Regresión real (2026-06): alumnos inscriptos recibían 403.

Contrato:
- oversight (superadmin/docente_admin) → True (es staff), sin consultar DB.
- docente asignado (usuarios_comision) → True.
- alumno inscripto (inscripciones, no staff) → False (acceso de solo-lectura).
- ni staff ni inscripto → 403.

Mock-based, mismo estilo que `test_comision_membership.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.services.comision_service import assert_comision_access
from fastapi import HTTPException


def _user(roles: set[str], tenant_id: UUID, user_id: UUID) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email="u@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


def _rows(comision_ids: list[UUID]) -> MagicMock:
    rows = MagicMock()
    rows.all.return_value = [(cid,) for cid in comision_ids]
    return rows


def _session_seq(*results: MagicMock) -> MagicMock:
    """Mock cuyo `execute` devuelve `results[i]` en la i-ésima llamada.

    El orden de consultas de `assert_comision_access` es: (1) usuarios_comision
    (staff), (2) inscripciones (alumno) — solo si la 1ra no matcheó.
    """
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


@pytest.mark.parametrize("role", ["superadmin", "docente_admin"])
async def test_oversight_es_staff_sin_consultar(role: str, tenant_a_id: UUID) -> None:
    session = _session_seq()
    user = _user({role}, tenant_a_id, uuid4())

    assert await assert_comision_access(session, user, uuid4()) is True
    session.execute.assert_not_called()


async def test_docente_miembro_es_staff(tenant_a_id: UUID) -> None:
    com = uuid4()
    session = _session_seq(_rows([com, uuid4()]))  # usuarios_comision contiene `com`
    user = _user({"docente"}, tenant_a_id, uuid4())

    assert await assert_comision_access(session, user, com) is True


async def test_alumno_inscripto_no_staff(tenant_a_id: UUID) -> None:
    com = uuid4()
    # 1) usuarios_comision vacío  2) inscripciones contiene `com`
    session = _session_seq(_rows([]), _rows([com]))
    user = _user({"estudiante"}, tenant_a_id, uuid4())

    # Acceso permitido, pero NO es staff (no ve borradores).
    assert await assert_comision_access(session, user, com) is False


async def test_ni_staff_ni_inscripto_403(tenant_a_id: UUID) -> None:
    session = _session_seq(_rows([]), _rows([]))  # ni staff ni inscripto
    user = _user({"estudiante"}, tenant_a_id, uuid4())

    with pytest.raises(HTTPException) as exc:
        await assert_comision_access(session, user, uuid4())
    assert exc.value.status_code == 403
