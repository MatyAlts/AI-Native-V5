"""Endpoints de la corrección asistida por ejercicio (Epic 3).

    POST /api/v1/entregas/{id}/correccion-ia        preview o disparo
    GET  /api/v1/entregas/{id}/correccion-ia        las de esta entrega
    GET  /api/v1/entregas/{id}/correccion-ia/{cid}  una

Los tres verifican **membresía de comisión** y devuelven **404 y no 403**
cuando el docente no pertenece: un 403 confirmaría que la entrega existe, y
con eso el `entrega_id` de una comisión ajena se vuelve un oráculo. Acá pesa
más que en el resto del servicio, porque disparar sobre una entrega ajena
gasta cuota de otro y manda el código de un alumno afuera.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.auth import User, get_db
from evaluation_service.auth.dependencies import require_correccion_ia
from evaluation_service.config import settings
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.models.entregas import Entrega
from evaluation_service.schemas.activeia import (
    CorreccionIABody,
    CorreccionIAListOut,
    CorreccionIAOut,
    CorreccionPreviewOut,
)
from evaluation_service.services.activeia_sync import EstadoSync, estado_de_sincronizacion
from evaluation_service.services.correccion_cuota import (
    CuotaExcedidaError,
    CuotaIndeterminadaError,
    assert_cuota_disponible,
)
from evaluation_service.services.correccion_ejecutor import ejecutar_correccion
from evaluation_service.services.correccion_ia import (
    CorreccionRechazadaError,
    assert_puede_dispararse,
    buscar_existente,
    es_de_mi_comision,
    mapear_error_activeia,
    reabrir_para_reintento,
    resolver_rubrica,
)
from evaluation_service.services.correccion_pdf import get_storage as get_storage_pdf
from evaluation_service.services.correccion_worker import con_semaforo_y_presupuesto

router = APIRouter(prefix="/api/v1/entregas", tags=["correccion-ia"])

_OVERSIGHT = frozenset({"superadmin", "docente_admin"})


async def _contar_test_cases(db: AsyncSession, ejercicio_id: UUID | None) -> int:
    """Cuántos casos se van a correr. El preview lo enumera entre las cosas
    que el docente ve antes de gastar; devolverlo hardcodeado en 0 hacía que
    esa parte del preview mintiera."""
    if ejercicio_id is None:
        return 0
    row = await db.execute(
        text("SELECT jsonb_array_length(test_cases) FROM ejercicios WHERE id = :i"),
        {"i": str(ejercicio_id)},
    )
    return int(row.scalar_one_or_none() or 0)


async def _entrega_de_mi_comision(db: AsyncSession, entrega_id: UUID, user: User) -> Entrega:
    """La entrega, o 404. Nunca 403.

    El oversight (`superadmin`, `docente_admin`) saltea el chequeo de
    comisión, igual que en el listado de entregas.
    """
    stmt = select(Entrega).where(and_(Entrega.id == entrega_id, Entrega.deleted_at.is_(None)))
    entrega = (await db.execute(stmt)).scalar_one_or_none()
    if entrega is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entrega no existe")

    if not (user.roles & _OVERSIGHT) and not await es_de_mi_comision(
        db, user.id, entrega.comision_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entrega no existe")
    return entrega


def _out(c: CorreccionIA) -> CorreccionIAOut:
    _, infra = mapear_error_activeia(c.error_code, c.error_detail or "")
    return CorreccionIAOut(
        id=c.id,
        entrega_id=c.entrega_id,
        tp_ejercicio_id=c.tp_ejercicio_id,
        orden=c.orden,
        estado=c.estado,
        rubrica_id=c.rubrica_id,
        nota_100=c.nota_100,
        desglose=c.desglose,
        tests_snapshot=c.tests_snapshot,
        artefacto_sha256=c.artefacto_sha256,
        error_code=c.error_code,
        error_detail=c.error_detail,
        es_infraestructura=bool(c.error_code) and infra,
        external_correccion_id=c.external_correccion_id,
        tiene_pdf=bool(c.pdf_storage_key),
        created_at=c.created_at,
        finished_at=c.finished_at,
    )


@router.post("/{entrega_id}/correccion-ia", status_code=status.HTTP_202_ACCEPTED)
async def disparar_correccion(
    entrega_id: UUID,
    body: CorreccionIABody,
    background: BackgroundTasks,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> CorreccionPreviewOut | CorreccionIAOut:
    """Preview con `confirmado=false`, disparo con `true`.

    El preview NO ejecuta, NO contacta a Active-IA y NO consume cuota. Es el
    default a propósito: la operación cuesta plata y tiempo de cómputo.
    """
    if not settings.activeia_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La corrección asistida está desactivada en este entorno.",
        )

    entrega = await _entrega_de_mi_comision(db, entrega_id, user)
    # `ejercicio_orden` es OBLIGATORIO. El spec decía que ausente significaba
    # "corregir todos", y el código corregía sólo el 1 — una desviación
    # silenciosa. Se cerró exigiéndolo en vez de implementando el "todos":
    # cada corrección se paga, y un click que gasta N de golpe tiene que ser
    # una decisión explícita, no el default de un campo omitido. El spec se
    # actualizó para decir esto.
    orden = body.ejercicio_orden

    try:
        artefacto = await assert_puede_dispararse(db, entrega, orden)
        vinculo = await resolver_rubrica(db, user.tenant_id, artefacto.ejercicio_id)
    except CorreccionRechazadaError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

    existente = await buscar_existente(
        db, user.tenant_id, entrega.id, orden, vinculo.rubrica_id, artefacto.sha256
    )

    # La cuota se lee incluso para el preview: mostrarle al docente cuántas le
    # quedan ANTES de que apriete es parte de que la decisión sea suya.
    try:
        restante = await assert_cuota_disponible(db, user.tenant_id, user.id)
    except CuotaIndeterminadaError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except CuotaExcedidaError as e:
        if body.confirmado:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e)) from e
        restante = 0

    if not body.confirmado:
        estados = await estado_de_sincronizacion(db, user.tenant_id, entrega.tarea_practica_id)
        n_test_cases = await _contar_test_cases(db, artefacto.ejercicio_id)
        este = next((e for e in estados if e.ejercicio_id == artefacto.ejercicio_id), None)
        return CorreccionPreviewOut(
            orden=orden,
            ejercicio_titulo=este.titulo if este else f"Ejercicio {orden}",
            rubrica_id=vinculo.rubrica_id,
            rubrica_estado=(este.estado.value if este else EstadoSync.SIN_SINCRONIZAR.value),
            rubrica_simulada=bool(vinculo.rubrica_id.startswith("MOCK-")),
            n_test_cases=n_test_cases,
            codigo_bytes=len(artefacto.codigo.encode("utf-8")),
            ya_corregido=existente is not None,
            cuota_restante=restante,
        )

    # Idempotencia: mismo código, misma rúbrica, mismo ejercicio = el mismo
    # trabajo. Un doble click no paga dos veces.
    if existente is not None:
        if not await reabrir_para_reintento(db, existente):
            # Ya salió bien, sigue en vuelo, o otro request la reabrió
            # primero. En los tres casos se devuelve lo que hay: reiniciar una
            # `running` perdería el trabajo que se está pagando ahora mismo, y
            # disparar dos veces sobre la misma fila paga dos subidas.
            return _out(existente)
        # Falló y el docente reintenta. Se REUSA la fila y no se inserta otra:
        # el UNIQUE de la tabla no excluye las fallidas, así que un INSERT
        # nuevo chocaría y el docente recibiría un 500 sobre el botón que
        # existe para esto.
        correccion = existente
        structlog.get_logger().info(
            "activeia_correccion_reintentada",
            correccion_id=str(correccion.id),
            disparado_por=str(user.id),
        )
    else:
        correccion = CorreccionIA(
            tenant_id=user.tenant_id,
            entrega_id=entrega.id,
            tp_ejercicio_id=artefacto.ejercicio_id,
            orden=orden,
            disparado_por=user.id,
            rubrica_id=vinculo.rubrica_id,
            estado="pending",
            artefacto_sha256=artefacto.sha256,
        )
        db.add(correccion)
        await db.flush()
        await db.refresh(correccion)

    # El trabajo va a background con SU PROPIA sesión: la del request se cierra
    # apenas sale el 202, y sostenerla los 180s que puede durar agotaría el
    # pool (que es de 8) con cuatro docentes disparando a la vez.
    #
    # Los headers del sandbox se arman ACÁ, con la identidad de este request:
    # en background no hay request del cual sacarlos.
    background.add_task(
        con_semaforo_y_presupuesto,
        lambda: ejecutar_correccion(
            correccion_id=correccion.id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            comision_id=entrega.comision_id,
            ejercicio_id=artefacto.ejercicio_id,
            codigo=artefacto.codigo,
            language=artefacto.language,
            alumno_nombre=str(entrega.student_pseudonym),
            # El `external_ref` del EJERCICIO, que es lo que este campo tuvo
            # siempre: hasta el 2026-08-27 se llamaba `activeia_comision_id` y
            # viajaba como `comision_id` en el formulario, así que Active-IA
            # recibía un id de ejercicio donde esperaba una comisión. El
            # endpoint nuevo lo lleva en la URL, que es su lugar.
            ejercicio_ref=str(vinculo.external_ref or ""),
            headers_sandbox={
                "X-Tenant-Id": str(user.tenant_id),
                "X-User-Id": str(user.id),
                "X-User-Roles": ",".join(sorted(user.roles)),
                "X-User-Email": user.email,
            },
        ),
        tenant_id=user.tenant_id,
        correccion_id=correccion.id,
    )

    structlog.get_logger().info(
        "activeia_correccion_disparada",
        correccion_id=str(correccion.id),
        entrega_id=str(entrega.id),
        orden=orden,
        rubrica_id=vinculo.rubrica_id,
        disparado_por=str(user.id),
        simulada=vinculo.rubrica_id.startswith("MOCK-"),
    )
    return _out(correccion)


@router.get("/{entrega_id}/correccion-ia", response_model=CorreccionIAListOut)
async def listar_correcciones(
    entrega_id: UUID,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> CorreccionIAListOut:
    """Las correcciones de esta entrega, la más nueva primero por ejercicio."""
    entrega = await _entrega_de_mi_comision(db, entrega_id, user)
    rows = await db.execute(
        select(CorreccionIA)
        .where(CorreccionIA.entrega_id == entrega.id)
        .order_by(CorreccionIA.orden, CorreccionIA.created_at.desc())
    )
    return CorreccionIAListOut(correcciones=[_out(c) for c in rows.scalars().all()])


@router.get("/{entrega_id}/correccion-ia/{correccion_id}/pdf")
async def descargar_pdf(
    entrega_id: UUID,
    correccion_id: UUID,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """El PDF de devolución de Active-IA.

    Se sirve por acá y NO por una URL firmada: una URL que sobrevive a que el
    docente cierre la sesión es una URL que puede circular, y este PDF lleva
    el nombre del alumno y la devolución sobre su código. Cada descarga pasa
    por el mismo gate de comisión que el resto del epic — 404 y no 403.
    """
    entrega = await _entrega_de_mi_comision(db, entrega_id, user)
    stmt = select(CorreccionIA).where(
        and_(CorreccionIA.id == correccion_id, CorreccionIA.entrega_id == entrega.id)
    )
    c = (await db.execute(stmt)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corrección no existe")
    if not c.pdf_storage_key:
        # 404 y no 204: para el cliente "esta corrección no tiene PDF" y "esta
        # corrección no existe" se resuelven igual, y un 204 con cuerpo vacío
        # se lee como un PDF de cero bytes.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Esta corrección no tiene PDF de devolución.",
        )

    try:
        contenido = await get_storage_pdf().get(c.pdf_storage_key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo recuperar el PDF en este momento.",
        ) from e

    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="devolucion_{correccion_id}.pdf"'},
    )


@router.get("/{entrega_id}/correccion-ia/{correccion_id}", response_model=CorreccionIAOut)
async def obtener_correccion(
    entrega_id: UUID,
    correccion_id: UUID,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> CorreccionIAOut:
    """Una corrección. Es lo que poletea el frontend."""
    entrega = await _entrega_de_mi_comision(db, entrega_id, user)
    stmt = select(CorreccionIA).where(
        and_(CorreccionIA.id == correccion_id, CorreccionIA.entrega_id == entrega.id)
    )
    c = (await db.execute(stmt)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corrección no existe")
    return _out(c)
