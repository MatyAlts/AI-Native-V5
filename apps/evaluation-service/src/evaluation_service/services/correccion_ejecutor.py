"""El trabajo real de una corrección: sandbox → Active-IA → resultado.

Corre en `BackgroundTasks` con su **propia sesión corta** (no la del request,
que se cierra cuando el 202 ya salió) y bajo el semáforo del worker.

Son dos pasos:

1. Se re-ejecutan los tests en el sandbox. **Que no compile ya no corta**
   (19/08): un punto y coma que falta no justifica dejar al alumno sin
   devolución. Lo que sí viaja es el estado de compilación, explícito, para
   que el motor no cierre criterios de "funciona" que ninguna corrida respalda.
2. Se pide la corrección del ejercicio en **una sola llamada sincrónica**, con
   el código y el resultado de los tests adentro.

**Eran tres hasta el 2026-08-27**, y el del medio era subir un zip. El equipo
de Active-IA construyó el endpoint del §3.4 que les pedimos —confirmado en su
documento del 24/08— y con él desaparecen tres cosas que este archivo manejaba:
el zip, el 409 de entrega duplicada, y el polling de hasta 150s. No es que
dejaran de pasar: **dejaron de existir**. Reintentar ahora es repetir la misma
llamada, y ellos archivan la corrección anterior en su historial (§4.2).

Y la regla que atraviesa todo y NO cambió: **un fallo de infraestructura nunca
es una nota.** El timeout del motor se reporta como error para reintentar,
jamás como un número.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import structlog

from evaluation_service.config import settings
from evaluation_service.db.session import tenant_session
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.services import correccion_metrics as metrics
from evaluation_service.services import correccion_nativa
from evaluation_service.services.activeia_client import ActiveIAError
from evaluation_service.services.correccion_ia import mapear_error_activeia, marcar_error
from evaluation_service.services.correccion_pdf import bajar_y_guardar
from evaluation_service.services.correccion_pre_ejecucion import (
    PreEjecucionError,
    ResultadoTests,
    correr_tests,
)

log = structlog.get_logger()


def _resultado_tests_para_activeia(tests: dict[str, Any]) -> dict[str, Any]:
    """Traduce nuestro `ResultadoTests.as_dict()` al contrato del §3.4.

    La única diferencia real es el nombre: nosotros contamos `passed`, el
    contrato que acordamos dice `pasados`. Se remapea acá y no se renombra el
    dataclass porque `as_dict()` también es lo que se persiste en
    `tests_snapshot`, y cambiarle las claves rompería la lectura de las
    correcciones viejas.

    `failed` no viaja: es `total - pasados` y mandar un tercer número que puede
    contradecir a los otros dos es darle al motor la chance de creerle al
    equivocado.
    """
    return {
        "compila": bool(tests.get("compila", True)),
        "error_compilacion": tests.get("error_compilacion") or None,
        "total": int(tests.get("total", 0) or 0),
        "pasados": int(tests.get("passed", 0) or 0),
        "casos": tests.get("casos") or [],
    }


async def ejecutar_correccion(
    *,
    correccion_id: UUID,
    tenant_id: UUID,
    user_id: UUID,
    comision_id: UUID,
    ejercicio_id: UUID | None,
    codigo: str,
    language: str,
    alumno_nombre: str,
    ejercicio_ref: str,
    headers_sandbox: dict[str, str],
) -> None:
    """El trabajo completo. NUNCA levanta: todo fallo termina en la fila.

    Que no levante es deliberado — corre en background, así que una excepción
    que escape se pierde en un log y la corrección queda en `running` para
    siempre, girando en la pantalla del docente.

    `ejercicio_ref` es el `external_ref` con el que ESTE ejercicio quedó
    sincronizado del otro lado, y es lo que identifica la rúbrica contra la
    cual se corrige. Se lee del vínculo y no se re-deriva de `ejercicio_id`:
    aunque hoy sean el mismo UUID, el que vale es el que Active-IA vio en el
    último sync — re-derivarlo sería adivinar qué conoce el otro lado.

    Hasta el 2026-08-27 este parámetro se llamaba `activeia_comision_id` y
    viajaba en el campo `comision_id` del formulario. **El nombre mentía**: lo
    que se le pasaba era ya `vinculo.external_ref`, o sea el id del ejercicio,
    así que Active-IA recibía un id de ejercicio donde esperaba una comisión.
    Es el «comision_id mal cableado» que ellos nos marcaron. El endpoint nuevo
    lo cierra por construcción: el ejercicio va en la URL, que es su lugar, y
    de comisión se encarga la comisión de integración de ellos (§3.3).
    """
    from evaluation_service.services.activeia_credenciales import CredencialNoConfiguradaError

    async with tenant_session(tenant_id) as db:
        c = await db.get(CorreccionIA, correccion_id)
        if c is None:
            log.error("activeia_correccion_desaparecida", correccion_id=str(correccion_id))
            return
        es_reintento = c.started_at is not None
        c.estado = "running"
        c.started_at = datetime.now(UTC)

    arranque = time.monotonic()
    metrics.record_disparada(es_reintento=es_reintento)
    log.info(
        "correccion_ia_disparada",
        correccion_id=str(correccion_id),
        comision_id=str(comision_id),
        ejercicio_id=str(ejercicio_id) if ejercicio_id else None,
        language=language,
        reintento=es_reintento,
    )

    try:
        # ── 1. Tests en el sandbox ────────────────────────────────────────
        if ejercicio_id is not None:
            tests = await correr_tests(
                ejercicio_id=ejercicio_id,
                codigo=codigo,
                comision_id=comision_id,
                headers=headers_sandbox,
            )
        else:
            # TP monolítica: no hay ejercicio del banco contra el cual correr
            # test cases. Se sigue sin ellos, y el snapshot lo dice.
            tests = ResultadoTests(compila=True)

        # Que no compile YA NO CORTA (decisión de Juani, 19/08). Un punto y coma
        # que falta no es motivo para dejar al alumno sin devolución: el motor
        # igual puede decirle si el diseño va encaminado, y esa es la parte que
        # un compilador no le da.
        #
        # Lo que sí cambia es que el estado del código **viaja explícito**: sin
        # eso, el motor recibiría un archivo roto sin saberlo y podría cerrar
        # criterios de "funciona" que ninguna corrida respalda. Con `compila:
        # false` y el error adentro, la decisión de cuánto pesar eso queda del
        # lado que corrige, que es donde vive la rúbrica.
        #
        # Los tests que fallan nunca cortaron: eso ya se mandaba con su
        # `passed/total`.
        if not tests.compila:
            log.info(
                "correccion_ia_sin_compilar",
                correccion_id=str(correccion_id),
                detalle=(tests.error_compilacion or "")[:300],
            )

        # ── 2. La corrección ──────────────────────────────────────────────
        #
        # ACÁ se elige el motor, y es el ÚNICO lugar donde se elige. Los pasos
        # 1 a 4 —las cuotas que fallan cerradas, la idempotencia, el sandbox, la
        # regla de que un fallo de infraestructura no es una nota— son comunes a
        # los dos: duplicarlos es garantizar que dentro de seis meses uno tenga
        # un arreglo que el otro no.
        #
        # El default es `activeia`. Prender el motor nuevo por omisión cambiaría
        # notas de alumnos sin que nadie lo decida.
        if settings.correccion_motor == correccion_nativa.MOTOR:
            resultado = await _corregir_nativo(
                tenant_id=tenant_id,
                ejercicio_id=ejercicio_id,
                codigo=codigo,
                tests=tests.as_dict(),
            )
            await _cerrar_con_resultado(tenant_id, correccion_id, resultado, tests.as_dict())
            # No hay PDF que bajar: el de devolución lo genera Active-IA.
            return

        await _correr_activeia(
            tenant_id=tenant_id,
            user_id=user_id,
            correccion_id=correccion_id,
            ejercicio_ref=ejercicio_ref,
            alumno_nombre=alumno_nombre,
            codigo=codigo,
            tests=tests,
        )

    except asyncio.CancelledError:
        # Se acabó el presupuesto. NO se cierra la fila acá: estamos siendo
        # cancelados, así que cualquier `await` volvería a levantar antes de
        # llegar a la base. La cierra `con_semaforo_y_presupuesto`, que corre
        # en el task de afuera y sigue vivo.
        #
        # Se re-lanza: `CancelledError` es lo único que nunca hay que tragarse.
        # Y NO la agarraba el `except Exception` de abajo, porque hereda de
        # `BaseException` — por eso la corrección quedaba `running` para
        # siempre, girando en la pantalla del docente.
        raise
    except PreEjecucionError as e:
        await _cerrar_con_error(tenant_id, correccion_id, e.error_code, e.mensaje, True)
    except (CredencialNoConfiguradaError, ActiveIAError) as e:
        code, detalle, es_infra = _clasificar_fallo(e)
        await _cerrar_con_error(tenant_id, correccion_id, code, detalle, es_infra)
    except Exception as e:
        log.exception("activeia_correccion_excepcion", correccion_id=str(correccion_id))
        await _cerrar_con_error(
            tenant_id, correccion_id, "ERROR_INTERNO", f"{type(e).__name__}", True
        )
    finally:
        # En `finally` y no al final del `try`: el cuerpo tiene returns
        # tempranos (SIN_RUBRICA, por ejemplo) y los except cierran por su
        # cuenta. Si esto viviera en el camino feliz, `in_flight` subiría para
        # siempre en cuanto algo fallara — y el indicador de saturación
        # mentiría justo cuando hace falta leerlo.
        await _registrar_desenlace(tenant_id, correccion_id, time.monotonic() - arranque)


async def _correr_activeia(
    *,
    tenant_id: UUID,
    user_id: UUID,
    correccion_id: UUID,
    ejercicio_ref: str,
    alumno_nombre: str,
    codigo: str,
    tests: ResultadoTests,
) -> None:
    """El camino de Active-IA, entero. NO CAMBIÓ: se movió.

    Se extrajo del cuerpo de `ejecutar_correccion` cuando entró el segundo
    motor, para que los dos queden simétricos y la elección se lea en una sola
    línea. Levanta lo mismo que levantaba adentro (`ActiveIAError`,
    `CredencialNoConfiguradaError`) y lo agarra el mismo `except` de allá.
    """
    from evaluation_service.services.activeia_credenciales import cliente_para

    async with tenant_session(tenant_id) as db:
        cliente = await cliente_para(db, tenant_id, user_id)

    rubrica_id = await _rubrica_de(tenant_id, correccion_id)
    if not rubrica_id:
        # Sin rúbrica no hay contra qué corregir. Antes se enviaba igual
        # con `rubrica_id=""` y se pagaba la llamada para que Active-IA la
        # rechazara después.
        await _cerrar_con_error(
            tenant_id,
            correccion_id,
            "SIN_RUBRICA",
            "La corrección no tiene rúbrica asociada. No se envió nada.",
            False,
            tests.as_dict(),
        )
        return

    if not ejercicio_ref:
        # El endpoint nuevo corrige POR EJERCICIO: sin referencia no hay a
        # qué apuntar. Antes esto no se notaba porque el ejercicio no
        # viajaba en la URL sino como un campo más del formulario, así que
        # un ref vacío se mandaba igual y el rechazo venía de allá.
        #
        # NO es infraestructura: reintentar sin sincronizar el TP devuelve
        # exactamente lo mismo.
        await _cerrar_con_error(
            tenant_id,
            correccion_id,
            "SIN_EJERCICIO_REF",
            (
                "Este ejercicio no tiene referencia sincronizada con Active-IA. "
                "Sincronizá el trabajo práctico y volvé a disparar."
            ),
            False,
            tests.as_dict(),
        )
        return

    resultado = await _corregir_ejercicio(
        cliente=cliente,
        ejercicio_ref=ejercicio_ref,
        alumno_nombre=alumno_nombre,
        codigo=codigo,
        tests=tests.as_dict(),
    )

    entrega_id = await _cerrar_con_resultado(tenant_id, correccion_id, resultado, tests.as_dict())
    if entrega_id is None:
        return

    await _guardar_pdf(
        cliente=cliente,
        tenant_id=tenant_id,
        entrega_id=entrega_id,
        correccion_id=correccion_id,
        external_correccion_id=resultado.get("external_correccion_id"),
    )


async def _corregir_nativo(
    *,
    tenant_id: UUID,
    ejercicio_id: UUID | None,
    codigo: str,
    tests: dict[str, Any],
) -> dict[str, Any]:
    """El camino propio: la rúbrica del docente y la suma de este lado.

    Devuelve la MISMA forma que `_corregir_ejercicio`, así que `_cerrar_con_resultado`
    no se entera de qué motor corrigió. Esa simetría es lo que hace que el panel
    del docente, el PDF y el CHECK de la base sigan valiendo para los dos.

    Sin `ejercicio_id` no hay corrección: la rúbrica vive DENTRO del ejercicio.
    Es el caso de la TP monolítica, y es un rechazo —no infraestructura—: sin
    ejercicios cargados, reintentar devuelve lo mismo.
    """
    if ejercicio_id is None:
        return {
            "error_code": "SIN_EJERCICIO",
            "error_detail": (
                "Este trabajo práctico no tiene ejercicios del banco, así que no hay "
                "rúbrica contra la cual corregir. Cargá los ejercicios y volvé a disparar."
            ),
        }

    async with tenant_session(tenant_id) as db:
        ejercicio = await correccion_nativa.leer_ejercicio(db, ejercicio_id)

    if ejercicio is None:
        return {
            "error_code": "SIN_EJERCICIO",
            "error_detail": f"El ejercicio {ejercicio_id} ya no existe.",
        }

    return await correccion_nativa.corregir_con_ia_nativa(
        tenant_id=tenant_id,
        ejercicio=ejercicio,
        codigo=codigo,
        tests=tests,
    )


def _clasificar_fallo(e: Exception) -> tuple[str, str, bool]:
    """Traduce un fallo del circuito a `(error_code, detalle, es_infraestructura)`.

    Vive acá y no inline en el `except` porque la clasificación es lo ÚNICO que
    decide si la UI le muestra al docente el botón "Reintentar", y esa decisión
    merece un lugar con nombre.

    Dos casos que antes se pintaban mal, los dos como infraestructura:

    - **El docente nunca conectó su cuenta.** `CredencialNoConfiguradaError`
      caía al `except Exception` genérico y se cerraba como `ERROR_INTERNO`, que
      está en el set de infra. O sea que la pantalla le ofrecía "Reintentar" a
      alguien cuyo único paso posible era ir a conectar su cuenta.

    - **La contraseña de Active-IA cambió.** `mapear_error_activeia` devuelve
      `("ACTIVEIA_ERROR", False)` para un rechazo sin código, pero
      `ACTIVEIA_ERROR` está DENTRO del set de infra por las filas históricas —
      y como el flag no se persiste, la UI lo re-deriva del código guardado y
      vuelve a decir "reintentar puede servir". El `False` era inalcanzable.

    Los rechazos nuevos usan códigos propios (`SIN_CREDENCIAL`,
    `ACTIVEIA_RECHAZO`) que no están en el set, así que la re-derivación da lo
    mismo que la clasificación original.
    """
    from evaluation_service.services.activeia_credenciales import CredencialNoConfiguradaError

    if isinstance(e, CredencialNoConfiguradaError):
        return "SIN_CREDENCIAL", str(e), False

    assert isinstance(e, ActiveIAError)
    code, infra = mapear_error_activeia(None, e.mensaje)
    es_infra = infra or e.es_infraestructura
    if not es_infra and code == "ACTIVEIA_ERROR":
        code = "ACTIVEIA_RECHAZO"
    return code, e.mensaje, es_infra


async def _registrar_desenlace(tenant_id: UUID, correccion_id: UUID, duracion_s: float) -> None:
    """Métricas y rastro de cierre (tareas 6.2 y 6.3).

    El desenlace se lee de la FILA y no de una variable de la función: la fila
    es la que gobierna —tiene el CHECK que impide una nota sin `done`— y hay
    caminos que la cierran desde adentro (`marcar_error` en `_cerrar_con_resultado`)
    sin volver acá con un valor. Una variable local se desincronizaría del
    estado real justo en los caminos de error, que son los que se miden.

    Nunca levanta: una métrica rota no puede tumbar una corrección que ya
    terminó, ni dejarla `running` para siempre.
    """
    try:
        async with tenant_session(tenant_id) as db:
            c = await db.get(CorreccionIA, correccion_id)
            if c is None:
                metrics.record_completada(outcome="desaparecida", duration_seconds=duracion_s)
                return
            estado, code = c.estado, c.error_code

        if estado == "done":
            outcome = "con_nota"
        elif estado == "running":
            # Llegar acá todavía en `running` significa **cancelación**: este
            # bloque corre en el `finally` del ejecutor, y el único camino que
            # lo alcanza sin haber cerrado la fila es el `wait_for` del
            # envoltorio de presupuesto. El `TIMEOUT` lo escribe él, DESPUÉS —
            # así que leer la fila acá devuelve `error_code=None`.
            #
            # Sin este branch, `mapear_error_activeia(None, "")` devuelve
            # `("ACTIVEIA_ERROR", False)` y el timeout —el fallo de infra más
            # probable que hay— se contaba como rechazo. O sea que durante un
            # incidente de Active-IA el panel mostraba **cero** `infra_failure`
            # y un pico de rechazos: exactamente la lectura opuesta a la que
            # este módulo existe para permitir.
            outcome = "infra_failure"
            metrics.record_infra_failure(causa="TIMEOUT")
        else:
            # La clasificación infra/rechazo sale de `mapear_error_activeia`,
            # que es la misma que usa el endpoint para pintar la tarjeta ámbar
            # o roja. Una lista propia acá se desincronizaría de la de allá, y
            # entonces el panel y la UI dirían cosas distintas del mismo fallo.
            #
            # `es_infraestructura` NO es una columna: es un campo derivado del
            # schema de salida. Leerlo de la fila (con `getattr`, por ejemplo)
            # devuelve siempre `False` y parece que se consultó algo.
            causa, es_infra = mapear_error_activeia(code, "")
            if es_infra:
                outcome = "infra_failure"
                metrics.record_infra_failure(causa=causa)
            else:
                outcome = "rechazada"

        metrics.record_completada(outcome=outcome, duration_seconds=duracion_s)
        log.info(
            "correccion_ia_completada",
            correccion_id=str(correccion_id),
            outcome=outcome,
            error_code=code,
            duracion_s=round(duracion_s, 2),
        )
    except Exception:
        log.warning(
            "activeia_metrica_desenlace_fallo",
            correccion_id=str(correccion_id),
            exc_info=True,
        )


def _marcar_sin_ejecucion(
    desglose: list[dict[str, Any]],
    criterios_sin_ejecucion: list[Any],
    *,
    correccion_id: UUID,
) -> list[dict[str, Any]]:
    """Marca en el desglose los criterios que se cerraron sin poder verificarse.

    Active-IA devuelve esos criterios como una lista de identificadores aparte
    (§3.2 de su documento del 24/08). Se estampan **dentro** de cada criterio en
    vez de guardarse como lista paralela por una razón práctica: el panel del
    docente ya recorre `desglose`, y una lista de ids obligaría a cruzar dos
    estructuras para pintar una fila. El dato pertenece al criterio.

    La distinción que esto habilita no es cosmética. «El alumno no lo hizo» y
    «no se pudo verificar porque el código no compilaba» son dos cosas
    distintas, y sólo una de las dos es culpa del alumno. Mostrarlas iguales es
    exactamente el modo de falla que le reportamos al motor.

    Un id que no matchea con ningún criterio se **loguea**: perderlo en silencio
    dejaría al docente viendo un 0 sin explicación, que es peor que un warning.
    """
    if not criterios_sin_ejecucion:
        return list(desglose)

    pendientes = {str(x) for x in criterios_sin_ejecucion}
    marcados: list[dict[str, Any]] = []
    for criterio in desglose:
        if not isinstance(criterio, dict):
            marcados.append(criterio)
            continue
        # Se prueba contra los nombres posibles del identificador porque el
        # contrato no fija uno solo, y el `nombre` es lo único garantizado.
        claves = {str(criterio.get(k)) for k in ("id", "criterio_id", "nombre") if criterio.get(k)}
        golpe = claves & pendientes
        if golpe:
            pendientes -= golpe
            marcados.append({**criterio, "sin_ejecucion": True})
        else:
            marcados.append(criterio)

    if pendientes:
        log.warning(
            "activeia_criterio_sin_ejecucion_sin_match",
            correccion_id=str(correccion_id),
            ids=sorted(pendientes),
            detalle=(
                "Active-IA marcó criterios como no verificables pero no matchean "
                "ninguna entrada del desglose. El docente ve el 0 sin el motivo."
            ),
        )
    return marcados


async def _cerrar_con_resultado(
    tenant_id: UUID,
    correccion_id: UUID,
    resultado: dict[str, Any],
    tests: dict[str, Any],
) -> UUID | None:
    """Escribe el resultado. Devuelve el `entrega_id`, o `None` si no hay PDF
    que bajar (porque no hubo nota, o porque la fila desapareció).

    Sin nota no hay nota: el estado terminal es `error`, y el CHECK de la base
    lo hace cumplir aunque este código se equivoque.
    """
    async with tenant_session(tenant_id) as db:
        c = await db.get(CorreccionIA, correccion_id)
        if c is None:
            return None
        c.tests_snapshot = tests
        c.external_entrega_id = resultado.get("external_entrega_id")
        c.external_correccion_id = resultado.get("external_correccion_id")
        # Con qué se corrigió. Se escribe ANTES del branch de la nota, y a
        # propósito: si el modelo devolvió un desglose que no respeta la
        # rúbrica, saber con qué prompt y qué modelo pasó eso es justamente lo
        # que hace falta para arreglarlo. Vacío en el camino de Active-IA, que
        # no expone ninguna de las cuatro cosas.
        c.motor = resultado.get("motor")
        c.prompt_version = resultado.get("prompt_version")
        c.prompt_hash = resultado.get("prompt_hash")
        c.modelo = resultado.get("modelo")

        nota = resultado.get("nota_100")
        if nota is None:
            marcar_error(
                c,
                error_code=resultado.get("error_code") or "SIN_NOTA",
                detalle=resultado.get("error_detail") or "Active-IA no devolvió una nota.",
                es_infraestructura=True,
            )
            return None

        c.estado = "done"
        c.nota_100 = nota
        c.desglose = _marcar_sin_ejecucion(
            resultado.get("desglose") or [],
            resultado.get("criterios_sin_ejecucion") or [],
            correccion_id=correccion_id,
        )
        c.finished_at = datetime.now(UTC)
        # Se captura DENTRO de la sesión: leerlo afuera anda sólo porque el
        # factory tiene `expire_on_commit=False`, y apoyarse en eso es
        # apoyarse en una config que alguien puede cambiar.
        return c.entrega_id


async def _guardar_pdf(
    *,
    cliente: Any,
    tenant_id: UUID,
    entrega_id: UUID,
    correccion_id: UUID,
    external_correccion_id: Any,
) -> None:
    """Baja el PDF y guarda su key. Corre DESPUÉS de cerrar la corrección.

    En su propia sesión y después de que la nota está guardada: un fallo
    bajando el PDF no puede revertirla. El PDF es un extra, no el resultado.
    """
    if not external_correccion_id:
        return
    key = await bajar_y_guardar(
        cliente=cliente,
        tenant_id=tenant_id,
        entrega_id=entrega_id,
        correccion_id=correccion_id,
        external_correccion_id=str(external_correccion_id),
    )
    if not key:
        return
    async with tenant_session(tenant_id) as db:
        fila = await db.get(CorreccionIA, correccion_id)
        if fila is not None:
            fila.pdf_storage_key = key


async def _rubrica_de(tenant_id: UUID, correccion_id: UUID) -> str:
    async with tenant_session(tenant_id) as db:
        c = await db.get(CorreccionIA, correccion_id)
        return c.rubrica_id if c else ""


async def _cerrar_con_error(
    tenant_id: UUID,
    correccion_id: UUID,
    code: str,
    detalle: str,
    infra: bool,
    tests: dict[str, Any] | None = None,
) -> None:
    """Cierra la fila. Si esto falla, la corrección queda `running` y el
    reconciliador del lifespan la levanta en el próximo arranque."""
    try:
        async with tenant_session(tenant_id) as db:
            c = await db.get(CorreccionIA, correccion_id)
            if c is not None:
                # La evidencia de los tests se guarda IGUAL si la corrección
                # falló después de correrlos: se corrió, se pagó el cómputo, y
                # sirve para auditar por qué el resultado fue el que fue.
                if tests is not None:
                    c.tests_snapshot = tests
                marcar_error(c, error_code=code, detalle=detalle, es_infraestructura=infra)
    except Exception:
        log.exception("activeia_no_se_pudo_cerrar", correccion_id=str(correccion_id))


async def _corregir_ejercicio(
    *,
    cliente: Any,
    ejercicio_ref: str,
    alumno_nombre: str,
    codigo: str,
    tests: dict[str, Any],
) -> dict[str, Any]:
    """Una llamada, la nota vuelve en la respuesta.

    Reemplaza a `_subir_y_corregir` + `_poletear` + `_ubicar_entrega` (2026-08-27),
    que implementaban el camino de tres pasos con zip, 409 y polling. Ese camino
    no se rompió: el equipo de Active-IA construyó el endpoint del §3.4 que le
    pedimos y con él esos tres problemas dejan de existir.

    `alumno_nombre` es el **pseudónimo** del alumno, no su nombre: es lo que
    viaja como `alumno_ref` y es lo único que identifica a la persona del otro
    lado. Sigue llamándose así acá porque así se llama en toda la cadena de
    llamadas; renombrarlo es un cambio aparte.

    Los códigos de error se arman con el status crudo (`HTTP_502`) porque
    `mapear_error_activeia` resuelve la infraestructura por prefijo `HTTP_5`:
    una lista enumerada se queda corta con el primer código que invente un
    proxy, y ese flag es lo único que decide si la UI muestra "Reintentar".
    """
    status, cuerpo = await cliente.corregir_ejercicio(
        ejercicio_ref=ejercicio_ref,
        alumno_ref=alumno_nombre,
        codigo=codigo,
        resultado_tests=_resultado_tests_para_activeia(tests),
        # No se manda: su modelo usa una comisión de integración por materia
        # cuando el campo no viene (§3.3). Ver el docstring del cliente.
        comision_external_ref=None,
    )

    if status >= 500:
        return {
            "error_code": f"HTTP_{status}",
            "error_detail": "El motor de Active-IA no pudo corregir. Reintentar puede servir.",
        }
    if status >= 400:
        # Un 4xx es un RECHAZO: no arrancó y no va a arrancar. Se conserva el
        # detalle que manden, que en el 422 nombra el ejercicio y el caso.
        detalle = cuerpo.get("detail") or cuerpo.get("mensaje") or ""
        return {
            "error_code": f"HTTP_{status}",
            "error_detail": (
                f"Active-IA rechazó la corrección ({status}). "
                f"Reintentar sin cambiar nada va a devolver lo mismo. {detalle}".strip()
            ),
        }
    if status != 200:
        return {
            "error_code": f"HTTP_{status}",
            "error_detail": f"Active-IA respondió {status}, que no es un resultado.",
        }

    # Se aceptan los nombres viejos porque el contrato del §3.4 no fija el de la
    # nota y el flujo anterior ya leía estos tres. Lo que NO se hace es inventar
    # una: sin nota, el estado terminal es `error`.
    #
    # **Se busca por `is not None` y no con `or`.** La cadena `a or b or c`
    # trataba el CERO como ausente: un `{"nota": 0}` legítimo —el alumno que
    # entrega el template vacío, o el código que no compila— caía a `None` y la
    # corrección cerraba como `SIN_NOTA`, que está en el set de infraestructura.
    # La UI pintaba ámbar con "Reintentar", el docente reintentaba, y la misma
    # llamada devolvía el mismo cero: un bucle de reintentos que paga una corrida
    # de Gemini cada vez, sobre una corrección que en realidad termino bien.
    #
    # Es la regla de oro del epic aplicada al revés: una nota real convertida en
    # un fallo de infraestructura. Y cae justo en el camino que el propio PR
    # declara abierto — el nombre del campo de la nota en la respuesta de ellos.
    # El campo es `nota`, confirmado por ellos el 27/08: no existe `nota_100`,
    # ni `nota_final`, ni `calificacion`. La cascada que probaba los cuatro se
    # baja — funcionaba hasta el dia que devolviera el equivocado.
    #
    # **Y viaja como STRING**: `"85.50"`, con comillas. Es el default de
    # Pydantic v2 para `Decimal` y lo dejaron a proposito, porque una nota no
    # deberia pasar por un float en ningun tramo. Se castea EXPLICITO acá:
    # `float("85.50")` anda por accidente, y ese es el problema — un parser
    # asi funciona meses y revienta el dia que alguien agrega una comparacion
    # de tipos o un `if not nota`. Es el mismo mecanismo silencioso que hizo
    # que `salida_obtenida` se perdiera sin un solo error.
    nota_cruda = cuerpo.get("nota")
    nota: Decimal | None = None
    if nota_cruda is not None:
        try:
            nota = Decimal(str(nota_cruda))
        except (InvalidOperation, ValueError):
            # Una nota ilegible NO es una nota. Cae a `SIN_NOTA`, que es
            # infraestructura y reintentable, en vez de escribir basura en la
            # fila o dejar que el CHECK de la base explote despues.
            log.error(
                "activeia_nota_ilegible",
                nota_cruda=repr(nota_cruda)[:120],
                detalle="La respuesta trajo `nota` pero no se pudo interpretar como numero.",
            )
    if nota is None:
        return {
            "error_code": cuerpo.get("error_code") or "SIN_NOTA",
            "error_detail": cuerpo.get("error_mensaje") or "La corrección terminó sin nota.",
        }

    return {
        "nota_100": nota,
        "desglose": cuerpo.get("desglose") or cuerpo.get("criterios") or [],
        # Los criterios que cerraron en 0 porque el código no compilaba (§3.2).
        # Van aparte para que el docente lea "no se pudo verificar" y no "no lo
        # hizo": son dos cosas distintas y una de ellas no es culpa del alumno.
        "criterios_sin_ejecucion": cuerpo.get("criterios_sin_ejecucion") or [],
        "external_entrega_id": str(cuerpo.get("entrega_id") or "") or None,
        "external_correccion_id": str(cuerpo.get("correccion_id") or cuerpo.get("id") or ""),
    }
