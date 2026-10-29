"""Pedidos de ayuda: el alumno le pide ayuda a los docentes de su comision.

Endpoints:
  POST   /api/v1/pedidos-ayuda                  alumno: crea (201)
  GET    /api/v1/pedidos-ayuda/mios             alumno: los suyos
  GET    /api/v1/pedidos-ayuda?comision_id=     docente de la comision / supervision
  PATCH  /api/v1/pedidos-ayuda/{id}/resolver    docente de la comision / supervision

FUERA DE LA TRAZA COGNITIVA. Este modulo no importa nada del CTR, del tutor ni
del classifier, no hace requests salientes y no publica eventos. Pedir ayuda a
una persona es ayuda fuera de banda: queda registrada aca (con `episode_id` y
hora, para poder filtrarla) y en el log estructurado, nunca en la cadena del
episodio. El log NUNCA lleva el `mensaje` del alumno (texto libre: puede traer
datos personales y los logs los ve mas gente que los docentes de la comision).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.auth import User, get_db
from evaluation_service.auth.dependencies import require_docente, require_estudiante
from evaluation_service.models.entregas import Entrega
from evaluation_service.models.pedidos_ayuda import PedidoAyuda
from evaluation_service.routes.entregas import (
    _comision_de_la_tp,
    _ejercicios_esperados,
)
from evaluation_service.schemas.pedido_ayuda import (
    PedidoAyudaCreate,
    PedidoAyudaListMeta,
    PedidoAyudaListResponse,
    PedidoAyudaOut,
)

router = APIRouter(prefix="/api/v1/pedidos-ayuda", tags=["pedidos-ayuda"])
log = structlog.get_logger()

# Roles de supervision: ven y resuelven en cualquier comision del tenant.
_OVERSIGHT_ROLES = frozenset({"superadmin", "docente_admin"})

# Anti-spam (design D4): en la base y no en Redis, porque el caso de uso es
# justamente "la infraestructura esta mal".
_ESPERA_ENTRE_PEDIDOS_S = 60
_MAX_PENDIENTES_POR_TP = 3
_MAX_MIOS = 20
_MAX_LISTA = 200


# ── Consultas (cada una, probada contra Postgres real) ────────────────────


async def _esta_inscripto(db: AsyncSession, comision_id: UUID, student_id: UUID) -> bool:
    """Inscripcion vigente del alumno en la comision (el `user.id` es el pseudonimo)."""
    rows = await db.execute(
        text(
            "SELECT 1 FROM inscripciones "
            "WHERE comision_id = :cid AND student_pseudonym = :sid AND deleted_at IS NULL"
        ),
        {"cid": str(comision_id), "sid": str(student_id)},
    )
    return rows.first() is not None


async def _entrega_del_alumno_en_la_tp(
    db: AsyncSession, entrega_id: UUID, student_id: UUID, tarea_practica_id: UUID
) -> bool:
    """La entrega existe, es del alumno y es de esa TP."""
    rows = await db.execute(
        select(Entrega.id).where(
            Entrega.id == entrega_id,
            Entrega.student_pseudonym == student_id,
            Entrega.tarea_practica_id == tarea_practica_id,
            Entrega.deleted_at.is_(None),
        )
    )
    return rows.first() is not None


async def _segundos_desde_ultimo_pedido(db: AsyncSession, student_id: UUID) -> float | None:
    """Segundos desde el ultimo pedido del alumno (cualquier TP), o None si no hay.

    El reloj es el de la base: `created_at` lo pone la base, asi que comparar
    contra el reloj de la app mezclaria dos relojes.
    """
    rows = await db.execute(
        text(
            "SELECT EXTRACT(EPOCH FROM (clock_timestamp() - max(created_at))) "
            "FROM pedidos_ayuda WHERE student_pseudonym = :sid"
        ),
        {"sid": str(student_id)},
    )
    fila = rows.first()
    if fila is None or fila[0] is None:
        return None
    return float(fila[0])


async def _pendientes_en_la_tp(db: AsyncSession, student_id: UUID, tarea_practica_id: UUID) -> int:
    rows = await db.execute(
        select(func.count())
        .select_from(PedidoAyuda)
        .where(
            PedidoAyuda.student_pseudonym == student_id,
            PedidoAyuda.tarea_practica_id == tarea_practica_id,
            PedidoAyuda.estado == "pendiente",
        )
    )
    return int(rows.scalar_one())


async def _assert_docente_de_comision(db: AsyncSession, comision_id: UUID, user: User) -> None:
    """El docente solo opera sobre pedidos de SUS comisiones.

    Misma consulta y mismo **404** que `entregas._assert_comision_visible` (no se
    reutiliza esa funcion porque recibe una `Entrega`). 404 y no 403: un 403
    confirmaria que el pedido o la comision existen.
    """
    if user.roles & _OVERSIGHT_ROLES:
        return
    rows = await db.execute(
        text(
            "SELECT 1 FROM usuarios_comision "
            "WHERE user_id = :uid AND comision_id = :cid AND deleted_at IS NULL"
        ),
        {"uid": str(user.id), "cid": str(comision_id)},
    )
    if rows.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no existe")


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("", response_model=PedidoAyudaOut, status_code=status.HTTP_201_CREATED)
async def crear_pedido(
    data: PedidoAyudaCreate,
    user: User = Depends(require_estudiante),
    db: AsyncSession = Depends(get_db),
) -> PedidoAyudaOut:
    # 1. La comision sale de la TP, nunca del body.
    comision_id = await _comision_de_la_tp(db, data.tarea_practica_id)
    if comision_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Trabajo practico no existe"
        )

    # 2. Inscripcion vigente en esa comision.
    if not await _esta_inscripto(db, comision_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No estas inscripto en la comision de este trabajo",
        )

    # 3. La entrega, si viene, es del alumno y de esa TP.
    if data.entrega_id is not None and not await _entrega_del_alumno_en_la_tp(
        db, data.entrega_id, user.id, data.tarea_practica_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La entrega no es tuya o no es de este trabajo",
        )

    # 4. El ejercicio, si viene y la TP declara ejercicios, tiene que ser uno de ellos.
    # `episode_id` NO se valida: en "Episode no encontrado" ni existe.
    if data.ejercicio_orden is not None:
        esperados = await _ejercicios_esperados(db, data.tarea_practica_id)
        if esperados and data.ejercicio_orden not in {e["orden"] for e in esperados}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ese ejercicio no es de este trabajo",
            )

    # 5. Anti-spam (D4).
    desde = await _segundos_desde_ultimo_pedido(db, user.id)
    if desde is not None and desde < _ESPERA_ENTRE_PEDIDOS_S:
        espera = max(1, int(_ESPERA_ENTRE_PEDIDOS_S - desde))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Esperá {espera} segundos antes de mandar otro pedido.",
        )
    if await _pendientes_en_la_tp(db, user.id, data.tarea_practica_id) >= _MAX_PENDIENTES_POR_TP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya tenés {_MAX_PENDIENTES_POR_TP} pedidos sin responder en este trabajo. "
                "Esperá a que tu docente los resuelva."
            ),
        )

    pedido = PedidoAyuda(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        comision_id=comision_id,
        student_pseudonym=user.id,
        tarea_practica_id=data.tarea_practica_id,
        entrega_id=data.entrega_id,
        ejercicio_orden=data.ejercicio_orden,
        episode_id=data.episode_id,
        categoria=data.categoria,
        mensaje=data.mensaje,
        contexto=data.contexto.model_dump(exclude_none=True),
        estado="pendiente",
    )
    db.add(pedido)
    await db.flush()
    await db.refresh(pedido)

    # Nunca `mensaje`: ver docstring del modulo.
    log.info(
        "pedido_ayuda_creado",
        pedido_id=str(pedido.id),
        tenant_id=str(user.tenant_id),
        comision_id=str(comision_id),
        tarea_practica_id=str(data.tarea_practica_id),
        ejercicio_orden=data.ejercicio_orden,
        episode_id=str(data.episode_id) if data.episode_id else None,
        categoria=data.categoria,
    )
    return PedidoAyudaOut.model_validate(pedido)


@router.get("/mios", response_model=list[PedidoAyudaOut])
async def mis_pedidos(
    tarea_practica_id: UUID | None = Query(default=None),
    user: User = Depends(require_estudiante),
    db: AsyncSession = Depends(get_db),
) -> list[PedidoAyudaOut]:
    """Los pedidos del alumno, del mas nuevo al mas viejo (ultimos 20)."""
    stmt = select(PedidoAyuda).where(PedidoAyuda.student_pseudonym == user.id)
    if tarea_practica_id is not None:
        stmt = stmt.where(PedidoAyuda.tarea_practica_id == tarea_practica_id)
    stmt = stmt.order_by(PedidoAyuda.created_at.desc()).limit(_MAX_MIOS)
    rows = (await db.execute(stmt)).scalars().all()
    return [PedidoAyudaOut.model_validate(r) for r in rows]


@router.get("", response_model=PedidoAyudaListResponse)
async def listar_pedidos(
    comision_id: UUID = Query(...),
    estado: Literal["pendiente", "resuelto"] | None = Query(default=None),
    user: User = Depends(require_docente),
    db: AsyncSession = Depends(get_db),
) -> PedidoAyudaListResponse:
    await _assert_docente_de_comision(db, comision_id, user)

    stmt = select(PedidoAyuda).where(PedidoAyuda.comision_id == comision_id)
    if estado is not None:
        stmt = stmt.where(PedidoAyuda.estado == estado)
    # Los pendientes primero los mas viejos (los que mas esperan); los resueltos
    # los mas recientes primero.
    orden = PedidoAyuda.created_at.asc() if estado == "pendiente" else PedidoAyuda.created_at.desc()
    rows = (await db.execute(stmt.order_by(orden).limit(_MAX_LISTA))).scalars().all()

    pendientes = (
        await db.execute(
            select(func.count())
            .select_from(PedidoAyuda)
            .where(PedidoAyuda.comision_id == comision_id, PedidoAyuda.estado == "pendiente")
        )
    ).scalar_one()
    return PedidoAyudaListResponse(
        data=[PedidoAyudaOut.model_validate(r) for r in rows],
        meta=PedidoAyudaListMeta(pendientes=int(pendientes), total=len(rows)),
    )


@router.patch("/{pedido_id}/resolver", response_model=PedidoAyudaOut)
async def resolver_pedido(
    pedido_id: UUID,
    user: User = Depends(require_docente),
    db: AsyncSession = Depends(get_db),
) -> PedidoAyudaOut:
    """pendiente -> resuelto. Idempotente: no hay camino inverso en esta version."""
    pedido = await db.get(PedidoAyuda, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no existe")
    # Mismo 404 y mismo texto que el not-found genuino: no es un oraculo de existencia.
    await _assert_docente_de_comision(db, pedido.comision_id, user)

    if pedido.estado != "resuelto":
        pedido.estado = "resuelto"
        pedido.resuelto_por = user.id
        pedido.resuelto_at = datetime.now(UTC)
        await db.flush()
        log.info(
            "pedido_ayuda_resuelto",
            pedido_id=str(pedido.id),
            tenant_id=str(user.tenant_id),
            comision_id=str(pedido.comision_id),
            tarea_practica_id=str(pedido.tarea_practica_id),
            ejercicio_orden=pedido.ejercicio_orden,
            episode_id=str(pedido.episode_id) if pedido.episode_id else None,
            categoria=pedido.categoria,
            resuelto_por=str(user.id),
        )
    return PedidoAyudaOut.model_validate(pedido)
