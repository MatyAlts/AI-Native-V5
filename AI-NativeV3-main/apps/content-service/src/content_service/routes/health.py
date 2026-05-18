"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si content_db responde Y la extension pgvector está
                  instalada; 503 si alguno falla
- /health      → alias de readiness por compatibilidad

Critical: `content_db`, `pgvector_extension`. Sin pgvector el RAG es
no-op — D7 del design del change `real-health-checks`.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    DEFAULT_TIMEOUT_SEC,
    CheckResult,
    HealthResponse,
    assemble_readiness,
    check_postgres,
)
from sqlalchemy import text

from content_service.db.session import get_engine

router = APIRouter(prefix="/health", tags=["health"])

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


async def _check_pgvector(timeout: float = DEFAULT_TIMEOUT_SEC) -> CheckResult:
    """Valida que la extension pgvector esté instalada en content_db."""
    start = time.perf_counter()
    try:

        async def _probe() -> bool:
            engine = get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname='vector'")
                )
                return result.scalar() == 1

        installed = await asyncio.wait_for(_probe(), timeout=timeout)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if installed:
            return CheckResult(ok=True, latency_ms=latency_ms)
        return CheckResult(
            ok=False,
            latency_ms=latency_ms,
            error="pgvector extension not installed",
        )
    except TimeoutError:
        return CheckResult(
            ok=False,
            latency_ms=int(timeout * 1000),
            error=f"timeout after {timeout}s",
        )
    except Exception as exc:
        logger.warning("check_pgvector_failed", exc_info=exc)
        msg = str(exc).split("\n", 1)[0].strip() or type(exc).__name__
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=msg,
        )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    db_check, pgvector_check = await asyncio.gather(
        check_postgres(get_engine()),
        _check_pgvector(),
    )
    health, http_code = assemble_readiness(
        service="content-service",
        version=VERSION,
        checks={
            "content_db": db_check,
            "pgvector_extension": pgvector_check,
        },
        critical={"content_db", "pgvector_extension"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
