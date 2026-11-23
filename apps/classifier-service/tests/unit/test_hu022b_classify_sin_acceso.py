"""HU-022 (vuelta 2), C04 (F28): `POST /classify_episode/{id}` sobre un episodio
SIN clasificación vigente y sin acceso responde 403, no 502.

En producción (23/11) el alumno de prueba pidió clasificar un episodio ajeno y
recibió 502 con una página HTML. El camino "no existe clasificación" pide el
episodio al CTR con la identidad del usuario; si el CTR contesta 403 (no es
tuyo, no sos de la comisión), eso se mapeaba a 502 "CTR error". Un 403 del CTR
es una respuesta de acceso, no una falla del CTR, y tiene que llegar como 403.
Un 5xx real del CTR sigue siendo 502 (guarda).
"""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from classifier_service.config import settings
from classifier_service.main import app
from httpx import ASGITransport, AsyncClient

TENANT = UUID("00000000-0000-0000-0000-000000000001")
CLERK = "estudiante,docente"


def _headers() -> dict[str, str]:
    return {
        "X-User-Id": str(uuid4()),
        "X-Tenant-Id": str(TENANT),
        "X-User-Email": "x@utn.test",
        "X-User-Roles": CLERK,
    }


def _sesion_sin_clasificacion() -> Any:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async def _execute(*_a: Any, **_k: Any) -> Any:
        res = MagicMock()
        res.scalar_one_or_none = MagicMock(return_value=None)
        return res

    session.execute = _execute
    return session


@contextlib.asynccontextmanager
async def _ts(session: Any, _tenant: UUID) -> Any:
    yield session


def _ctr_responde(codigo: int) -> AsyncMock:
    req = httpx.Request("GET", "http://ctr/api/v1/episodes/x")
    resp = httpx.Response(codigo, request=req)
    return AsyncMock(side_effect=httpx.HTTPStatusError("x", request=req, response=resp))


@pytest.fixture(autouse=True)
def _prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enforce_comision_access", True)


async def _post(ctr: AsyncMock) -> httpx.Response:
    session = _sesion_sin_clasificacion()
    with (
        patch("classifier_service.routes.classify_ep.tenant_session", lambda t: _ts(session, t)),
        patch("classifier_service.routes.classify_ep._fetch_episode_from_ctr", ctr),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await c.post(f"/api/v1/classify_episode/{uuid4()}", headers=_headers())


async def test_sin_clasificacion_y_sin_acceso_da_403() -> None:
    r = await _post(_ctr_responde(403))
    assert r.status_code == 403, f"esperaba 403 y vino {r.status_code}: {r.text}"


async def test_un_5xx_real_del_ctr_sigue_siendo_502() -> None:
    r = await _post(_ctr_responde(500))
    assert r.status_code == 502, r.text
