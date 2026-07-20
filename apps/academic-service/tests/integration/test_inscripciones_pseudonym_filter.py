"""Tests del filtrado por membresía en `list_inscripciones` (fix QA #10).

Cubre el IDOR + leak de `student_pseudonym` reportado en CLAUDE.md. El
contrato cambió de "filtrado por ROL" a "filtrado por MEMBRESÍA": como el
gateway le infla el rol `docente` a TODO alumno, filtrar por rol era
inútil. La ruta resuelve la membresía con `assert_comision_access` (que
tira 403 si el caller no pertenece a la comisión) y propaga el resultado
al service vía el parámetro `is_staff`:

- `is_staff=False` (alumno inscripto) → solo ve su propia inscripción
  (WHERE student_pseudonym = user.id).
- `is_staff=True` (staff con membresía) → ve todas.
- `user=None` (caller interno) → ve todas (legacy).

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
        email=f"{uid}@utn.edu.ar",
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


# ── Caso A: alumno inscripto (is_staff=False) solo ve su pseudonym ─────


async def test_alumno_inscripto_solo_ve_su_propia_inscripcion(
    mock_session, tenant_a_id: UUID
) -> None:
    """Caso A — alumno inscripto pega, solo recibe su fila (NO la de B).

    `is_staff=False` lo computa la ruta vía `assert_comision_access`
    (devolvió False = alumno inscripto). El rol `docente` inflado por el
    gateway YA NO importa — el filtro depende solo de la membresía.
    """
    svc = ComisionService(mock_session)
    comision_id = uuid4()
    student_a_id = uuid4()
    student_b_id = uuid4()

    svc.repo.get_or_404 = AsyncMock(return_value=_fake_comision(comision_id, tenant_a_id))

    # El service aplica el WHERE por student_pseudonym = user.id, así que
    # el "DB" mockeado solo devolvería la fila del estudiante A.
    only_a = [_fake_inscripcion(uuid4(), tenant_a_id, comision_id, student_a_id)]
    mock_session.execute = _execute_returning(only_a)

    # Rol `docente` inflado por el gateway — irrelevante: is_staff manda.
    user_a = _user(student_a_id, tenant_a_id, "estudiante", "docente")
    result = await svc.list_inscripciones(comision_id, user=user_a, is_staff=False)

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


# ── Caso B: staff con membresía (is_staff=True) ve todos ──────────────


@pytest.mark.parametrize("rol", ["docente", "docente_admin", "superadmin", "jtp", "auxiliar"])
async def test_staff_con_membresia_ve_todas_las_inscripciones(
    mock_session, tenant_a_id: UUID, rol: str
) -> None:
    """Caso B — staff con membresía de comisión ve todos los pseudonyms.

    `is_staff=True` lo computa la ruta vía `assert_comision_access`
    (membresía en `usuarios_comision` u oversight). El rol acá es
    ilustrativo; lo que habilita la vista total es `is_staff`.
    """
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
    result = await svc.list_inscripciones(comision_id, user=docente, is_staff=True)

    assert len(result) == 3
    pseudonyms = {r.student_pseudonym for r in result}
    assert pseudonyms == {a, b, c}

    # Validar que el WHERE NO filtró por student_pseudonym (caller staff)
    call_args = mock_session.execute.call_args
    stmt = call_args.args[0]
    where_text = str(stmt.whereclause)
    assert "student_pseudonym" not in where_text


# ── Caso C: alumno inscripto sin fila propia → lista vacía ────────────


async def test_alumno_sin_fila_propia_recibe_lista_vacia(mock_session, tenant_a_id: UUID) -> None:
    """Caso C — alumno inscripto cuyo pseudonym no matchea ninguna fila.

    El filtro `WHERE student_pseudonym = user.id` no matchea, entonces el
    response es vacío. (El caso del caller que NO pertenece a la comisión
    se corta antes en la ruta con 403 vía `assert_comision_access` — no
    llega al service.)
    """
    svc = ComisionService(mock_session)
    comision_id = uuid4()
    student_id = uuid4()

    svc.repo.get_or_404 = AsyncMock(return_value=_fake_comision(comision_id, tenant_a_id))

    # Sin filas que matcheen el filtro
    mock_session.execute = _execute_returning([])

    user_alumno = _user(student_id, tenant_a_id, "estudiante", "docente")
    result = await svc.list_inscripciones(comision_id, user=user_alumno, is_staff=False)

    assert result == []


# ── Compat: callers internos sin user (legacy) ────────────────────────


async def test_caller_interno_sin_user_no_filtra(mock_session, tenant_a_id: UUID) -> None:
    """`user=None` mantiene comportamiento legacy (sin filtrado adicional).

    Aplica para callers internos que ya filtraron autorización aguas
    arriba. El WHERE no incluye student_pseudonym. El default
    `is_staff=True` no afecta este camino (la guarda es `user is not None`).
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
