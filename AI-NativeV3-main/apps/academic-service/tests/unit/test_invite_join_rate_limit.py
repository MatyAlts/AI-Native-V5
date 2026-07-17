"""Tests del rate-limit dedicado del canje de invite_code (A0.7).

Dos capas:
  1. `InviteJoinRateLimiter` sobre fakeredis — propiedades del sliding window
     (permite hasta el tope, corta después, retry-after, buckets independientes,
     fail-open).
  2. Endpoint `POST /api/v1/comisiones/join` vía TestClient con el limiter
     inyectado sobre fakeredis y topes bajos: N intentos fallidos seguidos →
     429; el intento correcto DENTRO del límite → 200.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import fakeredis.aioredis
import pytest
from academic_service.auth.dependencies import User, get_current_user, get_db
from academic_service.main import app
from academic_service.routes import comisiones as comisiones_routes
from academic_service.services.rate_limit import (
    DEFAULT_ACTOR_CONFIG,
    InviteJoinRateLimiter,
    RateLimitConfig,
    actor_principal,
)
from fastapi import HTTPException, status
from fastapi.testclient import TestClient


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


# ── Capa 1: el limiter ────────────────────────────────────────────────


async def test_actor_permite_hasta_el_tope(redis_client) -> None:
    limiter = InviteJoinRateLimiter(
        redis_client, actor_config=RateLimitConfig(window_seconds=60, max_requests=3)
    )
    for i in range(3):
        r = await limiter.check_actor("u:alice")
        assert r.allowed
        assert r.current == i + 1


async def test_actor_corta_tras_exceder(redis_client) -> None:
    limiter = InviteJoinRateLimiter(
        redis_client, actor_config=RateLimitConfig(window_seconds=60, max_requests=2)
    )
    await limiter.check_actor("u:bob")
    await limiter.check_actor("u:bob")
    r = await limiter.check_actor("u:bob")
    assert not r.allowed
    assert r.limit == 2
    assert r.retry_after_seconds is not None and r.retry_after_seconds > 0


async def test_actores_independientes(redis_client) -> None:
    limiter = InviteJoinRateLimiter(
        redis_client, actor_config=RateLimitConfig(window_seconds=60, max_requests=1)
    )
    await limiter.check_actor("u:alice")
    assert not (await limiter.check_actor("u:alice")).allowed
    # bob arranca limpio aunque alice esté bloqueada.
    assert (await limiter.check_actor("u:bob")).allowed


async def test_code_solo_cuenta_fallos(redis_client) -> None:
    """El bucket del código sube solo con `register_code_failure`; el peek no."""
    limiter = InviteJoinRateLimiter(
        redis_client, code_config=RateLimitConfig(window_seconds=300, max_requests=2)
    )
    # Peek inicial: libre.
    assert (await limiter.code_is_exhausted("ABC123")).allowed
    await limiter.register_code_failure("ABC123")
    await limiter.register_code_failure("ABC123")
    # 2 fallos alcanzaron el tope → el próximo peek corta.
    r = await limiter.code_is_exhausted("ABC123")
    assert not r.allowed
    assert r.retry_after_seconds is not None and r.retry_after_seconds > 0


async def test_fail_open_si_redis_cae() -> None:
    """Si Redis lanza, el limiter permite (no bloquea inscripciones legítimas)."""

    class _BrokenRedis:
        async def incr(self, key):
            raise ConnectionError("redis down")

        async def expire(self, key, seconds):
            raise ConnectionError("redis down")

        async def ttl(self, key):
            raise ConnectionError("redis down")

        async def get(self, key):
            raise ConnectionError("redis down")

    limiter = InviteJoinRateLimiter(_BrokenRedis())  # type: ignore[arg-type]
    assert (await limiter.check_actor("u:alice")).allowed
    assert (await limiter.code_is_exhausted("ABC123")).allowed


def test_actor_principal_prioriza_user_y_cae_a_ip() -> None:
    assert actor_principal("user-1", "1.2.3.4") == "u:user-1"
    assert actor_principal(None, "1.2.3.4") == "ip:1.2.3.4"
    assert actor_principal(None, None) == "ip:unknown"


def test_default_actor_config_es_10_por_60s() -> None:
    assert DEFAULT_ACTOR_CONFIG.window_seconds == 60
    assert DEFAULT_ACTOR_CONFIG.max_requests == 10


# ── Capa 2: el endpoint ───────────────────────────────────────────────


def _student() -> User:
    tid = uuid4()
    return User(
        id=uuid4(),
        tenant_id=tid,
        email="alu@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm=str(tid),
    )


def _fake_comision(user: User) -> SimpleNamespace:
    """Objeto attribute-compatible con `ComisionOut.model_validate`."""
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=user.tenant_id,
        materia_id=uuid4(),
        periodo_id=uuid4(),
        codigo="COM-A",
        nombre="Comision A",
        cupo_maximo=50,
        horario={},
        ai_budget_monthly_usd=Decimal("100.00"),
        materia_nombre=None,
        materia_codigo=None,
        curso_config_hash=None,
        invite_code="ABC123",
        created_at=datetime.now(UTC),
        deleted_at=None,
    )


@pytest.fixture
def student() -> User:
    return _student()


@pytest.fixture
def client(student: User, redis_client):
    """TestClient con auth, DB y limiter (actor tope=3) inyectados."""
    limiter = InviteJoinRateLimiter(
        redis_client,
        actor_config=RateLimitConfig(window_seconds=60, max_requests=3),
        code_config=RateLimitConfig(window_seconds=300, max_requests=20),
    )

    async def _fake_db():
        yield object()  # el service está monkeypatcheado; la sesión no se usa

    app.dependency_overrides[get_current_user] = lambda: student
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[comisiones_routes.get_invite_rate_limiter] = lambda: limiter
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_n_intentos_fallidos_seguidos_devuelven_429(client, monkeypatch) -> None:
    """Con tope de actor=3: 3 códigos inválidos (404) y el 4º → 429."""

    async def _always_404(self, invite_code, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="inválido")

    monkeypatch.setattr(
        comisiones_routes.ComisionService, "join_by_invite_code", _always_404
    )

    for _ in range(3):
        r = client.post("/api/v1/comisiones/join", json={"invite_code": "ZZZ999"})
        assert r.status_code == status.HTTP_404_NOT_FOUND

    blocked = client.post("/api/v1/comisiones/join", json={"invite_code": "ZZZ999"})
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Retry-After" in blocked.headers


def test_intento_correcto_dentro_del_limite_entra(client, student, monkeypatch) -> None:
    """2 fallos y luego el código correcto (intento 3 ≤ tope) → 200."""
    calls = {"n": 0}
    good = _fake_comision(student)

    async def _fail_twice_then_ok(self, invite_code, user):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="inválido")
        return good

    monkeypatch.setattr(
        comisiones_routes.ComisionService, "join_by_invite_code", _fail_twice_then_ok
    )

    assert (
        client.post("/api/v1/comisiones/join", json={"invite_code": "AAA111"}).status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        client.post("/api/v1/comisiones/join", json={"invite_code": "AAA111"}).status_code
        == status.HTTP_404_NOT_FOUND
    )
    ok = client.post("/api/v1/comisiones/join", json={"invite_code": "ABC123"})
    assert ok.status_code == status.HTTP_200_OK
    body = ok.json()
    assert body["id"] == str(good.id)
    # El alumno no privilegiado no ve invite_code ni tenant_id (redacción).
    assert body["invite_code"] is None
    assert body["tenant_id"] is None
