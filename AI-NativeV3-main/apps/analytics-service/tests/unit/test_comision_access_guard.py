"""Tests del guard de membresía por comisión del análisis.

El conftest pone `enforce_comision_access=False` para el resto de los
tests; acá lo prendemos explícitamente y verificamos la lógica del guard
sin tocar la DB (mockeando `assert_comision_member`).

Ver docs/filtrado-teacher-plan.md.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service import config
from analytics_service.routes import analytics as routes
from fastapi import HTTPException


async def test_enforce_off_es_noop(monkeypatch) -> None:
    """Con el flag en False el guard no exige nada (modo dev/test)."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", False)
    # No levanta aunque falte X-User-Id.
    await routes.require_comision_access(comision_id=uuid4(), x_user_id=None, tenant_id=uuid4())


async def test_enforce_on_sin_user_id_401(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    with pytest.raises(HTTPException) as exc:
        await routes.require_comision_access(comision_id=uuid4(), x_user_id=None, tenant_id=uuid4())
    assert exc.value.status_code == 401


async def test_enforce_on_user_id_invalido_400(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    with pytest.raises(HTTPException) as exc:
        await routes.require_comision_access(
            comision_id=uuid4(), x_user_id="not-a-uuid", tenant_id=uuid4()
        )
    assert exc.value.status_code == 400


async def test_enforce_on_delega_en_assert_member(monkeypatch) -> None:
    """Con flag on + user válido, llama a assert_comision_member con los args."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", True)
    seen: dict[str, object] = {}

    async def fake_assert(user_id, comision_id, tenant_id):
        seen["args"] = (user_id, comision_id, tenant_id)

    monkeypatch.setattr(routes, "assert_comision_member", fake_assert)
    uid, cid, tid = uuid4(), uuid4(), uuid4()
    await routes.require_comision_access(comision_id=cid, x_user_id=str(uid), tenant_id=tid)
    assert seen["args"] == (uid, cid, tid)


async def test_assert_member_enforce_off_no_toca_db(monkeypatch) -> None:
    """assert_comision_member con flag off retorna sin tocar la DB."""
    monkeypatch.setattr(config.settings, "enforce_comision_access", False)
    # Si intentara conectar a la DB con estos UUID random, fallaría/403.
    await routes.assert_comision_member(uuid4(), uuid4(), uuid4())
