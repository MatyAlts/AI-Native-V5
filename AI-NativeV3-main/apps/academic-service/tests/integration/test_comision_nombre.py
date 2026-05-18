"""Tests del flujo `nombre` en Comision (capability academic-comisiones).

Verifica que:
- POST con `nombre` valido lo persiste al repo (a) `nombre=""` falla 422
  via schema (cubierto en `tests/unit/test_schemas.py`).
- GET devuelve `nombre` (covered by ComisionOut hereda de ComisionBase).
- PATCH actualiza `nombre` sin tocar `codigo`.

Estilo mock-based, alineado con `test_comision_periodo_cerrado.py`. El
test de migracion + persistencia real con Postgres queda cubierto por
`test_rls_isolation.py` y por la verificacion E2E del piloto.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from academic_service.models import Comision, Materia, Periodo
from academic_service.schemas.comision import ComisionCreate, ComisionUpdate
from academic_service.services.comision_service import ComisionService


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


async def test_create_persiste_nombre(mock_session, user_docente_admin_a) -> None:
    """`ComisionService.create` pasa `nombre` al repo.create."""
    svc = ComisionService(mock_session)

    materia_id = uuid4()
    periodo_id = uuid4()

    fake_materia = MagicMock(spec=Materia)
    fake_materia.id = materia_id
    fake_materia.tenant_id = user_docente_admin_a.tenant_id
    svc.materias.get_or_404 = AsyncMock(return_value=fake_materia)

    fake_periodo = MagicMock(spec=Periodo)
    fake_periodo.id = periodo_id
    fake_periodo.tenant_id = user_docente_admin_a.tenant_id
    fake_periodo.estado = "abierto"
    svc.periodos.get_or_404 = AsyncMock(return_value=fake_periodo)

    fake_comision = MagicMock(spec=Comision)
    svc.repo.create = AsyncMock(return_value=fake_comision)

    data = ComisionCreate(
        materia_id=materia_id,
        periodo_id=periodo_id,
        codigo="A",
        nombre="A-Manana",
    )

    result = await svc.create(data, user_docente_admin_a)
    assert result is fake_comision

    # El payload pasado al repo incluye `nombre`
    call_args = svc.repo.create.call_args
    payload = call_args.args[0] if call_args.args else call_args.kwargs.get("payload", {})
    assert payload["nombre"] == "A-Manana"
    assert payload["codigo"] == "A"


async def test_update_nombre_no_toca_codigo(mock_session, user_docente_admin_a) -> None:
    """PATCH con solo `nombre` no modifica `codigo` del objeto persistido."""
    svc = ComisionService(mock_session)

    comision_id = uuid4()
    fake_comision = MagicMock(spec=Comision)
    fake_comision.id = comision_id
    fake_comision.tenant_id = user_docente_admin_a.tenant_id
    fake_comision.codigo = "A"
    fake_comision.nombre = "A"  # backfill desde codigo
    svc.repo.get_or_404 = AsyncMock(return_value=fake_comision)

    data = ComisionUpdate(nombre="A-Manana")
    await svc.update(comision_id, data, user_docente_admin_a)

    # Solo `nombre` cambio; `codigo` queda intacto.
    assert fake_comision.nombre == "A-Manana"
    assert fake_comision.codigo == "A"


async def test_update_solo_nombre_aplica_setattr(mock_session, user_docente_admin_a) -> None:
    """Si solo viene `nombre`, los otros campos no son tocados (exclude_unset)."""
    svc = ComisionService(mock_session)

    comision_id = uuid4()
    fake_comision = MagicMock(spec=Comision)
    fake_comision.id = comision_id
    fake_comision.tenant_id = user_docente_admin_a.tenant_id
    fake_comision.codigo = "B"
    fake_comision.nombre = "B"
    fake_comision.cupo_maximo = 50
    svc.repo.get_or_404 = AsyncMock(return_value=fake_comision)

    data = ComisionUpdate(nombre="B-Tarde")
    await svc.update(comision_id, data, user_docente_admin_a)

    assert fake_comision.nombre == "B-Tarde"
    assert fake_comision.cupo_maximo == 50  # no se toca
    assert fake_comision.codigo == "B"
