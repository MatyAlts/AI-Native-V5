"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si dependencias están OK (DB, Redis); 503 si alguna falla
- /health      → alias de readiness por compatibilidad
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import redis.asyncio as redis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from ctr_service.config import settings
from ctr_service.db.session import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# El timeout debe ser corto: el kubelet recortea readiness cada 5s (ver
# infrastructure/helm/platform/templates/backend-services.yaml). Si el ping
# tarda más, el pod se marca NotReady — eso es lo que queremos.
_DEP_TIMEOUT_SEC = 2.0


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
    checks: dict[str, str] = {}


async def _check_db() -> str:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=_DEP_TIMEOUT_SEC)
        return "ok"
    except Exception as exc:
        logger.warning("readiness_db_check_failed", exc_info=exc)
        return f"fail: {type(exc).__name__}"


async def _check_redis() -> str:
    client: redis.Redis | None = None
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=_DEP_TIMEOUT_SEC)
        # redis-py async ping() devuelve Awaitable[bool]; el stub a veces lo
        # tipa como `Awaitable[bool] | bool` cuando el cliente es sync.
        await asyncio.wait_for(client.ping(), timeout=_DEP_TIMEOUT_SEC)  # type: ignore[arg-type]
        return "ok"
    except Exception as exc:
        logger.warning("readiness_redis_check_failed", exc_info=exc)
        return f"fail: {type(exc).__name__}"
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    db_status, redis_status = await asyncio.gather(_check_db(), _check_redis())
    checks = {"db": db_status, "redis": redis_status}
    overall_ok = all(v == "ok" for v in checks.values())
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        service="ctr-service",
        status="ready" if overall_ok else "degraded",
        version="0.1.0",
        checks=checks,
    )


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
