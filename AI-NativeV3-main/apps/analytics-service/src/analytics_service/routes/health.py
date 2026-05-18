"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si ctr_store DB y classifier_db responden; 503 si no
- /health      → alias de readiness por compatibilidad

Critical: `ctr_store_db`, `classifier_db`. Cross-reads necesarios para
los endpoints de progression/kappa/alerts. analytics-service NO depende
de Redis hoy.

`analytics-service` no instancia engines async para esas DBs en su flujo
normal (lee via adaptadores _Real/_Stub). El readiness check crea engines
lazy locales — si la URL está vacía (modo dev stub), el check devuelve
`error` y la route retorna 503: en dev sin DBs reales, el servicio NO
está ready (deseado, ver design.md D5).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    CheckResult,
    HealthResponse,
    assemble_readiness,
    check_postgres,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from analytics_service.config import settings

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "0.1.0"

_ctr_store_engine: AsyncEngine | None = None
_classifier_db_engine: AsyncEngine | None = None


def _lazy_engine(url: str, slot: str) -> AsyncEngine | None:
    """Crea un engine async lazy para health checks (sin RLS, read-only).

    `slot` selecciona el singleton ('ctr' o 'classifier'). Si `url` está
    vacío (modo dev stub), retorna None — el caller emite un CheckResult
    fallido con error explícito.
    """
    global _ctr_store_engine, _classifier_db_engine
    if not url:
        return None
    if slot == "ctr":
        if _ctr_store_engine is None:
            _ctr_store_engine = create_async_engine(url, pool_pre_ping=True)
        return _ctr_store_engine
    if slot == "classifier":
        if _classifier_db_engine is None:
            _classifier_db_engine = create_async_engine(
                url, pool_pre_ping=True
            )
        return _classifier_db_engine
    raise ValueError(f"unknown slot: {slot}")


async def _check_db(url: str, slot: str) -> CheckResult:
    engine = _lazy_engine(url, slot)
    if engine is None:
        return CheckResult(
            ok=False,
            latency_ms=0,
            error="db url not configured (dev stub mode)",
        )
    return await check_postgres(engine)


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    ctr_check, classifier_check = await asyncio.gather(
        _check_db(settings.ctr_store_url, "ctr"),
        _check_db(settings.classifier_db_url, "classifier"),
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
