"""Orquestación de una corrección asistida por ejercicio (Epic 3).

El orden de los pasos NO es arbitrario, y cada uno está antes que el
siguiente por una razón:

1. **Gates** (comisión, artefacto, LEGACY, rúbrica sincronizada). Son gratis y
   cortan sin gastar nada.
2. **Idempotencia.** Si esta misma corrección ya existe, se devuelve. Un doble
   click no paga dos veces.
3. **Cuota.** Falla cerrada. Va antes de ejecutar porque ejecutar ya cuesta.
4. **Pre-ejecución en el sandbox.** Si no compila, se corta acá: pagar una
   corrección sobre código que no compila es tirar plata, y el error de
   compilación es la devolución más accionable que hay.
5. **Active-IA.**

Y la regla que atraviesa todo: **un fallo de infraestructura nunca es una
nota.** Timeout, Gemini saturado, sandbox caído — todos terminan en
`estado='error'` con `error_code` y `nota_100 IS NULL`, que la base además
hace cumplir con un CHECK.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import and_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.models.activeia import ActiveIARubricaEjercicio
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.models.entregas import Entrega, EntregaArtefacto

log = structlog.get_logger()


class CorreccionRechazadaError(Exception):
    """No se puede disparar. Es un 400/422, no un fallo — y NO consume cuota."""


@dataclass(frozen=True)
class Preview:
    """Lo que se muestra ANTES de gastar, con `confirmado=false`.

    Existe porque una corrección cuesta plata y tiempo de cómputo, y porque el
    docente tiene que poder ver con qué rúbrica se va a corregir antes de que
    se corrija. Una rúbrica equivocada no da una nota floja: corrige otra cosa.
    """

    orden: int
    ejercicio_titulo: str
    rubrica_id: str
    rubrica_estado: str
    rubrica_simulada: bool
    n_test_cases: int
    codigo_bytes: int
    ya_corregido: bool
    cuota_restante: int


async def _artefacto_de(db: AsyncSession, entrega: Entrega, orden: int) -> EntregaArtefacto | None:
    stmt = select(EntregaArtefacto).where(
        and_(EntregaArtefacto.entrega_id == entrega.id, EntregaArtefacto.orden == orden)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def assert_puede_dispararse(
    db: AsyncSession, entrega: Entrega, orden: int
) -> EntregaArtefacto:
    """Gates que no dependen de nadie externo (tarea 3.10).

    Una entrega LEGACY no se corrige: su código no existe. Lo único
    reconstruible es una lectura del CTR, y eso no es lo que el alumno
    entregó — corregir sobre eso pondría en un legajo la nota de un texto que
    nadie garantiza que sea el entregado.
    """
    if entrega.legacy:
        raise CorreccionRechazadaError(
            "Esta entrega es anterior a que la plataforma guardara el código. "
            "No hay artefacto que corregir."
        )
    if entrega.estado not in ("submitted", "graded", "returned"):
        raise CorreccionRechazadaError(
            f"La entrega está en '{entrega.estado}': todavía no se entregó."
        )

    artefacto = await _artefacto_de(db, entrega, orden)
    if artefacto is None:
        raise CorreccionRechazadaError(
            f"No hay código guardado para el ejercicio {orden} de esta entrega."
        )
    return artefacto


async def _vinculo_rubrica(
    db: AsyncSession, tenant_id: UUID, ejercicio_id: UUID | None
) -> ActiveIARubricaEjercicio | None:
    if ejercicio_id is None:
        return None
    stmt = select(ActiveIARubricaEjercicio).where(
        and_(
            ActiveIARubricaEjercicio.tenant_id == tenant_id,
            ActiveIARubricaEjercicio.ejercicio_id == ejercicio_id,
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def resolver_rubrica(
    db: AsyncSession, tenant_id: UUID, ejercicio_id: UUID | None
) -> ActiveIARubricaEjercicio:
    """La rúbrica con la que se va a corregir, o un error que dice qué falta."""
    vinculo = await _vinculo_rubrica(db, tenant_id, ejercicio_id)
    if vinculo is None:
        raise CorreccionRechazadaError(
            "Este ejercicio no tiene una rúbrica sincronizada con Active-IA. "
            "Sincronizá el trabajo práctico primero."
        )
    return vinculo


async def buscar_existente(
    db: AsyncSession,
    tenant_id: UUID,
    entrega_id: UUID,
    orden: int,
    rubrica_id: str,
    artefacto_sha256: str,
) -> CorreccionIA | None:
    """La misma corrección, si ya existe (tarea 3.11).

    Mismo alumno + mismo ejercicio + misma rúbrica + mismo código = el mismo
    trabajo. Re-disparar devuelve lo que hay en vez de pagar otra corrida.

    Devuelve TAMBIÉN las que quedaron en `error`. Antes las excluía —para
    permitir reintentar— pero el UNIQUE de la tabla no excluye nada: la fila
    fallida sigue ocupando la clave, así que el "reintento" chocaba contra
    `uq_correccion_ia_idempotencia` y el docente recibía un 500 sobre el botón
    que existe justamente para reintentar.

    El reintento se resuelve REUSANDO la fila (ver `reabrir_para_reintento`),
    no insertando otra. Es además lo correcto: es el mismo trabajo sobre el
    mismo código y la misma rúbrica, y merece la misma fila.
    """
    stmt = select(CorreccionIA).where(
        and_(
            CorreccionIA.tenant_id == tenant_id,
            CorreccionIA.entrega_id == entrega_id,
            CorreccionIA.orden == orden,
            CorreccionIA.rubrica_id == rubrica_id,
            CorreccionIA.artefacto_sha256 == artefacto_sha256,
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def reabrir_para_reintento(db: AsyncSession, correccion: CorreccionIA) -> bool:
    """Deja una corrección fallida lista para volver a correr. Atómico.

    Devuelve False si no hay nada que reintentar — o porque salió bien, o
    porque sigue en vuelo, o **porque otro request la reabrió primero**. Un
    doble click sobre una `running` NO la reinicia: reiniciarla perdería el
    trabajo que está pagándose ahora mismo.

    **El UPDATE lleva `estado='error'` en el WHERE y se decide por su
    `rowcount`, no por lo que dice el objeto en memoria.** Chequear en memoria
    y después escribir deja una ventana: dos requests que leen la fila antes de
    que cualquiera commitee ven las dos `error`, las dos devuelven True, y las
    dos mandan un trabajo sobre la MISMA fila — dos corridas del sandbox y
    **dos subidas a Active-IA**, que se pagan las dos. Con la condición en el
    WHERE, la segunda actualiza cero filas y se va.

    La nota se limpia explícitamente aunque ya deba ser `None`: el CHECK de la
    base exige que un estado distinto de `done` no la tenga, y confiar en que
    ya está limpia es confiar en que ningún camino la dejó puesta.
    """
    if correccion.estado != "error":
        return False

    res = await db.execute(
        update(CorreccionIA)
        .where(
            and_(
                CorreccionIA.id == correccion.id,
                # La guarda que hace esto atómico. Sin ella, el UPDATE
                # sobreescribe igual y los dos requests ganan.
                CorreccionIA.estado == "error",
            )
        )
        .values(
            estado="pending",
            nota_100=None,
            desglose=[],
            error_code=None,
            error_detail=None,
            started_at=None,
            finished_at=None,
        )
    )
    if (getattr(res, "rowcount", 0) or 0) == 0:
        # Otro request llegó primero. No es un error: es que ya se está
        # reintentando, y una sola vez es exactamente lo que queremos.
        return False

    await db.refresh(correccion)
    return True


async def es_de_mi_comision(db: AsyncSession, user_id: UUID, comision_id: UUID) -> bool:
    """Membresía de comisión (tarea 3.9).

    Se verifica contra `usuarios_comision` y NO con `_assert_can_read`, que
    sólo mira el frozenset de roles: en producción todos los docentes
    comparten tenant, así que la RLS no los separa. Sin esto, un docente puede
    gastar la cuota de otro y mandar el código de un alumno ajeno afuera.
    """
    rows = await db.execute(
        text(
            "SELECT 1 FROM usuarios_comision "
            "WHERE user_id = :uid AND comision_id = :cid AND deleted_at IS NULL"
        ),
        {"uid": str(user_id), "cid": str(comision_id)},
    )
    return rows.first() is not None


def marcar_error(
    correccion: CorreccionIA, *, error_code: str, detalle: str, es_infraestructura: bool
) -> None:
    """Cierra una corrección fallida SIN nota.

    `es_infraestructura` no cambia el estado —los dos son `error`— pero sí lo
    que la UI muestra: ámbar y "reintentá" para infraestructura, rojo y "el
    servicio rechazó esto" para un rechazo. Confundirlos ya costó dos días de
    reintentos sobre una entrega que nunca iba a destrabarse sola.
    """
    correccion.estado = "error"
    correccion.nota_100 = None
    correccion.error_code = error_code
    correccion.error_detail = detalle[:4000]
    correccion.finished_at = datetime.now(UTC)
    log.warning(
        "activeia_correccion_fallo",
        correccion_id=str(correccion.id),
        error_code=error_code,
        es_infraestructura=es_infraestructura,
    )


def mapear_error_activeia(error_code: str | None, mensaje: str) -> tuple[str, bool]:
    """Traduce un fallo de Active-IA a `(error_code, es_infraestructura)`.

    `GEMINI_OVERLOADED` es infraestructura, con un matiz medido: el mismo
    texto cubre "el servicio está saturado" (se destraba solo, reintentar
    sirve) y "esta entrega quedó atascada" (nunca se destraba, reintentar es
    reintentar el error). Acá no se pueden distinguir — la señal que las
    separa es si la entrega vino retomada por un 409 Y figura en ERROR — así
    que se marca como infraestructura y la UI dice que reintentar PUEDE servir,
    no que va a servir.
    """
    code = (error_code or "").upper()
    infra = {
        "GEMINI_OVERLOADED",
        "NBN_TIMEOUT",
        "TIMEOUT",
        "SANDBOX_TIMEOUT",
        "SANDBOX_UNREACHABLE",
        "SANDBOX_ERROR",
        "SANDBOX_QUOTA",
        "SANDBOX_DISABLED",
        # Los seis de abajo faltaban, y el efecto no era cosmético: este flag es
        # lo ÚNICO que decide si la UI muestra el botón "Reintentar". Con
        # `es_infraestructura=False` el panel pinta rojo, dice "reintentar sin
        # cambiar nada va a devolver el mismo error" y NO renderiza el botón.
        #
        # El caso que lo delata: `PROCESO_INTERRUMPIDO` lo escribe el
        # reconciliador con el detalle "probablemente por un reinicio del
        # servicio… podés volver a dispararla" — y la pantalla le escondía el
        # botón para hacer exactamente eso.
        #
        # `marcar_error(es_infraestructura=...)` NO persiste: sólo loguea. La UI
        # re-deriva el flag de acá, así que este set es la única fuente de
        # verdad y tiene que cubrir todo lo que el flujo emite.
        "PROCESO_INTERRUMPIDO",
        "ERROR_INTERNO",
        "SIN_NOTA",
        "SIN_ENTREGA_ID",
        "CONFLICTO_SIN_SALIDA",
        "ACTIVEIA_ERROR",
    }
    # Todo 5xx de Active-IA es infraestructura: el servicio no pudo responder.
    # Se resuelve por prefijo y no enumerando, porque `_subir_y_corregir` arma
    # el código con el status crudo (`HTTP_502`, `HTTP_504`…) y una lista se
    # queda corta con el primer código que el proxy invente.
    if code.startswith("HTTP_5"):
        return code, True
    if code in infra:
        return code, True
    if not code:
        # Sin código, un mensaje de red o timeout sigue siendo infraestructura.
        bajo = mensaje.lower()
        if any(p in bajo for p in ("timeout", "no respondió", "no se pudo contactar")):
            return "TIMEOUT", True
        return "ACTIVEIA_ERROR", False
    return code, False
