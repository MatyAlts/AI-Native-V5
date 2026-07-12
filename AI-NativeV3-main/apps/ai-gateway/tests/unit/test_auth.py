"""Tests de auth cross-service del ai-gateway (A0.1).

Verifica que, con `require_gateway_signature` ON, los endpoints de BYOK y del
LLM proxy exigen procedencia probada:

  - sin firma ni token           -> 401
  - con firma valida del gateway -> pasa la capa de auth (no 401)
  - con token de service-account -> pasa la capa de auth (camino del tutor)

Y que con el flag OFF (default) el llamado directo del tutor-service (sin
firma) sigue funcionando -> NO 401 (backwards-compat, no rompe el chat).

Nota: para el LLM proxy solo comprobamos que la CAPA DE AUTH no bloquea (i.e.
el status no es 401); el resto del pipeline (budget/cache/provider mock) se
cubre en test_complete_routes.py. Para BYOK el flag OFF conserva los checks de
rol previos (403 para no-admin), que se cubren en test_byok_routes.py.
"""

from __future__ import annotations

import time

import fakeredis.aioredis
import pytest
from ai_gateway.config import settings
from ai_gateway.main import app
from httpx import ASGITransport, AsyncClient
from platform_observability import sign_headers

SECRET = "test-gateway-shared-secret"
SERVICE_TOKEN = "test-internal-service-token"

VALID_TENANT = "11111111-1111-1111-1111-111111111111"
VALID_USER = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _redis_isolation(monkeypatch: pytest.MonkeyPatch):
    """FakeRedis aislado por test (el LLM proxy toca budget/cache al pasar auth)."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("ai_gateway.routes.complete._redis_client", fake)
    yield


@pytest.fixture(autouse=True)
def _reset_flag(monkeypatch: pytest.MonkeyPatch):
    """Cada test arranca con el flag OFF (default de prod dev) salvo que lo prenda.

    Ademas neutraliza el resolver BYOK (byok_enabled=False) y las keys de provider
    reales del .env, para que los tests del LLM proxy que PASAN la auth corran el
    pipeline con MockProvider + fakeredis sin pegarle a la DB ni a un provider real
    (mismo criterio que `_mock_provider` en test_complete_routes.py)."""
    monkeypatch.setattr(settings, "require_gateway_signature", False)
    monkeypatch.setattr(settings, "gateway_shared_secret", "")
    monkeypatch.setattr(settings, "internal_service_token", "")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "byok_enabled", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "mistral_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    yield


def _enable_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)


def _valid_signature_headers(roles: str = "superadmin") -> dict[str, str]:
    ts = int(time.time())
    sig = sign_headers(SECRET, VALID_USER, VALID_TENANT, roles, ts)
    return {
        "X-User-Id": VALID_USER,
        "X-Tenant-Id": VALID_TENANT,
        "X-User-Roles": roles,
        "X-Gateway-Ts": str(ts),
        "X-Gateway-Signature": sig,
    }


def _tutor_stream_body() -> dict:
    return {
        "messages": [{"role": "user", "content": "hola"}],
        "model": "mock-model",
        "feature": "tutor",
    }


# ── Flag OFF (default): no rompe al tutor-service ────────────────────────────


async def test_flag_off_llm_proxy_sin_firma_no_401(client: AsyncClient) -> None:
    """Default (flag OFF): el tutor llama /stream directo sin firma -> no 401."""
    resp = await client.post(
        "/api/v1/stream",
        json=_tutor_stream_body(),
        headers={"X-Tenant-Id": VALID_TENANT, "X-Caller": "tutor-service"},
    )
    assert resp.status_code != 401


async def test_flag_off_byok_sin_firma_conserva_check_rol(client: AsyncClient) -> None:
    """Default (flag OFF): BYOK conserva su check de rol previo — un no-admin
    recibe 403 (NO 401), probando que la capa de auth apagada no altera F11.

    Se usa rol no-admin a proposito: el 403 corta ANTES de tocar la DB, asi el
    test no requiere Postgres (un admin llegaria a `list_byok_keys`)."""
    resp = await client.get(
        "/api/v1/byok/keys?scope_type=tenant",
        headers={
            "X-Tenant-Id": VALID_TENANT,
            "X-User-Id": VALID_USER,
            "X-User-Roles": "estudiante",
        },
    )
    assert resp.status_code == 403


# ── Flag ON: enforcement ─────────────────────────────────────────────────────


async def test_flag_on_llm_proxy_sin_firma_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_enforcement(monkeypatch)
    resp = await client.post(
        "/api/v1/stream",
        json=_tutor_stream_body(),
        headers={"X-Tenant-Id": VALID_TENANT, "X-Caller": "tutor-service"},
    )
    assert resp.status_code == 401


async def test_flag_on_byok_sin_firma_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_enforcement(monkeypatch)
    resp = await client.get(
        "/api/v1/byok/keys?scope_type=tenant",
        headers={
            "X-Tenant-Id": VALID_TENANT,
            "X-User-Id": VALID_USER,
            "X-User-Roles": "superadmin",
        },
    )
    assert resp.status_code == 401


async def test_flag_on_token_servicio_valido_no_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Camino del tutor-service: token de service-account -> pasa auth (no 401)."""
    _enable_enforcement(monkeypatch)
    resp = await client.post(
        "/api/v1/stream",
        json=_tutor_stream_body(),
        headers={
            "X-Tenant-Id": VALID_TENANT,
            "X-Caller": "tutor-service",
            "X-Internal-Service-Token": SERVICE_TOKEN,
        },
    )
    assert resp.status_code != 401


