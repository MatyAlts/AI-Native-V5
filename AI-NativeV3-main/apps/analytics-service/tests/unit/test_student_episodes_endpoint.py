"""Tests de los 3 endpoints nuevos del ADR-022:
- GET /student/{id}/episodes (drill-down navegacional)
- GET /cohort/{id}/cii-quartiles (cuartiles agregados privacidad-safe)
- GET /student/{id}/alerts (alertas vs cohorte, audit G7)
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient

_TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER = "11111111-1111-1111-1111-111111111111"
_HEADERS = {"X-Tenant-Id": _TENANT, "X-User-Id": _USER}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── /student/{id}/episodes ────────────────────────────────────────────


def test_episodes_sin_user_header_devuelve_401(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/student/{uuid4()}/episodes?comision_id={uuid4()}",
        headers={"X-Tenant-Id": _TENANT},
    )
    assert r.status_code == 401


def test_episodes_sin_comision_id_query_devuelve_422(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/student/{uuid4()}/episodes",
        headers=_HEADERS,
    )
    assert r.status_code == 422


def test_episodes_modo_dev_devuelve_lista_vacia(client: TestClient) -> None:
    student = str(uuid4())
    comision = str(uuid4())
    r = client.get(
        f"/api/v1/analytics/student/{student}/episodes?comision_id={comision}",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["student_pseudonym"] == student
    assert data["comision_id"] == comision
    assert data["n_episodes"] == 0
    assert data["episodes"] == []


# ── /cohort/{id}/cii-quartiles ────────────────────────────────────────


def test_quartiles_sin_user_header_devuelve_401(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/cohort/{uuid4()}/cii-quartiles",
        headers={"X-Tenant-Id": _TENANT},
    )
    assert r.status_code == 401


def test_quartiles_modo_dev_devuelve_insufficient_data(client: TestClient) -> None:
    """Sin DBs, no hay slopes → insufficient_data: true (privacidad
    automática: cohorte chica/vacía → no expone cuartiles)."""
    comision = str(uuid4())
    r = client.get(
        f"/api/v1/analytics/cohort/{comision}/cii-quartiles",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["comision_id"] == comision
    assert data["insufficient_data"] is True
    assert data["n_students_evaluated"] == 0
    assert data["q1"] is None
    assert data["median"] is None
    assert data["q3"] is None
    assert data["min_students_for_quartiles"] == 5
    assert data["labeler_version"] == "1.0.0"


def test_quartiles_response_shape_es_estable(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/cohort/{uuid4()}/cii-quartiles",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "comision_id",
        "labeler_version",
        "min_students_for_quartiles",
        "n_students_evaluated",
        "insufficient_data",
        "q1",
        "median",
        "q3",
        "min",
        "max",
        "mean",
        "stdev",
    }


# ── /student/{id}/alerts ──────────────────────────────────────────────


def test_alerts_sin_user_header_devuelve_401(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/student/{uuid4()}/alerts?comision_id={uuid4()}",
        headers={"X-Tenant-Id": _TENANT},
    )
    assert r.status_code == 401


def test_alerts_modo_dev_devuelve_estructura_vacia(client: TestClient) -> None:
    """Modo dev: sin slope ni cohorte stats → 0 alertas, severity null."""
    student = str(uuid4())
    comision = str(uuid4())
    r = client.get(
        f"/api/v1/analytics/student/{student}/alerts?comision_id={comision}",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["student_pseudonym"] == student
    assert data["comision_id"] == comision
    assert data["alerts"] == []
    assert data["n_alerts"] == 0
    assert data["highest_severity"] is None
    assert data["quartile"] is None
    assert data["student_slope"] is None
    assert data["cohort_stats"]["insufficient_data"] is True


def test_alerts_response_shape_estable(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/student/{uuid4()}/alerts?comision_id={uuid4()}",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "student_pseudonym",
        "comision_id",
        "labeler_version",
        "student_slope",
        "cohort_stats",
        "quartile",
        "alerts",
        "n_alerts",
        "highest_severity",
    }
