"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si Keycloak JWKS responde; 503 si falla
- /health      → alias de readiness por compatibilidad

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
