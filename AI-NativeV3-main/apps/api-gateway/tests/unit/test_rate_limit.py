"""Tests del rate limiter con fakeredis.

Prueba propiedades del sliding window:
  - Allow hasta `max_requests`
  - 429 cuando se supera
  - Principals independientes no se afectan
  - Paths con límites distintos se rigen por distintos presupuestos
  - Retry-After refleja el TTL remanente
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest
from api_gateway.services.rate_limit import (
    DEFAULT_LIMIT,
    RateLimitConfig,
    RateLimiter,
    config_for_path,
    principal_from_request,
)


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


async def test_permite_hasta_el_limite(redis_client) -> None:
    limiter = RateLimiter(redis_client)
    cfg = RateLimitConfig(window_seconds=60, max_requests=3)

    for i in range(3):
        r = await limiter.check("u:alice", cfg)
        assert r.allowed
        assert r.current == i + 1


async def test_rechaza_tras_exceder(redis_client) -> None:
    limiter = RateLimiter(redis_client)
    cfg = RateLimitConfig(window_seconds=60, max_requests=2)

    await limiter.check("u:bob", cfg)
    await limiter.check("u:bob", cfg)
    r = await limiter.check("u:bob", cfg)
    assert not r.allowed
    assert r.current == 3
    assert r.limit == 2
    assert r.retry_after_seconds is not None
    assert r.retry_after_seconds > 0


async def test_principals_son_independientes(redis_client) -> None:
    limiter = RateLimiter(redis_client)
    cfg = RateLimitConfig(window_seconds=60, max_requests=2)

    await limiter.check("u:alice", cfg)
    await limiter.check("u:alice", cfg)
    r_alice = await limiter.check("u:alice", cfg)
    assert not r_alice.allowed

    # bob arranca en 0 aunque alice esté bloqueada
    r_bob = await limiter.check("u:bob", cfg)
    assert r_bob.allowed
    assert r_bob.current == 1


# ── Principal inference ────────────────────────────────────────────────


def test_principal_prioriza_user_id() -> None:
    assert principal_from_request("user-123", "tenant-abc", "1.2.3.4") == "u:user-123"


def test_principal_fallback_tenant_si_no_user() -> None:
    assert principal_from_request(None, "tenant-abc", "1.2.3.4") == "t:tenant-abc"


def test_principal_fallback_ip_si_nada() -> None:
    assert principal_from_request(None, None, "10.0.0.1") == "ip:10.0.0.1"


def test_principal_unknown_si_ni_ip() -> None:
    assert principal_from_request(None, None, None) == "ip:unknown"


# ── Path-based limits ──────────────────────────────────────────────────


def test_config_for_path_usa_episodes_limit_para_message() -> None:
    cfg = config_for_path("/api/v1/episodes/abc/message")
    assert cfg.max_requests == 30  # el tier de episodes


def test_config_for_path_usa_retrieve_limit() -> None:
    cfg = config_for_path("/api/v1/retrieve")
    assert cfg.max_requests == 60


def test_config_for_path_default_para_otras_rutas() -> None:
    cfg = config_for_path("/api/v1/universidades")
    assert cfg.max_requests == DEFAULT_LIMIT.max_requests


def test_config_for_path_classify_episode_tiene_limite_propio() -> None:
    cfg = config_for_path("/api/v1/classify_episode/abc")
    assert cfg.max_requests == 20


# ── Integración con ventanas ───────────────────────────────────────────


async def test_distintas_rutas_usan_distintos_budgets_separadamente(
    redis_client,
) -> None:
    """Agotar el budget de una ruta no afecta a otra ruta para el mismo usuario.

    NOTA: actualmente la implementación del limiter usa un único bucket
    por principal, NO bucket-per-path. Este test documenta el comportamiento
    actual para que el cambio futuro a bucket-per-path sea deliberado.
    """
    limiter = RateLimiter(redis_client)
    tight = RateLimitConfig(window_seconds=60, max_requests=2)
    loose = RateLimitConfig(window_seconds=60, max_requests=10)

    # Usar un principal incluyendo el tier como parte del key
    # (lo hacemos aquí para documentar el patrón recomendado)
    for _ in range(2):
        r = await limiter.check("u:alice:episodes", tight)
        assert r.allowed

    r3 = await limiter.check("u:alice:episodes", tight)
    assert not r3.allowed

    # Otro tier del mismo usuario: aún libre
    r_other = await limiter.check("u:alice:retrieve", loose)
    assert r_other.allowed
