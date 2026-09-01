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

import copy
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from evaluation_service.auth import User, get_db, require_permission
from evaluation_service.models.entregas import Calificacion, Entrega, EntregaArtefacto
from evaluation_service.schemas.entrega import (
    ArtefactoItem,
    ArtefactoOut,
    CalificacionCreate,
    CalificacionOut,
    CalificacionUpdate,
    EntregaArtefactoOut,
    EntregaCreate,
    EntregaListMeta,
    EntregaListResponse,
    EntregaOut,
    EntregaSubmitBody,
    MarkEjercicioBody,
)

router = APIRouter(prefix="/api/v1/entregas", tags=["entregas"])

_DOCENTE_ROLES = frozenset({"superadmin", "docente_admin", "docente", "jtp", "auxiliar"})
_OVERSIGHT_ROLES = frozenset({"superadmin", "docente_admin"})
# Quién puede leer el código de un alumno que no es él mismo. Es el mismo set
# que ve la cola de corrección: leer la entrega es parte de corregirla.
_READ_ARTEFACTO_ROLES = _DOCENTE_ROLES

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

    El `comision_id` del body se valida contra la TP ANTES de mirar si ya
    existe la entrega: un body que declara una comisión que no es la de la TP
    está mal armado, exista o no la entrega, y devolver 200 con la entrega
    buena ante un body inválido esconde el error del cliente.
    """
    log = structlog.get_logger()
    student_id = user.id

    await _assert_comision_de_la_tp(db, data.tarea_practica_id, data.comision_id)

    existing = await _find_existing_entrega(db, data.tarea_practica_id, student_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return EntregaOut.model_validate(existing)

    # Sembrar los ejercicios que la TP declara, todos incompletos. Antes esto
    # nacía `[]`, y el submit sólo validaba `if estados:` — con la lista vacía
    # NO validaba nada: entregar sin haber tocado un solo ejercicio pasaba.
    # Sembrado, "falta el ejercicio 2" es un estado detectable en vez del
    # estado inicial de toda entrega.
    esperados = await _ejercicios_esperados(db, data.tarea_practica_id)
    estados_iniciales: list[dict[str, Any]] = [
        {
            "ejercicio_id": e["ejercicio_id"],
            "orden": e["orden"],
            "episode_id": None,
            "completado": False,
            "completed_at": None,
        }
        for e in esperados
    ]

    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        tarea_practica_id=data.tarea_practica_id,
        student_pseudonym=student_id,
        comision_id=data.comision_id,
        estado="draft",
        ejercicio_estados=estados_iniciales,
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
    _assert_can_read(entrega, user)
    await _assert_comision_visible(db, entrega, user)
    return EntregaOut.model_validate(entrega)


@router.post("/{entrega_id}/submit", response_model=EntregaOut)
async def submit_entrega(
    entrega_id: UUID,
    body: EntregaSubmitBody | None = None,
    user: User = Depends(require_permission("entrega", "create")),
    db: AsyncSession = Depends(get_db),
) -> EntregaOut:
    """Transicion draft -> submitted.

    Valida que todos los ejercicios esperados esten completados Y que el
    cliente mande el codigo de cada uno, y lo persiste como artefacto.
    Emite audit log tp_entregada (structlog, no CTR chain).
    """
    # Con los artefactos YA cargados. `Entrega.artefactos` es lazy por
    # default, y tocar una relación no cargada desde una corrutina —fuera de
    # `greenlet_spawn`— tira `MissingGreenlet`, no un lazy load silencioso.
    # Es el único endpoint que la escribe, así que el eager load va acá y no
    # en el modelo: ponerlo en la relación haría que el listado del docente
    # (hasta 200 entregas) se traiga el código de todos los alumnos.
    entrega = await _get_or_404(db, entrega_id, con_artefactos=True, para_escritura=True)
    _assert_can_write(entrega, user)
    await _assert_comision_visible(db, entrega, user)

    if entrega.estado == "submitted":
        return EntregaOut.model_validate(entrega)

    if entrega.estado not in ("draft", "returned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede enviar una entrega en estado '{entrega.estado}'",
        )

    # Los ejercicios que la TP declara HOY. La entrega nace sembrada con
    # ellos, pero una TP puede haber sumado ejercicios después: si nos
    # quedamos con la lista guardada, un ejercicio agregado post-creación
    # nunca sería exigido.
    esperados = await _ejercicios_esperados(db, entrega.tarea_practica_id)
    estados: list[dict[str, Any]] = _reconciliar_estados(
        list(entrega.ejercicio_estados or []), esperados
    )
    entrega.ejercicio_estados = estados

    incompletos = [e for e in estados if not e.get("completado")]
    if incompletos:
        ordenes = sorted(e["orden"] for e in incompletos)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ejercicios incompletos: {ordenes}. Completa todos antes de entregar.",
        )

    # El código de CADA ejercicio esperado tiene que venir. Aceptar un submit
    # sin código reabre el agujero que este cambio cierra: dejaría entregas
    # `submitted` de las que no se sabe qué se entregó, y esas son
    # indistinguibles de las buenas hasta el momento de corregirlas.
    items = list(body.artefactos) if body is not None else []
    if esperados:
        recibidos = {i.orden for i in items}
        ordenes_esperados = {e["orden"] for e in esperados}
        faltantes = sorted(ordenes_esperados - recibidos)
        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Falta el código de los ejercicios: {faltantes}. "
                    "Abrí cada ejercicio una vez antes de entregar."
                ),
            )
        # Y que no SOBRE ninguno. Un `orden` que la TP no declara se
        # persistiría igual y entraría al hash del conjunto — el docente vería
        # un "Ejercicio 9" inexistente, y la constancia de lo entregado
        # dependería de una fila que ningún `tp_ejercicios` respalda.
        sobrantes = sorted(recibidos - ordenes_esperados)
        if sobrantes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"La TP no tiene los ejercicios: {sobrantes}.",
            )
    elif not items and entrega.artefactos:
        # Re-entrega monolítica sin código. Dejar pasar movería `submitted_at`
        # conservando el artefacto y el hash del envío anterior: el hash
        # dejaría de certificar el momento que la entrega declara, que es
        # justo la propiedad que esto viene a dar.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No mandaste código. Abrí el ejercicio antes de volver a entregar.",
        )

    # Un `orden` repetido violaría el UNIQUE recién en el flush, y ahí sale
    # como 500 con stack trace. El resto del endpoint responde 422 a un body
    # mal armado; esto también.
    duplicados = sorted({i.orden for i in items if [x.orden for x in items].count(i.orden) > 1})
    if duplicados:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Hay más de un código para los ejercicios: {duplicados}.",
        )

    if items:
        await _persistir_artefactos(db, entrega, items, estados, user.tenant_id)

    entrega.estado = "submitted"
    entrega.submitted_at = datetime.now(UTC)
    # Los locales se leen ANTES del refresh: `refresh` expira la relación
    # `artefactos`, y volver a tocarla después sería otro lazy load en async.
    n_artefactos = len(items)
    artefacto_sha256 = entrega.artefacto_sha256
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
        artefacto_sha256=artefacto_sha256,
        n_artefactos=n_artefactos,
    )

    return EntregaOut.model_validate(entrega)


@router.get("/{entrega_id}/artefacto", response_model=EntregaArtefactoOut)
async def get_entrega_artefacto(
    entrega_id: UUID,
    user: User = Depends(require_permission("entrega", "read")),
    db: AsyncSession = Depends(get_db),
) -> EntregaArtefactoOut:
    """Devuelve el código que el alumno entregó.

    El docente sólo puede leer entregas de SUS comisiones. Cuando no puede,
    la respuesta es 404 y no 403: un 403 confirmaría que la entrega existe,
    y con eso el `entrega_id` de una comisión ajena se vuelve un oráculo de
    existencia. Mismo criterio de aislamiento por comisión que el listado.
    """
    entrega = await _get_or_404(db, entrega_id)

    is_owner = entrega.student_pseudonym == user.id
    if not is_owner and not (user.roles & _READ_ARTEFACTO_ROLES):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entrega no existe")
    await _assert_comision_visible(db, entrega, user)

    artefactos = (
        (
            await db.execute(
                select(EntregaArtefacto)
                .where(EntregaArtefacto.entrega_id == entrega.id)
                .order_by(EntregaArtefacto.orden)
            )
        )
        .scalars()
        .all()
    )

    return EntregaArtefactoOut(
        entrega_id=entrega.id,
        tarea_practica_id=entrega.tarea_practica_id,
        student_pseudonym=entrega.student_pseudonym,
        submitted_at=entrega.submitted_at,
        artefacto_sha256=entrega.artefacto_sha256,
        legacy=entrega.legacy,
        artefactos=[ArtefactoOut.model_validate(a) for a in artefactos],
    )


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
    entrega = await _get_or_404(db, entrega_id, para_escritura=True)
    _assert_can_write(entrega, user)
    await _assert_comision_visible(db, entrega, user)

    if entrega.estado not in ("draft", "returned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede modificar ejercicios en estado '{entrega.estado}'",
        )

    completado = body.completado if body else True
    episode_id = body.episode_id if body else None
    ejercicio_id = body.ejercicio_id if body else None

    # ADR-047: match prefiere `ejercicio_id` (UUID estable) sobre `orden`
    # cuando ambos están disponibles. Si a CUALQUIERA de los dos lados le
    # falta el UUID, cae al match por orden — no sólo cuando le falta al
    # estado guardado. Desde que la entrega nace sembrada (con `ejercicio_id`
    # ya cargado), un cliente que marca sin UUID no encontraba nada y
    # appendeaba una fila duplicada para el mismo ejercicio.
    # `deepcopy` y NO `list(...)`: `list()` copia la lista pero comparte los
    # dicts, así que mutarlos acá muta también el valor cargado. Al reasignar,
    # SQLAlchemy compara viejo contra nuevo, los ve iguales (son los mismos
    # objetos, ya mutados) y NO emite el UPDATE. La columna es JSONB plano sin
    # `MutableList`, así que nadie avisa: el flush pasa limpio y el cambio se
    # pierde. Con `deepcopy` el valor nuevo es realmente distinto del viejo.
    estados = copy.deepcopy(list(entrega.ejercicio_estados or []))
    found = False
    for est in estados:
        matches_by_uuid = ejercicio_id is not None and est.get("ejercicio_id") == str(ejercicio_id)
        matches_by_orden = est.get("orden") == orden and (
            est.get("ejercicio_id") is None or ejercicio_id is None
        )
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
    entrega = await _get_or_404(db, entrega_id, para_escritura=True)
    await _assert_comision_visible(db, entrega, user)

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
      que quedo en `submitted` con la calificacion vieja adherida — NB-4).
    - Emite audit log `tp_recalificada` (structlog, NO va al CTR chain — ADR-010)
      con la nota anterior y la nueva.
    """
    entrega = await _get_or_404(db, entrega_id, para_escritura=True)
    await _assert_comision_visible(db, entrega, user)

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
    # EXCEPTO si ya esta 'returned': ahi la devolucion es intencional y el alumno
    # tiene la pelota. `submit_entrega` solo acepta 'draft'/'returned', asi que
    # pisarla con 'graded' le contesta 409 cuando intenta re-entregar — o sea que
    # el docente que corrige un TYPO en la nota le traba el TP al alumno, sin
    # enterarse. Y no hay perdida por no normalizar: no existe forma de llegar a
    # `returned` sin una calificacion previa.
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
    """Lee la calificacion. Docentes ven las de SUS comisiones; estudiantes la suya."""
    entrega = await _get_or_404(db, entrega_id)
    _assert_can_read(entrega, user)
    await _assert_comision_visible(db, entrega, user)

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
    """Devuelve la entrega al alumno (graded -> returned) y le reabre los ejercicios.

    Las DOS cosas, en la MISMA transaccion. Hasta el 2026-08-31 esto solo
    cambiaba el estado, y ahi el boton "Devolver al estudiante" era una promesa
    vacia: al alumno le aparecia el cartel

        "Devuelta para revisar. Tu docente devolvio la entrega con observaciones."

    y ningun boton para revisar nada, porque `ExerciseListView` gateaba tanto el
    boton de cada ejercicio como el de entregar con `estado === "draft"`. El
    docente podia pasarse semanas devolviendo TP creyendo que llegaban.

    POR QUE ACA Y NO EN EL FRONTEND
    -------------------------------
    La alternativa era que el frontend, al ver `returned`, disparara N llamadas
    al PATCH de ejercicio. Eso hace que "devolver" deje de ser atomico: si la
    tercera de cinco falla —o el docente cierra la pestana— la entrega queda
    `returned` con dos ejercicios abiertos y tres cerrados, un estado que nadie
    diseno y del que no se sale. Aca es una sola transaccion: o vuelve entera o
    no vuelve.

    QUE **NO** SE REABRE: EL EPISODIO
    ---------------------------------
    Se evaluo pasar el episodio de `closed` a `open` y se DESCARTO. Queda
    escrito para que no se vuelva a proponer:

      - `resume_episode` ya devuelve 409 sobre un episodio cerrado, y no es un
        olvido: esta documentado.
      - Cerrar dispara `episodio_cerrado` -> `attestation_producer` (ADR-021).
        El episodio queda sellado y firmado criptograficamente.
      - Reabrirlo dejaria una cadena append-only donde el evento de cierre ya no
        es el ultimo, y una atestacion certificando un estado que dejo de
        existir. Si "cerrado" se puede deshacer, cerrado no significa nada — y
        esa irreversibilidad es la premisa de la tesis, no un detalle tecnico.

    Lo que se reabre es el EJERCICIO, que es otra cosa: `completado` es un flag
    de progreso en la entrega, no un hecho firmado. Y el sistema ya sabe hacer
    lo correcto con el episodio viejo: `openEpisodeAndNavigate` solo retoma
    episodios `paused` u `open`, y ante uno `closed` abre uno NUEVO.

    De yapa, y no es menor: con un episodio nuevo el docente termina viendo los
    DOS intentos, antes y despues de la devolucion, y puede comparar que cambio
    el alumno cuando le senalaron el error. Para una plataforma cuyo producto es
    la traza cognitiva, eso es evidencia del ciclo de correccion.
    """
    entrega = await _get_or_404(db, entrega_id, para_escritura=True)
    await _assert_comision_visible(db, entrega, user)

    if entrega.estado != "graded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se puede devolver una entrega en 'graded' (estado: '{entrega.estado}')",
        )

    entrega.estado = "returned"
    entrega.ejercicio_estados = _reabrir_ejercicios(entrega.ejercicio_estados)
    await db.flush()
    await db.refresh(entrega)
    return EntregaOut.model_validate(entrega)


