"""Tests del helper compartido `platform_observability.health`.

Cubre los 4 grupos exigidos por la spec
(`openspec/changes/real-health-checks/specs/service-readiness/spec.md`):

- `check_postgres`: success, failure, timeout (mock engine).
- `check_redis`: success, failure, timeout, cleanup en failure (mock client).
- `check_http`: success, failure, timeout, cache hit/miss/expiry, status mismatch.
- `assemble_readiness`: ready, degraded, error, missing critical, error precedence.

Sin infra real: todo con mocks.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from platform_observability.health import (
    CheckResult,
    HealthResponse,
    _http_cache_clear,
    assemble_readiness,
    check_http,
    check_postgres,
    check_redis,
)

# ────────────────── check_postgres ──────────────────


class _AsyncEngineMock:
    """Mock minimal de AsyncEngine.connect()."""

    def __init__(self, on_execute: Any = None, raise_at_connect: BaseException | None = None):
        self._on_execute = on_execute
        self._raise_at_connect = raise_at_connect

    def connect(self) -> _AsyncEngineMock:
        return self

    async def __aenter__(self) -> _AsyncEngineMock:
        if self._raise_at_connect is not None:
            raise self._raise_at_connect
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def execute(self, _stmt: Any) -> Any:
        if self._on_execute is not None:
            await self._on_execute()
        return MagicMock()


@pytest.mark.asyncio
async def test_check_postgres_ok() -> None:
    engine = _AsyncEngineMock()
    result = await check_postgres(engine, timeout=1.0)  # type: ignore[arg-type]
    assert result.ok is True
    assert result.error is None
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_check_postgres_failure_returns_check_result() -> None:
    engine = _AsyncEngineMock(raise_at_connect=RuntimeError("connection refused"))
    result = await check_postgres(engine, timeout=1.0)  # type: ignore[arg-type]
    assert result.ok is False
    assert result.error is not None
    assert "connection refused" in result.error
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_check_postgres_timeout() -> None:
    async def _slow() -> None:
        await asyncio.sleep(5)

    engine = _AsyncEngineMock(on_execute=_slow)
    result = await check_postgres(engine, timeout=0.05)  # type: ignore[arg-type]
    assert result.ok is False
    assert result.error is not None
    assert "timeout" in result.error
    assert result.latency_ms >= 50


# ────────────────── check_redis ──────────────────


class _RedisClientMock:
    """Mock de redis.asyncio.Redis."""

    def __init__(
        self,
        ping_raises: BaseException | None = None,
        ping_sleeps: float = 0.0,
    ):
        self._ping_raises = ping_raises
        self._ping_sleeps = ping_sleeps
        self.aclose_called = False

    async def ping(self) -> bool:
        if self._ping_sleeps:
            await asyncio.sleep(self._ping_sleeps)
        if self._ping_raises is not None:
            raise self._ping_raises
        return True

    async def aclose(self) -> None:
        self.aclose_called = True


def _patch_redis_from_url(client: _RedisClientMock) -> Any:
    return patch("redis.asyncio.from_url", return_value=client)


@pytest.mark.asyncio
async def test_check_redis_ok() -> None:
    client = _RedisClientMock()
    with _patch_redis_from_url(client):
        result = await check_redis("redis://localhost:6379", timeout=1.0)
    assert result.ok is True
    assert result.error is None
    assert client.aclose_called


@pytest.mark.asyncio
async def test_check_redis_failure_cleans_up() -> None:
    client = _RedisClientMock(ping_raises=ConnectionError("nope"))
    with _patch_redis_from_url(client):
        result = await check_redis("redis://localhost:6379", timeout=1.0)
    assert result.ok is False
    assert result.error is not None
    assert "nope" in result.error
    assert client.aclose_called  # cleanup garantizado en failure


@pytest.mark.asyncio
async def test_check_redis_timeout() -> None:
    client = _RedisClientMock(ping_sleeps=2.0)
    with _patch_redis_from_url(client):
        result = await check_redis("redis://localhost:6379", timeout=0.05)
    assert result.ok is False
    assert result.error is not None
    assert "timeout" in result.error


# ────────────────── check_http ──────────────────


class _ResponseMock:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _HTTPXClientMock:
    def __init__(
        self,
        response: _ResponseMock | None = None,
        raises: BaseException | None = None,
        sleeps: float = 0.0,
    ):
        self._response = response or _ResponseMock(200)
        self._raises = raises
        self._sleeps = sleeps
        self.calls = 0

    async def __aenter__(self) -> _HTTPXClientMock:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, _url: str) -> _ResponseMock:
        self.calls += 1
        if self._sleeps:
            await asyncio.sleep(self._sleeps)
        if self._raises is not None:
            raise self._raises
        return self._response


def _patch_httpx(client_factory: Any) -> Any:
    return patch("httpx.AsyncClient", side_effect=client_factory)


@pytest.fixture(autouse=True)
def _clear_http_cache() -> None:
    _http_cache_clear()


@pytest.mark.asyncio
async def test_check_http_ok_caches_result() -> None:
    client = _HTTPXClientMock(response=_ResponseMock(200))

    def factory(*_a: Any, **_kw: Any) -> _HTTPXClientMock:
        return client

    now = [1000.0]

    def fake_now() -> float:
        return now[0]

    with _patch_httpx(factory):
        first = await check_http(
            "http://x/y", timeout=1.0, cache_ttl=5.0, _now=fake_now
        )
        # advance 1s — cache still valid
        now[0] += 1
        second = await check_http(
            "http://x/y", timeout=1.0, cache_ttl=5.0, _now=fake_now
        )

    assert first.ok is True
    assert second.ok is True
    assert client.calls == 1  # second was cache hit


@pytest.mark.asyncio
async def test_check_http_cache_expires() -> None:
    client = _HTTPXClientMock(response=_ResponseMock(200))

    def factory(*_a: Any, **_kw: Any) -> _HTTPXClientMock:
        return client

    now = [1000.0]

    def fake_now() -> float:
        return now[0]

    with _patch_httpx(factory):
        await check_http("http://x/y", cache_ttl=5.0, _now=fake_now)
        now[0] += 6  # cache expired
        await check_http("http://x/y", cache_ttl=5.0, _now=fake_now)

    assert client.calls == 2  # both probes hit


@pytest.mark.asyncio
async def test_check_http_unexpected_status() -> None:
    client = _HTTPXClientMock(response=_ResponseMock(503))

    def factory(*_a: Any, **_kw: Any) -> _HTTPXClientMock:
        return client

    with _patch_httpx(factory):
        result = await check_http(
            "http://x/y", timeout=1.0, expect_status=200, cache_ttl=5.0
        )

    assert result.ok is False
    assert result.error is not None
    assert "503" in result.error


@pytest.mark.asyncio
async def test_check_http_timeout() -> None:
    client = _HTTPXClientMock(sleeps=2.0)

    def factory(*_a: Any, **_kw: Any) -> _HTTPXClientMock:
        return client

    with _patch_httpx(factory):
        result = await check_http(
            "http://x/y", timeout=0.05, cache_ttl=5.0
        )

    assert result.ok is False
    assert result.error is not None
    assert "timeout" in result.error


@pytest.mark.asyncio
async def test_check_http_failure() -> None:
    client = _HTTPXClientMock(raises=ConnectionRefusedError("boom"))

    def factory(*_a: Any, **_kw: Any) -> _HTTPXClientMock:
        return client

    with _patch_httpx(factory):
        result = await check_http(
            "http://x/y", timeout=1.0, cache_ttl=5.0
        )

    assert result.ok is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_check_http_cache_isolated_per_url() -> None:
    client_a = _HTTPXClientMock(response=_ResponseMock(200))
    client_b = _HTTPXClientMock(response=_ResponseMock(200))
    queue = [client_a, client_b]

    def factory_fn(*_a: Any, **_kw: Any) -> _HTTPXClientMock:
        return queue.pop(0)

    with _patch_httpx(factory_fn):
        await check_http("http://x/a", cache_ttl=5.0)
        await check_http("http://x/b", cache_ttl=5.0)

    assert client_a.calls == 1
    assert client_b.calls == 1


# ────────────────── assemble_readiness ──────────────────


def _ok(latency: int = 5) -> CheckResult:
    return CheckResult(ok=True, latency_ms=latency)


def _ko(error: str = "down") -> CheckResult:
    return CheckResult(ok=False, latency_ms=2000, error=error)


def test_assemble_readiness_all_ok() -> None:
    response, code = assemble_readiness(
        "svc",
        "0.1.0",
        {"db": _ok(), "redis": _ok()},
        critical={"db", "redis"},
    )
    assert isinstance(response, HealthResponse)
    assert response.status == "ready"
    assert code == 200
    assert response.service == "svc"
    assert response.version == "0.1.0"
    assert set(response.checks.keys()) == {"db", "redis"}


def test_assemble_readiness_non_critical_failed_returns_degraded() -> None:
    response, code = assemble_readiness(
        "svc",
        "0.1.0",
        {"db": _ok(), "downstream": _ko()},
        critical={"db"},
    )
    assert response.status == "degraded"
    assert code == 200


def test_assemble_readiness_critical_failed_returns_error_503() -> None:
    response, code = assemble_readiness(
        "svc",
        "0.1.0",
        {"db": _ko(), "redis": _ok()},
        critical={"db", "redis"},
    )
    assert response.status == "error"
    assert code == 503


def test_assemble_readiness_error_takes_precedence_over_degraded() -> None:
    response, code = assemble_readiness(
        "svc",
        "0.1.0",
        {"db": _ko(), "downstream": _ko()},
        critical={"db"},
    )
    assert response.status == "error"
    assert code == 503


def test_assemble_readiness_missing_critical_treated_as_failure() -> None:
    response, code = assemble_readiness(
        "svc",
        "0.1.0",
        {"redis": _ok()},  # no "db" key
        critical={"db"},
    )
    assert response.status == "error"
    assert code == 503
    assert "db" in response.checks
    assert response.checks["db"].ok is False
    assert response.checks["db"].error == "check missing"


def test_assemble_readiness_does_not_mutate_input_dict() -> None:
    checks: dict[str, CheckResult] = {"redis": _ok()}
    assemble_readiness(
        "svc", "0.1.0", checks, critical={"db", "redis"}
    )
    # caller's dict must not have been mutated with the synthetic "db" key
    assert "db" not in checks
