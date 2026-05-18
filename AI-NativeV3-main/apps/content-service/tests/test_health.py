"""Tests del endpoint /health del content-service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from content_service.main import app
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


def _patch(db: CheckResult, pgvector: CheckResult) -> Any:
    return [
        patch(
            "content_service.routes.health.check_postgres",
            AsyncMock(return_value=db),
        ),
        patch(
            "content_service.routes.health._check_pgvector",
            AsyncMock(return_value=pgvector),
        ),
    ]


async def _with_patches(
    client: AsyncClient, db: CheckResult, pgvector: CheckResult
) -> Any:
    patches = _patch(db, pgvector)
    for p in patches:
        p.start()
    try:
        return await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()


async def test_health_ready_all_ok(client: AsyncClient) -> None:
    response = await _with_patches(client, _ok(), _ok())
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "content-service"
    assert body["status"] == "ready"
    assert set(body["checks"].keys()) == {"content_db", "pgvector_extension"}


async def test_health_ready_db_down(client: AsyncClient) -> None:
    response = await _with_patches(client, _ko("db down"), _ok())
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_ready_pgvector_missing(client: AsyncClient) -> None:
    """DB up but pgvector extension not installed → 503 (D7)."""
    response = await _with_patches(
        client, _ok(), _ko("pgvector extension not installed")
    )
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"]["content_db"]["ok"] is True
    assert body["checks"]["pgvector_extension"]["ok"] is False
    assert "pgvector" in body["checks"]["pgvector_extension"]["error"]


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "content-service"