# ── Helpers privados ──────────────────────────────────────────────────────


def _reabrir_ejercicios(estados: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Des-marca todos los ejercicios para que el alumno pueda volver a entrar.

    `deepcopy` y NO `list(...)`: `list()` copia la lista pero comparte los
    dicts, asi que mutarlos aca muta tambien el valor cargado. Al reasignar,
    SQLAlchemy compara viejo contra nuevo, los ve iguales (son los mismos
    objetos, ya mutados) y NO emite el UPDATE. La columna es JSONB plano sin
    `MutableList`, asi que nadie avisa: el flush pasa limpio y el cambio se
    pierde en silencio. Es la misma trampa que ya documenta
    `mark_ejercicio_completado`, y muerde igual.

    `completed_at` se pone en None junto con el flag. Dejarlo con la fecha
    vieja hace que el par diga dos cosas incompatibles —"no completado, el
    martes a las 14:03"— y despues alguien lo lee como si fuera la fecha de
    entrega. Es exactamente lo que hace el PATCH al des-marcar.

    Lo que NO se toca es `episode_id`: apunta al episodio del intento anterior,
    que sigue cerrado, firmado y siendo la evidencia de lo que el alumno hizo
    la primera vez. Se pisa solo cuando el alumno abre el episodio NUEVO, y en
    el medio es lo unico que permite recuperar el codigo del intento viejo.
    """
    reabiertos = copy.deepcopy(list(estados or []))
    for est in reabiertos:
        est["completado"] = False
        est["completed_at"] = None
    return reabiertos


async def _ejercicios_esperados(db: AsyncSession, tarea_practica_id: UUID) -> list[dict[str, Any]]:
    """Los ejercicios que la TP declara, en orden.

    `tp_ejercicios` vive en la misma DB (academic_main) pero es propiedad de
    academic-service, así que se lee por SQL y no importando su modelo —
    mismo criterio que la consulta a `usuarios_comision` del listado.

    Esto es la lista ESPERADA. Sin ella, `ejercicio_estados` nace vacío y
    "falta un ejercicio" deja de ser un estado detectable para pasar a ser el
    estado inicial de toda entrega.
    """
    rows = await db.execute(
        text(
            "SELECT orden, ejercicio_id FROM tp_ejercicios "
            "WHERE tarea_practica_id = :tp ORDER BY orden"
        ),
        {"tp": str(tarea_practica_id)},
    )
    return [{"orden": r[0], "ejercicio_id": str(r[1]) if r[1] else None} for r in rows.all()]


async def _comision_de_la_tp(db: AsyncSession, tarea_practica_id: UUID) -> UUID | None:
    """La comisión a la que pertenece la TP, o `None` si la TP no es visible.

    `tareas_practicas` es propiedad de academic-service pero vive en la misma
    DB (`academic_main`), así que se lee por SQL crudo — mismo criterio que
    `_ejercicios_esperados` acá y que `_assert_tp_de_mi_comision` en
    `activeia.py`.

    "No visible" incluye la TP de otro tenant: la tabla tiene RLS y la sesión
    entra con `app.current_tenant` seteado, así que una TP ajena no aparece y
    el caller la trata igual que a una inexistente.

    Y también incluye la TP BORRADA. `tareas_practicas` tiene `deleted_at`
    (soft-delete del academic-service) y esta consulta no lo miraba: una TP que
    el docente había borrado seguía devolviendo su comisión, así que
    `create_entrega` la aceptaba, sembraba `ejercicio_estados` desde la TP
    muerta, y el alumno podía completar, entregar y hacerse calificar sobre un
    trabajo práctico que ya no existe. Borrada e inexistente devuelven lo mismo
    (`None`) a propósito: el caller las trata igual y el mensaje no distingue
    una de otra.
    """
    rows = await db.execute(
        text("SELECT comision_id FROM tareas_practicas WHERE id = :tp AND deleted_at IS NULL"),
        {"tp": str(tarea_practica_id)},
    )
    fila = rows.first()
    return UUID(str(fila[0])) if fila is not None else None


async def _assert_tp_viva(db: AsyncSession, tarea_practica_id: UUID) -> None:
    """409 si la TP de la entrega fue borrada. Gate de ESCRITURA, no de lectura.

    `_comision_de_la_tp` cierra la puerta de entrada (`create_entrega`) y nada
    más. Los endpoints que operan sobre una entrega YA EXISTENTE —`submit`,
    `mark_ejercicio_completado`, `calificar`, `recalificar`, `return`— arrancan
    en `_get_or_404`, que filtra `Entrega.deleted_at` pero nunca mira la TP. Y
    el camino realista ni siquiera necesita el agujero de la puerta: el alumno
    que tenía la entrega abierta cuando el docente borró la TP podía enviarla
    igual, y el docente terminaba poniéndole nota a un TP que él mismo borró
    (`list_entregas` filtra `estado != "draft"`, así que le aparecía en la cola
    de corrección como trabajo pendiente).

    Del otro lado tampoco hay nada: `TareaPracticaService.soft_delete` tiene un
    `# DEFERRED` explícito y cero guards — no avisa a nadie ni bloquea si hay
    entregas en curso. Ese servicio es de otro dueño; acá se cierra el lado que
    escribe.

    **409 y no 404**: la entrega existe y el alumno tiene derecho a verla. Lo
    que no se puede es seguir avanzando el ciclo. Por eso este guard NO se
    aplica a los GET — cerrar la lectura le borraría al docente el trabajo
    histórico del alumno de la vista, y eso es evidencia legítima: la entrega
    existió y la TP existía cuando se hizo.
    """
    if await _comision_de_la_tp(db, tarea_practica_id) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El trabajo practico ya no esta disponible. "
                "Consulta con tu docente antes de seguir."
            ),
        )


async def _assert_comision_de_la_tp(
    db: AsyncSession, tarea_practica_id: UUID, comision_id: UUID
) -> UUID:
    """La comisión que el alumno declara tiene que ser la de la TP.

    El FK de `entregas.comision_id` garantiza que la comisión EXISTE, no que
    sea la de la tarea práctica. Sin este chequeo el alumno elegía a qué cola
    de corrección iba su trabajo: `list_entregas` filtra por
    `Entrega.comision_id`, así que declarar una comisión ajena mandaba la
    entrega a los docentes equivocados, y declarar una comisión sin docentes
    la escondía de la propia.

    422 y no 500: es un body mal armado del cliente. Hasta acá una TP o una
    comisión inexistente reventaban recién en el `IntegrityError` del FK, que
    caía en la rama de recuperación del race del UNIQUE, no encontraba nada y
    devolvía "Error inesperado al crear entrega".

    Devuelve la comisión de la TP para que el caller no tenga que releerla.
    """
    de_la_tp = await _comision_de_la_tp(db, tarea_practica_id)
    if de_la_tp is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trabajo practico no existe",
        )
    if de_la_tp != comision_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La comision declarada no es la del trabajo practico",
        )
    return de_la_tp


def _reconciliar_estados(
    estados: list[dict[str, Any]], esperados: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Suma los ejercicios de la TP que faltan en `ejercicio_estados`.

    Nunca borra ni des-marca: un ejercicio que la TP ya no declara igual se
    entregó, y quitarlo perdería la constancia de que el alumno lo hizo. Lo
    que agrega es el ejercicio nuevo, incompleto — así el submit lo exige.

    Con `esperados` vacío (TP monolítica sin `tp_ejercicios`) devuelve los
    estados tal cual: sin lista esperada no hay nada contra qué reconciliar,
    y exigir sobre una lista vacía bloquearía toda entrega monolítica.

    Devuelve SIEMPRE una copia profunda: el caller reasigna el resultado a la
    columna JSONB, y si compartiera los dicts con el valor cargado SQLAlchemy
    no vería diferencia y no emitiría el UPDATE.
    """
    estados = copy.deepcopy(estados)
    if not esperados:
        return estados

    por_uuid = {e["ejercicio_id"] for e in estados if e.get("ejercicio_id")}
    # Los `orden` que ya figuran SIN UUID. Un esperado con UUID tiene que
    # mirar acá también: si el estado guardado no tiene `ejercicio_id` (lo que
    # escribe el PATCH cuando el cliente no lo manda), buscar sólo por UUID no
    # lo encuentra y se agrega un SEGUNDO estado con el mismo `orden`. El
    # duplicado nace incompleto y no se destraba nunca: el PATCH siguiente
    # matchea el primero, y el submit exige el segundo para siempre.
    ordenes_sin_uuid = {e["orden"] for e in estados if not e.get("ejercicio_id")}
    todos_los_ordenes = {e["orden"] for e in estados}

    out = list(estados)
    for esp in esperados:
        eid = esp["ejercicio_id"]
        if eid:
            ya_esta = eid in por_uuid or esp["orden"] in ordenes_sin_uuid
        else:
            ya_esta = esp["orden"] in todos_los_ordenes
        if not ya_esta:
            out.append(
                {
                    "ejercicio_id": eid,
                    "orden": esp["orden"],
                    "episode_id": None,
                    "completado": False,
                    "completed_at": None,
                }
            )
    return out


async def _persistir_artefactos(
    db: AsyncSession,
    entrega: Entrega,
    items: list[ArtefactoItem],
    estados: list[dict[str, Any]],
    tenant_id: UUID,
) -> None:
    """Guarda el código del submit y sella el hash del conjunto.

    Reemplaza los artefactos previos: un re-submit tras `returned` entrega
    código nuevo, y conservar el viejo dejaría dos versiones sin decir cuál
    es la entregada.

    El `episode_id` que el cliente no manda se resuelve contra
    `ejercicio_estados`, que ya lo tiene desde que el alumno cerró el
    ejercicio (tarea 1.10).
    """
    por_uuid = {e["ejercicio_id"]: e for e in estados if e.get("ejercicio_id")}
    por_orden = {e["orden"]: e for e in estados}

    # El flush entre el clear y los append NO es opcional. En un solo flush,
    # la unit of work de SQLAlchemy ordena los INSERT antes que los DELETE del
    # `delete-orphan`, y el re-submit choca contra
    # `uq_entrega_artefacto_orden` con un IntegrityError. Separándolos, el
    # DELETE de la versión vieja va primero.
    if entrega.artefactos:
        entrega.artefactos.clear()
        await db.flush()
    for item in sorted(items, key=lambda i: i.orden):
        est = por_uuid.get(str(item.ejercicio_id)) if item.ejercicio_id else None
        if est is None:
            est = por_orden.get(item.orden, {})
        episode_id = item.episode_id
        if episode_id is None and est.get("episode_id"):
            episode_id = UUID(str(est["episode_id"]))

        entrega.artefactos.append(
            EntregaArtefacto(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                orden=item.orden,
                episode_id=episode_id,
                ejercicio_id=item.ejercicio_id,
                codigo=item.codigo,
                language=item.language,
                sha256=hashlib.sha256(item.codigo.encode("utf-8")).hexdigest(),
            )
        )

    # Hash del CONJUNTO: mismo criterio que `chunks_used_hash` (RN-026) —
    # join con separador sobre una lista ordenada, para que el mismo conjunto
    # dé siempre el mismo hash sin depender del orden en que llegó.
    canonical = "|".join(f"{a.orden}:{a.sha256}" for a in entrega.artefactos)
    entrega.artefacto_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


async def _get_or_404(
    db: AsyncSession,
    entrega_id: UUID,
    *,
    con_artefactos: bool = False,
    para_escritura: bool = False,
) -> Entrega:
    """La entrega, o 404.

    `para_escritura=True` suma el gate de `_assert_tp_viva`: la entrega existe
    pero su trabajo práctico fue borrado, así que el ciclo no puede seguir
    (409). Va acá y no repetido en cada endpoint porque los cinco escritores
    (`submit`, `mark_ejercicio_completado`, `calificar`, `recalificar`,
    `return`) empiezan todos por esta función — un `if` copiado cinco veces es
    cinco oportunidades de que el próximo endpoint nazca sin él, que es
    exactamente cómo quedaron abiertos.

    Default `False` porque las LECTURAS tienen que seguir pasando: el docente
    necesita ver el trabajo histórico de una TP borrada. Ver `_assert_tp_viva`.
    """
    stmt = select(Entrega).where(and_(Entrega.id == entrega_id, Entrega.deleted_at.is_(None)))
    if con_artefactos:
        stmt = stmt.options(selectinload(Entrega.artefactos))
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if obj is None:
        # Mismo texto que el rechazo por comisión de `_assert_comision_visible`,
        # y sin el id adentro. Devolver dos mensajes distintos deja el oráculo
        # de existencia abierto en el body aunque el status sea 404 en los dos
        # casos: "no encontrada" diria que no existe y "no existe" que existe
        # pero es de otra comision. Si se toca uno, se tocan los dos.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no existe",
        )
    if para_escritura:
        await _assert_tp_viva(db, obj.tarea_practica_id)
    return obj


