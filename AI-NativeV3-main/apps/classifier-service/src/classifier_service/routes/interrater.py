"""Codificación inter-jueces — CRUD de etiquetas humanas (classifier-service).

Endpoints:
  - GET  /api/v1/interrater/sample       episodios a codificar, A CIEGAS (sin la
                                         etiqueta de la máquina). Orden estable →
                                         todos los codificadores ven el MISMO set.
  - POST /api/v1/interrater/ratings      el docente guarda/actualiza SU etiqueta.
  - GET  /api/v1/interrater/my-progress  qué episodios ya codificó el docente.

La agregación y el cálculo de κ viven en analytics-service (tiene platform-ops).
La traza del episodio (prompts/ediciones/tests) la trae el front aparte, desde
el timeline de auditoría del ctr-service.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from classifier_service.auth import User, require_role
from classifier_service.db import tenant_session
from classifier_service.models import Classification, InterraterRating

router = APIRouter(prefix="/api/v1/interrater", tags=["interrater"])
logger = logging.getLogger(__name__)

CODER_ROLES = ("docente", "docente_admin", "superadmin")

# Etiquetas válidas por protocolo (mismo vocabulario que el clasificador).
_LABELS: dict[str, frozenset[str]] = {
    "ejes": frozenset(
        {"delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva"}
    ),
    "subgrupos": frozenset(
        {
            "autonomo_competente",
            "autonomo_trabado",
            "escribe_sin_validar",
            "desenganchado",
            "colaborador_reflexivo",
            "colaborador_funcional",
            "dependiente_delegador",
            "dependiente_sobreuso",
            "indeterminado",
        }
    ),
    "niveles": frozenset({"N1", "N2", "N3", "N4"}),
}


class SampleEpisode(BaseModel):
    episode_id: str
    # Comisión del episodio: el front la necesita para guardar el rating
    # (la fila exige comision_id). NO es la etiqueta de la máquina → no rompe
    # el "a ciegas".
    comision_id: str


class SampleOut(BaseModel):
    n: int
    episodes: list[SampleEpisode]


# Solo episodios DONDE EL ALUMNO HABLÓ CON EL TUTOR (los 4 subgrupos del brazo
# con-prompts del clasificador). Son los casos interesantes para calibrar el κ; los
# autónomos sin IA (autonomo_*, escribe_sin_validar) y "indeterminado" quedan fuera
# del corpus inter-jueces.
_WITH_TUTOR_SUBGRUPOS = (
    "colaborador_reflexivo",
    "colaborador_funcional",
    "dependiente_sobreuso",
    "dependiente_delegador",
)


@router.get("/sample", response_model=SampleOut)
async def get_sample(
    comision_id: list[UUID] = Query(default=[]),
    per_eje: int = Query(50, ge=1, le=200),
    user: User = Depends(require_role(*CODER_ROLES)),
) -> SampleOut:
    """Corpus a codificar A CIEGAS, GLOBAL de materia, SOLO con-tutor y BALANCEADO.

    El front resuelve la materia a sus comisiones (`GET /comisiones?materia_id=`) y
    las pasa (`?comision_id=a&comision_id=b&...`). Se devuelven SOLO episodios donde
    el alumno habló con el tutor (los 4 subgrupos con-prompts), con un tope de
    `per_eje` por cada eje (default 50) para que la reflexiva no domine y el κ no se
    hunda por prevalencia. Orden estable por `episode_id` → todos los codificadores
    reciben el MISMO set → overlap → κ. NUNCA se devuelve la etiqueta de la máquina."""
    if not comision_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Falta comision_id (el conjunto de comisiones de la materia).",
        )
    async with tenant_session(user.tenant_id) as session:
        # Tope por eje vía window function: hasta `per_eje` episodios por cada
        # `appropriation`, ordenados estable por episode_id (mismo set para todos).
        ranked = (
            select(
                Classification.episode_id.label("episode_id"),
                Classification.comision_id.label("comision_id"),
                func.row_number()
                .over(
                    partition_by=Classification.appropriation,
                    order_by=Classification.episode_id,
                )
                .label("rn"),
            )
            .where(
                Classification.comision_id.in_(comision_id),
                Classification.is_current.is_(True),
                Classification.features["subgrupo"]["key"].astext.in_(
                    _WITH_TUTOR_SUBGRUPOS
                ),
            )
            .subquery()
        )
        rows = await session.execute(
            select(ranked.c.episode_id, ranked.c.comision_id)
            .where(ranked.c.rn <= per_eje)
            .order_by(ranked.c.episode_id)
        )
        eps = [
            SampleEpisode(episode_id=str(ep), comision_id=str(com))
            for ep, com in rows.all()
        ]
    return SampleOut(n=len(eps), episodes=eps)


class RatingIn(BaseModel):
    episode_id: UUID
    comision_id: UUID
    materia_id: UUID | None = None
    label: str = Field(..., max_length=40)
    protocol: str = Field(default="ejes")
    notes: str | None = Field(default=None, max_length=1000)


@router.post("/ratings", status_code=status.HTTP_204_NO_CONTENT)
async def save_rating(
    body: RatingIn,
    user: User = Depends(require_role(*CODER_ROLES)),
) -> None:
    """Guarda (o actualiza) la etiqueta del docente actual para un episodio.
    Upsert por (tenant, episodio, docente): re-etiquetar pisa la anterior, no
    acumula duplicados."""
    valid = _LABELS.get(body.protocol)
    if valid is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"protocol inválido: {body.protocol}"
        )
    if body.label not in valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"label '{body.label}' no es válida para protocol '{body.protocol}'",
        )
    async with tenant_session(user.tenant_id) as session:
        stmt = (
            pg_insert(InterraterRating)
            .values(
                tenant_id=user.tenant_id,
                episode_id=body.episode_id,
                comision_id=body.comision_id,
                materia_id=body.materia_id,
                rater_id=user.id,
                label=body.label,
                protocol=body.protocol,
                notes=body.notes,
            )
            .on_conflict_do_update(
                constraint="uq_interrater_episode_rater",
                set_={
                    "materia_id": body.materia_id,
                    "label": body.label,
                    "protocol": body.protocol,
                    "notes": body.notes,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()


class ProgressOut(BaseModel):
    materia_id: str
    rated_episode_ids: list[str]


@router.get("/my-progress", response_model=ProgressOut)
async def my_progress(
    materia_id: UUID,
    user: User = Depends(require_role(*CODER_ROLES)),
) -> ProgressOut:
    """Episodios que el docente actual YA codificó en esta materia (para que la
    UI marque avance y no re-muestre lo hecho)."""
    async with tenant_session(user.tenant_id) as session:
        rows = await session.execute(
            select(InterraterRating.episode_id).where(
                InterraterRating.materia_id == materia_id,
                InterraterRating.rater_id == user.id,
            )
        )
        ids = [str(r[0]) for r in rows.all()]
    return ProgressOut(materia_id=str(materia_id), rated_episode_ids=ids)
