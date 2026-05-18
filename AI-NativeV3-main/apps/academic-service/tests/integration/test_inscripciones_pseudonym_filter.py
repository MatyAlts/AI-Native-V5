"""Tests del filtrado por rol en `list_inscripciones` (fix QA A11).

Cubre el leak de `student_pseudonym` reportado en CLAUDE.md:
- Estudiante A pega → solo ve su propia inscripción (NO la de B).
- Docente / docente_admin / superadmin / jtp / auxiliar → ven todas.
- Estudiante a una comisión donde NO está inscripto → response vacío.

Mock-based (siguen el estilo de `test_tareas_practicas_crud.py`): se
mockea el repo y la session para validar que el `WHERE` se construya
correctamente, y se inspeccionan los argumentos del `select(...)` que
llega a `session.execute`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import Comision, Inscripcion
from academic_service.services.comision_service import ComisionService


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _fake_comision(cid: UUID, tenant_id: UUID) -> MagicMock:
    c = MagicMock(spec=Comision)
    c.id = cid
    c.tenant_id = tenant_id
    return c


def _fake_inscripcion(
    insc_id: UUID,
    tenant_id: UUID,
    comision_id: UUID,
    student_pseudonym: UUID,
) -> MagicMock:
    i = MagicMock(spec=Inscripcion)
    i.id = insc_id
    i.tenant_id = tenant_id
    i.comision_id = comision_id
    i.student_pseudonym = student_pseudonym
    i.deleted_at = None
    return i


def _user(uid: UUID, tenant: UUID, *roles: str) -> User:
    return User(
        id=uid,
        tenant_id=tenant,
        email=f"{uid}@unsl.edu.ar",
        roles=frozenset(roles),
        realm=str(tenant),
    )


def _execute_returning(rows: list) -> AsyncMock:
    """Helper: AsyncMock para session.execute que devuelve un Result-like
    con .scalars().all() == rows."""
    scalars_obj = MagicMock()
    scalars_obj.all.return_value = rows
    result_obj = MagicMock()
    result_obj.scalars.return_value = scalars_obj
    return AsyncMock(return_value=result_obj)


# ── Caso A: estudiante A solo ve su pseudonym ─────────────────────────


async def test_estudiante_solo_ve_su_propia_inscripcion(
    mock_session, tenant_a_id: UUID
) -> None:
    """Caso A — estudiante A pega, solo recibe su fila (NO la de B)."""
    svc = ComisionService(mock_session)
    comision_id = uuid4()
    student_a_id = uuid4()
    student_b_id = uuid4()

    svc.repo.get_or_404 = AsyncMock(return_value=_fake_comision(comision_id, tenant_a_id))

    # El service aplica el WHERE por student_pseudonym = user.id, así que
    # el "DB" mockeado solo devolvería la fila del estudiante A.
    only_a = [_fake_inscripcion(uuid4(), tenant_a_id, comision_id, student_a_id)]
    mock_session.execute = _execute_returning(only_a)

    user_a = _user(student_a_id, tenant_a_id, "estudiante")
    result = await svc.list_inscripciones(comision_id, user=user_a)

    assert len(result) == 1
    assert result[0].student_pseudonym == student_a_id
    # No tiene que aparecer el pseudonym del estudiante B
    assert student_b_id not in {r.student_pseudonym for r in result}

    # Validar que el WHERE incluyó el filtro por student_pseudonym = user.id.
    # Solo inspeccionamos el WHERE (no el SELECT, que siempre menciona
    # todas las columnas). Sin compilar a SQL — evita conexión DB.
    call_args = mock_session.execute.call_args
    stmt = call_args.args[0]
    where_text = str(stmt.whereclause)
    assert "student_pseudonym" in where_text


# ── Caso B: docente ve todos ──────────────────────────────────────────


@pytest.mark.parametrize("rol", ["docente", "docente_admin", "superadmin", "jtp", "auxiliar"])
async def test_rol_privilegiado_ve_todas_las_inscripciones(
    mock_session, tenant_a_id: UUID, rol: str
) -> None:
    """Caso B — roles privilegiados ven todos los pseudonyms."""
    svc = ComisionService(mock_session)
    comision_id = uuid4()

    svc.repo.get_or_404 = AsyncMock(return_value=_fake_comision(comision_id, tenant_a_id))

    a, b, c = uuid4(), uuid4(), uuid4()
    rows = [
        _fake_inscripcion(uuid4(), tenant_a_id, comision_id, a),
        _fake_inscripcion(uuid4(), tenant_a_id, comision_id, b),
        _fake_inscripcion(uuid4(), tenant_a_id, comision_id, c),
    ]
    mock_session.execute = _execute_returning(rows)

    docente = _user(uuid4(), tenant_a_id, rol)
    result = await svc.list_inscripciones(comision_id, user=docente)

    assert len(result) == 3
    pseudonyms = {r.student_pseudonym for r in result}
    assert pseudonyms == {a, b, c}

    # Validar que el WHERE NO filtró por student_pseudonym (caller priv.)
    call_args = mock_session.execute.call_args
    stmt = call_args.args[0]
    where_text = str(stmt.whereclause)
    assert "student_pseudonym" not in where_text


# ── Caso C: estudiante en comisión a la que NO está inscripto ─────────


async def test_estudiante_no_inscripto_recibe_lista_vacia(
    mock_session, tenant_a_id: UUID
) -> None:
    """Caso C — estudiante pide comisión a la que NO está inscripto.

    El filtro `WHERE student_pseudonym = user.id` no matchea ninguna
    fila, entonces el response es vacío. NO es 200 con datos (eso era
    el bug).
    """
    svc = ComisionService(mock_session)
    comision_id = uuid4()
    student_id = uuid4()

    svc.repo.get_or_404 = AsyncMock(return_value=_fake_comision(comision_id, tenant_a_id))

    # Sin filas que matcheen el filtro
    mock_session.execute = _execute_returning([])

    user_outsider = _user(student_id, tenant_a_id, "estudiante")
    result = await svc.list_inscripciones(comision_id, user=user_outsider)

    assert result == []


# ── Compat: callers internos sin user (legacy) ────────────────────────


async def test_caller_interno_sin_user_no_filtra(
    mock_session, tenant_a_id: UUID
) -> None:
    """`user=None` mantiene comportamiento legacy (sin filtrado adicional).

    Aplica para callers internos que ya filtraron autorización aguas
    arriba. El WHERE no incluye student_pseudonym.
    """
    svc = ComisionService(mock_session)
    comision_id = uuid4()

    svc.repo.get_or_404 = AsyncMock(return_value=_fake_comision(comision_id, tenant_a_id))

    rows = [
        _fake_inscripcion(uuid4(), tenant_a_id, comision_id, uuid4()),
        _fake_inscripcion(uuid4(), tenant_a_id, comision_id, uuid4()),
    ]
    mock_session.execute = _execute_returning(rows)

    result = await svc.list_inscripciones(comision_id, user=None)

    assert len(result) == 2
    call_args = mock_session.execute.call_args
    stmt = call_args.args[0]
    where_text = str(stmt.whereclause)
    # No hay filtro extra por pseudonym — el WHERE solo nombra
    # comision_id y deleted_at.
    assert "student_pseudonym" not in where_text
