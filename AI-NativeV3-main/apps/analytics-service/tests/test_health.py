"""Tests del endpoint /health del analytics-service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from analytics_service.main import app
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


def _ko(error: str = "down") -> CheckResult:
    return CheckResult(ok=False, latency_ms=2000, error=error)


def _patch_check_db(*results: CheckResult) -> Any:
    return patch(
        "analytics_service.routes.health._check_db",
        AsyncMock(side_effect=list(results)),
    )


async def test_health_ready_both_dbs_ok(client: AsyncClient) -> None:
    with _patch_check_db(_ok(), _ok()):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "analytics-service"
    assert body["status"] == "ready"
    assert set(body["checks"].keys()) == {"ctr_store_db", "classifier_db"}


async def test_health_ready_ctr_store_down(client: AsyncClient) -> None:
    with _patch_check_db(_ko("ctr down"), _ok()):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_ready_classifier_db_down(client: AsyncClient) -> None:
    with _patch_check_db(_ok(), _ko("classifier down")):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_ready_both_down(client: AsyncClient) -> None:
    with _patch_check_db(_ko(), _ko()):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "analytics-service"
