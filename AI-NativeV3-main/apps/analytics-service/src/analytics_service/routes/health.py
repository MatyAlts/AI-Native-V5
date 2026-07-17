"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si ctr_store DB y classifier_db responden; 503 si no
- /health      → alias de readiness por compatibilidad

Critical: `ctr_store_db`, `classifier_db`. Cross-reads necesarios para
los endpoints de progression/kappa/alerts. analytics-service NO depende
de Redis hoy.

El readiness check reusa los engines singleton compartidos de
`analytics_service.db` (P-8: 1 engine por DB para todo el proceso, en vez
de crear engines propios para el health check). Si la URL está vacía (modo
dev stub), el check devuelve `error` y la route retorna 503: en dev sin DBs
reales, el servicio NO está ready (deseado, ver design.md D5).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    CheckResult,
    HealthResponse,
    assemble_readiness,
    check_postgres,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from analytics_service.config import settings
from analytics_service.db import get_classifier_engine, get_ctr_engine

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "0.1.0"


async def _check_db(url: str, engine_getter: Callable[[], AsyncEngine]) -> CheckResult:
    """Chequea una DB reusando el engine singleton compartido.

    Si `url` está vacío (modo dev stub) NO instancia engine — devuelve un
    CheckResult fallido con error explícito. Solo llama al getter (que crea
    el engine cacheado a nivel proceso) cuando hay URL configurada.
    """
    if not url:
        return CheckResult(
            ok=False,
            latency_ms=0,
            error="db url not configured (dev stub mode)",
        )
    return await check_postgres(engine_getter())


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    ctr_check, classifier_check = await asyncio.gather(
        _check_db(settings.ctr_store_url, get_ctr_engine),
        _check_db(settings.classifier_db_url, get_classifier_engine),
    )
    health, http_code = assemble_readiness(
        service="analytics-service",
        version=VERSION,
        checks={
            "ctr_store_db": ctr_check,
            "classifier_db": classifier_check,
        },
        critical={"ctr_store_db", "classifier_db"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
