"""Tests legacy del endpoint /health del api-gateway.

Cobertura granular en `tests/unit/test_health_ready.py`. Este archivo
mantiene los smokes mínimos que pre-existían, ahora con mocks del helper
porque `/health/ready` pega real a Keycloak + academic-service desde la
epic `real-health-checks` (2026-05-04).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from api_gateway.main import app
from httpx import ASGITransport, AsyncClient
from platform_observability.health import CheckResult, _http_cache_clear


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _http_cache_clear()


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _ok() -> CheckResult:
    return CheckResult(ok=True, latency_ms=5)


def _patch_check_http(*results: CheckResult) -> Any:
    return patch(
        "api_gateway.routes.health.check_http",
        AsyncMock(side_effect=list(results)),
    )


async def test_health_ready(client: AsyncClient) -> None:
    with _patch_check_http(_ok(), _ok()):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "api-gateway"
    assert data["status"] == "ready"


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "api-gateway"
