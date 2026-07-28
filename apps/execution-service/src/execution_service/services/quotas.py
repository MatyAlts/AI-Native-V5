"""Cuotas de ejecucion por alumno — FALLAN CERRADAS (D5 del design).

Es lo contrario del criterio del resto del sistema. El rate-limit del chat y el
de invitaciones degradan ABIERTO a proposito: si Redis no responde, dejan pasar,
porque bloquear el tutor por un problema de infraestructura es peor que servir
unos mensajes de mas.

Acá no. Cada ejecucion consume CPU y dinero reales en el sandbox. Si el contador
se cae y las cuotas se desactivan, un alumno puede saturarlo sin techo. **Sin
contador, no se ejecuta.**

Es la segunda de las dos capas del ADR-059. La primera son los limites por
corrida del propio sandbox (CPU, memoria, procesos), que no dependen de ningun
almacen externo y siguen aplicando aunque esta capa este caida.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import redis.asyncio as redis

from execution_service.config import settings

_KEY_PREFIX = "exec:quota"


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    remaining: int
    reason: str = ""


class QuotaUnavailableError(RuntimeError):
    """El contador no respondio.

    NO se traduce a "permitido": es el fallo cerrado. El caller devuelve 503.
    """


def _key(tenant_id: UUID, user_id: UUID) -> str:
    return f"{_KEY_PREFIX}:{tenant_id}:{user_id}"


async def check_and_consume(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client: redis.Redis | None = None,
) -> QuotaDecision:
    """Consume una unidad de cuota si queda disponible.

    Ventana fija por clave con TTL: mas barata que una ventana deslizante y
    suficiente acá — el objetivo es acotar el costo, no repartir con precision.

    Raises:
        QuotaUnavailableError: Redis no respondio. **No se ejecuta nada.**
    """
    r = client or redis.from_url(settings.redis_url, decode_responses=True)
    key = _key(tenant_id, user_id)
    limite = settings.execution_quota_max_per_window

    try:
        # INCR + EXPIRE en pipeline: si la clave es nueva, arranca la ventana.
        async with r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, settings.execution_quota_window_seconds, nx=True)
            usados, _ = await pipe.execute()
    except Exception as exc:
        raise QuotaUnavailableError(
            f"contador de cuota no disponible: {type(exc).__name__}"
        ) from exc

    usados = int(usados)
    if usados > limite:
        return QuotaDecision(
            allowed=False,
            remaining=0,
            reason=(
                f"Alcanzaste el limite de {limite} ejecuciones cada "
                f"{settings.execution_quota_window_seconds // 60} minutos. "
                f"Podes seguir escribiendo codigo y consultando al tutor."
            ),
        )

    return QuotaDecision(allowed=True, remaining=max(0, limite - usados))
