"""Tests del health check del resolver BYOK + provider unknown.

Cubre `apps/ai-gateway/src/ai_gateway/routes/health.py`:
- `_check_byok_resolver` con BYOK_ENABLED=False (ok).
- Con BYOK_ENABLED=True + master key valida (ok).
- Con BYOK_ENABLED=True sin master key pero env fallback (degraded ok=False).
- Con BYOK_ENABLED=True sin master key NI env (error ok=False).
- `_check_llm_provider` con LLM_PROVIDER=other-provider (unknown).
"""

from __future__ import annotations

import base64
import os
from unittest.mock import AsyncMock, patch

import pytest
from ai_gateway.main import app
from ai_gateway.routes.health import _check_byok_resolver, _check_llm_provider
from httpx import ASGITransport, AsyncClient
from platform_observability.health import CheckResult


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ── _check_byok_resolver (sync) ────────────────────────────────────────


def test_byok_disabled_ok(monkeypatch) -> None:
    from ai_gateway import config as ai_config

    monkeypatch.setattr(ai_config.settings, "byok_enabled", False)
    result = _check_byok_resolver()
    assert result.ok is True


def test_byok_enabled_master_key_valida_ok(monkeypatch) -> None:
    from ai_gateway import config as ai_config

    valid_key = base64.b64encode(b"\x33" * 32).decode()
    monkeypatch.setattr(ai_config.settings, "byok_enabled", True)
    monkeypatch.setattr(ai_config.settings, "byok_master_key", valid_key)
    result = _check_byok_resolver()
    assert result.ok is True


def test_byok_enabled_sin_master_pero_env_fallback_es_degraded(monkeypatch) -> None:
    from ai_gateway import config as ai_config

    monkeypatch.setattr(ai_config.settings, "byok_enabled", True)
    monkeypatch.setattr(ai_config.settings, "byok_master_key", "")
    monkeypatch.setattr(ai_config.settings, "anthropic_api_key", "sk-ant-fake")
    monkeypatch.setattr(ai_config.settings, "openai_api_key", "")
    monkeypatch.setattr(ai_config.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai_config.settings, "mistral_api_key", "")

    result = _check_byok_resolver()
    assert result.ok is False
    assert "BYOK_MASTER_KEY missing" in result.error
    assert "env fallback disponible" in result.error


def test_byok_enabled_sin_master_y_sin_env_es_error(monkeypatch) -> None:
    from ai_gateway import config as ai_config

    monkeypatch.setattr(ai_config.settings, "byok_enabled", True)
    monkeypatch.setattr(ai_config.settings, "byok_master_key", "")
    monkeypatch.setattr(ai_config.settings, "anthropic_api_key", "")
    monkeypatch.setattr(ai_config.settings, "openai_api_key", "")
    monkeypatch.setattr(ai_config.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai_config.settings, "mistral_api_key", "")

    result = _check_byok_resolver()
    assert result.ok is False
    assert "sin env fallback" in result.error


# ── _check_llm_provider unknown ────────────────────────────────────────


def test_llm_provider_unknown_es_error(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "perplexity")
    result = _check_llm_provider()
    assert result.ok is False
    assert "unknown provider" in result.error


def test_llm_provider_anthropic_con_key_ok(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    from ai_gateway import config as ai_config

    monkeypatch.setattr(ai_config.settings, "anthropic_api_key", "sk-ant-real")
    result = _check_llm_provider()
    assert result.ok is True


# ── Endpoint /health/ready integration con byok degraded ───────────────


async def test_health_byok_degraded_pero_redis_ok_devuelve_200_degraded(
    client: AsyncClient, monkeypatch
) -> None:
    """BYOK degraded NO escala a critical. Si redis ok + llm_provider ok pero
    byok degraded, status='degraded' con HTTP 200."""
    from ai_gateway import config as ai_config

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr(ai_config.settings, "byok_enabled", True)
    monkeypatch.setattr(ai_config.settings, "byok_master_key", "")
    monkeypatch.setattr(ai_config.settings, "anthropic_api_key", "sk-ant-fake")

    with patch(
        "ai_gateway.routes.health.check_redis",
        AsyncMock(return_value=CheckResult(ok=True, latency_ms=5)),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["byok_resolver"]["ok"] is False
