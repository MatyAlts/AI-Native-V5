"""Tests del endpoint GET /api/v1/comisiones/mis.

Cubren la lógica del service `ComisionService.list_for_user`: un docente
sólo ve las comisiones donde tiene una asignación activa en
`usuarios_comision`; otro docente del mismo tenant no ve las del primero.
Estilo mock-based, alineado con `test_facultades_crud.py` y
`test_comision_periodo_cerrado.py`.

El aislamiento RLS multi-tenant a nivel DB lo cubre `test_rls_isolation.py`;
acá verificamos el filtrado por user_id que es la lógica de aplicación.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import Comision
from academic_service.services.comision_service import ComisionService
from sqlalchemy.dialects import postgresql


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _user(tenant_id: UUID, *, user_id: UUID | None = None, role: str = "docente") -> User:
    return User(
        id=user_id or uuid4(),
        tenant_id=tenant_id,
        email=f"{role}@unsl.edu.ar",
        roles=frozenset({role}),
        realm=str(tenant_id),
    )


def _fake_comision(cid: UUID, tenant_id: UUID) -> MagicMock:
    c = MagicMock(spec=Comision)
    c.id = cid
    c.tenant_id = tenant_id
    return c


async def test_list_for_user_returns_only_user_comisiones(mock_session) -> None:
    """`list_for_user` ejecuta el JOIN y devuelve lo que la query produce.

    En vez de mockear el SQL real (frágil), verificamos contra una
    `session.execute` que devuelve un resultset prefabricado. La
    correctness del JOIN se ejercita con base real en el test
    end-to-end de `test_rls_isolation.py`.
    """
    tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    docente = _user(tenant_id)

    com_a = _fake_comision(uuid4(), tenant_id)
    com_b = _fake_comision(uuid4(), tenant_id)

    scalars = MagicMock()
    unique = MagicMock()
    unique.all = MagicMock(return_value=[com_a, com_b])
    scalars.unique = MagicMock(return_value=unique)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    mock_session.execute = AsyncMock(return_value=result)

    svc = ComisionService(mock_session)
    items = await svc.list_for_user(user_id=docente.id)

    assert items == [com_a, com_b]
    mock_session.execute.assert_awaited_once()


async def test_list_for_user_empty_when_no_assignments(mock_session) -> None:
    """Un docente sin asignaciones activas obtiene lista vacía (no 404)."""
    tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    docente_solitario = _user(tenant_id)

    scalars = MagicMock()
    unique = MagicMock()
    unique.all = MagicMock(return_value=[])
    scalars.unique = MagicMock(return_value=unique)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    mock_session.execute = AsyncMock(return_value=result)

    svc = ComisionService(mock_session)
    items = await svc.list_for_user(user_id=docente_solitario.id)

    assert items == []


async def test_list_for_user_isolates_between_users(mock_session) -> None:
    """Dos docentes distintos del mismo tenant ven sets disjuntos.

    Modelamos `session.execute` devolviendo distinto resultset según el
    user_id que aparece en la query — equivalente a lo que el JOIN real
    haría contra `usuarios_comision`.
    """
    tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    docente_x = _user(tenant_id)
    docente_y = _user(tenant_id)

    com_x = _fake_comision(uuid4(), tenant_id)
    com_y = _fake_comision(uuid4(), tenant_id)

    def _execute(stmt):
        # Heurística simple: detectamos cuál user_id está siendo filtrado
        # leyendo la WHERE clause renderizada como string.
        rendered = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        scalars = MagicMock()
        unique = MagicMock()
        if str(docente_x.id) in rendered:
            unique.all = MagicMock(return_value=[com_x])
        elif str(docente_y.id) in rendered:
            unique.all = MagicMock(return_value=[com_y])
        else:
            unique.all = MagicMock(return_value=[])
        scalars.unique = MagicMock(return_value=unique)
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)

    svc = ComisionService(mock_session)
    items_x = await svc.list_for_user(user_id=docente_x.id)
    items_y = await svc.list_for_user(user_id=docente_y.id)

    assert items_x == [com_x]
    assert items_y == [com_y]
    # Cross-check: ningún docente ve la comisión del otro
    assert com_y not in items_x
    assert com_x not in items_y


async def test_list_for_user_respects_limit_param(mock_session) -> None:
    """El parámetro `limit` se aplica a la query (no en memoria)."""
    tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    docente = _user(tenant_id)

    captured: dict = {}

    def _execute(stmt):
        captured["sql"] = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        scalars = MagicMock()
        unique = MagicMock()
        unique.all = MagicMock(return_value=[])
        scalars.unique = MagicMock(return_value=unique)
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)

    svc = ComisionService(mock_session)
    await svc.list_for_user(user_id=docente.id, limit=5)

    assert "LIMIT 5" in captured["sql"]
