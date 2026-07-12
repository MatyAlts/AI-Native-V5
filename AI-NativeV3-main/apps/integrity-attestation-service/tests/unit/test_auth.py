"""Tests de auth cross-service del integrity-attestation-service (A0.1).

Verifica que, con `require_gateway_signature` ON, el POST /api/v1/attestations
exige procedencia probada:

  - sin firma ni token           -> 401
  - con firma valida del gateway -> 201
  - con token de service-account -> 201

Y que con el flag OFF (default) el POST sigue funcionando sin headers -> 201
(backwards-compat, no rompe la ingesta actual).

Ademas verifica el invariante de diseno (ADR-021): los GET (/pubkey, /{date})
y el /health quedan ABIERTOS incluso con el flag ON — publicos para auditores
externos y probes.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from integrity_attestation_service.config import settings
from integrity_attestation_service.main import app
from integrity_attestation_service.services.signing import load_keypair_with_failsafe
from platform_observability import sign_headers

SECRET = "test-gateway-shared-secret"
SERVICE_TOKEN = "test-internal-service-token"

_VALID_REQUEST = {
    "episode_id": "11111111-2222-3333-4444-555555555555",
    "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "final_chain_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "total_events": 42,
    "ts_episode_closed": "2026-04-27T10:30:00Z",
}


@pytest.fixture(autouse=True)
def _redirect_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirige el log_dir global a tmp_path para no contaminar el repo."""
    monkeypatch.setattr(settings, "attestation_log_dir", tmp_path)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # `lifespan` NO se ejecuta con `ASGITransport` — pre-populamos las keys.
    private_key, public_key, pubkey_id = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment="development",
    )
    app.state.signing = {
        "private_key": private_key,
        "public_key": public_key,
        "pubkey_id": pubkey_id,
    }
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


# ── Flag OFF (default): no rompe la ingesta actual ───────────────────────────


async def test_flag_off_post_sin_headers_devuelve_201(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default (flag OFF): el POST sin headers sigue funcionando -> 201."""
    monkeypatch.setattr(settings, "require_gateway_signature", False)
    resp = await client.post("/api/v1/attestations", json=_VALID_REQUEST)
    assert resp.status_code == 201


# ── Flag ON: enforcement en el POST ──────────────────────────────────────────


async def test_flag_on_post_sin_firma_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.post("/api/v1/attestations", json=_VALID_REQUEST)
    assert resp.status_code == 401


async def test_flag_on_post_firma_invalida_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    headers = _valid_signature_headers()
    headers["X-Gateway-Signature"] = "deadbeef" * 8  # firma corrupta
    resp = await client.post("/api/v1/attestations", json=_VALID_REQUEST, headers=headers)
    assert resp.status_code == 401


async def test_flag_on_post_firma_valida_devuelve_201(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.post(
        "/api/v1/attestations", json=_VALID_REQUEST, headers=_valid_signature_headers()
    )
    assert resp.status_code == 201


async def test_flag_on_post_token_servicio_valido_devuelve_201(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Camino del caller interno directo: token de service-account -> 201."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.post(
        "/api/v1/attestations",
        json=_VALID_REQUEST,
        headers={"X-Internal-Service-Token": SERVICE_TOKEN},
    )
    assert resp.status_code == 201


async def test_flag_on_post_token_servicio_invalido_devuelve_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    monkeypatch.setattr(settings, "internal_service_token", SERVICE_TOKEN)
    resp = await client.post(
        "/api/v1/attestations",
        json=_VALID_REQUEST,
        headers={"X-Internal-Service-Token": "wrong-token"},
    )
    assert resp.status_code == 401


# ── Invariante de diseno: GET y health abiertos aun con flag ON ──────────────


async def test_flag_on_get_pubkey_queda_abierto(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-021: /pubkey es publico para auditores — 200 aun con el flag ON."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    resp = await client.get("/api/v1/attestations/pubkey")
    assert resp.status_code == 200


async def test_flag_on_get_by_date_queda_abierto(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-021: el JSONL del dia es publico para auditores — 404 (no 401) sin
    datos, probando que la auth NO gatea el GET aun con el flag ON."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    resp = await client.get("/api/v1/attestations/2099-01-01")
    assert resp.status_code == 404


async def test_flag_on_health_queda_abierto(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health/live no lleva auth (probes de k8s), aun con el flag ON."""
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", SECRET)
    resp = await client.get("/health/live")
    assert resp.status_code == 200
