"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si la DB academic_main responde; 503 si no
- /health      → alias de readiness por compatibilidad

Critical: `academic_main_db`. El servicio es skeleton (sin lógica de
negocio), pero mantenemos el patrón uniforme — D5 del design del change
`real-health-checks`.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    HealthResponse,
    assemble_readiness,
    check_postgres,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from evaluation_service.config import settings

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "0.1.0"

_engine: AsyncEngine | None = None


def _get_engine() -> AsyncEngine:
    """Lazy singleton para el readiness check."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.academic_db_url, pool_pre_ping=True
        )
    return _engine


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    db_check = await check_postgres(_get_engine())
    health, http_code = assemble_readiness(
        service="evaluation-service",
        version=VERSION,
        checks={"academic_main_db": db_check},
        critical={"academic_main_db"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
