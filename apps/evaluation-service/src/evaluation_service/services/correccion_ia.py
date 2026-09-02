"""Orquestación de una corrección asistida por ejercicio (Epic 3).

El orden de los pasos NO es arbitrario, y cada uno está antes que el
siguiente por una razón:

1. **Gates** (comisión, artefacto, LEGACY, rúbrica sincronizada). Son gratis y
   cortan sin gastar nada.
2. **Idempotencia.** Si esta misma corrección ya existe, se devuelve. Un doble
   click no paga dos veces.
3. **Cuota.** Falla cerrada. Va antes de ejecutar porque ejecutar ya cuesta.
4. **Pre-ejecución en el sandbox.** Que no compile NO corta (19/08): se manda
   igual, con el estado de compilación explícito. El error de
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


@dataclass(frozen=True)
class RubricaElegida:
    """Contra qué rúbrica va a corregir ESTE disparo, según el motor activo.

    Existe para que la ruta no tenga un `if motor` adentro. La ruta pregunta
    "¿con qué rúbrica?" y recibe siempre la misma forma; qué significa cada
    campo depende del motor, y eso vive acá.
    """

    rubrica_id: str
    # El `external_ref` del ejercicio del otro lado. Vacío en el camino propio:
    # no hay otro lado.
    external_ref: str
    estado: str
    simulada: bool


async def resolver_rubrica_del_motor(
    db: AsyncSession, tenant_id: UUID, ejercicio_id: UUID | None
) -> RubricaElegida:
    """La rúbrica del motor activo, o un rechazo que dice qué falta.

    **El camino propio no consulta el vínculo con Active-IA.** No es un atajo:
    es la corrección del problema que el propio panel del docente advierte —los
    criterios de Active-IA van SOLOS, no cruzados con la rúbrica local— y que
    dejó registrado el caso de una rúbrica con una reducción del 30 % contra la
    que el motor devolvió la suma limpia, 87 donde correspondía ~61.

    Acá el `rubrica_id` es el hash de la rúbrica que el docente escribió y ve.
    """
    from evaluation_service.config import settings
    from evaluation_service.services import correccion_nativa

    if settings.correccion_motor != correccion_nativa.MOTOR:
        vinculo = await resolver_rubrica(db, tenant_id, ejercicio_id)
        return RubricaElegida(
            rubrica_id=vinculo.rubrica_id,
            external_ref=str(vinculo.external_ref or ""),
            estado="",
            simulada=vinculo.rubrica_id.startswith("MOCK-"),
        )

    if ejercicio_id is None:
        raise CorreccionRechazadaError(
            "Este trabajo práctico no tiene ejercicios del banco, así que no hay "
            "rúbrica contra la cual corregir."
        )

    ejercicio = await correccion_nativa.leer_ejercicio(db, ejercicio_id)
    if ejercicio is None:
        raise CorreccionRechazadaError("El ejercicio de esta entrega ya no existe.")
    try:
        # Se valida ACÁ y no sólo al corregir: rechazar antes de disparar no
        # consume cuota, y el docente se entera de que falta la rúbrica cuando
        # todavía puede cargarla, no después de que la corrección falló.
        correccion_nativa.leer_rubrica(ejercicio.rubrica)
    except correccion_nativa.RubricaInvalidaError as e:
        raise CorreccionRechazadaError(str(e)) from e

    return RubricaElegida(
        rubrica_id=correccion_nativa.rubrica_id_nativa(ejercicio.rubrica),
        external_ref="",
        # No hay sincronización que reportar: la rúbrica es local. Decir
        # "sin_sincronizar" leería como un fallo de algo que no aplica.
        estado="local",
        simulada=False,
    )


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
        "ACTIVEIA_ERROR",
        # ── Del corrector propio ───────────────────────────────────────────
        #
        # Los tres son reintentables, cada uno por su motivo:
        #
        # - `GATEWAY_ERROR`: el ai-gateway no respondio, o el proveedor esta
        #   caido / sin cupo. Se destraba solo o lo destraba un humano; en los
        #   dos casos el mismo boton sirve despues.
        # - `SIN_PROMPT`: el governance-service no esta arriba. Es infra pura.
        # - `MODELO_NO_RESPETO_RUBRICA`: el modelo devolvio un desglose que no
        #   empareja con la rubrica. Reintentar PUEDE servir —la temperatura es
        #   0 pero el proveedor no garantiza identidad— y lo que NO se hace es
        #   completar el criterio faltante con un cero. Ver `correccion_nativa`.
        "GATEWAY_ERROR",
        "SIN_PROMPT",
        "MODELO_NO_RESPETO_RUBRICA",
        # ── Códigos que el flujo YA NO EMITE (2026-08-27) ──────────────────
        #
        # Salían del camino de tres pasos: `SIN_ENTREGA_ID` de un 201 sin id y
        # `CONFLICTO_SIN_SALIDA` de un 409 que no se podía ubicar. El endpoint
        # nuevo no tiene ninguna de las dos cosas.
        #
        # **Se quedan igual, y no es descuido.** La UI re-deriva
        # `es_infraestructura` de este set cada vez que pinta una fila, también
        # las viejas. Sacarlos volvería "rechazo" a correcciones históricas que
        # se cerraron como infraestructura, y el docente vería cambiar de color
        # algo que ya había leído. Un set de clasificación es sobre lo que hay
        # guardado, no sólo sobre lo que se escribe hoy.
        "SIN_ENTREGA_ID",
        "CONFLICTO_SIN_SALIDA",
        # ── Deliberadamente FUERA del set (2026-08-27) ────────────────────
        #
        # `ACTIVEIA_RECHAZO` y `SIN_CREDENCIAL` son rechazos, no fallos de
        # infraestructura, y por eso no figuran acá.
        #
        # Existen porque `ACTIVEIA_ERROR` estaba en los DOS lados: adentro de
        # este set, y a la vez era lo que devolvía la rama sin código con
        # `False`. Como el flag NO se persiste y la UI lo re-deriva del código
        # guardado, ese `False` era inalcanzable: un docente que cambió su
        # contraseña en Active-IA veía ámbar y "reintentar puede servir" sobre
        # algo que sólo se arregla reconectando la cuenta.
        #
        # `ACTIVEIA_ERROR` se queda adentro por las filas históricas: sacarlo
        # volvería "rechazo" correcciones viejas que se cerraron como
        # infraestructura, y el docente vería cambiar de color algo que ya leyó.
    }
    # Todo 5xx de Active-IA es infraestructura: el servicio no pudo responder.
    # Se resuelve por prefijo y no enumerando, porque `_corregir_ejercicio` arma
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
