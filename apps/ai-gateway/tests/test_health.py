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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
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


def _byok_apagado() -> Any:
    """Neutraliza el TERCER check del readiness.

    `/health/ready` agrega tres checks —`redis`, `llm_provider` y
    `byok_resolver`— y los tests de abajo solo fijaban los dos primeros. El
    tercero se resolvia contra el ambiente: `Settings.byok_enabled` viene en
    `True` por default y `byok_master_key` en `""`, asi que
    `_check_byok_resolver()` devuelve KO ("BYOK_MASTER_KEY missing y sin env
    fallback") y el readiness global sale `degraded`. Eso NO es un bug del
    endpoint —el resolver realmente esta inservible sin master key— sino un
    test que afirmaba `ready` sin controlar una de las tres entradas.

    Con BYOK apagado el check devuelve ok y cada test vuelve a medir lo que
    su nombre dice. La degradacion por BYOK tiene su propio test abajo.
    """
    return patch("ai_gateway.routes.health.settings.byok_enabled", False)


async def test_health_ready_mock_provider_redis_ok(client: AsyncClient) -> None:
    with _patch_redis(_ok()), _byok_apagado(), patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai-gateway"
    assert body["status"] == "ready"
    assert body["checks"]["llm_provider"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True
    assert body["checks"]["byok_resolver"]["ok"] is True


async def test_health_ready_redis_down_returns_error(client: AsyncClient) -> None:
    with (
        _patch_redis(_ko("redis down")),
        _byok_apagado(),
        patch.dict(os.environ, {"LLM_PROVIDER": "mock"}),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


async def test_health_ready_anthropic_no_key_returns_degraded(
    client: AsyncClient,
) -> None:
    """LLM_PROVIDER=anthropic sin api key → llm_provider KO → degraded."""
    with (
        _patch_redis(_ok()),
        _byok_apagado(),
        patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}),
        patch("ai_gateway.routes.health.settings.anthropic_api_key", ""),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["llm_provider"]["ok"] is False
    assert "anthropic api key" in body["checks"]["llm_provider"]["error"]


async def test_health_ready_byok_sin_master_key_ni_fallback_degrada(
    client: AsyncClient,
) -> None:
    """El caso que estaba tapando al test de arriba, ahora verificado a proposito.

    `BYOK_ENABLED=True` (el default de `Settings`) sin `BYOK_MASTER_KEY` ni
    env fallback deja al resolver inservible. Es non-critical: el readiness
    baja a `degraded` pero sigue devolviendo 200, porque los handlers ya
    contestan 503 por su cuenta cuando el resolver no puede darles una key.
    """
    with (
        _patch_redis(_ok()),
        patch("ai_gateway.routes.health.settings.byok_enabled", True),
        patch("ai_gateway.routes.health.settings.byok_master_key", ""),
        patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=False),
    ):
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY"):
            os.environ.pop(var, None)
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["byok_resolver"]["ok"] is False
    assert "BYOK_MASTER_KEY missing" in body["checks"]["byok_resolver"]["error"]


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "ai-gateway"
