"""Endpoints de liveness y readiness del execution-service.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si las dependencias criticas responden; 503 si no
- /health       → alias de readiness por compatibilidad

Criticos: `redis` y `docker`.

`redis` es critico porque las cuotas de ejecucion **fallan cerradas** (D5 del
design): sin contador no se ejecuta nada, asi que un Redis caido deja al
servicio incapaz de cumplir su funcion. Es lo contrario del criterio del resto
del sistema, donde el rate-limit degrada abierto a proposito.

`docker` es critico porque es el motor de ejecucion (ADR-060). Su caida NO
bloquea el episodio del alumno: el editor degrada al estado explicito de
"ejecucion no disponible" y el tutor sigue funcionando.
"""

from __future__ import annotations

import asyncio
import logging
import time

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


async def _check_docker() -> CheckResult:
    """Verifica que el daemon de Docker responde.

    Se usa `docker version`, que consulta al daemon sin lanzar ningun
    contenedor — a diferencia de correr una ejecucion de prueba, que gastaria
    CPU en cada health check.
    """
    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "version",
            "--format",
            "{{.Server.Version}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _out, err = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        latency = int((time.perf_counter() - start) * 1000)
        if proc.returncode != 0:
            return CheckResult(
                ok=False,
                latency_ms=latency,
                error=err.decode(errors="replace").strip()[:120] or "docker no respondio",
            )
        return CheckResult(ok=True, latency_ms=latency)
    except (TimeoutError, OSError) as exc:
        logger.warning("check_docker_failed", exc_info=exc)
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
        "docker": await _check_docker(),
    }
    health, http_code = assemble_readiness(
        service=settings.service_name,
        version=VERSION,
        checks=checks,
        critical={"redis", "docker"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
