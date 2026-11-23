"""HU-017 (ronda de arreglos): `POST /classify_episode/{id}` sobre un episodio
ya clasificado es una LECTURA y no puede saltear el control de acceso.

Con Clerk toda cuenta trae `estudiante,docente`, y `docente` está en
`CLASSIFY_ROLES`: antes, el pre-check de idempotencia devolvía la fila a
cualquiera. Ahora el que decide es el ctr-service (se le pide el episodio con la
identidad del usuario, como en el camino que clasifica de cero). Excepción:
`classifier_worker` y el oversight reciben la fila sin consultar.
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
from classifier_service.models import Classification
from classifier_service.services.pipeline import compute_classifier_config_hash
from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE
from httpx import ASGITransport, AsyncClient

TENANT = UUID("00000000-0000-0000-0000-000000000001")
CLERK = "estudiante,docente"


def _headers(roles: str, uid: UUID | None = None) -> dict[str, str]:
    return {
        "X-User-Id": str(uid or uuid4()),
        "X-Tenant-Id": str(TENANT),
        "X-User-Email": "x@utn.test",
        "X-User-Roles": roles,
    }


def _existente(episode_id: UUID) -> Classification:
    return Classification(
        id=9,
        tenant_id=TENANT,
        episode_id=episode_id,
        comision_id=uuid4(),
        classifier_config_hash=compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE),
        appropriation="apropiacion_superficial",
        appropriation_reason="x",
        features={},
        is_current=True,
    )


def _sesion(existing: Classification) -> Any:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async def _execute(*_a: Any, **_k: Any) -> Any:
        res = MagicMock()
        res.scalar_one_or_none = MagicMock(return_value=existing)
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


async def _post(roles: str, ctr: AsyncMock, uid: UUID | None = None) -> httpx.Response:
    ep = uuid4()
    session = _sesion(_existente(ep))
    with (
        patch("classifier_service.routes.classify_ep.tenant_session", lambda t: _ts(session, t)),
        patch("classifier_service.routes.classify_ep._fetch_episode_from_ctr", ctr),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await c.post(f"/api/v1/classify_episode/{ep}", headers=_headers(roles, uid))


async def test_alumno_ajeno_recibe_403_y_no_ve_la_fila() -> None:
    r = await _post(CLERK, _ctr_responde(403))
    assert r.status_code == 403
    assert "appropriation" not in r.text


async def test_sin_base_academica_en_el_ctr_un_tercero_recibe_503() -> None:
    r = await _post(CLERK, _ctr_responde(503))
    assert r.status_code == 503


async def test_ctr_inalcanzable_falla_cerrado() -> None:
    ctr = AsyncMock(side_effect=httpx.ConnectError("caido"))
    r = await _post(CLERK, ctr)
    assert r.status_code == 503


async def test_el_duenio_recibe_su_clasificacion() -> None:
    duenio = uuid4()
    ctr = AsyncMock(return_value={"student_pseudonym": str(duenio), "events": []})
    r = await _post(CLERK, ctr, uid=duenio)
    assert r.status_code == 200, r.text
    assert r.json()["appropriation"] == "apropiacion_superficial"
    ctr.assert_awaited_once()


@pytest.mark.parametrize("rol", ["classifier_worker", "superadmin", "docente_admin"])
async def test_worker_y_oversight_no_consultan_al_ctr(rol: str) -> None:
    ctr = AsyncMock(side_effect=AssertionError("no debia consultar al CTR"))
    r = await _post(rol, ctr)
    assert r.status_code == 200, r.text
    ctr.assert_not_called()
