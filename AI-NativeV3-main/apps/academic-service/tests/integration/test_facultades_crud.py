"""Tests CRUD del service de Facultad.

Mock-based: cubre lógica de dominio (validación FK, audit log, soft delete,
filtrado, RLS por tenant) sin requerir Postgres real. Sigue el estilo de
test_comision_periodo_cerrado.py.

El test de RLS multi-tenant a nivel DB vive en test_rls_isolation.py — acá
verificamos el aislamiento a nivel de service (que el repo filtre por tenant
del user activo, que es lo que el caller HTTP termina invocando).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Facultad, Universidad
from academic_service.schemas.facultad import FacultadCreate, FacultadUpdate
from academic_service.services.facultad_service import FacultadService
from fastapi import HTTPException


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def tenant_a_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def tenant_b_id() -> UUID:
    return UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def user_docente_admin_a(tenant_a_id: UUID) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_a_id,
        email="admin-a@unsl.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm=str(tenant_a_id),
    )


@pytest.fixture
def user_docente_admin_b(tenant_b_id: UUID) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_b_id,
        email="admin-b@otra.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm=str(tenant_b_id),
    )


def _fake_universidad(uid: UUID) -> MagicMock:
    u = MagicMock(spec=Universidad)
    u.id = uid
    u.nombre = "U"
    u.codigo = "U"
    u.keycloak_realm = "u"
    return u


def _fake_facultad(fid: UUID, tenant_id: UUID, universidad_id: UUID, **kw) -> MagicMock:
    f = MagicMock(spec=Facultad)
    f.id = fid
    f.tenant_id = tenant_id
    f.universidad_id = universidad_id
    f.nombre = kw.get("nombre", "FCFMyN")
    f.codigo = kw.get("codigo", "FCFMYN")
    f.decano_user_id = kw.get("decano_user_id")
    f.deleted_at = kw.get("deleted_at")
    return f


async def test_facultad_create_happy_path(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """POST devuelve 201 y se inserta una fila de audit_log en la misma tx."""
    svc = FacultadService(mock_session)

    # universidad_id == tenant_id del user (caso normal)
    universidad = _fake_universidad(tenant_a_id)
    svc.universidades.get_or_404 = AsyncMock(return_value=universidad)

    fake_fac = MagicMock(spec=Facultad)
    svc.repo.create = AsyncMock(return_value=fake_fac)

    data = FacultadCreate(
        universidad_id=tenant_a_id,
        nombre="Facultad de Ciencias",
        codigo="FCFMYN",
    )

    result = await svc.create(data, user_docente_admin_a)

    assert result is fake_fac
    svc.repo.create.assert_called_once()

    # Verificar que se agregó el audit log a la misma sesión (RN-016)
    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    audit = audit_calls[0]
    assert audit.action == "facultad.create"
    assert audit.resource_type == "facultad"
    assert audit.tenant_id == tenant_a_id


async def test_facultad_create_universidad_inexistente_404(
    mock_session, user_docente_admin_a: User
) -> None:
    """Si la universidad no existe, propaga HTTPException 404 del repo."""
    svc = FacultadService(mock_session)

    svc.universidades.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Universidad no encontrada")
    )

    data = FacultadCreate(
        universidad_id=uuid4(),
        nombre="Facultad fantasma",
        codigo="FANTA",
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 404


async def test_facultad_create_otra_universidad_403(
    mock_session, user_docente_admin_a: User
) -> None:
    """Un docente_admin no puede crear facultades en otra universidad."""
    svc = FacultadService(mock_session)

    otra_uni_id = uuid4()
    universidad = _fake_universidad(otra_uni_id)
    svc.universidades.get_or_404 = AsyncMock(return_value=universidad)

    data = FacultadCreate(
        universidad_id=otra_uni_id,
        nombre="Facultad ajena",
        codigo="AJENA",
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 403


async def test_facultad_list_filtra_por_universidad(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """list(universidad_id=X) propaga el filtro al repo."""
    svc = FacultadService(mock_session)

    target_uni = uuid4()
    fake_facs = [_fake_facultad(uuid4(), tenant_a_id, target_uni)]
    svc.repo.list = AsyncMock(return_value=fake_facs)

    result = await svc.list(limit=50, universidad_id=target_uni)

    assert result == fake_facs
    svc.repo.list.assert_called_once_with(
        limit=50, cursor=None, filters={"universidad_id": target_uni}
    )


async def test_facultad_get_one_404(mock_session) -> None:
    """get(id) propaga 404 cuando el repo no encuentra el row."""
    svc = FacultadService(mock_session)

    svc.repo.get_or_404 = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Facultad no encontrada")
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.get(uuid4())

    assert exc_info.value.status_code == 404


async def test_facultad_update_happy_path(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """PATCH aplica los cambios al obj y registra audit log."""
    svc = FacultadService(mock_session)

    fac_id = uuid4()
    obj = _fake_facultad(fac_id, tenant_a_id, tenant_a_id, nombre="Vieja")
    svc.repo.get_or_404 = AsyncMock(return_value=obj)

    data = FacultadUpdate(nombre="Nueva Facultad")
    result = await svc.update(fac_id, data, user_docente_admin_a)

    assert result.nombre == "Nueva Facultad"

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "facultad.update"
    assert audit_calls[0].resource_id == fac_id


async def test_facultad_soft_delete(
    mock_session, user_docente_admin_a: User, tenant_a_id: UUID
) -> None:
    """DELETE invoca repo.soft_delete y registra audit log."""
    svc = FacultadService(mock_session)

    fac_id = uuid4()
    obj = _fake_facultad(fac_id, tenant_a_id, tenant_a_id)
    svc.repo.soft_delete = AsyncMock(return_value=obj)

    result = await svc.soft_delete(fac_id, user_docente_admin_a)

    assert result is obj
    svc.repo.soft_delete.assert_called_once_with(fac_id)

    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "facultad.delete"
    assert audit_calls[0].changes == {"soft_delete": True}


async def test_facultad_rls_isolation(
    mock_session,
    user_docente_admin_a: User,
    user_docente_admin_b: User,
    tenant_a_id: UUID,
    tenant_b_id: UUID,
) -> None:
    """Aislamiento por tenant a nivel service.

    El repo recibe la session del user activo (que en producción tiene
    SET LOCAL app.current_tenant via tenant_session()). Acá verificamos
    que dos services con users de tenants distintos no comparten estado:
    cada uno escribe audit logs con su propio tenant_id, y los listados
    reflejan lo que el repo retorna para ESE tenant.

    El aislamiento real a nivel DB lo cubre test_rls_isolation.py.
    """
    # Service del tenant A crea una facultad
    svc_a = FacultadService(mock_session)
    universidad_a = _fake_universidad(tenant_a_id)
    svc_a.universidades.get_or_404 = AsyncMock(return_value=universidad_a)
    svc_a.repo.create = AsyncMock(return_value=MagicMock(spec=Facultad))

    await svc_a.create(
        FacultadCreate(universidad_id=tenant_a_id, nombre="Facultad A", codigo="FA"),
        user_docente_admin_a,
    )

    # Service del tenant B lista — el repo simula RLS devolviendo vacío
    svc_b = FacultadService(mock_session)
    svc_b.repo.list = AsyncMock(return_value=[])

    result = await svc_b.list(limit=50, universidad_id=tenant_a_id)

    assert result == []

    # Cada audit log usa el tenant_id de SU user (no se cruzan)
    audit_logs = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert all(a.tenant_id == tenant_a_id for a in audit_logs)
    assert not any(a.tenant_id == tenant_b_id for a in audit_logs)
