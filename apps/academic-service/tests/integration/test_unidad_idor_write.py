"""Tests del guard de escritura (IDOR A0.6) en `UnidadService`.

Bug A0.6 (parte academic): los verbos de ESCRITURA de Unidades
(create/update/soft_delete/reorder) no validaban que el docente perteneciera
a la comisión sobre la que escribían — un docente podía crear/editar/borrar
Unidades de comisiones ajenas. El fix agrega `assert_comision_member` (mismo
gate que usa la gestión docente en `comisiones`/`student_profiles`) al inicio
de cada verbo de escritura.

Contrato del fix:
- docente NO asignado a la comisión de la Unidad → 403 en todo verbo de
  escritura (sin poder mutar nada).
- docente asignado → la operación procede normalmente (acceso legítimo
  preservado).
- oversight (superadmin/docente_admin) → pasa sin consultar `usuarios_comision`.

Mock-based (sin Postgres), mismo estilo que `test_comision_access.py` y
`test_tareas_practicas_crud.py`. El orden de `session.execute` que asume cada
test replica el flujo del service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import Unidad
from academic_service.schemas.unidad import (
    UnidadCreate,
    UnidadReorderItem,
    UnidadUpdate,
)
from academic_service.services.unidad_service import UnidadService
from fastapi import HTTPException


def _user(roles: set[str], tenant_id: UUID, user_id: UUID | None = None) -> User:
    return User(
        id=user_id or uuid4(),
        tenant_id=tenant_id,
        email="u@example.com",
        roles=frozenset(roles),
        realm=str(tenant_id),
    )


def _result_scalar(obj: object | None) -> MagicMock:
    """Resultado de un `select(...).scalar_one_or_none()` (get_by_id / _find_by_nombre)."""
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _result_rows(comision_ids: list[UUID]) -> MagicMock:
    """Resultado del `select(UsuarioComision.comision_id)` de `comisiones_del_usuario`."""
    r = MagicMock()
    r.all = MagicMock(return_value=[(cid,) for cid in comision_ids])
    return r


def _session(*results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _fake_unidad(comision_id: UUID, tenant_id: UUID) -> MagicMock:
    u = MagicMock(spec=Unidad)
    u.id = uuid4()
    u.tenant_id = tenant_id
    u.comision_id = comision_id
    u.nombre = "U1"
    u.orden = 0
    return u


# ── CREATE ────────────────────────────────────────────────────────────────


async def test_create_docente_ajeno_403(tenant_a_id: UUID) -> None:
    """Un docente no-miembro no puede crear una Unidad en comisión ajena."""
    com = uuid4()
    # 1er execute: comisiones_del_usuario → vacío (no es miembro).
    session = _session(_result_rows([]))
    svc = UnidadService(session)
    # get_or_404 no debería llegar a ejecutarse (403 antes).
    svc.comisiones.get_or_404 = AsyncMock()  # type: ignore[method-assign]
    user = _user({"docente"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await svc.create(UnidadCreate(comision_id=com, nombre="U1"), user)
    assert exc.value.status_code == 403
    svc.comisiones.get_or_404.assert_not_called()


async def test_create_docente_miembro_ok(tenant_a_id: UUID) -> None:
    """El docente asignado a la comisión sí puede crear (acceso legítimo)."""
    com = uuid4()
    # 1) membresía OK  2) _find_by_nombre → None (no duplicado)
    session = _session(_result_rows([com]), _result_scalar(None))
    svc = UnidadService(session)
    svc.comisiones.get_or_404 = AsyncMock(  # type: ignore[method-assign]
        return_value=_fake_unidad(com, tenant_a_id)
    )
    user = _user({"docente"}, tenant_a_id)

    obj = await svc.create(UnidadCreate(comision_id=com, nombre="U1"), user)
    assert obj.comision_id == com
    session.flush.assert_awaited()


# ── UPDATE (PATCH) ─────────────────────────────────────────────────────────


async def test_update_docente_ajeno_403(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    # 1) get_by_id → unidad  2) comisiones_del_usuario → vacío
    session = _session(_result_scalar(unidad), _result_rows([]))
    svc = UnidadService(session)
    user = _user({"docente"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await svc.update(unidad.id, UnidadUpdate(nombre="nuevo"), user)
    assert exc.value.status_code == 403
    session.flush.assert_not_called()


async def test_update_docente_miembro_ok(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    # 1) get_by_id → unidad  2) membresía OK  (no cambia nombre → sin _find_by_nombre)
    session = _session(_result_scalar(unidad), _result_rows([com]))
    svc = UnidadService(session)
    user = _user({"docente"}, tenant_a_id)

    await svc.update(unidad.id, UnidadUpdate(orden=5), user)
    assert unidad.orden == 5
    session.flush.assert_awaited()


# ── DELETE (soft-delete) ───────────────────────────────────────────────────


async def test_soft_delete_docente_ajeno_403(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    session = _session(_result_scalar(unidad), _result_rows([]))
    svc = UnidadService(session)
    user = _user({"docente"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await svc.soft_delete(unidad.id, user)
    assert exc.value.status_code == 403
    session.flush.assert_not_called()


async def test_soft_delete_docente_miembro_ok(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    session = _session(_result_scalar(unidad), _result_rows([com]))
    svc = UnidadService(session)
    user = _user({"docente"}, tenant_a_id)

    await svc.soft_delete(unidad.id, user)
    assert unidad.deleted_at is not None
    session.flush.assert_awaited()


# ── REORDER ────────────────────────────────────────────────────────────────


async def test_reorder_docente_ajeno_403(tenant_a_id: UUID) -> None:
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    # 1) select de las unidades del batch  2) comisiones_del_usuario → vacío
    batch_result = MagicMock()
    batch_scalars = MagicMock()
    batch_scalars.all = MagicMock(return_value=[unidad])
    batch_result.scalars = MagicMock(return_value=batch_scalars)
    session = _session(batch_result, _result_rows([]))
    svc = UnidadService(session)
    user = _user({"docente"}, tenant_a_id)

    with pytest.raises(HTTPException) as exc:
        await svc.reorder([UnidadReorderItem(id=unidad.id, orden=1)], user)
    assert exc.value.status_code == 403
    session.flush.assert_not_called()


# ── OVERSIGHT (no se le exige membresía) ────────────────────────────────────


async def test_soft_delete_oversight_no_consulta_membresia(tenant_a_id: UUID) -> None:
    """docente_admin borra sin que se consulte `usuarios_comision`."""
    com = uuid4()
    unidad = _fake_unidad(com, tenant_a_id)
    # Solo el get_by_id ejecuta; el guard corta antes de la query de membresía.
    session = _session(_result_scalar(unidad))
    svc = UnidadService(session)
    user = _user({"docente_admin"}, tenant_a_id)

    await svc.soft_delete(unidad.id, user)
    assert unidad.deleted_at is not None
    # 1 sola query (get_by_id) — oversight no dispara comisiones_del_usuario.
    assert session.execute.await_count == 1
