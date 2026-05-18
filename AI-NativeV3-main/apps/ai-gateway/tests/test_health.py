"""Tests del endpoint /health del ai-gateway."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from ai_gateway.main import app
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


def _patch_redis(result: CheckResult) -> Any:
    return patch(
        "ai_gateway.routes.health.check_redis",
        AsyncMock(return_value=result),
    )


async def test_health_ready_mock_provider_redis_ok(client: AsyncClient) -> None:
    with _patch_redis(_ok()), patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai-gateway"
    assert body["status"] == "ready"
    assert body["checks"]["llm_provider"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True


async def test_health_ready_redis_down_returns_error(client: AsyncClient) -> None:
    with _patch_redis(_ko("redis down")), patch.dict(
        os.environ, {"LLM_PROVIDER": "mock"}
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_ready_anthropic_no_key_returns_degraded(
    client: AsyncClient,
) -> None:
    """LLM_PROVIDER=anthropic sin api key → llm_provider KO → degraded."""
    with _patch_redis(_ok()), patch.dict(
        os.environ, {"LLM_PROVIDER": "anthropic"}
    ), patch("ai_gateway.routes.health.settings.anthropic_api_key", ""):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["llm_provider"]["ok"] is False
    assert "anthropic api key" in body["checks"]["llm_provider"]["error"]


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ai-gateway"