async def test_flag_on_token_servicio_invalido_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_enforcement(monkeypatch)
    resp = await client.post(
        "/api/v1/stream",
        json=_tutor_stream_body(),
        headers={
            "X-Tenant-Id": VALID_TENANT,
            "X-Caller": "tutor-service",
            "X-Internal-Service-Token": "wrong-token",
        },
    )
    assert resp.status_code == 401


async def test_flag_on_firma_valida_pasa_auth(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Firma HMAC valida del gateway (camino frontend admin -> BYOK) -> pasa la
    auth de procedencia. Se firma con rol no-admin para caer en el check de rol
    (403) ANTES de tocar la DB — el 403 (no 401) prueba que la firma valido."""
    _enable_enforcement(monkeypatch)
    resp = await client.get(
        "/api/v1/byok/keys?scope_type=tenant",
        headers=_valid_signature_headers(roles="estudiante"),
    )
    assert resp.status_code == 403


async def test_flag_on_firma_invalida_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_enforcement(monkeypatch)
    headers = _valid_signature_headers()
    headers["X-Gateway-Signature"] = "deadbeef" * 8  # firma corrupta
    resp = await client.get("/api/v1/byok/keys?scope_type=tenant", headers=headers)
    assert resp.status_code == 401


async def test_flag_on_budget_endpoint_protegido(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La auth cubre TODO el router del LLM proxy, no solo /stream."""
    _enable_enforcement(monkeypatch)
    resp = await client.get(
        "/api/v1/budget?feature=tutor",
        headers={"X-Tenant-Id": VALID_TENANT, "X-Caller": "tutor-service"},
    )
    assert resp.status_code == 401


async def test_flag_on_health_queda_abierto(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health/live no lleva auth (probes de k8s), aun con el flag ON."""
    _enable_enforcement(monkeypatch)
    resp = await client.get("/health/live")
    assert resp.status_code == 200


async def test_flag_on_token_servicio_valido_byok_pasa_a_check_rol(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con token valido pero rol no-admin, BYOK pasa la auth de procedencia y
    cae en el check de rol (403), NO en 401 — confirma que ambas capas coexisten."""
    _enable_enforcement(monkeypatch)
    resp = await client.get(
        "/api/v1/byok/keys?scope_type=tenant",
        headers={
            "X-Tenant-Id": VALID_TENANT,
            "X-User-Id": VALID_USER,
            "X-User-Roles": "estudiante",
            "X-Internal-Service-Token": SERVICE_TOKEN,
        },
    )
    assert resp.status_code == 403
