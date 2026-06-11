"""Endpoints del classifier-service.

POST /api/v1/classify_episode/{episode_id}     trigger manual de clasificación
GET  /api/v1/classifications/{episode_id}      devuelve la clasificación current
GET  /api/v1/classifications/aggregated        estadísticas agregadas por comisión
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classifier_service.auth import CLASSIFY_ROLES, READ_ROLES, User, require_role
from classifier_service.config import settings
from classifier_service.db import tenant_session
from classifier_service.models import Classification
from classifier_service.services import (
    DEFAULT_REFERENCE_PROFILE,
    classify_episode_from_events,
    compute_classifier_config_hash,
    persist_classification,
)
from classifier_service.services.aggregation import aggregate_by_comision

router = APIRouter(prefix="/api/v1", tags=["classifier"])

logger = logging.getLogger(__name__)


class ClassificationOut(BaseModel):
    episode_id: UUID
    comision_id: UUID
    classifier_config_hash: str
    appropriation: str
    appropriation_reason: str
    ct_summary: float | None
    ccd_mean: float | None
    ccd_orphan_ratio: float | None
    cii_stability: float | None
    cii_evolution: float | None
    is_current: bool
    # Modo sombra (B1 Fase 2): subgrupo + 4 dimensiones, derivado de features.
    # None para clasificaciones viejas (pre-modo-sombra) — el front cae a la etiqueta clásica.
    subgrupo: dict | None = None

    class Config:
        from_attributes = True


async def _fetch_episode_from_ctr(episode_id: UUID, user: User) -> dict:
    """Llama al ctr-service para traer el episodio con todos sus eventos."""
    headers = {
        "X-User-Id": str(user.id),
        "X-Tenant-Id": str(user.tenant_id),
        "X-User-Email": user.email,
        "X-User-Roles": ",".join(user.roles),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{settings.ctr_service_url}/api/v1/episodes/{episode_id}",
            headers=headers,
        )
        r.raise_for_status()
        return r.json()


async def _find_current_classification(
    session: AsyncSession,
    episode_id: UUID,
    classifier_config_hash: str,
) -> Classification | None:
    """SELECT defensivo: ¿existe ya una clasificación current con este hash?

    Usado por el handler como pre-check de idempotencia ANTES de pegarle al
    CTR. Si ya existe, evitamos la roundtrip HTTP completa al ctr-service y
    devolvemos la fila tal cual con 200 (no-op idempotente).

    NOTA: `persist_classification` también hace este SELECT internamente —
    duplicarlo acá es intencional para (1) cortar temprano y (2) tener un
    handle al objeto antes/después del intento de INSERT (necesario para el
    race-condition guard de abajo).
    """
    result = await session.execute(
        select(Classification).where(
            Classification.episode_id == episode_id,
            Classification.classifier_config_hash == classifier_config_hash,
            Classification.is_current.is_(True),
        )
    )
    return result.scalar_one_or_none()


@router.post(
    "/classify_episode/{episode_id}",
    response_model=ClassificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def classify_episode(
    episode_id: UUID,
    response: Response,
    user: User = Depends(require_role(*CLASSIFY_ROLES)),
) -> ClassificationOut:
    """Clasifica un episodio dado (idempotente por classifier_config_hash).

    Contrato (deuda QA 2026-05-07):
      - Episodio nuevo → 201 CREATED + classification recién insertada.
      - Re-POST con MISMO classifier_config_hash → 200 OK + classification
        existente (no-op idempotente, NO se viola el UniqueConstraint).
      - Re-POST con classifier_config_hash DISTINTO (bump LABELER_VERSION o
        profile cambiado) → 201 CREATED + nueva fila; la vieja queda con
        `is_current=false` (append-only ADR-010).

    Race condition guard: si dos POSTs concurrentes pasan el pre-SELECT y
    colisionan en el UniqueConstraint(episode_id, classifier_config_hash) a
    nivel DB, el perdedor atrapa el IntegrityError, hace rollback y re-SELECT
    devuelve la fila ganadora con 200 OK.
    """
    profile = DEFAULT_REFERENCE_PROFILE
    config_hash = compute_classifier_config_hash(profile, "v1.0.0")

    # Pre-check idempotencia: si ya existe la classification current con este
    # hash, devolvemos 200 sin pegarle al ctr-service (ahorro de roundtrip).
    async with tenant_session(user.tenant_id) as session:
        existing = await _find_current_classification(session, episode_id, config_hash)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return ClassificationOut.model_validate(existing)

    # No existe — flujo normal: fetch eventos del CTR + clasificar + persistir.
    try:
        episode = await _fetch_episode_from_ctr(episode_id, user)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Episode {episode_id} no encontrado en CTR",
            )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"CTR error: {e}")

    events = episode.get("events", [])
    result = classify_episode_from_events(events, reference_profile=profile)

    async with tenant_session(user.tenant_id) as session:
        try:
            persisted = await persist_classification(
                session=session,
                tenant_id=user.tenant_id,
                episode_id=episode_id,
                comision_id=UUID(episode["comision_id"]),
                result=result,
                classifier_config_hash=config_hash,
            )
        except IntegrityError:
            # Race condition: otro POST concurrente ganó el INSERT entre
            # nuestro pre-SELECT y este flush. Recuperamos la fila ganadora
            # y devolvemos 200 (no-op idempotente). No re-raise: el cliente
            # tiene la classification — la respuesta es semánticamente
            # equivalente al caso "ya existía al entrar".
            await session.rollback()
            logger.info(
                "classify_episode_race_resolved",
                extra={"episode_id": str(episode_id), "config_hash": config_hash},
            )
            existing = await _find_current_classification(session, episode_id, config_hash)
            if existing is None:
                # Inesperado: integrity error pero la fila no aparece. Re-raise
                # como 500 con contexto explícito para auditoría.
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Race condition irrecuperable en classify_episode",
                ) from None
            response.status_code = status.HTTP_200_OK
            return ClassificationOut.model_validate(existing)

    # Path normal: classification recién insertada → 201 (default del router).
    return ClassificationOut.model_validate(persisted)


# ── Agregación por comisión ───────────────────────────────────────────
# IMPORTANTE: registrar /classifications/aggregated ANTES de
# /classifications/{episode_id} para que FastAPI no matchee "aggregated"
# como UUID path param.


class AppropriationCountsOut(BaseModel):
    delegacion_pasiva: int
    apropiacion_superficial: int
    apropiacion_reflexiva: int


class DailyCountsOut(BaseModel):
    date: str
    counts: AppropriationCountsOut


class AggregatedStatsOut(BaseModel):
    comision_id: UUID
    period_days: int
    total_episodes: int
    distribution: AppropriationCountsOut
    avg_ct_summary: float | None
    avg_ccd_mean: float | None
    avg_ccd_orphan_ratio: float | None
    avg_cii_stability: float | None
    avg_cii_evolution: float | None
    timeseries: list[DailyCountsOut]


@router.get("/classifications/aggregated", response_model=AggregatedStatsOut)
async def get_aggregated_classifications(
    comision_id: UUID = Query(...),
    period_days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role(*READ_ROLES)),
) -> AggregatedStatsOut:
    """Estadísticas agregadas de clasificaciones de una comisión.

    Usada por el dashboard docente para ver distribución N4, promedios de
    las 3 coherencias y evolución temporal. Solo considera clasificaciones
    `is_current=true` (la reclasificación con nuevo config preserva la vieja
    con `is_current=false`, pero solo la actual cuenta para estadísticas).
    """
    async with tenant_session(user.tenant_id) as session:
        stats = await aggregate_by_comision(session, comision_id, period_days)

    return AggregatedStatsOut(
        comision_id=stats.comision_id,
        period_days=stats.period_days,
        total_episodes=stats.total_episodes,
        distribution=AppropriationCountsOut(
            delegacion_pasiva=stats.distribution.delegacion_pasiva,
            apropiacion_superficial=stats.distribution.apropiacion_superficial,
            apropiacion_reflexiva=stats.distribution.apropiacion_reflexiva,
        ),
        avg_ct_summary=stats.avg_ct_summary,
        avg_ccd_mean=stats.avg_ccd_mean,
        avg_ccd_orphan_ratio=stats.avg_ccd_orphan_ratio,
        avg_cii_stability=stats.avg_cii_stability,
        avg_cii_evolution=stats.avg_cii_evolution,
        timeseries=[
            DailyCountsOut(
                date=d.date,
                counts=AppropriationCountsOut(
                    delegacion_pasiva=d.counts.delegacion_pasiva,
                    apropiacion_superficial=d.counts.apropiacion_superficial,
                    apropiacion_reflexiva=d.counts.apropiacion_reflexiva,
                ),
            )
            for d in stats.timeseries
        ],
    )


# ── Clasificación individual (va DESPUÉS de /aggregated) ────────────


@router.get("/classifications/{episode_id}", response_model=ClassificationOut)
async def get_current_classification(
    episode_id: UUID,
    user: User = Depends(require_role(*READ_ROLES)),
) -> ClassificationOut:
    async with tenant_session(user.tenant_id) as session:
        result = await session.execute(
            select(Classification).where(
                Classification.episode_id == episode_id,
                Classification.is_current.is_(True),
            )
        )
        c = result.scalar_one_or_none()
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sin clasificación actual para episodio {episode_id}",
        )
    out = ClassificationOut.model_validate(c)
    out.subgrupo = (c.features or {}).get("subgrupo")
    return out
