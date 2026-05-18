"""Endpoints de liveness y readiness.

- /health/live  → siempre 200 si el proceso corre
- /health/ready → 200 si classifier_db + Redis responden; 503 si alguno falla
- /health      → alias de readiness por compatibilidad

Critical: `classifier_db`, `redis` (consumer del CTR stream).

Adicionalmente, esta lookup expone también `GET /api/v1/classifier/config-hash`
(metadata pública sin auth) para que el bootstrap del web-student pueda
resolver el `classifier_config_hash` vigente al abrir un episodio.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status
from platform_observability.health import (
    HealthResponse,
    assemble_readiness,
    check_postgres,
    check_redis,
)
from pydantic import BaseModel

from classifier_service.config import settings
from classifier_service.db import get_engine
from classifier_service.services import (
    DEFAULT_REFERENCE_PROFILE,
    compute_classifier_config_hash,
)

router = APIRouter(prefix="/health", tags=["health"])

# Router separado para exponer el hash vigente del classifier bajo
# /api/v1/classifier/* (mismo namespace que clasificación pero metadata).
config_router = APIRouter(prefix="/api/v1/classifier", tags=["classifier"])

VERSION = "0.1.0"
# Tree version vigente — sincronizar con el árbol de decisión activo.
# Hoy es "v1.0.0" (idéntico al que usa /classify_episode/{id}).
_TREE_VERSION = "v1.0.0"


@router.get("", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    db_check, redis_check = await asyncio.gather(
        check_postgres(get_engine()),
        check_redis(settings.redis_url),
    )
    health, http_code = assemble_readiness(
        service="classifier-service",
        version=VERSION,
        checks={
            "classifier_db": db_check,
            "redis": redis_check,
        },
        critical={"classifier_db", "redis"},
    )
    response.status_code = http_code
    return health


@router.get("/live", status_code=status.HTTP_200_OK)
async def live() -> dict[str, str]:
    return {"status": "alive"}


class ConfigHashOut(BaseModel):
    """Metadata pública del classifier para el bootstrap del frontend.

    Hash determinista calculado con `compute_classifier_config_hash` sobre
    el `reference_profile` y `tree_version` vigentes (ver
    `apps/classifier-service/src/classifier_service/services/pipeline.py`).
    Si esto cambia, cambia el hash y se invalidan classifications
    históricas — invariante doctoral.
    """

    classifier_config_hash: str
    tree_version: str


@config_router.get("/config-hash", response_model=ConfigHashOut)
async def get_classifier_config_hash() -> ConfigHashOut:
    """Devuelve el `classifier_config_hash` que el classifier usa hoy.

    Sin auth: es metadata pública del pipeline. La fórmula exacta vive
    en `compute_classifier_config_hash` (`pipeline.py`) y NO se duplica
    acá — esto es solo un getter sobre los valores vigentes.
    """
    config_hash = compute_classifier_config_hash(
        DEFAULT_REFERENCE_PROFILE,
        _TREE_VERSION,
    )
    return ConfigHashOut(
        classifier_config_hash=config_hash,
        tree_version=_TREE_VERSION,
    )
