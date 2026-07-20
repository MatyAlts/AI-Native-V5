"""Tests de auth de procedencia cross-service del classifier-service (A0.1).

Verifica que, con `require_gateway_signature` ON, los routers de datos/metadata
del classifier exigen procedencia probada:

  - sin firma ni token           -> 401
  - con firma valida del gateway -> 200
  - con token de service-account -> 200 (camino de reclassify_all + academic)

Y que con el flag OFF (default) los callers directos (reclassify_all,
academic-service) siguen funcionando sin headers de procedencia -> no-op.

Se usa `GET /api/v1/classifier/config-hash` como sonda del gate porque su
handler no toca DB (200 determinista cuando la auth pasa). Los routers de datos
(`/api/v1/classify_episode`, `/api/v1/interrater`) se cubren afirmando el 401
con el flag ON — el dependency de router corre ANTES del handler, así que no
llegan a tocar DB/CTR.
"""

from __future__ import annotations

import time

import pytest
from classifier_service.config import settings
from classifier_service.main import app
from httpx import ASGITransport, AsyncClient
from platform_observability import sign_headers

SECRET = "test-gateway-shared-secret"
SERVICE_TOKEN = "test-internal-service-token"

CONFIG_HASH_URL = "/api/v1/classifier/config-hash"
CLASSIFY_URL = "/api/v1/classify_episode/11111111-1111-1111-1111-111111111111"
INTERRATER_URL = "/api/v1/interrater/sample?comision_id=22222222-2222-2222-2222-222222222222"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _valid_signature_headers() -> dict[str, str]:
    user_id = "11111111-1111-1111-1111-111111111111"
    tenant_id = "22222222-2222-2222-2222-222222222222"
    roles = "docente"
    ts = int(time.time())
    sig = sign_headers(SECRET, user_id, tenant_id, roles, ts)
    return {
        "X-User-Id": user_id,
        "X-Tenant-Id": tenant_id,
        "X-User-Roles": roles,
        "X-Gateway-Ts": str(ts),
        "X-Gateway-Signature": sig,
    }


def _enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)


# ── Flag OFF (default): no rompe callers directos ────────────────────────────


async def test_flag_off_sin_headers_devuelve_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default (flag OFF): config-hash sin headers de procedencia -> 200."""
    monkeypatch.setattr(settings, "require_gateway_signature", False)
    resp = await client.get(CONFIG_HASH_URL)
    assert resp.status_code == 200
    assert len(resp.json()["classifier_config_hash"]) == 64


# ── Flag ON: enforcement ─────────────────────────────────────────────────────


async def test_flag_on_sin_firma_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_flag(monkeypatch)
    resp = await client.get(CONFIG_HASH_URL)
    assert resp.status_code == 401


async def test_flag_on_firma_invalida_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_flag(monkeypatch)
    headers = _valid_signature_headers()
    headers["X-Gateway-Signature"] = "deadbeef" * 8  # firma corrupta
    resp = await client.get(CONFIG_HASH_URL, headers=headers)
    assert resp.status_code == 401


async def test_flag_on_firma_valida_devuelve_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_flag(monkeypatch)
    resp = await client.get(CONFIG_HASH_URL, headers=_valid_signature_headers())
    assert resp.status_code == 200
    assert len(resp.json()["classifier_config_hash"]) == 64


async def test_flag_on_token_servicio_valido_devuelve_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Camino de reclassify_all / academic-service: token de service-account -> 200."""
    _enable_flag(monkeypatch)
    resp = await client.get(CONFIG_HASH_URL, headers={"X-Internal-Service-Token": SERVICE_TOKEN})
    assert resp.status_code == 200


async def test_flag_on_token_servicio_invalido_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_flag(monkeypatch)
    resp = await client.get(CONFIG_HASH_URL, headers={"X-Internal-Service-Token": "wrong-token"})
    assert resp.status_code == 401


async def test_flag_on_protege_routers_de_datos(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El gate cubre classify_episode e interrater, no solo config-hash.

    El dependency de router corre antes del handler => 401 sin tocar DB/CTR.
    """
    _enable_flag(monkeypatch)
    assert (await client.post(CLASSIFY_URL)).status_code == 401
    assert (await client.get(INTERRATER_URL)).status_code == 401


async def test_health_queda_abierto_con_flag_on(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health/live no lleva auth (probes de k8s), aun con el flag ON."""
    _enable_flag(monkeypatch)
    resp = await client.get("/health/live")
    assert resp.status_code == 200
