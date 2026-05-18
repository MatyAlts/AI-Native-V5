"""Worker de detección de abandono por timeout (ADR-025, G10-A).

Escanea las sesiones activas en Redis cada `check_interval_seconds` y, para
cada una con `last_activity_at` mayor o igual a `idle_timeout_seconds`,
emite un evento `EpisodioAbandonado(reason="timeout")` y borra el state.

Cubre el caso en que el `beforeunload` del navegador no se dispara o no
llega al backend (mobile, crash, conexion caida). El frontend tambien
emite con `reason="beforeunload"` — la idempotencia del
`record_episodio_abandonado` garantiza que NO haya doble emision para el
mismo episodio (audi2.md G10 "Riesgo A: emision doble" → mitigado por
estado de sesion).

Diseno:
  - Single-instance friendly: si hay 2 replicas del tutor-service corriendo,
    cada una escanea las mismas keys; pierde una sola, el `record_episodio_abandonado`
    falla idempotente en la otra (state ya borrado). No hace falta un
    lock distribuido.
  - Falla soft: si el publish al CTR falla, log + continua con la
    siguiente sesion. No bloquea otras detecciones.
  - Cancelable: el lifespan del FastAPI lo cancela en shutdown via
    `asyncio.CancelledError`.
"""

from __future__ import annotations

import asyncio
import logging
import time

from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore

logger = logging.getLogger(__name__)


async def _sweep_once(
    sessions: SessionManager,
    tutor: TutorCore,
    idle_timeout_seconds: float,
    now: float | None = None,
) -> int:
    """Hace un pase: detecta + emite abandono para sesiones inactivas.

    Args:
        sessions: SessionManager para iterar las sesiones.
        tutor: TutorCore que emite el evento (idempotente).
        idle_timeout_seconds: umbral de inactividad. Sesiones con
            `now - last_activity_at >= idle_timeout_seconds` se abandonan.
        now: epoch de referencia. Default = time.time(). Inyectable para tests.

    Returns:
        Cantidad de sesiones abandonadas en este pase (0 si todas activas).
    """
    if now is None:
        now = time.time()

    abandoned = 0
    async for state in sessions.iter_active_sessions():
        idle = now - state.last_activity_at
        if idle < idle_timeout_seconds:
            continue
        try:
            seq = await tutor.record_episodio_abandonado(
                episode_id=state.episode_id,
                reason="timeout",
                last_activity_seconds_ago=idle,
                # Worker server-side: caller es el service-account del tutor.
                # Para reason=beforeunload/explicit el caller es el estudiante
                # (lo setea el endpoint a partir del header X-User-Id).
                user_id=TUTOR_SERVICE_USER_ID,
            )
            if seq is not None:
                abandoned += 1
                logger.info(
                    "episodio_abandonado(timeout) emitido episode_id=%s idle=%.1fs seq=%d",
                    state.episode_id,
                    idle,
                    seq,
                )
        except Exception:
            # Falla soft: log y continuar. No detenemos el sweep por una
            # sesion problematica.
            logger.exception(
                "Error emitiendo episodio_abandonado(timeout) para episode_id=%s",
                state.episode_id,
            )
    return abandoned


async def run_abandonment_worker(
    sessions: SessionManager,
    tutor: TutorCore,
    idle_timeout_seconds: float,
    check_interval_seconds: float,
) -> None:
    """Loop infinito del worker. Cancelable via asyncio.CancelledError.

    Usado en el lifespan de la app. Hace un sweep cada `check_interval_seconds`.
    Si el sweep falla (ej. Redis caido), log + reintenta en el proximo tick.
    """
    logger.info(
        "abandonment_worker arrancado (idle_timeout=%ds, check_interval=%ds)",
        int(idle_timeout_seconds),
        int(check_interval_seconds),
    )
    try:
        while True:
            try:
                await _sweep_once(sessions, tutor, idle_timeout_seconds)
            except Exception:
                logger.exception("abandonment_worker sweep fallo (continua loop)")
            await asyncio.sleep(check_interval_seconds)
    except asyncio.CancelledError:
        logger.info("abandonment_worker cancelado (shutdown)")
        raise
