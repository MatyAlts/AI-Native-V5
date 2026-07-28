"""Estado de las ejecuciones en curso, en Redis.

Este servicio NO tiene base propia a proposito: el estado de una corrida es
efimero (vive minutos) y el registro permanente es el evento CTR. Meter una
base seria sumar migraciones, backups y un punto de fallo mas a un piloto sin
administrador de sistemas dedicado.

TTL corto: si el alumno cierra la pestaña, el estado se limpia solo.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from execution_service.config import settings

_KEY_PREFIX = "exec:run"
# Sobrevive a la corrida mas larga posible (wall time x casos) con margen para
# que el cliente alcance a leer el resultado.
_TTL_SECONDS = 600


class ExecutionState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


def _key(execution_id: UUID) -> str:
    return f"{_KEY_PREFIX}:{execution_id}"


class ExecutionStoreUnavailableError(RuntimeError):
    """Redis no respondio. Mismo criterio que las cuotas: no se sigue a ciegas."""


async def put(
    execution_id: UUID,
    *,
    state: ExecutionState,
    owner_id: UUID,
    tenant_id: UUID,
    result: dict[str, Any] | None = None,
    client: redis.Redis | None = None,
) -> None:
    r = client or redis.from_url(settings.redis_url, decode_responses=True)
    payload = {
        "state": state.value,
        # El dueño se guarda para que el GET pueda rechazar a otro alumno: sin
        # esto, conocer un id ajeno alcanza para leer su resultado.
        "owner_id": str(owner_id),
        "tenant_id": str(tenant_id),
        "result": result,
    }
    try:
        await r.set(_key(execution_id), json.dumps(payload), ex=_TTL_SECONDS)
    except Exception as exc:
        raise ExecutionStoreUnavailableError(
            f"no se pudo guardar el estado: {type(exc).__name__}"
        ) from exc


async def get(execution_id: UUID, *, client: redis.Redis | None = None) -> dict[str, Any] | None:
    r = client or redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await r.get(_key(execution_id))
    except Exception as exc:
        raise ExecutionStoreUnavailableError(
            f"no se pudo leer el estado: {type(exc).__name__}"
        ) from exc
    if raw is None:
        return None
    return json.loads(raw)
