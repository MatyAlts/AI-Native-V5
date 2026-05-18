"""Tests de los endpoints de cohort/export del analytics-service."""

from __future__ import annotations

import asyncio

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient

TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_ID = "11111111-1111-1111-1111-111111111111"
AUTH_HEADERS = {"X-Tenant-Id": TENANT_ID, "X-User-Id": USER_ID}


@pytest.fixture
def client():
    with TestClient(app) as c:  # activa lifespan → arranca worker
        yield c


def _reset_store_between_tests():
    """Limpia el singleton del store entre tests."""
    from analytics_service.services.export import get_job_store

    get_job_store.cache_clear()


def test_export_encola_job_y_devuelve_job_id(client: TestClient) -> None:
    _reset_store_between_tests()
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "period_days": 30,
            "include_prompts": False,
            "salt": "research_salt_16_chars_or_more",
            "cohort_alias": "UNSL_2026_P2",
        },
        headers=AUTH_HEADERS,
    )
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


def test_export_sin_tenant_header_401(client: TestClient) -> None:
    """Sin X-Tenant-Id el endpoint rechaza con 401 (no más hardcoded tenant)."""
    _reset_store_between_tests()
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers={"X-User-Id": USER_ID},
    )
    assert r.status_code == 401


def test_cohort_export_sin_user_header_401(client: TestClient) -> None:
    """Sin X-User-Id el endpoint rechaza con 401 (audit log requiere requester real)."""
    _reset_store_between_tests()
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers={"X-Tenant-Id": TENANT_ID},
    )
    assert r.status_code == 401


def test_cohort_export_user_header_invalido_400(client: TestClient) -> None:
    """X-User-Id no-UUID retorna 400."""
    _reset_store_between_tests()
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers={"X-Tenant-Id": TENANT_ID, "X-User-Id": "not-a-uuid"},
    )
    assert r.status_code == 400


def test_export_persiste_user_id_del_header_en_requested_by(client: TestClient) -> None:
    """ExportJob.requested_by_user_id refleja el X-User-Id del request, no un placeholder."""
    _reset_store_between_tests()
    custom_user = "22222222-2222-2222-2222-222222222222"
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers={"X-Tenant-Id": TENANT_ID, "X-User-Id": custom_user},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    r2 = client.get(f"/api/v1/analytics/cohort/export/{job_id}/status")
    assert r2.status_code == 200
    assert r2.json()["requested_by_user_id"] == custom_user


def test_export_status_404_si_job_no_existe(client: TestClient) -> None:
    r = client.get("/api/v1/analytics/cohort/export/00000000-0000-0000-0000-000000000000/status")
    assert r.status_code == 404


def test_export_status_devuelve_estado_del_job(client: TestClient) -> None:
    _reset_store_between_tests()
    # Crear job
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers=AUTH_HEADERS,
    )
    job_id = r.json()["job_id"]

    # Consultar status (puede estar pending o ya succeeded si el worker fue rápido)
    r2 = client.get(f"/api/v1/analytics/cohort/export/{job_id}/status")
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] in ("pending", "running", "succeeded")
    assert data["comision_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    # El salt NO aparece (solo el hash)
    assert "salt" not in data
    assert "salt_hash" in data


def test_download_425_si_aun_pending(client: TestClient) -> None:
    _reset_store_between_tests()
    # Crear job que quedará pending un ratito (worker tarda en pollear)
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers=AUTH_HEADERS,
    )
    job_id = r.json()["job_id"]

    # Intentar descargar inmediatamente — puede ser 425 (aún pending) o 200 (worker rápido)
    r2 = client.get(f"/api/v1/analytics/cohort/export/{job_id}/download")
    assert r2.status_code in (200, 425)


def test_download_200_eventualmente(client: TestClient) -> None:
    _reset_store_between_tests()
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "research_salt_16_chars_or_more",
        },
        headers=AUTH_HEADERS,
    )
    job_id = r.json()["job_id"]

    # En TestClient el worker async no gana tiempo de CPU automáticamente,
    # así que disparamos el procesamiento manualmente.
    from analytics_service.services.export import _StubDataSource, get_job_store
    from platform_ops import ExportWorker

    async def _drain() -> None:
        worker = ExportWorker(
            store=get_job_store(),
            data_source_factory=lambda tid: _StubDataSource(tenant_id=tid),
            salt="research_salt_16_chars_or_more",
        )
        # Correr hasta que no queden pending (max 10 iteraciones)
        for _ in range(10):
            if not await worker.run_once():
                break

    asyncio.run(_drain())

    r3 = client.get(f"/api/v1/analytics/cohort/export/{job_id}/download")
    assert r3.status_code == 200
    payload = r3.json()
    # El stub DataSource devuelve vacío, pero la estructura debe estar
    assert payload["schema_version"] == "1.0.0"
    assert payload["total_episodes"] == 0


def test_download_404_si_job_no_existe(client: TestClient) -> None:
    r = client.get("/api/v1/analytics/cohort/export/00000000-0000-0000-0000-000000000001/download")
    assert r.status_code == 404
