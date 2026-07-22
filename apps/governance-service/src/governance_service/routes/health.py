"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si el prompt activo del tutor es legible en disco;
                  503 si no
- /health      → alias de readiness por compatibilidad

Critical: `prompts_filesystem`. Sin prompt el `tutor-service` no puede
abrir episodios — D8 del design del change `real-health-checks`.
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

from governance_service.config import settings

router = APIRouter(prefix="/health", tags=["health"])

logger = logging.getLogger(__name__)

VERSION = "0.1.0"

# Mismo default que `tutor-service.config.default_prompt_version`. Si el
# tutor rota la versión activa, governance debería verificar el archivo
# correspondiente. Para mantener simple el chequeo, validamos la última
# version activable conocida — el manifest declarativo de
# `ai-native-prompts/manifest.yaml` es el source of truth para frontends.
DEFAULT_TUTOR_PROMPT_VERSION = "v1.0.1"


def _check_prompt_filesystem() -> CheckResult:
    start = time.perf_counter()
    path = os.path.join(
        settings.prompts_repo_path,
        "prompts",
        "tutor",
        DEFAULT_TUTOR_PROMPT_VERSION,
        "system.md",
    )
    try:
        if not os.path.isfile(path):
            return CheckResult(
                ok=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"prompt file not found at {path}",
            )
        if not os.access(path, os.R_OK):
            return CheckResult(
                ok=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"prompt file not readable at {path}",
            )
        return CheckResult(
            ok=True,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except OSError as exc:
        logger.warning("check_prompt_fs_failed", exc_info=exc)
        return CheckResult(
            ok=False,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=str(exc).split("\n", 1)[0].strip() or type(exc).__name__,
        )


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    prompt_check = _check_prompt_filesystem()
    health, http_code = assemble_readiness(
        service="governance-service",
        version=VERSION,
        checks={"prompts_filesystem": prompt_check},
        critical={"prompts_filesystem"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}
