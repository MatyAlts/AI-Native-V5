"""Tests del endpoint /api/v1/analytics/kappa."""

from __future__ import annotations

import logging

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _rating(ep: str, a: str, b: str) -> dict:
    return {"episode_id": ep, "rater_a": a, "rater_b": b}


_KAPPA_HEADERS = {
    "X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "X-User-Id": "11111111-1111-1111-1111-111111111111",
}


# ── Happy path ────────────────────────────────────────────────────────


def test_kappa_endpoint_con_acuerdo_perfecto(client: TestClient) -> None:
    ratings = [
        _rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva"),
        _rating("ep2", "apropiacion_superficial", "apropiacion_superficial"),
        _rating("ep3", "delegacion_pasiva", "delegacion_pasiva"),
    ]
    r = client.post("/api/v1/analytics/kappa", json={"ratings": ratings}, headers=_KAPPA_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["kappa"] == 1.0
    assert data["n_episodes"] == 3
    assert data["interpretation"] == "casi perfecto"


def test_kappa_endpoint_con_desacuerdo_parcial(client: TestClient) -> None:
    ratings = [
        _rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva"),
        _rating("ep2", "apropiacion_reflexiva", "apropiacion_superficial"),  # disagree
        _rating("ep3", "apropiacion_superficial", "apropiacion_superficial"),
        _rating("ep4", "delegacion_pasiva", "delegacion_pasiva"),
    ]
    r = client.post("/api/v1/analytics/kappa", json={"ratings": ratings}, headers=_KAPPA_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert 0 < data["kappa"] < 1.0
    assert data["observed_agreement"] == 0.75  # 3 de 4 aciertos


def test_kappa_endpoint_incluye_matriz_de_confusion(client: TestClient) -> None:
    ratings = [
        _rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva"),
        _rating("ep2", "apropiacion_reflexiva", "apropiacion_superficial"),
    ]
    r = client.post("/api/v1/analytics/kappa", json={"ratings": ratings}, headers=_KAPPA_HEADERS)
    assert r.status_code == 200
    data = r.json()
    cm = data["confusion_matrix"]
    assert cm["apropiacion_reflexiva"]["apropiacion_reflexiva"] == 1
    assert cm["apropiacion_reflexiva"]["apropiacion_superficial"] == 1


def test_kappa_endpoint_incluye_per_class_agreement(client: TestClient) -> None:
    ratings = [
        _rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva"),
        _rating("ep2", "delegacion_pasiva", "delegacion_pasiva"),
    ]
    r = client.post("/api/v1/analytics/kappa", json={"ratings": ratings}, headers=_KAPPA_HEADERS)
    data = r.json()
    assert "per_class_agreement" in data
    assert data["per_class_agreement"]["apropiacion_reflexiva"] == 1.0


# ── Validación ────────────────────────────────────────────────────────


def test_kappa_endpoint_categoria_invalida_422(client: TestClient) -> None:
    """Pydantic Literal rechaza categorías inválidas con 422."""
    bad = {"episode_id": "x", "rater_a": "foobar", "rater_b": "apropiacion_reflexiva"}
    r = client.post("/api/v1/analytics/kappa", json={"ratings": [bad]}, headers=_KAPPA_HEADERS)
    assert r.status_code == 422


def test_kappa_endpoint_sin_ratings_422(client: TestClient) -> None:
    r = client.post("/api/v1/analytics/kappa", json={"ratings": []}, headers=_KAPPA_HEADERS)
    assert r.status_code == 422  # min_length=1


# ── BUG-26: auth + audit log ──────────────────────────────────────────


def test_kappa_sin_tenant_header_401(client: TestClient) -> None:
    """Sin X-Tenant-Id el endpoint rechaza con 401 (BUG-26)."""
    ratings = [_rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva")]
    r = client.post(
        "/api/v1/analytics/kappa",
        json={"ratings": ratings},
        headers={"X-User-Id": "11111111-1111-1111-1111-111111111111"},
    )
    assert r.status_code == 401


def test_kappa_user_header_invalido_400(client: TestClient) -> None:
    """X-User-Id no-UUID retorna 400 (BUG-26)."""
    ratings = [_rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva")]
    r = client.post(
        "/api/v1/analytics/kappa",
        json={"ratings": ratings},
        headers={
            "X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "X-User-Id": "not-a-uuid",
        },
    )
    assert r.status_code == 400


def test_kappa_emite_audit_log_estructurado(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """El endpoint emite `kappa_computed` con tenant/user/n_episodes/kappa (BUG-26)."""
    ratings = [
        _rating("ep1", "apropiacion_reflexiva", "apropiacion_reflexiva"),
        _rating("ep2", "delegacion_pasiva", "delegacion_pasiva"),
    ]
    with caplog.at_level(logging.INFO, logger="analytics_service.routes.analytics"):
        r = client.post(
            "/api/v1/analytics/kappa", json={"ratings": ratings}, headers=_KAPPA_HEADERS
        )
    assert r.status_code == 200

    audit_lines = [rec for rec in caplog.records if "kappa_computed" in rec.getMessage()]
    assert len(audit_lines) == 1, f"esperaba 1 audit log, obtuve {len(audit_lines)}"

    msg = audit_lines[0].getMessage()
    assert _KAPPA_HEADERS["X-Tenant-Id"] in msg
    assert _KAPPA_HEADERS["X-User-Id"] in msg
    assert "n_episodes=2" in msg
    assert "kappa=" in msg


# ── Cohort export endpoint ────────────────────────────────────────────


_AUTH_HEADERS = {
    "X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "X-User-Id": "11111111-1111-1111-1111-111111111111",
}


def test_cohort_export_acepta_request_valido(client: TestClient) -> None:
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "period_days": 90,
            "include_prompts": False,
            "salt": "research_salt_16_chars_min_yes",
            "cohort_alias": "UNSL_2026_P2",
        },
        headers=_AUTH_HEADERS,
    )
    assert r.status_code == 202
    data = r.json()
    # F7: respuesta con job_id + status pending
    assert data["status"] == "pending"
    assert "job_id" in data


def test_cohort_export_salt_corto_falla_422(client: TestClient) -> None:
    r = client.post(
        "/api/v1/analytics/cohort/export",
        json={
            "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "salt": "short",  # < 16 chars
        },
        headers=_AUTH_HEADERS,
    )
    assert r.status_code == 422
