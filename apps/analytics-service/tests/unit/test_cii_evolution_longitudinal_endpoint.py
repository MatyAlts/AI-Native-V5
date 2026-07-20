"""Tests del endpoint /api/v1/analytics/student/{id}/cii-evolution-longitudinal (ADR-018)."""

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


def _url(student_pseudonym: str, comision_id: str) -> str:
    return (
        f"/api/v1/analytics/student/{student_pseudonym}/"
        f"cii-evolution-longitudinal?comision_id={comision_id}"
    )


# ── Auth ──────────────────────────────────────────────────────────────


def test_sin_tenant_header_devuelve_401(client: TestClient) -> None:
    r = client.get(_url(str(uuid4()), str(uuid4())))
    assert r.status_code == 401
    assert "X-Tenant-Id" in r.json()["detail"]


def test_sin_user_header_devuelve_401(client: TestClient) -> None:
    """ADR-018 requiere X-Tenant-Id + X-User-Id (alineado con FIX 4 de la
    revisión adversarial 2026-04-27)."""
    r = client.get(
        _url(str(uuid4()), str(uuid4())),
        headers={"X-Tenant-Id": _TENANT_ID},
    )
    assert r.status_code == 401
    assert "X-User-Id" in r.json()["detail"]


def test_tenant_header_no_uuid_devuelve_400(client: TestClient) -> None:
    r = client.get(
        _url(str(uuid4()), str(uuid4())),
        headers={"X-Tenant-Id": "not-a-uuid", "X-User-Id": _USER_ID},
    )
    assert r.status_code == 400


def test_student_pseudonym_no_uuid_devuelve_422(client: TestClient) -> None:
    """FastAPI valida tipos de path params."""
    r = client.get(
        f"/api/v1/analytics/student/not-a-uuid/cii-evolution-longitudinal?comision_id={uuid4()}",
        headers=_VALID_HEADERS,
    )
    assert r.status_code == 422


def test_comision_id_query_param_requerido(client: TestClient) -> None:
    """`comision_id` es query param requerido. Sin él → 422."""
    r = client.get(
        f"/api/v1/analytics/student/{uuid4()}/cii-evolution-longitudinal",
        headers=_VALID_HEADERS,
    )
    assert r.status_code == 422


# ── Modo dev ──────────────────────────────────────────────────────────


def test_modo_dev_devuelve_estructura_vacia_con_200(client: TestClient) -> None:
    """Sin DBs configuradas, el endpoint devuelve estructura vacía con
    `labeler_version`. Coherente con `/cohort/progression` y `/n-level-distribution`."""
    student = str(uuid4())
    comision = str(uuid4())
    r = client.get(_url(student, comision), headers=_VALID_HEADERS)
    assert r.status_code == 200

    data = r.json()
    assert data["student_pseudonym"] == student
    assert data["comision_id"] == comision
    assert data["labeler_version"] == "1.0.0"
    assert data["n_groups_evaluated"] == 0
    assert data["n_groups_insufficient"] == 0
    assert data["n_episodes_total"] == 0
    assert data["evolution_per_template"] == []
    assert data["mean_slope"] is None
    assert data["sufficient_data"] is False


def test_response_shape_es_estable(client: TestClient) -> None:
    """Sanity: el response model expone exactamente las claves documentadas
    en ADR-018 para que consumers (dashboard docente G7) tengan contrato estable."""
    r = client.get(_url(str(uuid4()), str(uuid4())), headers=_VALID_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "student_pseudonym",
        "comision_id",
        "n_groups_evaluated",
        "n_groups_insufficient",
        "n_episodes_total",
        "evolution_per_template",
        "evolution_per_unidad",  # AD-4, AD-6 — nuevo campo, default []
        "mean_slope",
        "sufficient_data",
        "labeler_version",
    }


def test_propaga_student_y_comision_recibidos(client: TestClient) -> None:
    """El endpoint refleja los IDs pedidos (no inventa otros)."""
    student = "12345678-1234-1234-1234-123456789abc"
    comision = "87654321-4321-4321-4321-cba987654321"
    r = client.get(_url(student, comision), headers=_VALID_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["student_pseudonym"] == student
    assert data["comision_id"] == comision
