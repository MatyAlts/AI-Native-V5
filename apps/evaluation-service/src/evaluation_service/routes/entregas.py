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
  PATCH  /api/v1/entregas/{id}/calificacion    re-calificar in-place + audit tp_recalificada (NB-4)
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
from sqlalchemy.sql.elements import ColumnElement

from evaluation_service.auth import User, get_db, require_permission
from evaluation_service.models.entregas import Calificacion, Entrega
from evaluation_service.schemas.entrega import (
    CalificacionCreate,
    CalificacionOut,
    CalificacionUpdate,
    EntregaCreate,
    EntregaListMeta,
    EntregaListResponse,
    EntregaOut,
    MarkEjercicioBody,
)

router = APIRouter(prefix="/api/v1/entregas", tags=["entregas"])

# Oversight academico del tenant: ve y corrige cualquier comision. Mismo
# conjunto que usa `list_entregas` para saltear el filtro por comision.
OVERSIGHT_ROLES = frozenset({"superadmin", "docente_admin"})

# Roles del lado docente. El scope de un docente lo da `usuarios_comision`; el
# de un estudiante, ser dueño de la entrega (los alumnos no estan en esa tabla,
# estan en `inscripciones`). Por eso los dos caminos no se pueden unificar.
DOCENTE_ROLES = frozenset({"superadmin", "docente_admin", "docente", "jtp", "auxiliar"})

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
        existing = await _find_existing_entrega(db, data.tarea_practica_id, student_id)
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
    is_oversight = bool(user.roles & frozenset({"superadmin", "docente_admin"}))

    # Anotado explicito: `.is_(None)` infiere `BinaryExpression[bool]`, pero los
    # `.append()` de mas abajo agregan comparaciones `==`/`.in_()` que SQLAlchemy
    # tipa como `ColumnElement[bool]` (el tipo base comun). Sin la anotacion,
    # mypy fija el tipo de la lista al del primer elemento y rechaza el resto.
    conditions: list[ColumnElement[bool]] = [Entrega.deleted_at.is_(None)]

    if tarea_practica_id:
        conditions.append(Entrega.tarea_practica_id == tarea_practica_id)
    if comision_id:
        conditions.append(Entrega.comision_id == comision_id)
    if estado:
        conditions.append(Entrega.estado == estado)

    if is_docente:
        if not is_oversight:
            # Aislamiento por comisión: en prod todos los docentes comparten un
            # tenant fijo, así que la RLS no los separa. Restringimos la cola de
            # corrección a las comisiones donde el docente está asignado
            # (usuarios_comision vive en la misma DB academic_main). Pedir una
            # comisión ajena queda fuera del IN → no se filtra nada de otro
            # docente. Ver docs/filtrado-teacher-plan.md.
            rows_c = await db.execute(
                text(
                    "SELECT comision_id FROM usuarios_comision "
                    "WHERE user_id = :uid AND deleted_at IS NULL"
                ),
                {"uid": str(user.id)},
            )
            my_comisiones = [r[0] for r in rows_c.all()]
            if not my_comisiones:
                return EntregaListResponse(
                    data=[], meta=EntregaListMeta(cursor_next=None, limit=limit)
                )
            conditions.append(Entrega.comision_id.in_(my_comisiones))
        if student_pseudonym:
            conditions.append(Entrega.student_pseudonym == student_pseudonym)
        # NEW-004 QA: la COLA de correccion del docente NO debe mostrar entregas
        # en 'draft' (el alumno todavia esta trabajando, no entrego). Solo se
        # ocultan si no pidio un estado explicito (puede filtrar estado=draft a
        # proposito). El estudiante SI ve su propio draft (rama else).
        # 2026-06-19: el ocultamiento aplica SOLO a la cola general. Si se pide
        # un `student_pseudonym` concreto es un lookup puntual (ej. reabrir un
        # episodio para que el alumno retome) y ahi SI hay que ver su draft, que
        # es justamente la entrega en curso a resetear.
        if not estado and not student_pseudonym:
            conditions.append(Entrega.estado != "draft")
    else:
        conditions.append(Entrega.student_pseudonym == user.id)

    if cursor is not None:
        conditions.append(Entrega.id > cursor)

    stmt = select(Entrega).where(and_(*conditions)).order_by(Entrega.id.asc()).limit(limit)
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
    await _assert_read_scope(db, entrega, user)
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
    # Autorizacion ANTES de la logica de estado, incluido el atajo idempotente
    # de abajo: si no, un docente ajeno distingue por el status code en que
    # estado esta una entrega que no deberia ni ver.
    await _assert_write_scope(db, entrega, user)

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
    episode_ids = [e.get("episode_id") for e in estados if e.get("episode_id")]
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
    """Marca un ejercicio como completado/no-completado (asociado a un episode_id).

    `body.completado` (default True) decide el sentido:
      - True  → marca completado (flujo normal del alumno al cerrar el ejercicio).
      - False → lo des-marca (reapertura docente 2026-06-19: el docente reabrió el
                episodio para que el alumno lo retome, así que el ejercicio vuelve a
                quedar pendiente). Solo aplica si el ejercicio ya existía; si no
                estaba, es un no-op (no se agrega un estado "incompleto" vacío).

    Si el ejercicio ya existe en ejercicio_estados, lo actualiza.
    Si no existe y se marca completado, lo agrega.
    """
    entrega = await _get_or_404(db, entrega_id)
    # Autorizacion ANTES del chequeo de estado, mismo motivo que en el resto:
    # el status code no debe delatar en que estado esta una entrega ajena.
    await _assert_write_scope(db, entrega, user)

    if entrega.estado not in ("draft", "returned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede modificar ejercicios en estado '{entrega.estado}'",
        )

    completado = body.completado if body else True
    episode_id = body.episode_id if body else None
    ejercicio_id = body.ejercicio_id if body else None

    # ADR-047: match prefiere `ejercicio_id` (UUID estable) sobre `orden`
    # cuando ambos están disponibles. Entregas legacy sin `ejercicio_id`
    # caen al match por orden.
    estados = list(entrega.ejercicio_estados or [])
    found = False
    for est in estados:
        matches_by_uuid = ejercicio_id is not None and est.get("ejercicio_id") == str(ejercicio_id)
        matches_by_orden = est.get("orden") == orden and est.get("ejercicio_id") is None
        if matches_by_uuid or matches_by_orden:
            est["completado"] = completado
            est["completed_at"] = datetime.now(UTC).isoformat() if completado else None
            if episode_id:
                est["episode_id"] = str(episode_id)
            # Backfill `ejercicio_id` si llegó por primera vez en esta llamada
            if ejercicio_id is not None and est.get("ejercicio_id") is None:
                est["ejercicio_id"] = str(ejercicio_id)
            # Actualizar orden si cambió (snapshot del momento de la marca)
            est["orden"] = orden
            found = True
            break

    # Solo agregamos un estado nuevo al MARCAR completado. Des-marcar un ejercicio
    # que no figura es un no-op (no tiene sentido un registro "incompleto" vacío).
    if not found and completado:
        estados.append(
            {
                "ejercicio_id": str(ejercicio_id) if ejercicio_id else None,
                "orden": orden,
                "episode_id": str(episode_id) if episode_id else None,
                "completado": True,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )

    entrega.ejercicio_estados = estados
    await db.flush()
    await db.refresh(entrega)
    return EntregaOut.model_validate(entrega)


# ── Endpoints de Calificaciones ───────────────────────────────────────────


@router.post(
    "/{entrega_id}/calificar", response_model=CalificacionOut, status_code=status.HTTP_201_CREATED
)
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
    # Autorizacion ANTES de la logica de negocio: si va despues, un docente
    # ajeno distingue por el status code en que estado esta la entrega.
    await _assert_docente_de_la_comision(db, entrega, user)

    if entrega.estado != "submitted":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Solo se puede calificar entregas en 'submitted' (estado actual: '{entrega.estado}')",
        )

    # Verificar que no tenga ya calificacion
    existing_stmt = select(Calificacion).where(Calificacion.entrega_id == entrega_id)
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


