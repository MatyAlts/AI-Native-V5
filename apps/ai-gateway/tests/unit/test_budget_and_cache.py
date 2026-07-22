"""Tests de BudgetTracker y ResponseCache usando fakeredis."""

from __future__ import annotations

from uuid import uuid4

import fakeredis.aioredis
import pytest
from ai_gateway.providers.base import CompletionRequest, CompletionResponse
from ai_gateway.services.budget_and_cache import BudgetTracker, ResponseCache


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


# ── BudgetTracker ──────────────────────────────────────────────────────


async def test_budget_empieza_en_cero(redis_client) -> None:
    tenant = uuid4()
    tracker = BudgetTracker(redis_client)
    status = await tracker.check(tenant, "tutor", limit_usd=100.0)
    assert status.used_usd == 0.0
    assert status.remaining_usd == 100.0
    assert not status.exceeded


async def test_budget_se_acumula(redis_client) -> None:
    tenant = uuid4()
    tracker = BudgetTracker(redis_client)
    total1 = await tracker.charge(tenant, "tutor", 1.5)
    total2 = await tracker.charge(tenant, "tutor", 2.5)
    assert total1 == pytest.approx(1.5)
    assert total2 == pytest.approx(4.0)


async def test_budget_exceeded_cuando_supera_limite(redis_client) -> None:
    tenant = uuid4()
    tracker = BudgetTracker(redis_client)
    await tracker.charge(tenant, "tutor", 99.0)
    status = await tracker.check(tenant, "tutor", limit_usd=50.0)
    assert status.exceeded
    assert status.remaining_usd == 0.0


async def test_budgets_separados_por_feature(redis_client) -> None:
    tenant = uuid4()
    tracker = BudgetTracker(redis_client)
    await tracker.charge(tenant, "tutor", 10.0)
    status_tutor = await tracker.check(tenant, "tutor", 100.0)
    status_classifier = await tracker.check(tenant, "classifier", 100.0)
    assert status_tutor.used_usd == pytest.approx(10.0)
    assert status_classifier.used_usd == 0.0


async def test_budgets_separados_por_tenant(redis_client) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    tracker = BudgetTracker(redis_client)
    await tracker.charge(tenant_a, "tutor", 10.0)
    status_a = await tracker.check(tenant_a, "tutor", 100.0)
    status_b = await tracker.check(tenant_b, "tutor", 100.0)
    assert status_a.used_usd == pytest.approx(10.0)
    assert status_b.used_usd == 0.0


# ── ResponseCache ──────────────────────────────────────────────────────


def _req(temp: float = 0.0) -> CompletionRequest:
    return CompletionRequest(
        messages=[{"role": "user", "content": "¿Qué es recursión?"}],
        model="claude-sonnet-4-6",
        temperature=temp,
        max_tokens=512,
    )


def _resp() -> CompletionResponse:
    return CompletionResponse(
        content="respuesta cacheable",
        model="claude-sonnet-4-6",
        provider="anthropic",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0001,
    )


async def test_cache_miss_primera_vez(redis_client) -> None:
    cache = ResponseCache(redis_client)
    result = await cache.get(_req())
    assert result is None


async def test_cache_hit_despues_de_set(redis_client) -> None:
    cache = ResponseCache(redis_client)
    req = _req()
    await cache.set(req, _resp())
    cached = await cache.get(req)
    assert cached is not None
    assert cached.content == "respuesta cacheable"
    assert cached.cache_hit is True


async def test_cache_no_guarda_si_temperature_no_cero(redis_client) -> None:
    """Con temperature > 0, el resultado no es determinista y no debe cachearse."""
    cache = ResponseCache(redis_client)
    req = _req(temp=0.7)
    await cache.set(req, _resp())
    cached = await cache.get(req)
    assert cached is None


async def test_cache_key_cambia_con_model(redis_client) -> None:
    """Cambiar el model cambia la key del cache."""
    cache = ResponseCache(redis_client)
    req_sonnet = _req()
    await cache.set(req_sonnet, _resp())

    req_haiku = CompletionRequest(
        messages=req_sonnet.messages,
        model="claude-haiku-4-5",
        temperature=0.0,
        max_tokens=512,
    )
    assert await cache.get(req_haiku) is None
    assert await cache.get(req_sonnet) is not None


async def test_cache_key_es_independiente_de_orden_de_keys(redis_client) -> None:
    """Dos requests lógicamente iguales pero con keys en distinto orden
    deben compartir cache (canonical JSON)."""
    cache = ResponseCache(redis_client)
    req1 = CompletionRequest(
        messages=[{"role": "user", "content": "¿qué es un bucle?"}],
        model="claude-sonnet-4-6",
        temperature=0.0,
        max_tokens=1024,
    )
    # Mismo canonical input
    req2 = CompletionRequest(
        messages=[{"content": "¿qué es un bucle?", "role": "user"}],
        model="claude-sonnet-4-6",
        temperature=0.0,
        max_tokens=1024,
    )
    await cache.set(req1, _resp())
    cached = await cache.get(req2)
    assert cached is not None
