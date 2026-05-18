"""Tests del endpoint /api/v1/analytics/episode/{id}/n-level-distribution (ADR-020)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient

_TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_ID = "11111111-1111-1111-1111-111111111111"
_VALID_HEADERS = {"X-Tenant-Id": _TENANT_ID, "X-User-Id": _USER_ID}


@pytest.fixture(autouse=True)
def _force_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla los tests del `.env` del repo (que puede declarar CTR_STORE_URL
    y CLASSIFIER_DB_URL para soporte de make migrate).

    Los tests `test_modo_dev_*` asumen modo dev (`_real_data_source_enabled()`
    retorna False). Sin este fixture, si el dev tiene un `.env` con esas vars
    los tests fallan con 404 en vez de 200.
    """
    from analytics_service.config import settings

    monkeypatch.setattr(settings, "ctr_store_url", "")
    monkeypatch.setattr(settings, "classifier_db_url", "")


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _url(episode_id: str) -> str:
    return f"/api/v1/analytics/episode/{episode_id}/n-level-distribution"


# ── Auth ──────────────────────────────────────────────────────────────


def test_sin_tenant_header_devuelve_401(client: TestClient) -> None:
    r = client.get(_url(str(uuid4())))
    assert r.status_code == 401
    assert "X-Tenant-Id" in r.json()["detail"]


def test_sin_user_header_devuelve_401(client: TestClient) -> None:
    """ADR-020 requiere X-Tenant-Id + X-User-Id (mismo patrón que /cohort/progression).
    Sin user_id, el endpoint rechaza con 401."""
    r = client.get(_url(str(uuid4())), headers={"X-Tenant-Id": _TENANT_ID})
    assert r.status_code == 401
    assert "X-User-Id" in r.json()["detail"]


def test_tenant_header_no_uuid_devuelve_400(client: TestClient) -> None:
    r = client.get(
        _url(str(uuid4())),
        headers={"X-Tenant-Id": "not-a-uuid", "X-User-Id": _USER_ID},
    )
    assert r.status_code == 400


def test_user_header_no_uuid_devuelve_400(client: TestClient) -> None:
    r = client.get(
        _url(str(uuid4())),
        headers={"X-Tenant-Id": _TENANT_ID, "X-User-Id": "not-a-uuid"},
    )
    assert r.status_code == 400


def test_episode_id_no_uuid_devuelve_422(client: TestClient) -> None:
    """FastAPI valida tipos de path params automáticamente."""
    r = client.get(_url("not-a-uuid"), headers=_VALID_HEADERS)
    assert r.status_code == 422


# ── Modo dev (sin CTR_STORE_URL) ──────────────────────────────────────


def test_modo_dev_devuelve_distribucion_vacia_con_200(client: TestClient) -> None:
    """En modo dev (sin DB CTR configurada) el endpoint devuelve un payload
    vacío con `labeler_version` para no bloquear el dev loop. Mismo patrón
    que `/cohort/{id}/progression`."""
    episode_id = str(uuid4())
    r = client.get(_url(episode_id), headers=_VALID_HEADERS)
    assert r.status_code == 200

    data = r.json()
    assert data["episode_id"] == episode_id
    assert data["labeler_version"] == "1.2.0"  # ADR-034 epic ai-native-completion (regla N3/N4 tests_ejecutados)

    # Distribución vacía
    assert data["distribution_seconds"] == {
        "N1": 0.0,
        "N2": 0.0,
        "N3": 0.0,
        "N4": 0.0,
        "meta": 0.0,
    }
    assert data["distribution_ratio"] == {
        "N1": 0.0,
        "N2": 0.0,
        "N3": 0.0,
        "N4": 0.0,
        "meta": 0.0,
    }
    assert data["total_events_per_level"] == {
        "N1": 0,
        "N2": 0,
        "N3": 0,
        "N4": 0,
        "meta": 0,
    }


def test_modo_dev_propaga_episode_id_recibido(client: TestClient) -> None:
    """El endpoint refleja el episode_id pedido (no inventa uno propio)."""
    episode_id = "12345678-1234-1234-1234-123456789abc"
    r = client.get(_url(episode_id), headers=_VALID_HEADERS)
    assert r.status_code == 200
    assert r.json()["episode_id"] == episode_id


def test_response_shape_es_estable(client: TestClient) -> None:
    """Sanity: el response model expone exactamente las 5 claves esperadas
    para que consumers (dashboard docente G7) tengan contrato estable."""
    r = client.get(_url(str(uuid4())), headers=_VALID_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "episode_id",
        "labeler_version",
        "distribution_seconds",
        "distribution_ratio",
        "total_events_per_level",
    }
