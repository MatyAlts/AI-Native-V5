"""Tests del endpoint /health/ready del api-gateway."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from api_gateway.main import app
from fastapi.testclient import TestClient
from platform_observability.health import CheckResult, _http_cache_clear


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _http_cache_clear()


def _ok() -> CheckResult:
    return CheckResult(ok=True, latency_ms=5)


def _ko() -> CheckResult:
    return CheckResult(ok=False, latency_ms=2000, error="down")


def _patch_check_http(*results: CheckResult) -> Any:
    mock = AsyncMock(side_effect=list(results))
    return patch("api_gateway.routes.health.check_http", mock)


def test_health_ready_all_ok() -> None:
    client = TestClient(app)
    with _patch_check_http(_ok(), _ok()):
        response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "api-gateway"
    assert set(body["checks"].keys()) == {"keycloak_jwks", "academic_service"}


def test_health_ready_keycloak_down_returns_503() -> None:
    client = TestClient(app)
    with _patch_check_http(_ko(), _ok()):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_health_ready_academic_down_returns_degraded() -> None:
    client = TestClient(app)
    with _patch_check_http(_ok(), _ko()):
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_live_always_200() -> None:
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