@router.patch("/{entrega_id}/calificacion", response_model=CalificacionOut)
async def recalificar_entrega(
    entrega_id: UUID,
    data: CalificacionUpdate,
    user: User = Depends(require_permission("calificacion", "update")),
    db: AsyncSession = Depends(get_db),
) -> CalificacionOut:
    """Re-califica una entrega actualizando la calificacion existente in-place (NB-4).

    Antes no habia forma de corregir una nota ya puesta: `POST /calificar`
    rechaza con 409 si ya existe calificacion, y el `UNIQUE(entrega_id)`
    bloquea insertar una segunda. Este PATCH resuelve ese bloqueo actualizando
    la MISMA fila (nunca inserta), por lo que el `UNIQUE(entrega_id)` se respeta
    trivialmente.

    Semantica:
    - Solo docentes (require_permission calificacion:update) — el docente sigue
      gobernando la nota; los estudiantes no pueden actualizar calificaciones.
    - Requiere que la calificacion YA exista (si no, 404 → usar POST /calificar
      para la primera). PATCH actualiza, POST crea.
    - Update parcial: solo los campos presentes en el body se tocan.
    - `graded_by` pasa al docente que re-califica (gobierna la nota vigente);
      `graded_at` preserva la primera calificacion, `updated_at` marca esta.
    - Deja la entrega en `graded` (normaliza el caso de una entrega re-enviada
      que quedo en `submitted` con la calificacion vieja adherida — NB-4),
      SALVO que ya este en `returned`: ese estado se conserva porque es lo que
      habilita al alumno a re-entregar.
    - Emite audit log `tp_recalificada` (structlog, NO va al CTR chain — ADR-010)
      con la nota anterior y la nueva.
    """
    entrega = await _get_or_404(db, entrega_id)
    await _assert_docente_de_la_comision(db, entrega, user)

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
            detail=(
                f"No hay calificacion para la entrega {entrega_id}. "
                "Usa POST /calificar para la primera calificacion."
            ),
        )

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nada para actualizar: envia al menos un campo.",
        )
    if "nota_final" in updates and data.nota_final is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="nota_final no puede ser null.",
        )

    nota_anterior = float(cal.nota_final)

    if "nota_final" in updates:
        # Ya validado arriba (linea ~457): `nota_final in updates` implica acá
        # `data.nota_final is not None`. El guard explícito hace esa garantía
        # visible al type checker (la columna no acepta `Decimal | None`) sin
        # tocar el orden de validacion existente.
        if data.nota_final is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="nota_final no puede ser null.",
            )
        cal.nota_final = data.nota_final
    if "feedback_general" in updates:
        cal.feedback_general = data.feedback_general
    if "detalle_criterios" in updates:
        cal.detalle_criterios = [c.model_dump(mode="json") for c in (data.detalle_criterios or [])]

    now = datetime.now(UTC)
    cal.graded_by = user.id
    cal.updated_at = now
    # Normaliza el estado: una re-calificacion deja la entrega calificada.
    # Cubre el caso NB-4 de una entrega re-enviada (returned -> submitted) que
    # quedo en 'submitted' con la calificacion vieja adherida.
    #
    # EXCEPTO si ya esta 'returned': ahi la devolucion es intencional y el
    # alumno tiene la pelota. `submit_entrega` solo acepta 'draft'/'returned',
    # asi que pisarla con 'graded' le contesta 409 cuando intenta re-entregar
    # — corregir un typo en la nota le trababa el TP.
    if entrega.estado != "returned":
        entrega.estado = "graded"

    await db.flush()
    await db.refresh(cal)

    # Audit log (meta-evento, NO va al CTR chain — ADR-010)
    log = structlog.get_logger()
    log.info(
        "tp_recalificada",
        entrega_id=str(entrega_id),
        calificacion_id=str(cal.id),
        nota_anterior=nota_anterior,
        nota_nueva=float(cal.nota_final),
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
    await _assert_docente_de_la_comision(db, entrega, user)

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
    stmt = select(Entrega).where(and_(Entrega.id == entrega_id, Entrega.deleted_at.is_(None)))
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entrega {entrega_id} no encontrada",
        )
    return obj


