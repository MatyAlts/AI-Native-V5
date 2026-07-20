"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si Keycloak JWKS responde; 503 si falla
- /health      → alias de readiness por compatibilidad
- /api/v1/health → liveness JSON minimal para el KPI del web-admin (no
  depende del path raiz `/health` que en deploy con nginx puede caer al
  SPA).

Critical: `keycloak_jwks`. Non-critical: `academic_service`.
Usa el helper compartido `platform_observability.health`.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    HealthResponse,
    assemble_readiness,
    check_http,
)

from api_gateway.config import settings

router = APIRouter(prefix="/health", tags=["health"])
api_router = APIRouter(prefix="/api/v1/health", tags=["health"])

VERSION = "0.1.0"


def _keycloak_jwks_url() -> str:
    if settings.jwt_jwks_uri:
        return settings.jwt_jwks_uri
    return (
        f"{settings.keycloak_url.rstrip('/')}"
        f"/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/certs"
    )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    keycloak_check, academic_check = await asyncio.gather(
        check_http(_keycloak_jwks_url()),
        check_http(f"{settings.academic_service_url.rstrip('/')}/health/live"),
    )
    health, http_code = assemble_readiness(
        service="api-gateway",
        version=VERSION,
        checks={
            "keycloak_jwks": keycloak_check,
            "academic_service": academic_check,
        },
        critical={"keycloak_jwks"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}


@api_router.get("", status_code=status.HTTP_200_OK)
async def api_health() -> dict[str, str]:
    """Liveness JSON minimal para el KPI del web-admin (ADMIN-BUG-001).

    El path `/health` sin prefijo `/api/v1/` cae al SPA en el deploy
    con nginx (devuelve text/html) y rompe el KPI 'API Gateway' del
    dashboard. Este alias garantiza JSON estable.
    """
    return {"status": "ok", "service": "api-gateway"}
