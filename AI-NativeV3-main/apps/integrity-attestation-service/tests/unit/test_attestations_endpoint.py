"""Tests de los endpoints HTTP del integrity-attestation-service (ADR-021).

Cubre:
- POST /api/v1/attestations: happy path (firma + appendea), validaciones, response shape
- GET /api/v1/attestations/pubkey: devuelve PEM con header X-Signer-Pubkey-Id
- GET /api/v1/attestations/{date}: 200 con bytes exactos / 404 / 400 si formato invalido
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from integrity_attestation_service.config import settings
from integrity_attestation_service.main import app
from integrity_attestation_service.services.signing import (
    DEV_PUBKEY_ID,
    compute_canonical_buffer,
    load_keypair_with_failsafe,
    load_public_key,
    verify_buffer,
)

_VALID_REQUEST = {
    "episode_id": "11111111-2222-3333-4444-555555555555",
    "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "final_chain_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "total_events": 42,
    "ts_episode_closed": "2026-04-27T10:30:00Z",
}


@pytest.fixture(autouse=True)
def _redirect_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirige el log_dir global a tmp_path para que cada test arranque limpio
    y no contamine `./attestations/` del repo."""
    monkeypatch.setattr(settings, "attestation_log_dir", tmp_path)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # `lifespan` NO se ejecuta con `ASGITransport` por default — pre-populamos
    # `app.state.signing` manualmente para que el endpoint encuentre las keys.
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


# ── POST /attestations ────────────────────────────────────────────────


async def test_post_attestation_happy_path(client: AsyncClient) -> None:
    r = await client.post("/api/v1/attestations", json=_VALID_REQUEST)
    assert r.status_code == 201
    data = r.json()

    # Campos del request
    assert data["episode_id"] == _VALID_REQUEST["episode_id"]
    assert data["tenant_id"] == _VALID_REQUEST["tenant_id"]
    assert data["final_chain_hash"] == _VALID_REQUEST["final_chain_hash"]
    assert data["total_events"] == _VALID_REQUEST["total_events"]
    assert data["ts_episode_closed"] == _VALID_REQUEST["ts_episode_closed"]

    # Campos generados por el servicio
    assert data["schema_version"] == "1.0.0"
    assert data["signer_pubkey_id"] == DEV_PUBKEY_ID
    assert data["ts_attested"].endswith("Z")
    assert len(data["signature"]) == 128


async def test_post_attestation_firma_es_verificable_con_pubkey(
    client: AsyncClient,
) -> None:
    """Roundtrip: la firma del POST debe validar con la pubkey del repo."""
    r = await client.post("/api/v1/attestations", json=_VALID_REQUEST)
    assert r.status_code == 201
    data = r.json()

    pub = load_public_key(
        Path(__file__).resolve().parent.parent.parent / "dev-keys" / "dev-public.pem"
    )
    canonical = compute_canonical_buffer(
        episode_id=data["episode_id"],
        tenant_id=data["tenant_id"],
        final_chain_hash=data["final_chain_hash"],
        total_events=data["total_events"],
        ts_episode_closed=data["ts_episode_closed"],
    )
    assert verify_buffer(pub, canonical, data["signature"]) is True


async def test_post_attestation_appendea_al_journal(client: AsyncClient, tmp_path: Path) -> None:
    """Despues del POST exitoso, debe existir un archivo JSONL del dia con
    al menos una linea conteniendo el episode_id."""
    r = await client.post("/api/v1/attestations", json=_VALID_REQUEST)
    assert r.status_code == 201

    files = list(tmp_path.glob("attestations-*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert _VALID_REQUEST["episode_id"] in content


async def test_post_attestation_falla_con_hash_invalido(client: AsyncClient) -> None:
    bad = {**_VALID_REQUEST, "final_chain_hash": "not-hex"}
    r = await client.post("/api/v1/attestations", json=bad)
    assert r.status_code == 422  # Pydantic field validation


async def test_post_attestation_falla_con_total_events_cero(client: AsyncClient) -> None:
    bad = {**_VALID_REQUEST, "total_events": 0}
    r = await client.post("/api/v1/attestations", json=bad)
    assert r.status_code == 422


async def test_post_attestation_falla_con_ts_sin_z(client: AsyncClient) -> None:
    """Ts sin Z pasa la validacion de Pydantic (es string) pero falla en
    `compute_canonical_buffer` con 400."""
    bad = {**_VALID_REQUEST, "ts_episode_closed": "2026-04-27T10:30:00+00:00"}
    r = await client.post("/api/v1/attestations", json=bad)
    assert r.status_code == 400
    assert "Z" in r.json()["detail"]


# ── GET /attestations/pubkey ──────────────────────────────────────────


async def test_get_pubkey_devuelve_pem(client: AsyncClient) -> None:
    r = await client.get("/api/v1/attestations/pubkey")
    assert r.status_code == 200
    text = r.text
    assert text.startswith("-----BEGIN PUBLIC KEY-----")
    assert text.rstrip().endswith("-----END PUBLIC KEY-----")


async def test_get_pubkey_incluye_header_pubkey_id(client: AsyncClient) -> None:
    r = await client.get("/api/v1/attestations/pubkey")
    assert r.status_code == 200
    assert r.headers["x-signer-pubkey-id"] == DEV_PUBKEY_ID


# ── GET /attestations/{date} ──────────────────────────────────────────


async def test_get_attestations_by_date_404_si_no_existe(client: AsyncClient) -> None:
    r = await client.get("/api/v1/attestations/2099-01-01")
    assert r.status_code == 404


async def test_get_attestations_by_date_devuelve_jsonl_con_attestation_creada(
    client: AsyncClient,
) -> None:
    """Despues de POSTear una attestation, GET por la fecha del ts_attested
    devuelve el JSONL con esa linea."""
    post_r = await client.post("/api/v1/attestations", json=_VALID_REQUEST)
    assert post_r.status_code == 201
    day = post_r.json()["ts_attested"][:10]  # YYYY-MM-DD

    r = await client.get(f"/api/v1/attestations/{day}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert _VALID_REQUEST["episode_id"] in r.text


async def test_get_attestations_by_date_400_con_formato_invalido(
    client: AsyncClient,
) -> None:
    r = await client.get("/api/v1/attestations/not-a-date")
    assert r.status_code == 400


async def test_get_attestations_by_date_400_con_path_traversal_attempt(
    client: AsyncClient,
) -> None:
    """Defensa basica contra path traversal — slash en el `day` no debe
    permitir leer archivos fuera de `attestation_log_dir`."""
    r = await client.get("/api/v1/attestations/..%2F..%2Fetc")
    # FastAPI rechaza el slash; sino, nuestro validator de longitud lo agarra
    assert r.status_code in (400, 404)
