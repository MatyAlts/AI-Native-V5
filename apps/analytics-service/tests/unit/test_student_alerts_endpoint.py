"""Tests del endpoint /api/v1/analytics/student/{id}/alerts (ADR-022).

Cubre modo dev (sin DBs) + declaración de lenguajes (multi-language-research-
integrity sección 4.6/4.8/4.9/4.10). La lógica estadística de alertas ya está
cubierta por `packages/platform-ops/tests/test_cii_alerts.py`.
"""

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
    return f"/api/v1/analytics/student/{student_pseudonym}/alerts?comision_id={comision_id}"


# ── Auth ──────────────────────────────────────────────────────────────


def test_sin_tenant_header_devuelve_401(client: TestClient) -> None:
    r = client.get(_url(str(uuid4()), str(uuid4())))
    assert r.status_code == 401


def test_sin_user_header_devuelve_401(client: TestClient) -> None:
    r = client.get(_url(str(uuid4()), str(uuid4())), headers={"X-Tenant-Id": _TENANT_ID})
    assert r.status_code == 401


def test_comision_id_query_param_requerido(client: TestClient) -> None:
    r = client.get(
        f"/api/v1/analytics/student/{uuid4()}/alerts",
        headers=_VALID_HEADERS,
    )
    assert r.status_code == 422


# ── Modo dev ──────────────────────────────────────────────────────────


def test_modo_dev_devuelve_estructura_vacia_con_200(client: TestClient) -> None:
    student = str(uuid4())
    comision = str(uuid4())
    r = client.get(_url(student, comision), headers=_VALID_HEADERS)
    assert r.status_code == 200

    data = r.json()
    assert data["student_pseudonym"] == student
    assert data["comision_id"] == comision
    assert data["student_slope"] is None
    assert data["alerts"] == []
    assert data["n_alerts"] == 0
    assert data["highest_severity"] is None


def test_response_shape_es_estable(client: TestClient) -> None:
    r = client.get(_url(str(uuid4()), str(uuid4())), headers=_VALID_HEADERS)
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
        "languages_present",  # multi-language-research-integrity sección 4.6
    }


# ── Segmentación por lenguaje (sección 4) ──────────────────────────────


def test_modo_dev_declara_languages_present_vacio(client: TestClient) -> None:
    """4.2/4.6: declaración SIEMPRE presente, incluso sin datos (modo dev)."""
    r = client.get(_url(str(uuid4()), str(uuid4())), headers=_VALID_HEADERS)
    assert r.status_code == 200
    assert r.json()["languages_present"] == []


def test_modo_dev_acepta_filtro_de_lenguaje_sin_romper(client: TestClient) -> None:
    """4.10: el query param `language` es aceptado en modo dev sin cambiar
    el comportamiento (sigue devolviendo la estructura vacía de siempre)."""
    student = str(uuid4())
    comision = str(uuid4())
    r = client.get(f"{_url(student, comision)}&language=java", headers=_VALID_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["student_slope"] is None
    assert data["languages_present"] == []
