"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si Redis responde; 503 si no. Downstreams HTTP
                  (academic-service, ai-gateway) son non-critical → degraded
                  + 200 cuando alguno cae.
- /health      → alias de readiness por compatibilidad

Critical: `redis` (sessions + producer del stream CTR).
Non-critical: `academic_service`, `ai_gateway` (degradan si caen).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    HealthResponse,
    assemble_readiness,
    check_http,
    check_redis,
)

from tutor_service.config import settings

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "0.1.0"


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    redis_check, academic_check, ai_check = await asyncio.gather(
        check_redis(settings.redis_url),
        check_http(
            f"{settings.academic_service_url.rstrip('/')}/health/live"
        ),
        check_http(
            f"{settings.ai_gateway_url.rstrip('/')}/health/live"
        ),
    )
    health, http_code = assemble_readiness(
        service="tutor-service",
        version=VERSION,
        checks={
            "redis": redis_check,
            "academic_service": academic_check,
            "ai_gateway": ai_check,
        },
        critical={"redis"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
