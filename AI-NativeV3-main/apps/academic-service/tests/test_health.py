"""Tests del endpoint /health del academic-service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from academic_service.main import app
from httpx import ASGITransport, AsyncClient
from platform_observability.health import CheckResult


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _ok() -> CheckResult:
    return CheckResult(ok=True, latency_ms=5)


def _ko() -> CheckResult:
    return CheckResult(ok=False, latency_ms=2000, error="connection refused")


def _patch_db(result: CheckResult) -> Any:
    return patch(
        "academic_service.routes.health.check_postgres",
        AsyncMock(return_value=result),
    )


async def test_health_ready_db_ok(client: AsyncClient) -> None:
    with _patch_db(_ok()):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "academic-service"
    assert body["status"] == "ready"
    assert body["checks"]["academic_main_db"]["ok"] is True


async def test_health_ready_db_down(client: AsyncClient) -> None:
    with _patch_db(_ko()):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_alias_routes_to_ready(client: AsyncClient) -> None:
    with _patch_db(_ok()):
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "academic-service"


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "academic-service"
