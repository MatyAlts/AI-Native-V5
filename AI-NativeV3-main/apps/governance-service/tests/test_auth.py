"""Tests de auth cross-service del governance-service (A0.4).

Verifica que, con `require_gateway_signature` ON, los endpoints de
prompts/configs exigen procedencia probada:

  - sin firma ni token           -> 401
  - con firma valida del gateway -> 200
  - con token de service-account -> 200 (camino del tutor-service)

Y que con el flag OFF (default) el llamado directo del tutor-service (sin
headers) sigue funcionando -> 200 (backwards-compat, no rompe episodios).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from governance_service.config import settings
from governance_service.main import app
from governance_service.routes.prompts import get_loader
from httpx import ASGITransport, AsyncClient
from platform_observability import sign_headers

SECRET = "test-gateway-shared-secret"
SERVICE_TOKEN = "test-internal-service-token"


@pytest.fixture
def prompts_repo(tmp_path: Path) -> Path:
    """Crea un repo de prompts minimal con tutor/v1.0.0/system.md."""
    prompt_dir = tmp_path / "prompts" / "tutor" / "v1.0.0"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "system.md").write_text("Sos un tutor socratico.")
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_state(prompts_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Apunta el loader al repo tmp y limpia su cache lru entre tests."""
    monkeypatch.setattr(settings, "prompts_repo_path", str(prompts_repo))
    get_loader.cache_clear()
    yield
    get_loader.cache_clear()


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


# ── Flag OFF (default): no rompe al tutor-service ────────────────────────────


async def test_flag_off_sin_headers_devuelve_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default (flag OFF): el llamado directo del tutor sin headers -> 200."""
    monkeypatch.setattr(settings, "require_gateway_signature", False)
    resp = await client.get("/api/v1/prompts/tutor/v1.0.0")
    assert resp.status_code == 200
    assert resp.json()["name"] == "tutor"


# ── Flag ON: enforcement ─────────────────────────────────────────────────────


async def test_flag_on_sin_firma_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.get("/api/v1/prompts/tutor/v1.0.0")
    assert resp.status_code == 401


async def test_flag_on_firma_invalida_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    headers = _valid_signature_headers()
    headers["X-Gateway-Signature"] = "deadbeef" * 8  # firma corrupta
    resp = await client.get("/api/v1/prompts/tutor/v1.0.0", headers=headers)
    assert resp.status_code == 401


async def test_flag_on_firma_valida_devuelve_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.get("/api/v1/prompts/tutor/v1.0.0", headers=_valid_signature_headers())
    assert resp.status_code == 200
    assert resp.json()["name"] == "tutor"


async def test_flag_on_token_servicio_valido_devuelve_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Camino del tutor-service: token de service-account -> 200."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.get(
        "/api/v1/prompts/tutor/v1.0.0",
        headers={"X-Internal-Service-Token": SERVICE_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "tutor"


async def test_flag_on_token_servicio_invalido_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.get(
        "/api/v1/prompts/tutor/v1.0.0",
        headers={"X-Internal-Service-Token": "wrong-token"},
    )
    assert resp.status_code == 401


async def test_flag_on_protege_active_configs_y_verify(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La auth cubre TODOS los endpoints del router, no solo get_prompt."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)

    assert (await client.get("/api/v1/active_configs")).status_code == 401
    assert (await client.post("/api/v1/prompts/tutor/v1.0.0/verify")).status_code == 401

    headers = _valid_signature_headers()
    assert (await client.get("/api/v1/active_configs", headers=headers)).status_code == 200
    assert (
        await client.post("/api/v1/prompts/tutor/v1.0.0/verify", headers=headers)
    ).status_code == 200


async def test_health_queda_abierto_con_flag_on(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health/live no lleva auth (probes de k8s), aun con el flag ON."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    resp = await client.get("/health/live")
    assert resp.status_code == 200
