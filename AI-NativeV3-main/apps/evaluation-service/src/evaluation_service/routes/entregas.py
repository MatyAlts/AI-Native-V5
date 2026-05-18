"""Endpoints de Entregas y Calificaciones (tp-entregas-correccion).

Flujo de estado:
  draft -> submitted -> graded -> returned -> (re-submit -> submitted)

Endpoints:
  POST   /api/v1/entregas                      crear draft (idempotente)
  GET    /api/v1/entregas                      listar con filtros
  GET    /api/v1/entregas/{id}                 detalle
  POST   /api/v1/entregas/{id}/submit          draft -> submitted + audit tp_entregada
  PATCH  /api/v1/entregas/{id}/ejercicio/{n}   marcar ejercicio completado
  POST   /api/v1/entregas/{id}/calificar       crear calificacion + audit tp_calificada
  GET    /api/v1/entregas/{id}/calificacion    leer calificacion
  POST   /api/v1/entregas/{id}/return          graded -> returned
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.auth import User, get_db, require_permission
from evaluation_service.models.entregas import Calificacion, Entrega
from evaluation_service.schemas.entrega import (
    CalificacionCreate,
    CalificacionOut,
    EntregaCreate,
    EntregaListMeta,
    EntregaListResponse,
    EntregaOut,
    MarkEjercicioBody,
)

router = APIRouter(prefix="/api/v1/entregas", tags=["entregas"])

# ── Endpoints de Entregas ─────────────────────────────────────────────────


@router.post("", response_model=EntregaOut, status_code=status.HTTP_201_CREATED)
async def create_entrega(
    data: EntregaCreate,
    response: Response,
    user: User = Depends(require_permission("entrega", "create")),
    db: AsyncSession = Depends(get_db),
) -> EntregaOut:
    """Crea una Entrega en draft (idempotente).

    Si ya existe una entrega para (tarea_practica_id, student_pseudonym)
    de este tenant, devuelve la existente con 200 (no crea duplicado).

    Race condition guard: si dos requests concurrentes pasan el SELECT y
    colisionan en el UNIQUE constraint, el perdedor reintenta el SELECT
    tras rollback del savepoint.
    """
    log = structlog.get_logger()
    student_id = user.id

    existing = await _find_existing_entrega(db, data.tarea_practica_id, student_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return EntregaOut.model_validate(existing)

    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        tarea_practica_id=data.tarea_practica_id,
        student_pseudonym=student_id,
        comision_id=data.comision_id,
        estado="draft",
        ejercicio_estados=[],
    )
    try:
        db.add(entrega)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        log.info(
            "entrega_create_race_resolved",
            tp=str(data.tarea_practica_id),
            student=str(student_id),
        )
        # Re-set RLS tenant after rollback (rollback clears SET LOCAL)
        await db.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(user.tenant_id)},
        )
        existing = await _find_existing_entrega(
            db, data.tarea_practica_id, student_id
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return EntregaOut.model_validate(existing)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error inesperado al crear entrega",
        )

    await db.refresh(entrega)
    return EntregaOut.model_validate(entrega)


@router.get("", response_model=EntregaListResponse)
async def list_entregas(
    tarea_practica_id: UUID | None = None,
    comision_id: UUID | None = None,
    estado: Literal["draft", "submitted", "graded", "returned"] | None = None,
    student_pseudonym: UUID | None = None,
    cursor: UUID | None = Query(None, description="UUID de la ultima entrega del batch anterior"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("entrega", "read")),
    db: AsyncSession = Depends(get_db),
) -> EntregaListResponse:
    """Lista entregas con filtros y paginacion cursor-based.

    Envelope `{data, meta}` donde `meta.cursor_next` es el `id` (UUID) de la
    ultima entrega devuelta — pasarlo como `?cursor=<uuid>&limit=<n>` en la
    siguiente llamada. `null` cuando no hay mas paginas.

    Casbin-scoped:
    - Docente: ve todas en su scope (tenant).
    - Estudiante: solo ve las propias (student_pseudonym = user.id).

    Orden estable por `id` ASC para que el cursor sea determinista.
    """
    is_docente = bool(
        user.roles & frozenset({"superadmin", "docente_admin", "docente", "jtp", "auxiliar"})
    )

    conditions = [Entrega.deleted_at.is_(None)]

    if tarea_practica_id:
        conditions.append(Entrega.tarea_practica_id == tarea_practica_id)
    if comision_id:
        conditions.append(Entrega.comision_id == comision_id)
    if estado:
        conditions.append(Entrega.estado == estado)

    if is_docente:
        if student_pseudonym:
            conditions.append(Entrega.student_pseudonym == student_pseudonym)
    else:
        conditions.append(Entrega.student_pseudonym == user.id)

    if cursor is not None:
        conditions.append(Entrega.id > cursor)

    stmt = (
        select(Entrega)
        .where(and_(*conditions))
        .order_by(Entrega.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    data = [EntregaOut.model_validate(r) for r in rows]
    cursor_next = str(rows[-1].id) if len(rows) == limit else None
    return EntregaListResponse(
        data=data,
        meta=EntregaListMeta(cursor_next=cursor_next, limit=limit),
    )


@router.get("/{entrega_id}", response_model=EntregaOut)
async def get_entrega(
    entrega_id: UUID,
    user: User = Depends(require_permission("entrega", "read")),
    db: AsyncSession = Depends(get_db),
) -> EntregaOut:
    entrega = await _get_or_404(db, entrega_id)
    _assert_can_read(entrega, user)
    return EntregaOut.model_validate(entrega)


@router.post("/{entrega_id}/submit", response_model=EntregaOut)
async def submit_entrega(
    entrega_id: UUID,
    user: User = Depends(require_permission("entrega", "create")),
    db: AsyncSession = Depends(get_db),
) -> EntregaOut:
    """Transicion draft -> submitted.

    Valida que todos los ejercicios esten completados.
    Emite audit log tp_entregada (structlog, no CTR chain).
    """
    entrega = await _get_or_404(db, entrega_id)
    _assert_can_write(entrega, user)

    if entrega.estado == "submitted":
        return EntregaOut.model_validate(entrega)

    if entrega.estado not in ("draft", "returned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede enviar una entrega en estado '{entrega.estado}'",
        )

    # Validar que todos los ejercicios esten completados
    estados: list[dict[str, Any]] = list(entrega.ejercicio_estados or [])
    if estados:
        incompletos = [e for e in estados if not e.get("completado")]
        if incompletos:
            ordenes = [e["orden"] for e in incompletos]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ejercicios incompletos: {ordenes}. Completa todos antes de entregar.",
            )

    entrega.estado = "submitted"
    entrega.submitted_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(entrega)

    # Audit log (meta-evento, NO va al CTR chain — ADR-010)
    log = structlog.get_logger()
    episode_ids = [
        e.get("episode_id")
        for e in estados
        if e.get("episode_id")
    ]
    log.info(
        "tp_entregada",
        entrega_id=str(entrega.id),
        tarea_practica_id=str(entrega.tarea_practica_id),
        tenant_id=str(user.tenant_id),
        student_pseudonym=str(entrega.student_pseudonym),
        n_ejercicios=len(estados),
        exercise_episode_ids=episode_ids,
    )

    return EntregaOut.model_validate(entrega)


@router.patch("/{entrega_id}/ejercicio/{orden}", response_model=EntregaOut)
async def mark_ejercicio_completado(
    entrega_id: UUID,
    orden: int,
    body: MarkEjercicioBody | None = None,
    user: User = Depends(require_permission("entrega", "create")),
    db: AsyncSession = Depends(get_db),
) -> EntregaOut:
    """Marca un ejercicio como completado (asociado a un episode_id).

    Si el ejercicio ya existe en ejercicio_estados, lo actualiza.
    Si no existe, lo agrega.
    """
    entrega = await _get_or_404(db, entrega_id)
    _assert_can_write(entrega, user)

    if entrega.estado not in ("draft", "returned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede modificar ejercicios en estado '{entrega.estado}'",
        )

    episode_id = body.episode_id if body else None
    ejercicio_id = body.ejercicio_id if body else None

    # ADR-047: match prefiere `ejercicio_id` (UUID estable) sobre `orden`
    # cuando ambos están disponibles. Entregas legacy sin `ejercicio_id`
    # caen al match por orden.
    estados = list(entrega.ejercicio_estados or [])
    found = False
    for est in estados:
        matches_by_uuid = (
            ejercicio_id is not None
            and est.get("ejercicio_id") == str(ejercicio_id)
        )
        matches_by_orden = est.get("orden") == orden and est.get("ejercicio_id") is None
        if matches_by_uuid or matches_by_orden:
            est["completado"] = True
            est["completed_at"] = datetime.now(UTC).isoformat()
            if episode_id:
                est["episode_id"] = str(episode_id)
            # Backfill `ejercicio_id` si llegó por primera vez en esta llamada
            if ejercicio_id is not None and est.get("ejercicio_id") is None:
                est["ejercicio_id"] = str(ejercicio_id)
            # Actualizar orden si cambió (snapshot del momento de la marca)
            est["orden"] = orden
            found = True
            break

    if not found:
        estados.append({
            "ejercicio_id": str(ejercicio_id) if ejercicio_id else None,
            "orden": orden,
            "episode_id": str(episode_id) if episode_id else None,
            "completado": True,
            "completed_at": datetime.now(UTC).isoformat(),
        })

    entrega.ejercicio_estados = estados
    await db.flush()
    await db.refresh(entrega)
    return EntregaOut.model_validate(entrega)


# ── Endpoints de Calificaciones ───────────────────────────────────────────

@router.post("/{entrega_id}/calificar", response_model=CalificacionOut, status_code=status.HTTP_201_CREATED)
async def calificar_entrega(
    entrega_id: UUID,
    data: CalificacionCreate,
    user: User = Depends(require_permission("calificacion", "create")),
    db: AsyncSession = Depends(get_db),
) -> CalificacionOut:
    """Crea calificacion. Transicion submitted -> graded.

    Solo docentes pueden calificar. Rechaza si no esta en submitted.
    Rechaza si ya tiene calificacion (v1 no permite re-correccion).
    Emite audit log tp_calificada (structlog, no CTR chain).
    """
    entrega = await _get_or_404(db, entrega_id)

    if entrega.estado != "submitted":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Solo se puede calificar entregas en 'submitted' (estado actual: '{entrega.estado}')",
        )

    # Verificar que no tenga ya calificacion
    existing_stmt = select(Calificacion).where(
        Calificacion.entrega_id == entrega_id
    )
    existing_cal = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing_cal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta entrega ya tiene una calificacion",
        )

    cal = Calificacion(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        entrega_id=entrega_id,
        graded_by=user.id,
        nota_final=data.nota_final,
        feedback_general=data.feedback_general,
        detalle_criterios=[c.model_dump(mode="json") for c in data.detalle_criterios],
        graded_at=datetime.now(UTC),
    )
    db.add(cal)

    entrega.estado = "graded"
    await db.flush()
    await db.refresh(cal)

    # Audit log (meta-evento, NO va al CTR chain — ADR-010)
    log = structlog.get_logger()
    log.info(
        "tp_calificada",
        entrega_id=str(entrega_id),
        calificacion_id=str(cal.id),
        nota_final=float(data.nota_final),
        graded_by=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    return CalificacionOut.model_validate(cal)


@router.get("/{entrega_id}/calificacion", response_model=CalificacionOut)
async def get_calificacion(
    entrega_id: UUID,
    user: User = Depends(require_permission("calificacion", "read")),
    db: AsyncSession = Depends(get_db),
) -> CalificacionOut:
    """Lee la calificacion. Docentes ven todas; estudiantes solo la suya."""
    entrega = await _get_or_404(db, entrega_id)
    _assert_can_read(entrega, user)

    stmt = select(Calificacion).where(
        and_(
            Calificacion.entrega_id == entrega_id,
            Calificacion.deleted_at.is_(None),
        )
    )
    cal = (await db.execute(stmt)).scalar_one_or_none()
    if cal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay calificacion para la entrega {entrega_id}",
        )
    return CalificacionOut.model_validate(cal)


@router.post("/{entrega_id}/return", response_model=EntregaOut)
async def return_entrega(
    entrega_id: UUID,
    user: User = Depends(require_permission("calificacion", "create")),
    db: AsyncSession = Depends(get_db),
) -> EntregaOut:
    """Devuelve la entrega al alumno (graded -> returned).

    El alumno puede volver a enviarla (returned -> submitted).
    """
    entrega = await _get_or_404(db, entrega_id)

    if entrega.estado != "graded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se puede devolver una entrega en 'graded' (estado: '{entrega.estado}')",
        )

    entrega.estado = "returned"
    await db.flush()
    await db.refresh(entrega)
    return EntregaOut.model_validate(entrega)


# ── Helpers privados ──────────────────────────────────────────────────────


async def _find_existing_entrega(
    db: AsyncSession,
    tarea_practica_id: UUID,
    student_id: UUID,
) -> Entrega | None:
    stmt = select(Entrega).where(
        and_(
            Entrega.tarea_practica_id == tarea_practica_id,
            Entrega.student_pseudonym == student_id,
            Entrega.deleted_at.is_(None),
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_or_404(db: AsyncSession, entrega_id: UUID) -> Entrega:
    stmt = select(Entrega).where(
        and_(Entrega.id == entrega_id, Entrega.deleted_at.is_(None))
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entrega {entrega_id} no encontrada",
        )
    return obj


def _assert_can_read(entrega: Entrega, user: User) -> None:
    """Estudiantes solo pueden leer sus propias entregas."""
    is_docente = bool(
        user.roles & frozenset({"superadmin", "docente_admin", "docente", "jtp", "auxiliar"})
    )
    if not is_docente and entrega.student_pseudonym != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver esta entrega",
        )


def _assert_can_write(entrega: Entrega, user: User) -> None:
    """Estudiantes solo pueden escribir sus propias entregas."""
    is_docente = bool(
        user.roles & frozenset({"superadmin", "docente_admin", "docente", "jtp", "auxiliar"})
    )
    if not is_docente and entrega.student_pseudonym != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar esta entrega",
        )
