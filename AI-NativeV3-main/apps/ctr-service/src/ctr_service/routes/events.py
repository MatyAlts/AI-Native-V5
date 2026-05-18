"""Endpoints HTTP del ctr-service.

- POST /api/v1/events                       publish al stream (tutor-service)
- GET  /api/v1/episodes/{id}                episodio completo con eventos (legacy, service-to-service)
- POST /api/v1/episodes/{id}/verify         verifica integridad criptográfica (legacy, service-to-service)
- GET  /api/v1/audit/episodes/{id}          alias publico via api-gateway (ADR-031, D.4)
- POST /api/v1/audit/episodes/{id}/verify   alias publico via api-gateway (ADR-031, D.4)

Los endpoints `/api/v1/audit/*` son alias del legacy expuestos al frontend
web-admin. El prefix `/api/v1/audit` se rutea al ctr-service en el ROUTE_MAP
del api-gateway, evitando el conflicto con `/api/v1/episodes/*` que apunta
al tutor-service. Misma autenticación (READ_ROLES) y misma respuesta.
"""

from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ctr_service.auth import (
    PUBLISH_ROLES,
    READ_ROLES,
    User,
    get_db,
    require_role,
)
from ctr_service.config import settings
from ctr_service.models import Episode, Event
from ctr_service.schemas import (
    ChainVerificationResult,
    EpisodeWithEvents,
    EventOut,
    EventPublishRequest,
    EventPublishResponse,
)
from ctr_service.services import (
    EventProducer,
    shard_of,
    verify_chain_integrity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ctr"])

# ADR-031 (D.4, 2026-04-29): router separado con prefix `/api/v1/audit` para
# que el web-admin pueda verificar integridad de cadenas CTR sin chocar con
# el ROUTE_MAP del api-gateway (donde `/api/v1/episodes` ya rutea al
# tutor-service). Los handlers se registran via `add_api_route` apuntando a
# las mismas funciones del router legacy — cero duplicación de lógica.
audit_router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    return _redis_client


@router.post(
    "/events",
    response_model=EventPublishResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def publish_event(
    req: EventPublishRequest,
    user: User = Depends(require_role(*PUBLISH_ROLES)),
) -> EventPublishResponse:
    """Publica un evento al stream Redis.

    El worker del shard correspondiente lo persistirá en DB. La respuesta
    es 202 porque la persistencia es asíncrona — el caller recibe el
    message_id para trazabilidad.
    """
    # Seguridad: tenant_id en el payload debe coincidir con el del user
    if req.tenant_id != user.tenant_id and "superadmin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id del evento no coincide con el usuario",
        )

    producer = EventProducer(_get_redis(), num_partitions=settings.num_partitions)
    event_dict = req.model_dump(mode="json")
    msg_id = await producer.publish(event_dict)
    partition = shard_of(req.episode_id, settings.num_partitions)
    return EventPublishResponse(message_id=msg_id, partition=partition)


@router.get("/episodes/{episode_id}", response_model=EpisodeWithEvents)
async def get_episode(
    episode_id: UUID,
    user: User = Depends(require_role(*READ_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> EpisodeWithEvents:
    """Devuelve el episodio con todos sus eventos en orden de seq."""
    ep_result = await db.execute(select(Episode).where(Episode.id == episode_id))
    ep = ep_result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_id} no encontrado",
        )

    events_result = await db.execute(
        select(Event).where(Event.episode_id == episode_id).order_by(Event.seq)
    )
    events = list(events_result.scalars().all())

    return EpisodeWithEvents(
        id=ep.id,
        tenant_id=ep.tenant_id,
        comision_id=ep.comision_id,
        student_pseudonym=ep.student_pseudonym,
        problema_id=ep.problema_id,
        estado=ep.estado,
        opened_at=ep.opened_at,
        closed_at=ep.closed_at,
        events_count=ep.events_count,
        last_chain_hash=ep.last_chain_hash,
        integrity_compromised=ep.integrity_compromised,
        prompt_system_hash=ep.prompt_system_hash,
        classifier_config_hash=ep.classifier_config_hash,
        curso_config_hash=ep.curso_config_hash,
        events=[EventOut.model_validate(e) for e in events],
    )


@router.post("/episodes/{episode_id}/verify", response_model=ChainVerificationResult)
async def verify_episode_chain(
    episode_id: UUID,
    user: User = Depends(require_role(*READ_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ChainVerificationResult:
    """Recomputa la cadena de hashes del episodio y valida integridad.

    Esta verificación se corre periódicamente en background. El endpoint
    HTTP permite forzarla on-demand para auditorías.
    """
    ep_result = await db.execute(select(Episode).where(Episode.id == episode_id))
    ep = ep_result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_id} no encontrado",
        )

    events_result = await db.execute(
        select(Event).where(Event.episode_id == episode_id).order_by(Event.seq)
    )
    events = list(events_result.scalars().all())

    # Reconstruir tuplas para verify_chain_integrity:
    # (event_dict_canónico, self_hash_declarado, chain_hash_declarado)
    tuples = []
    for e in events:
        # El "event dict" usado para self_hash debe ser exactamente igual
        # al que se usó al publicarlo (contrato): los mismos campos lógicos
        event_dict = {
            "event_uuid": str(e.event_uuid),
            "episode_id": str(e.episode_id),
            "tenant_id": str(e.tenant_id),
            "seq": e.seq,
            "event_type": e.event_type,
            "ts": e.ts.isoformat().replace("+00:00", "Z"),
            "payload": e.payload,
            "prompt_system_hash": e.prompt_system_hash,
            "prompt_system_version": e.prompt_system_version,
            "classifier_config_hash": e.classifier_config_hash,
        }
        tuples.append((event_dict, e.self_hash, e.chain_hash))

    valid, failing = verify_chain_integrity(tuples)
    message = (
        "Cadena íntegra"
        if valid
        else f"Cadena rota en seq={failing}: recomputado no coincide con persistido"
    )

    return ChainVerificationResult(
        episode_id=episode_id,
        valid=valid,
        events_count=len(events),
        failing_seq=failing,
        integrity_compromised=ep.integrity_compromised,
        message=message,
    )


# ADR-031 (D.4): aliases publicos de los endpoints de read/verify del CTR
# bajo `/api/v1/audit/episodes/...`. Apuntan a las mismas funciones del
# router legacy — cero duplicacion de logica. Los aliases existen para que
# el api-gateway (ROUTE_MAP) pueda enrutarlos al ctr-service sin chocar con
# el prefix `/api/v1/episodes` que ya esta tomado por el tutor-service.
audit_router.add_api_route(
    "/episodes/{episode_id}",
    get_episode,
    methods=["GET"],
    response_model=EpisodeWithEvents,
    name="audit_get_episode",
)
audit_router.add_api_route(
    "/episodes/{episode_id}/verify",
    verify_episode_chain,
    methods=["POST"],
    response_model=ChainVerificationResult,
    name="audit_verify_episode_chain",
)
