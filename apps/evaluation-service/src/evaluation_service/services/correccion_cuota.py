"""Cuota diaria de correcciones por docente (tarea 3.4).

**La cuota FALLA CERRADA.** Es al revés que casi todos los límites de este
sistema, y es deliberado: cada corrección cuesta CPU, una llamada a Gemini y
dinero. Sin poder leer el contador no sabemos cuánto se gastó, y el default
seguro ahí es no gastar. Es el mismo criterio que las cuotas del
`execution-service` (ADR-060).

Se cuenta con filas en Postgres y no con un contador en Redis: el contador es
la tabla `correcciones_ia`, que ya existe y es la verdad. Un contador aparte
puede desincronizarse, y un contador que miente hacia abajo deja pasar
corridas que se pagan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.config import settings
from evaluation_service.models.correcciones_ia import CorreccionIA

log = structlog.get_logger()


class CuotaExcedidaError(Exception):
    """El docente ya gastó su cuota de hoy. Se traduce a 429."""


class CuotaIndeterminadaError(Exception):
    """No se pudo leer el contador. Se traduce a 503, NO a "adelante".

    Separada de `CuotaExcedidaError` a propósito: son dos cosas distintas y el
    docente necesita saber cuál le pasó. "Gastaste tu cuota" se resuelve
    mañana; "no sé cuánto gastaste" se resuelve avisando que algo está roto.
    """


async def consumidas_hoy(db: AsyncSession, tenant_id: UUID, user_id: UUID) -> int:
    """Cuántas correcciones disparó este docente en las últimas 24h.

    Se cuentan las que NO fallaron por infraestructura: un `GEMINI_OVERLOADED`
    no consumió una corrección de Gemini, así que cobrárselo al docente sería
    cobrarle por algo que no recibió. Las `pending` y `running` sí cuentan —
    están en vuelo y van a gastar.
    """
    desde = datetime.now(UTC) - timedelta(days=1)
    stmt = select(func.count()).where(
        and_(
            CorreccionIA.tenant_id == tenant_id,
            CorreccionIA.disparado_por == user_id,
            CorreccionIA.created_at >= desde,
            CorreccionIA.estado.in_(("pending", "running", "done")),
        )
    )
    return int((await db.execute(stmt)).scalar_one())


async def assert_cuota_disponible(db: AsyncSession, tenant_id: UUID, user_id: UUID) -> int:
    """Verifica la cuota ANTES de gastar. Devuelve cuántas quedan.

    Cualquier error leyendo el contador levanta `CuotaIndeterminadaError`: sin
    contador no se ejecuta. El `except` es amplio a propósito — no importa POR
    QUÉ no se pudo contar, importa que no se pudo.
    """
    try:
        usadas = await consumidas_hoy(db, tenant_id, user_id)
    except Exception as e:
        log.error(
            "activeia_cuota_indeterminada",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            detalle=str(e),
        )
        raise CuotaIndeterminadaError(
            "No se pudo verificar tu cuota de correcciones. Por seguridad no se disparó ninguna."
        ) from e

    limite = settings.activeia_cuota_diaria_por_docente
    if usadas >= limite:
        raise CuotaExcedidaError(
            f"Llegaste a las {limite} correcciones de las últimas 24 horas. "
            "Probá de nuevo más tarde."
        )
    return limite - usadas