def _assert_can_read(entrega: Entrega, user: User) -> None:
    """Estudiantes solo pueden leer sus propias entregas."""
    if not (user.roles & DOCENTE_ROLES) and entrega.student_pseudonym != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver esta entrega",
        )


async def _assert_read_scope(db: AsyncSession, entrega: Entrega, user: User) -> None:
    """Scope completo de lectura sobre una entrega, para AMBOS tipos de caller.

    Espejo de `_assert_write_scope`: estudiante → ser dueño; docente → estar
    asignado a la comision. `list_entregas` ya filtraba su cola por
    `usuarios_comision`, asi que un docente nunca ve un `entrega_id` ajeno por
    la UI; pero el detalle por id no lo verificaba, y el id no es secreto.
    """
    _assert_can_read(entrega, user)
    if user.roles & DOCENTE_ROLES:
        await _assert_docente_de_la_comision(db, entrega, user)


async def _assert_docente_de_la_comision(db: AsyncSession, entrega: Entrega, user: User) -> None:
    """403 si el caller no es docente asignado a la comision de la entrega.

    Es el mismo aislamiento que `list_entregas` aplica a la COLA de correccion,
    pero para las ESCRITURAS. Hacia falta porque en prod todos los docentes
    comparten un tenant fijo: la RLS separa tenants, no comisiones. Con solo el
    chequeo de rol, cualquier docente con un `entrega_id` en la mano podia
    calificar, recalificar y devolver entregas de una comision ajena — el
    `entrega_id` ni siquiera es secreto, viaja en las URLs del web-teacher.

    Oversight academico (`OVERSIGHT_ROLES`) pasa: coordinacion corrige
    cross-comision a proposito, igual que ve toda la cola en `list_entregas`.

    `usuarios_comision` vive en la misma DB (academic_main) que `entregas`, asi
    que se consulta con la misma sesion — sin engine aparte ni join cross-base.
    Mismo patron que `assert_comision_member` de analytics-service y ctr-service.
    Ver docs/filtrado-teacher-plan.md.
    """
    if user.roles & OVERSIGHT_ROLES:
        return
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM usuarios_comision "
                "WHERE comision_id = :c AND user_id = :u "
                "AND deleted_at IS NULL LIMIT 1"
            ),
            {"c": str(entrega.comision_id), "u": str(user.id)},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenes acceso a las entregas de esta comision (no sos docente asignado).",
        )


def _assert_can_write(entrega: Entrega, user: User) -> None:
    """Estudiantes solo pueden escribir sus propias entregas."""
    if not (user.roles & DOCENTE_ROLES) and entrega.student_pseudonym != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar esta entrega",
        )


async def _assert_write_scope(db: AsyncSession, entrega: Entrega, user: User) -> None:
    """Scope completo de escritura sobre una entrega, para AMBOS tipos de caller.

    Los endpoints que comparten alumno y docente (`submit`, `ejercicio`) tienen
    dos scopes distintos y hay que aplicar el que corresponde:

    - Estudiante → ser dueño de la entrega (`_assert_can_write`). NO se le puede
      pedir membresia en `usuarios_comision`: los alumnos no viven ahi (viven en
      `inscripciones`), asi que ese chequeo le daria 403 a TODOS los alumnos y
      les romperia el flujo de entrega entero.
    - Docente → estar asignado a la comision de la entrega. Sin esto,
      `_assert_can_write` lo deja pasar sin mirar nada: solo frena estudiantes.
    """
    _assert_can_write(entrega, user)
    if user.roles & DOCENTE_ROLES:
        await _assert_docente_de_la_comision(db, entrega, user)
