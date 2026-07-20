"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si la DB academic_main responde; 503 si no
- /health      → alias de readiness por compatibilidad

Critical: `academic_main_db`. Usa el helper `platform_observability.health`.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    HealthResponse,
    assemble_readiness,
    check_postgres,
)

from academic_service.db.session import get_engine

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "0.1.0"


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    db_check = await check_postgres(get_engine())
    health, http_code = assemble_readiness(
        service="academic-service",
        version=VERSION,
        checks={"academic_main_db": db_check},
        critical={"academic_main_db"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
