"""Worker de cierre automatico por distraccion (cambio de pestaña sostenido).

Escanea las marcas de distraccion en Redis cada `check_interval_seconds` y,
para cada una con `started_at` mayor o igual a `distraction_threshold_seconds`,
emite un evento `EpisodioAbandonado(reason="distraccion_pestana")` y borra
el state del episodio.

Diseno mirror del `abandonment_worker.py` pero con:
  - Threshold corto (30s default vs 1800s de timeout normal).
  - Reason especifico ("distraccion_pestana") para distinguir en analitica.
  - Caller es el service-account del tutor (sistema decide, no el alumno).

El `record_pestana_recuperada` borra la marca antes que el worker la
detecte, asi que un alumno que pierde foco y vuelve dentro del umbral
NO genera cierre.
"""

from __future__ import annotations

import asyncio
import logging
import time

from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore

logger = logging.getLogger(__name__)


async def _sweep_distractions_once(
    sessions: SessionManager,
    tutor: TutorCore,
    distraction_threshold_seconds: float,
    now: float | None = None,
) -> int:
    """Hace un pase: detecta + emite abandono para distracciones sostenidas.

    Args:
        sessions: SessionManager con las marcas de distraccion.
        tutor: TutorCore que emite el evento (idempotente).
        distraction_threshold_seconds: umbral. Distracciones con
            `now - started_at >= threshold` cierran el episodio.
        now: epoch de referencia. Default = time.time(). Inyectable para tests.

    Returns:
        Cantidad de episodios cerrados en este pase.
    """
    if now is None:
        now = time.time()

    closed = 0
    async for episode_id, started_at in sessions.iter_distractions():
        elapsed = now - started_at
        if elapsed < distraction_threshold_seconds:
            continue
        try:
            seq = await tutor.record_episodio_abandonado(
                episode_id=episode_id,
                reason="distraccion_pestana",
                last_activity_seconds_ago=elapsed,
                user_id=TUTOR_SERVICE_USER_ID,
            )
            # Borrar la marca aunque el cierre haya sido idempotente
            # (state ya borrado) para no reintentar en el proximo sweep.
            await sessions.clear_distraction(episode_id)
            if seq is not None:
                closed += 1
                logger.info(
                    "episodio_abandonado(distraccion_pestana) emitido "
                    "episode_id=%s elapsed=%.1fs seq=%d",
                    episode_id,
                    elapsed,
                    seq,
                )
        except Exception:
            logger.exception(
                "Error emitiendo episodio_abandonado(distraccion_pestana) episode_id=%s",
                episode_id,
            )
    return closed


async def run_distraction_worker(
    sessions: SessionManager,
    tutor: TutorCore,
    distraction_threshold_seconds: float,
    check_interval_seconds: float,
) -> None:
    """Loop infinito del worker. Cancelable via asyncio.CancelledError."""
    logger.info(
        "distraction_worker arrancado (threshold=%ds, check_interval=%ds)",
        int(distraction_threshold_seconds),
        int(check_interval_seconds),
    )
    try:
        while True:
            try:
                await _sweep_distractions_once(sessions, tutor, distraction_threshold_seconds)
            except Exception:
                logger.exception("distraction_worker sweep fallo (continua loop)")
            await asyncio.sleep(check_interval_seconds)
    except asyncio.CancelledError:
        logger.info("distraction_worker cancelado (shutdown)")
        raise
