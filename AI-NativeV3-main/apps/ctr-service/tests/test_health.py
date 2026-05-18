"""Tests del endpoint de salud."""

from unittest.mock import AsyncMock, patch

import pytest
from ctr_service.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_ready_ok_when_deps_up(client: AsyncClient) -> None:
    with (
        patch("ctr_service.routes.health._check_db", new=AsyncMock(return_value="ok")),
        patch("ctr_service.routes.health._check_redis", new=AsyncMock(return_value="ok")),
    ):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ctr-service"
    assert data["status"] == "ready"
    assert data["checks"] == {"db": "ok", "redis": "ok"}


async def test_health_ready_degraded_when_db_down(client: AsyncClient) -> None:
    with (
        patch(
            "ctr_service.routes.health._check_db",
            new=AsyncMock(return_value="fail: ConnectionRefusedError"),
        ),
        patch("ctr_service.routes.health._check_redis", new=AsyncMock(return_value="ok")),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["db"].startswith("fail")
    assert data["checks"]["redis"] == "ok"


async def test_health_ready_degraded_when_redis_down(client: AsyncClient) -> None:
    with (
        patch("ctr_service.routes.health._check_db", new=AsyncMock(return_value="ok")),
        patch(
            "ctr_service.routes.health._check_redis",
            new=AsyncMock(return_value="fail: TimeoutError"),
        ),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"].startswith("fail")


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ctr-service"
