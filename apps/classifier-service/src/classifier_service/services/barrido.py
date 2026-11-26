"""Barrido de episodios pendientes de clasificar (HU-051).

La HU-050 hace que `POST /classify_episode/{id}` responda 202 mientras el CTR
no guardó el `episodio_cerrado`, y la web del alumno reintenta ~54 s. Si la
cola del CTR tarda más, nadie vuelve a pedir la clasificación. El ctr-service
no tiene un endpoint que liste episodios cerrados (y no se toca), así que el
clasificador se anota lo que no pudo clasificar (`services/pendientes.py`) y
este módulo lo reintenta solo, dentro del servicio (`main.lifespan`).

Una pasada (`barrer(tenant_id)`) hace dos cosas, en este orden:

1. **Pendientes** (C02, N03): los 'pendiente' más viejos primero, hasta
   `barrido_lote_maximo`. Cada uno va por `classify_ep.clasificar_episodio`,
   el mismo camino que el POST (misma etiqueta, mismo juez, guarda
   `eventos_vistos`). Si quedó clasificado (por el barrido o porque el POST
   del navegador ganó antes) pasa a 'clasificado'. Si el CTR sigue sin el
   cierre (o falla) queda 'pendiente', salvo que tenga más de
   `barrido_pendiente_max_dias`: ahí pasa a 'descartado' y no se pide más.
2. **Recálculo** (C03, N02): la última fila de máquina de la configuración
   vigente de cada episodio, CON `eventos_vistos` y `classified_at` de las
   últimas 48 h. Si el CTR tiene más eventos, `clasificar_episodio` recalcula
   (fila nueva, la anterior `is_current=false`; con revisión humana vigente,
   la fila nueva no gobierna). Las filas sin `eventos_vistos` (previas a la
   HU-050, entre ellas las del estudio) no entran a la consulta.

Carga sobre el CTR y el juez: cada pasada pide como mucho
`2 * barrido_lote_maximo` trazas por tenant, y una fila ya revisada no se
vuelve a pedir hasta `barrido_revisar_cada_segundos` después (memoria del
proceso: tras un reinicio se revisan de nuevo, con el mismo tope por pasada).
El juez sólo corre cuando hay algo que clasificar: un pendiente que recibió el
cierre o una traza que creció. Una traza igual a la ya vista es un no-op.

Identidad frente al CTR: `BARRIDO_SERVICE_USER_ID` (propia, no reusa la del
tutor ni la del estudio) con el rol `classifier_worker`. Es el rol mínimo que
el ctr-service deja leer episodios sin ser dueño ni miembro de la comisión
(`READ_ROLES` y `CTR_OVERSIGHT_ROLES` de `ctr_service/auth/dependencies.py`):
sin `User` de request no hay dueño, y `docente` exigiría membresía en una
comisión. Sólo se usa con `episode_id` que salen de la propia base del
clasificador: un 202 que ya pasó el control de acceso del CTR con la identidad
de quien cerró, o una clasificación ya guardada.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text

from classifier_service.auth import User
from classifier_service.config import settings
from classifier_service.db import tenant_session
from classifier_service.routes import classify_ep
from classifier_service.services.pendientes import TABLA

logger = logging.getLogger(__name__)

BARRIDO_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-0000000000b5")
BARRIDO_EMAIL = "barrido@classifier-service.internal"
BARRIDO_ROL = "classifier_worker"
VENTANA_RECALCULO_HORAS = 48

# Fila de `classifications` -> último `time.monotonic()` en que se le pidió la
# traza al CTR. Acota la carga del recálculo (ver docstring del módulo).
_revisadas: dict[int, float] = {}


def _usuario_de_servicio(tenant_id: UUID) -> User:
    return User(
        id=BARRIDO_SERVICE_USER_ID,
        tenant_id=tenant_id,
        email=BARRIDO_EMAIL,
        roles=frozenset({BARRIDO_ROL}),
        realm=str(tenant_id),
    )


def _registrar_falla(episode_id: UUID, exc: Exception) -> None:
    if isinstance(exc, httpx.HTTPError):
        logger.warning(
            "barrido_ctr_error", extra={"episode_id": str(episode_id), "error": str(exc)}
        )
    else:
        logger.exception("barrido_episodio_fallo", extra={"episode_id": str(episode_id)})


async def _pendientes(tenant_id: UUID, lote: int, max_dias: int) -> list[Any]:
    async with tenant_session(tenant_id) as s:
        r = await s.execute(
            text(
                f"SELECT episode_id, creado_at < now() - make_interval(days => :d) AS vencido "
                f"FROM {TABLA} WHERE estado = 'pendiente' ORDER BY creado_at, id LIMIT :n"
            ),
            {"d": max_dias, "n": lote},
        )
        return list(r.all())


async def _marcar(tenant_id: UUID, episode_id: UUID, estado: str) -> None:
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text(
                f"UPDATE {TABLA} SET estado = :e, intentos = intentos + 1, "
                "actualizado_at = now() WHERE episode_id = :ep AND estado = 'pendiente'"
            ),
            {"e": estado, "ep": str(episode_id)},
        )


async def _candidatas_a_recalculo(
    tenant_id: UUID, config_hash: str, lote: int, excluir: list[int]
) -> list[Any]:
    """Última fila de la configuración vigente por episodio, con `eventos_vistos`
    y de las últimas 48 h. Sin filtrar `is_current`: con una revisión humana
    vigente la fila de máquina ya no gobierna, pero es la que dice qué traza se
    vio (el recálculo entra no vigente, `persist_classification`). Filtrar por
    el hash vigente evita que un bump de `tree_version` convierta el barrido en
    una reclasificación masiva con juez."""
    async with tenant_session(tenant_id) as s:
        r = await s.execute(
            text(
                "SELECT c.id, c.episode_id FROM classifications c "
                "WHERE c.classifier_config_hash = :h "
                "AND (c.features ->> 'eventos_vistos') IS NOT NULL "
                "AND c.classified_at >= now() - make_interval(hours => :horas) "
                "AND NOT (c.id = ANY(:excluir)) "
                "AND NOT EXISTS (SELECT 1 FROM classifications n "
                "  WHERE n.episode_id = c.episode_id "
                "  AND n.classifier_config_hash = c.classifier_config_hash AND n.id > c.id) "
                "ORDER BY c.classified_at, c.id LIMIT :n"
            ),
            {"h": config_hash, "horas": VENTANA_RECALCULO_HORAS, "excluir": excluir, "n": lote},
        )
        return list(r.all())


async def barrer(tenant_id: UUID) -> dict[str, int]:
    """Una pasada del barrido para un tenant. Devuelve contadores para el log."""
    user = _usuario_de_servicio(tenant_id)
    lote = settings.barrido_lote_maximo
    cuenta = {"clasificados": 0, "siguen_pendientes": 0, "descartados": 0, "recalculados": 0}
    vistos_en_esta_pasada: set[UUID] = set()

    for fila in await _pendientes(tenant_id, lote, settings.barrido_pendiente_max_dias):
        episode_id, vencido = UUID(str(fila.episode_id)), bool(fila.vencido)
        vistos_en_esta_pasada.add(episode_id)
        try:
            res = await classify_ep.clasificar_episodio(episode_id, user)
            clasificado = res.clasificacion is not None
        except Exception as exc:
            # CTR caído, 404 porque la cola tampoco guardó la apertura, o un
            # episodio que rompe la clasificación: se registra y la pasada
            # sigue con el próximo (uno roto no traba la cola).
            _registrar_falla(episode_id, exc)
            clasificado = False
        if clasificado:
            await _marcar(tenant_id, episode_id, "clasificado")
            cuenta["clasificados"] += 1
        elif vencido:
            await _marcar(tenant_id, episode_id, "descartado")
            cuenta["descartados"] += 1
            logger.warning("barrido_pendiente_descartado", extra={"episode_id": str(episode_id)})
        else:
            await _marcar(tenant_id, episode_id, "pendiente")
            cuenta["siguen_pendientes"] += 1

    ahora = time.monotonic()
    espera = settings.barrido_revisar_cada_segundos
    for k in [k for k, t in _revisadas.items() if ahora - t >= espera]:
        del _revisadas[k]
    config_hash = classify_ep.compute_classifier_config_hash(classify_ep.DEFAULT_REFERENCE_PROFILE)
    candidatas = await _candidatas_a_recalculo(tenant_id, config_hash, lote, list(_revisadas))
    for fila in candidatas:
        _revisadas[int(fila.id)] = ahora
        episode_id = UUID(str(fila.episode_id))
        if episode_id in vistos_en_esta_pasada:
            continue
        try:
            res = await classify_ep.clasificar_episodio(episode_id, user)
        except Exception as exc:
            _registrar_falla(episode_id, exc)
            continue
        if res.nueva:
            cuenta["recalculados"] += 1

    logger.info("barrido_pasada", extra={"tenant_id": str(tenant_id), **cuenta})
    return cuenta


async def bucle(intervalo_segundos: float, tenant_ids: Sequence[UUID]) -> None:
    """Corre `barrer` para cada tenant cada `intervalo_segundos`, para siempre.

    Espera antes de la primera pasada (el servicio termina de arrancar). Toma
    una copia de `tenant_ids` en cada pasada: `main` le pasa la lista viva de
    `services/pendientes.py`. Una pasada que falla se registra y el bucle
    sigue; sólo la cancelación (apagado del servicio) lo termina.
    """
    while True:
        await asyncio.sleep(intervalo_segundos)
        for tenant_id in list(tenant_ids):
            try:
                await barrer(tenant_id)
            except Exception:
                logger.exception("barrido_pasada_fallo", extra={"tenant_id": str(tenant_id)})


__all__ = ["BARRIDO_SERVICE_USER_ID", "barrer", "bucle"]
