"""Tests CRUD del service de Periodo (PATCH + transiciones de estado).

Cubre la regla crítica para el invariante CTR de la tesis: una vez
cerrado, el periodo queda frozen. `abierto → cerrado` es one-way.

Mock-based, sigue el pattern de `test_facultades_crud.py` y
`test_comision_periodo_cerrado.py`.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Periodo
from academic_service.schemas.comision import PeriodoCreate, PeriodoUpdate
from academic_service.services.comision_service import PeriodoService
from fastapi import HTTPException


def _execute_returning(periodos: list[MagicMock]):
    """Construye un callable que simula `session.execute` devolviendo una
    lista de Periodos prefabricados (el resultset que la query de overlap
    tendría que producir contra la base real).
    """
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=periodos)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    return AsyncMock(return_value=result)


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _fake_periodo(
    pid: UUID,
    tenant_id: UUID,
    estado: str = "abierto",
    nombre: str = "Primer semestre 2026",
    fecha_inicio: date = date(2026, 3, 1),
    fecha_fin: date = date(2026, 7, 31),
) -> MagicMock:
    p = MagicMock(spec=Periodo)
    p.id = pid
    p.tenant_id = tenant_id
    p.codigo = "2026-S1"
    p.nombre = nombre
    p.fecha_inicio = fecha_inicio
    p.fecha_fin = fecha_fin
    p.estado = estado
    return p


async def test_update_nombre_ok_cuando_abierto(mock_session, user_docente_admin_a: User) -> None:
    """PATCH de `nombre` OK cuando estado=abierto + audit log escrito (RN-016)."""
    svc = PeriodoService(mock_session)
    pid = uuid4()
    fake = _fake_periodo(pid, user_docente_admin_a.tenant_id, estado="abierto")
    svc.repo.get_or_404 = AsyncMock(return_value=fake)

    data = PeriodoUpdate(nombre="Cuatrimestre otoño 2026")
    result = await svc.update(pid, data, user_docente_admin_a)

    assert result is fake
    assert fake.nombre == "Cuatrimestre otoño 2026"

    # Audit log emitido en la misma tx
    audit_calls = [
        c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditLog)
    ]
    assert len(audit_calls) == 1
    assert audit_calls[0].action == "periodo.update"
    assert audit_calls[0].resource_type == "periodo"
    assert audit_calls[0].resource_id == pid


async def test_transicion_abierto_a_cerrado_ok(mock_session, user_docente_admin_a: User) -> None:
    """`abierto → cerrado` es la transición válida (one-way)."""
    svc = PeriodoService(mock_session)
    pid = uuid4()
    fake = _fake_periodo(pid, user_docente_admin_a.tenant_id, estado="abierto")
    svc.repo.get_or_404 = AsyncMock(return_value=fake)

    data = PeriodoUpdate(estado="cerrado")
    result = await svc.update(pid, data, user_docente_admin_a)

    assert result is fake
    assert fake.estado == "cerrado"


async def test_rechaza_reabrir_periodo_cerrado(mock_session, user_docente_admin_a: User) -> None:
    """`cerrado → abierto` NO permitido — devuelve 409 Conflict.

    Protege el invariante CTR: el CTR se sella al cierre del ciclo. Si
    se necesita trazabilidad, audit log.
    """
    svc = PeriodoService(mock_session)
    pid = uuid4()
    fake = _fake_periodo(pid, user_docente_admin_a.tenant_id, estado="cerrado")
    svc.repo.get_or_404 = AsyncMock(return_value=fake)

    data = PeriodoUpdate(estado="abierto")

    with pytest.raises(HTTPException) as exc_info:
        await svc.update(pid, data, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    # El primer check que hit es "periodo cerrado, no se puede modificar"
    # — igualmente relevante (no se puede cambiar NADA estando cerrado).
    assert "cerrado" in exc_info.value.detail.lower() or "reabrir" in exc_info.value.detail.lower()


async def test_rechaza_modificar_campos_cuando_cerrado(
    mock_session, user_docente_admin_a: User
) -> None:
    """Periodo cerrado es frozen: cualquier intento de modificar (incluso
    solo nombre o fechas) debe fallar con 409.
    """
    svc = PeriodoService(mock_session)
    pid = uuid4()
    fake = _fake_periodo(pid, user_docente_admin_a.tenant_id, estado="cerrado")
    svc.repo.get_or_404 = AsyncMock(return_value=fake)

    data = PeriodoUpdate(nombre="Intento de renombrar")

    with pytest.raises(HTTPException) as exc_info:
        await svc.update(pid, data, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    assert "cerrado" in exc_info.value.detail.lower()


async def test_rechaza_fecha_fin_antes_de_inicio_en_patch(
    mock_session, user_docente_admin_a: User
) -> None:
    """Validación cruzada: si solo viene `fecha_fin` en el payload y queda
    antes de la `fecha_inicio` persistida, debe fallar con 400.
    """
    svc = PeriodoService(mock_session)
    pid = uuid4()
    fake = _fake_periodo(
        pid,
        user_docente_admin_a.tenant_id,
        estado="abierto",
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 7, 31),
    )
    svc.repo.get_or_404 = AsyncMock(return_value=fake)

    # Solo `fecha_fin` en el payload; queda antes de la `fecha_inicio`
    # persistida (2026-03-01).
    data = PeriodoUpdate(fecha_fin=date(2026, 1, 15))

    with pytest.raises(HTTPException) as exc_info:
        await svc.update(pid, data, user_docente_admin_a)

    assert exc_info.value.status_code == 400
    assert "fecha_fin" in exc_info.value.detail.lower()


# --- Overlap validation (RN emergente de la tesis: invariante CTR) ----------
# Dos periodos del mismo tenant no pueden solaparse en el tiempo. Adyacentes
# (fecha_fin de uno == fecha_inicio del siguiente) se consideran NO overlap
# (día compartido es aceptable — cierre de uno coincide con inicio de otro).


async def test_periodo_create_rejects_overlap(mock_session, user_docente_admin_a: User) -> None:
    """Crear P2 (Apr-Jul) cuando ya existe P1 (Feb-Jun) falla con 409.

    El mensaje de error incluye el código del periodo con el que se
    solapa, para que el front pueda mostrárselo al docente.
    """
    tenant_id = user_docente_admin_a.tenant_id
    p_existente = _fake_periodo(
        uuid4(),
        tenant_id,
        estado="abierto",
        fecha_inicio=date(2026, 2, 1),
        fecha_fin=date(2026, 6, 30),
    )
    p_existente.codigo = "2026-S1"

    svc = PeriodoService(mock_session)
    mock_session.execute = _execute_returning([p_existente])
    svc.repo.create = AsyncMock()  # no debería llamarse

    data = PeriodoCreate(
        codigo="2026-INT",
        nombre="Intensivo otoño",
        fecha_inicio=date(2026, 4, 1),
        fecha_fin=date(2026, 7, 31),
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.create(data, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    assert "solapan" in exc_info.value.detail.lower()
    assert "2026-S1" in exc_info.value.detail
    svc.repo.create.assert_not_awaited()


async def test_periodo_create_adjacent_ok(mock_session, user_docente_admin_a: User) -> None:
    """P1 (Feb-Jun) + P2 (Jun-Dic, inicio == fin de P1) → 201 OK.

    Adyacencia NO es overlap: el día de cierre puede coincidir con el
    día de apertura del siguiente periodo.
    """
    tenant_id = user_docente_admin_a.tenant_id
    svc = PeriodoService(mock_session)
    # Overlap query devuelve [] — ningún periodo se solapa con Jun-Dic,
    # aunque P1 termine justamente el 2026-06-30.
    mock_session.execute = _execute_returning([])

    created = _fake_periodo(
        uuid4(),
        tenant_id,
        estado="abierto",
        fecha_inicio=date(2026, 6, 30),
        fecha_fin=date(2026, 12, 15),
    )
    created.codigo = "2026-S2"
    svc.repo.create = AsyncMock(return_value=created)

    data = PeriodoCreate(
        codigo="2026-S2",
        nombre="Segundo semestre 2026",
        fecha_inicio=date(2026, 6, 30),
        fecha_fin=date(2026, 12, 15),
    )

    result = await svc.create(data, user_docente_admin_a)

    assert result is created
    svc.repo.create.assert_awaited_once()


async def test_periodo_update_rejects_overlap(mock_session, user_docente_admin_a: User) -> None:
    """PATCH de P2 que lo mete adentro del rango de P1 → 409.

    Contexto: P1=[Feb, Jun], P2=[Jul, Dic]. El docente intenta mover
    P2.fecha_inicio a May (dentro de P1). La query de overlap devuelve
    P1 (excluyendo el propio P2 por `id`).
    """
    tenant_id = user_docente_admin_a.tenant_id
    p1 = _fake_periodo(
        uuid4(),
        tenant_id,
        estado="abierto",
        fecha_inicio=date(2026, 2, 1),
        fecha_fin=date(2026, 6, 30),
    )
    p1.codigo = "2026-S1"

    pid2 = uuid4()
    p2 = _fake_periodo(
        pid2,
        tenant_id,
        estado="abierto",
        fecha_inicio=date(2026, 7, 1),
        fecha_fin=date(2026, 12, 15),
    )
    p2.codigo = "2026-S2"

    svc = PeriodoService(mock_session)
    svc.repo.get_or_404 = AsyncMock(return_value=p2)
    mock_session.execute = _execute_returning([p1])

    # Mover P2 adentro de P1: inicio=May, fin=Dic → overlap con P1.
    data = PeriodoUpdate(fecha_inicio=date(2026, 5, 1))

    with pytest.raises(HTTPException) as exc_info:
        await svc.update(pid2, data, user_docente_admin_a)

    assert exc_info.value.status_code == 409
    assert "solapan" in exc_info.value.detail.lower()
    assert "2026-S1" in exc_info.value.detail


async def test_periodo_update_can_extend_without_overlap(
    mock_session, user_docente_admin_a: User
) -> None:
    """Extender fecha_fin de P1 cuando es el único periodo → 200 OK.

    P1=[Feb, Jun] es el único periodo del tenant. El docente lo extiende
    a Dic. La query de overlap (excluyendo el propio P1) devuelve [].
    """
    tenant_id = user_docente_admin_a.tenant_id
    pid = uuid4()
    p1 = _fake_periodo(
        pid,
        tenant_id,
        estado="abierto",
        fecha_inicio=date(2026, 2, 1),
        fecha_fin=date(2026, 6, 30),
    )
    p1.codigo = "2026-S1"

    svc = PeriodoService(mock_session)
    svc.repo.get_or_404 = AsyncMock(return_value=p1)
    mock_session.execute = _execute_returning([])

    data = PeriodoUpdate(fecha_fin=date(2026, 12, 15))

    result = await svc.update(pid, data, user_docente_admin_a)

    assert result is p1
    assert p1.fecha_fin == date(2026, 12, 15)
