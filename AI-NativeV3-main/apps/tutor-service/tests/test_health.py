"""Tests del endpoint /health del tutor-service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from platform_observability.health import CheckResult, _http_cache_clear
from tutor_service.main import app


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


def _ko(error: str = "down") -> CheckResult:
    return CheckResult(ok=False, latency_ms=2000, error=error)


def _patch(redis_result: CheckResult, academic: CheckResult, ai: CheckResult) -> Any:
    return [
        patch(
            "tutor_service.routes.health.check_redis",
            AsyncMock(return_value=redis_result),
        ),
        patch(
            "tutor_service.routes.health.check_http",
            AsyncMock(side_effect=[academic, ai]),
        ),
    ]


async def test_health_ready_all_ok(client: AsyncClient) -> None:
    patches = _patch(_ok(), _ok(), _ok())
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "tutor-service"
    assert body["status"] == "ready"
    assert set(body["checks"].keys()) == {
        "redis",
        "academic_service",
        "ai_gateway",
    }


async def test_health_ready_redis_down_returns_error(client: AsyncClient) -> None:
    patches = _patch(_ko("redis down"), _ok(), _ok())
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_ready_ai_gateway_down_returns_degraded(
    client: AsyncClient,
) -> None:
    patches = _patch(_ok(), _ok(), _ko("ai down"))
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["ai_gateway"]["ok"] is False
    assert body["checks"]["redis"]["ok"] is True


async def test_health_ready_academic_service_down_returns_degraded(
    client: AsyncClient,
) -> None:
    patches = _patch(_ok(), _ko("academic down"), _ok())
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "tutor-service"
