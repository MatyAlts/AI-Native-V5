"""Endpoints de liveness y readiness del execution-service.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si las dependencias criticas responden; 503 si no
- /health       → alias de readiness por compatibilidad

Criticos: `redis` y `judge0`.

`redis` es critico porque las cuotas de ejecucion **fallan cerradas** (D5 del
design): sin contador no se ejecuta nada, asi que un Redis caido deja al
servicio incapaz de cumplir su funcion. Es lo contrario del criterio del resto
del sistema, donde el rate-limit degrada abierto a proposito.

`judge0` es critico por razones obvias, pero su caida NO bloquea el episodio del
alumno: el editor degrada al estado explicito de "ejecucion no disponible" y el
tutor sigue funcionando (ADR-059, consecuencias).
"""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import APIRouter, Response, status
from platform_observability.health import (
    CheckResult,
    HealthResponse,
    assemble_readiness,
    check_redis,
)

from execution_service.config import settings

router = APIRouter(prefix="/health", tags=["health"])

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


async def _check_judge0() -> CheckResult:
    """Pega al endpoint de estado del sandbox.

    Se usa `/about`, que no consume cuota del proveedor gestionado ni encola
    una ejecucion — a diferencia de mandar un submission de prueba.
    """
    start = time.perf_counter()
    headers = {}
    if settings.judge0_auth_token:
        headers["X-Auth-Token"] = settings.judge0_auth_token
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.judge0_base_url.rstrip('/')}/about", headers=headers
            )
        latency = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            return CheckResult(
                ok=False, latency_ms=latency, error=f"judge0 respondio {resp.status_code}"
            )
        return CheckResult(ok=True, latency_ms=latency)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("check_judge0_failed", exc_info=exc)
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=str(exc).split("\n", 1)[0].strip() or type(exc).__name__,
        )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    checks = {
        "redis": await check_redis(settings.redis_url),
        "judge0": await _check_judge0(),
    }
    health, http_code = assemble_readiness(
        service=settings.service_name,
        version=VERSION,
        checks=checks,
        critical={"redis", "judge0"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