async def _assert_comision_visible(db: AsyncSession, entrega: Entrega, user: User) -> None:
    """El docente sólo opera sobre entregas de SUS comisiones.

    `_assert_can_read` cubre al ESTUDIANTE (sólo lo suyo), pero deja pasar a
    cualquier docente sobre cualquier entrega. Sin esto, un docente de otra
    comisión podía leer una entrega ajena, calificarla, re-calificarla y
    devolverla: el `entrega_id` era la única credencial. Con el filtro puesto
    en el listado pero no acá, además, alcanzaba con probar ids.

    **404 y no 403**, mismo criterio que `GET /{id}/artefacto`: un 403
    confirmaría que la entrega existe, y ahí el id de una comisión ajena se
    vuelve un oráculo de existencia.

    El dueño de la entrega no pasa por acá — a un estudiante lo gobierna
    `_assert_can_read` / `_assert_can_write`, y su `student_pseudonym` ya es
    un filtro más estrecho que la comisión.
    """
    if entrega.student_pseudonym == user.id:
        return
    if user.roles & _OVERSIGHT_ROLES:
        return

    rows = await db.execute(
        text(
            "SELECT 1 FROM usuarios_comision "
            "WHERE user_id = :uid AND comision_id = :cid AND deleted_at IS NULL"
        ),
        {"uid": str(user.id), "cid": str(entrega.comision_id)},
    )
    if rows.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entrega no existe")


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
