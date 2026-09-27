"""Cola de revisión humana y registro de anulación (B3+B5).

Endpoints:
  - GET  /api/v1/classifications/review-queue           episodios retenidos, sin revisión posterior.
  - POST /api/v1/classifications/{episode_id}/review     registra el veredicto humano.

Ambos cuelgan del prefijo `/api/v1/classifications`, ya alcanzable por el
gateway (D8, verificado 5.5: `proxy.py:61` ya lo tiene, resuelve por
prefijo) — no hace falta tocar el `ROUTE_MAP`.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from classifier_service.auth import User, require_gateway_auth, require_role
from classifier_service.db import tenant_session
from classifier_service.services.review import (
    ReviewConflictError,
    ReviewTargetNotFoundError,
    list_review_queue,
    submit_review,
)

router = APIRouter(
    prefix="/api/v1/classifications",
    tags=["classification-review"],
    dependencies=[Depends(require_gateway_auth)],
)
logger = logging.getLogger(__name__)

# Decisión de design (open question resuelta): docente, docente_admin y
# superadmin pueden ver la cola y anular; el estudiante no. Mismo mecanismo
# que CLASSIFY_ROLES/READ_ROLES de classify_ep.py — headers del gateway,
# sin consultar Casbin (este servicio no lo hace en ningún endpoint
# existente). Las policies Casbin equivalentes van al seed de
# academic-service (tarea 5.6) como source-of-truth documentado del
# catálogo de permisos, aunque este servicio no las consulte en runtime.
REVIEW_ROLES = ("docente", "docente_admin", "superadmin")

# Orden de PRECEDENCIA explícito (hallazgo de QA, 2026-09-27, BAJA) — mayor
# autoridad primero. Un usuario puede tener más de un rol de REVIEW_ROLES a
# la vez (ej. docente + docente_admin); el campo que dice CON QUÉ AUTORIDAD
# se tomó la decisión, en una tabla de auditoría, tiene que ser reproducible
# y no depender del orden de iteración de un `set` (`next(iter(...))` sobre
# una intersección de sets no es un contrato, es un accidente de
# implementación de CPython).
REVIEW_ROLE_PRECEDENCE = ("superadmin", "docente_admin", "docente")

# Dominio conocido de `appropriation` HOY (hallazgo de QA, 2026-09-27, ALTA):
# los mismos 4 valores que `_EJE_TO_APPROPRIATION` puede producir
# (`pipeline.py`) — 3 del continuo + `autonomo` (eje ortogonal). Mismo patrón
# que `interrater.py::_LABELS` (400 explícito, no dejar pasar cualquier
# string). `sin_clasificar` (bloque 6, todavía no implementado en este repo)
# NO entra acá a propósito — agregarlo es tarea de ese bloque, no de este.
VALID_VERDICTS = frozenset(
    {
        "delegacion_pasiva",
        "apropiacion_superficial",
        "apropiacion_reflexiva",
        "autonomo",
    }
)


def _resolve_reviewer_role(user_roles: frozenset[str]) -> str:
    """Rol grabado en `classification_reviews.reviewer_role`, determinístico.

    Recorre `REVIEW_ROLE_PRECEDENCE` en orden fijo y devuelve el primero que
    el usuario tenga. `require_role(*REVIEW_ROLES)` ya garantizó que hay al
    menos una intersección no vacía antes de llegar acá — el fallback nunca
    debería ejecutarse en la práctica, pero preferible a un `IndexError` si
    algún día `REVIEW_ROLES` y `REVIEW_ROLE_PRECEDENCE` se desincronizan.
    """
    for role in REVIEW_ROLE_PRECEDENCE:
        if role in user_roles:
            return role
    return "docente"


class ReviewQueueItemOut(BaseModel):
    episode_id: UUID
    comision_id: UUID
    classification_id: int
    appropriation: str
    needs_review_reason: str | None
    estado_juez: str | None


class ReviewQueueOut(BaseModel):
    n: int
    items: list[ReviewQueueItemOut]


@router.get("/review-queue", response_model=ReviewQueueOut)
async def get_review_queue(
    comision_id: UUID | None = Query(default=None),
    user: User = Depends(require_role(*REVIEW_ROLES)),
) -> ReviewQueueOut:
    """Episodios con `needs_review=true` vigente y sin revisión posterior."""
    async with tenant_session(user.tenant_id) as session:
        items = await list_review_queue(session, comision_id=comision_id)
    return ReviewQueueOut(
        n=len(items),
        items=[
            ReviewQueueItemOut(
                episode_id=i.episode_id,
                comision_id=i.comision_id,
                classification_id=i.classification_id,
                appropriation=i.appropriation,
                needs_review_reason=i.needs_review_reason,
                estado_juez=i.estado_juez,
            )
            for i in items
        ],
    )


class ReviewIn(BaseModel):
    verdict: str = Field(..., max_length=40)
    reason: str = Field(..., max_length=2000)


class ReviewOut(BaseModel):
    review_id: int
    episode_id: UUID
    previous_classification_id: int
    new_classification_id: int
    verdict: str


@router.post(
    "/{episode_id}/review",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_review(
    episode_id: UUID,
    body: ReviewIn,
    user: User = Depends(require_role(*REVIEW_ROLES)),
) -> ReviewOut:
    """Registra el veredicto humano. REEMPLAZA la etiqueta oficial (gate 1.4):
    crea una `Classification` nueva con marca de procedencia humana y pone
    la anterior en `is_current=false`. Cada llamada apila una fila de
    historial nueva en `classification_reviews` — nunca pisa la anterior.
    """
    if body.verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"verdict '{body.verdict}' no es válido. Valores conocidos: "
            f"{sorted(VALID_VERDICTS)}",
        )

    async with tenant_session(user.tenant_id) as session:
        try:
            result = await submit_review(
                session,
                tenant_id=user.tenant_id,
                episode_id=episode_id,
                reviewer_id=user.id,
                reviewer_role=_resolve_reviewer_role(user.roles),
                verdict=body.verdict,
                reason=body.reason,
            )
        except ReviewTargetNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
        except ReviewConflictError as exc:
            # `retryable` viaja en el `detail` (hallazgo de QA, 2026-09-27,
            # ronda 5, punto 1): el frontend necesita distinguir "te ganó
            # otro docente, releé antes de insistir" de "te ganó el sistema,
            # podés reintentar" — son dos acciones distintas, no un 409 igual.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": str(exc), "retryable": exc.retryable},
            ) from None

    return ReviewOut(
        review_id=result.review_id,
        episode_id=episode_id,
        previous_classification_id=result.previous_classification_id,
        new_classification_id=result.new_classification_id,
        verdict=body.verdict,
    )
