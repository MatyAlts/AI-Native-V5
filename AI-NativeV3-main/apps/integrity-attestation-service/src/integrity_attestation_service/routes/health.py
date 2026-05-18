"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si el directorio de attestations es escribible Y la
                  private key es legible; 503 si alguno falla
- /health      → alias de readiness por compatibilidad

Critical: `attestation_dir_writable`, `private_key_readable`.
NO chequea conectividad de Redis stream — D9 del design del change
`real-health-checks`. El servicio es eventually consistent (SLO 24h);
caída temporal del bus NO debe sacarlo de rotación.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    CheckResult,
    HealthResponse,
    assemble_readiness,
)

from integrity_attestation_service.config import settings

router = APIRouter(prefix="/health", tags=["health"])

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


def _check_dir_writable(path: str) -> CheckResult:
    start = time.perf_counter()
    try:
        if not os.path.isdir(path):
            return CheckResult(
                ok=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"directory does not exist: {path}",
            )
        if not os.access(path, os.W_OK):
            return CheckResult(
                ok=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"directory not writable: {path}",
            )
        return CheckResult(
            ok=True,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except OSError as exc:
        logger.warning("check_dir_writable_failed", exc_info=exc)
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=str(exc).split("\n", 1)[0].strip() or type(exc).__name__,
        )


def _check_file_readable(path: str) -> CheckResult:
    start = time.perf_counter()
    try:
        if not os.path.isfile(path):
            return CheckResult(
                ok=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"file does not exist: {path}",
            )
        if not os.access(path, os.R_OK):
            return CheckResult(
                ok=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"file not readable: {path}",
            )
        return CheckResult(
            ok=True,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except OSError as exc:
        logger.warning("check_file_readable_failed", exc_info=exc)
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=str(exc).split("\n", 1)[0].strip() or type(exc).__name__,
        )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    dir_check = _check_dir_writable(str(settings.attestation_log_dir))
    key_check = _check_file_readable(
        str(settings.attestation_private_key_path)
    )
    health, http_code = assemble_readiness(
        service="integrity-attestation-service",
        version=VERSION,
        checks={
            "attestation_dir_writable": dir_check,
            "private_key_readable": key_check,
        },
        critical={"attestation_dir_writable", "private_key_readable"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
