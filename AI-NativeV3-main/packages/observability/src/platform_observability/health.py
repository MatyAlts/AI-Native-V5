"""Helpers de readiness para los 12 servicios FastAPI del monorepo.

Provee tres async checks (`check_postgres`, `check_redis`, `check_http`),
un assembler `assemble_readiness` que mapea estado agregado a HTTP code,
y los modelos canónicos `CheckResult` + `HealthResponse`.

Diseño en `openspec/changes/real-health-checks/design.md`. Spec en
`openspec/changes/real-health-checks/specs/service-readiness/spec.md`.

`ctr-service` NO usa este helper: tiene su propio patrón estable
(`_check_db()` + `_check_redis()` en `apps/ctr-service/.../routes/health.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 2.0
DEFAULT_HTTP_CACHE_TTL_SEC = 5.0


class CheckResult(BaseModel):
    """Resultado de un check individual de readiness.

    `latency_ms` siempre presente (incluso en error: tiempo hasta la falla
    o el timeout). `error` es `None` cuando `ok=True`, string non-empty
    cuando `ok=False`.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    latency_ms: int
    error: str | None = None


class HealthResponse(BaseModel):
    """Respuesta canónica de `/health/ready` para los 12 servicios."""

    service: str
    status: str
    version: str
    checks: dict[str, CheckResult] = Field(default_factory=dict)


async def check_postgres(
    engine: AsyncEngine, timeout: float = DEFAULT_TIMEOUT_SEC
) -> CheckResult:
    """Ejecuta `SELECT 1` con timeout. Captura todas las exceptions."""
    from sqlalchemy import text

    start = time.perf_counter()
    try:

        async def _probe() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_probe(), timeout=timeout)
        return CheckResult(
            ok=True, latency_ms=int((time.perf_counter() - start) * 1000)
        )
    except TimeoutError:
        return CheckResult(
            ok=False,
            latency_ms=int(timeout * 1000),
            error=f"timeout after {timeout}s",
        )
    except Exception as exc:
        logger.warning("check_postgres_failed", exc_info=exc)
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=_describe_error(exc),
        )


async def check_redis(
    redis_url: str, timeout: float = DEFAULT_TIMEOUT_SEC
) -> CheckResult:
    """Conecta a Redis, ejecuta PING, garantiza cleanup de conexión."""
    import redis.asyncio as redis_async

    start = time.perf_counter()
    client: Any = None
    try:
        client = redis_async.from_url(
            redis_url, socket_connect_timeout=timeout
        )
        await asyncio.wait_for(client.ping(), timeout=timeout)
        return CheckResult(
            ok=True, latency_ms=int((time.perf_counter() - start) * 1000)
        )
    except TimeoutError:
        return CheckResult(
            ok=False,
            latency_ms=int(timeout * 1000),
            error=f"timeout after {timeout}s",
        )
    except Exception as exc:
        logger.warning("check_redis_failed", exc_info=exc)
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=_describe_error(exc),
        )
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


_HTTP_CACHE: dict[str, tuple[CheckResult, float]] = {}


def _http_cache_clear() -> None:
    """Test-only helper to reset the per-process HTTP probe cache."""
    _HTTP_CACHE.clear()


async def check_http(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    expect_status: int = 200,
    cache_ttl: float = DEFAULT_HTTP_CACHE_TTL_SEC,
    *,
    _now: Callable[[], float] | None = None,
) -> CheckResult:
    """GET HTTP con TTL cache in-process. `_now` inyectable para tests."""
    import httpx

    now_fn = _now or time.monotonic
    cache_key = f"{url}|{expect_status}"

    cached = _HTTP_CACHE.get(cache_key)
    if cached is not None:
        result, expires_at = cached
        if now_fn() < expires_at:
            return result

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await asyncio.wait_for(
                client.get(url), timeout=timeout
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code == expect_status:
            result = CheckResult(ok=True, latency_ms=latency_ms)
        else:
            result = CheckResult(
                ok=False,
                latency_ms=latency_ms,
                error=(
                    f"unexpected status {response.status_code} "
                    f"(expected {expect_status})"
                ),
            )
    except TimeoutError:
        result = CheckResult(
            ok=False,
            latency_ms=int(timeout * 1000),
            error=f"timeout after {timeout}s",
        )
    except Exception as exc:
        logger.warning(
            "check_http_failed", exc_info=exc, extra={"url": url}
        )
        result = CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=_describe_error(exc),
        )

    _HTTP_CACHE[cache_key] = (result, now_fn() + cache_ttl)
    return result


def assemble_readiness(
    service: str,
    version: str,
    checks: dict[str, CheckResult],
    critical: set[str],
) -> tuple[HealthResponse, int]:
    """Agrega checks individuales en HealthResponse + status code HTTP.

    Reglas (ver design.md D3):
    - todos critical OK + todos non-critical OK → "ready"     → 200
    - todos critical OK + algún non-critical KO → "degraded"  → 200
    - algún critical KO                          → "error"    → 503

    Si una key declarada critical NO está en `checks`, se considera fallo
    (el helper agrega un CheckResult sintético con error="check missing").
    """
    aggregated = dict(checks)
    for key in critical - aggregated.keys():
        aggregated[key] = CheckResult(
            ok=False, latency_ms=0, error="check missing"
        )

    critical_failed = any(not aggregated[k].ok for k in critical)
    non_critical_failed = any(
        not v.ok for k, v in aggregated.items() if k not in critical
    )

    if critical_failed:
        status_str = "error"
        http_code = 503
    elif non_critical_failed:
        status_str = "degraded"
        http_code = 200
    else:
        status_str = "ready"
        http_code = 200

    return (
        HealthResponse(
            service=service,
            status=status_str,
            version=version,
            checks=aggregated,
        ),
        http_code,
    )


def _describe_error(exc: BaseException) -> str:
    msg = str(exc).split("\n", 1)[0].strip()
    return msg or type(exc).__name__


__all__ = [
    "DEFAULT_HTTP_CACHE_TTL_SEC",
    "DEFAULT_TIMEOUT_SEC",
    "CheckResult",
    "HealthResponse",
    "assemble_readiness",
    "check_http",
    "check_postgres",
    "check_redis",
]
