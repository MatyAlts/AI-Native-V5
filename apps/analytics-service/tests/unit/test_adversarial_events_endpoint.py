"""Tests del endpoint /api/v1/analytics/cohort/{id}/adversarial-events (ADR-019)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient

_TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_ID = "11111111-1111-1111-1111-111111111111"
_VALID_HEADERS = {"X-Tenant-Id": _TENANT_ID, "X-User-Id": _USER_ID}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _url(comision_id: str) -> str:
    return f"/api/v1/analytics/cohort/{comision_id}/adversarial-events"


def test_sin_tenant_header_devuelve_401(client: TestClient) -> None:
    r = client.get(_url(str(uuid4())))
    assert r.status_code == 401


def test_sin_user_header_devuelve_401(client: TestClient) -> None:
    r = client.get(_url(str(uuid4())), headers={"X-Tenant-Id": _TENANT_ID})
    assert r.status_code == 401


def test_comision_id_no_uuid_devuelve_422(client: TestClient) -> None:
    r = client.get(_url("not-a-uuid"), headers=_VALID_HEADERS)
    assert r.status_code == 422


def test_modo_dev_devuelve_estructura_vacia_con_200(client: TestClient) -> None:
    """Sin DBs configuradas, el endpoint devuelve estructura limpia con 0
    eventos. Buckets de severidad 1..5 explícitamente con 0 (visualización
    consistente)."""
    comision = str(uuid4())
    r = client.get(_url(comision), headers=_VALID_HEADERS)
    assert r.status_code == 200

    data = r.json()
    assert data["comision_id"] == comision
    assert data["n_events_total"] == 0
    assert data["counts_by_category"] == {}
    assert data["counts_by_severity"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    assert data["counts_by_student"] == {}
    assert data["top_students_by_n_events"] == []
    assert data["recent_events"] == []


def test_response_shape_es_estable(client: TestClient) -> None:
    r = client.get(_url(str(uuid4())), headers=_VALID_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "comision_id",
        "n_events_total",
        "counts_by_category",
        "counts_by_severity",
        "counts_by_student",
        "top_students_by_n_events",
        "recent_events",
    }
