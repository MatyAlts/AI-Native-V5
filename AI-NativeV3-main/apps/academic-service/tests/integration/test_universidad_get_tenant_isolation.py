"""Tests de aislamiento multi-tenant en `GET /universidades/{id}` (A0.2).

Regresion del leak cross-tenant: antes `UniversidadService.get()` seteaba
`app.current_tenant` a la universidad TARGET incondicionalmente, asi que
cualquiera con el UUID de otra universidad la leia. Ahora el tenant del
caller acota el acceso; una universidad de OTRO tenant devuelve 404 (no
403, para no confirmar existencia).

Mock-based (mismo estilo que test_facultades_crud.py / test_soft_delete.py):
cubre la logica de dominio del service sin Postgres real. El aislamiento a
nivel DB con RLS lo cubre test_rls_isolation.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import Universidad
from academic_service.services.universidad_service import UniversidadService
from fastapi import HTTPException


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def tenant_a_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def tenant_b_id() -> UUID:
    return UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def user_docente_admin_a(tenant_a_id: UUID) -> User:
    """Docente-admin del tenant A (su universidad ES el tenant: id == tenant_id)."""
    return User(
        id=uuid4(),
        tenant_id=tenant_a_id,
        email="admin-a@utn.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm=str(tenant_a_id),
    )


@pytest.fixture
def superadmin_user() -> User:
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="root@utn.edu.ar",
        roles=frozenset({"superadmin"}),
        realm="utn",
    )


def _fake_universidad(uid: UUID) -> MagicMock:
    u = MagicMock(spec=Universidad)
    u.id = uid
    u.tenant_id = uid
    return u


async def test_get_universidad_de_otro_tenant_da_404(
    mock_session, user_docente_admin_a: User, tenant_b_id: UUID
) -> None:
    """El leak A0.2: docente_admin del tenant A pide la universidad del tenant B.

    Debe recibir 404 (no 403) y el service NO debe siquiera consultar el repo
    con el id ajeno (no confirmamos existencia de universidades ajenas).
    """
    svc = UniversidadService(mock_session)
    svc.repo.get_or_404 = AsyncMock(return_value=_fake_universidad(tenant_b_id))

    with pytest.raises(HTTPException) as exc_info:
        await svc.get(tenant_b_id, user_docente_admin_a)

    assert exc_info.value.status_code == 404
    # No se filtra existencia: nunca se consulta la universidad ajena.
    svc.repo.get_or_404.assert_not_called()


async def test_get_propia_universidad_funciona(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """Acceso legitimo preservado: el docente_admin lee SU propia universidad."""
    svc = UniversidadService(mock_session)
    propia = _fake_universidad(tenant_a_id)
    svc.repo.get_or_404 = AsyncMock(return_value=propia)

    result = await svc.get(tenant_a_id, user_docente_admin_a)

    assert result is propia
    svc.repo.get_or_404.assert_called_once_with(tenant_a_id)


async def test_get_superadmin_lee_cualquier_universidad(
    mock_session, superadmin_user: User
) -> None:
    """superadmin opera cross-tenant legitimamente (selector del web-admin)."""
    svc = UniversidadService(mock_session)
    otra_uni_id = uuid4()
    otra = _fake_universidad(otra_uni_id)
    svc.repo.get_or_404 = AsyncMock(return_value=otra)

    result = await svc.get(otra_uni_id, superadmin_user)

    assert result is otra
    svc.repo.get_or_404.assert_called_once_with(otra_uni_id)
