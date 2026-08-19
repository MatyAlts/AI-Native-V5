"""El trabajo real de una corrección: sandbox → Active-IA → resultado.

Corre en `BackgroundTasks` con su **propia sesión corta** (no la del request,
que se cierra cuando el 202 ya salió) y bajo el semáforo del worker.

El orden de los pasos es el que evita gastar de más:

1. Se re-ejecutan los tests en el sandbox. **Que no compile ya no corta**
   (19/08): un punto y coma que falta no justifica dejar al alumno sin
   devolución. Lo que sí viaja es el estado de compilación, explícito, para
   que el motor no cierre criterios de "funciona" que ninguna corrida respalda.
2. Se sube el artefacto a Active-IA. Un **409** significa que ya estaba
   arriba: se retoma esa, no se sube de nuevo (subirla otra vez la cobra otra
   vez).
3. Se dispara la corrección y se poletea hasta `CORREGIDA` o `ERROR`.

Y la regla que atraviesa todo: **un fallo de infraestructura nunca es una
nota.** El timeout del motor se reporta como error para reintentar, jamás como
un número.
"""

from __future__ import annotations

import asyncio
import io
import time
import zipfile
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from evaluation_service.db.session import tenant_session
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.services import correccion_metrics as metrics
from evaluation_service.services.activeia_client import ActiveIAError
from evaluation_service.services.correccion_ia import mapear_error_activeia, marcar_error
from evaluation_service.services.correccion_pdf import bajar_y_guardar
from evaluation_service.services.correccion_pre_ejecucion import (
    PreEjecucionError,
    correr_tests,
)

log = structlog.get_logger()

_POLL_INTERVAL_S = 5.0
# Menos que el presupuesto total, para que el poll corte SOLO y la fila se
# pueda cerrar con su motivo, en vez de morir cancelado desde afuera.
_POLL_PRESUPUESTO_S = 150.0


_NOMBRE_POR_LENGUAJE = {"java": "Main.java", "python": "main.py"}


def _zip_del_codigo(codigo: str, language: str) -> bytes:
    """Active-IA recibe un zip, no un archivo suelto.

    El nombre importa: `Main.java` es lo que el compilador espera (una clase
    pública tiene que vivir en un archivo con su nombre), y es el mismo que
    usa el sandbox.

    Un lenguaje desconocido **corta**. Antes caía al `else` y empaquetaba el
    código como `main.py`: del otro lado eso es un archivo Python con algo que
    no es Python, y el motor corrige un sinsentido en vez de fallar. La
    columna `language` es un `String(20)` libre, así que "desconocido" es
    alcanzable.
    """
    nombre = _NOMBRE_POR_LENGUAJE.get(language)
    if nombre is None:
        raise PreEjecucionError(
            f"No sé cómo empaquetar código en '{language}' para Active-IA.",
            error_code="LENGUAJE_DESCONOCIDO",
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"src/{nombre}", codigo)
    return buf.getvalue()


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
    activeia_comision_id: str,
    headers_sandbox: dict[str, str],
) -> None:
    """El trabajo completo. NUNCA levanta: todo fallo termina en la fila.

    Que no levante es deliberado — corre en background, así que una excepción
    que escape se pierde en un log y la corrección queda en `running` para
    siempre, girando en la pantalla del docente.
    """
    from evaluation_service.services.activeia_credenciales import cliente_para

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
            from evaluation_service.services.correccion_pre_ejecucion import ResultadoTests

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

        # ── 2 y 3. Active-IA ──────────────────────────────────────────────
        async with tenant_session(tenant_id) as db:
            cliente = await cliente_para(db, tenant_id, user_id)

        rubrica_id = await _rubrica_de(tenant_id, correccion_id)
        if not rubrica_id:
            # Sin rúbrica no hay contra qué corregir. Antes se subía igual con
            # `rubrica_id=""` y se pagaba la subida para que Active-IA la
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

        resultado = await _subir_y_corregir(
            cliente=cliente,
            codigo=codigo,
            language=language,
            alumno_nombre=alumno_nombre,
            comision_id=activeia_comision_id,
            rubrica_id=rubrica_id,
            tests=tests.as_dict(),
        )

        entrega_id = await _cerrar_con_resultado(
            tenant_id, correccion_id, resultado, tests.as_dict()
        )
        if entrega_id is None:
            return

        await _guardar_pdf(
            cliente=cliente,
            tenant_id=tenant_id,
            entrega_id=entrega_id,
            correccion_id=correccion_id,
            external_correccion_id=resultado.get("external_correccion_id"),
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
    except ActiveIAError as e:
        code, infra = mapear_error_activeia(None, e.mensaje)
        await _cerrar_con_error(
            tenant_id, correccion_id, code, e.mensaje, infra or e.es_infraestructura
        )
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
        c.desglose = resultado.get("desglose") or []
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


async def _subir_y_corregir(
    *,
    cliente: Any,
    codigo: str,
    language: str,
    alumno_nombre: str,
    comision_id: str,
    rubrica_id: str,
    tests: dict[str, Any],
) -> dict[str, Any]:
    """Sube, dispara y poletea. Devuelve la nota o el motivo de que no haya."""
    data = _zip_del_codigo(codigo, language)
    files = {"archivo": (f"entrega_{rubrica_id}.zip", data, "application/zip")}
    form = {
        "alumno_nombre": alumno_nombre,
        "comision_id": comision_id,
        "rubrica_id": rubrica_id,
        # El resultado de los tests YA ejecutados. El motor cuenta presencia,
        # no vínculo: un criterio del tipo "funciona" necesita un hecho detrás.
        "tests_resultado": str(tests.get("passed", 0)) + "/" + str(tests.get("total", 0)),
        # Si compiló o no, EXPLÍCITO. Desde el 19/08 el código que no compila
        # se manda igual —un punto y coma que falta no justifica dejar al
        # alumno sin devolución— pero el motor tiene que saberlo: con
        # `tests_resultado: "0/6"` a secas no puede distinguir "no compiló" de
        # "compiló y falló todo", y son dos devoluciones distintas.
        "compila": "true" if tests.get("compila", True) else "false",
        # Vacío cuando compiló. Recortado: es un mensaje de compilador, y el
        # form no es el lugar para volcar un stack entero.
        "error_compilacion": (tests.get("error_compilacion") or "")[:1000],
    }

    resp = await cliente.request("POST", "/entregas/", data=form, files=files)

    if resp.status_code == 409:
        # Ya estaba arriba (tarea 3.15). Se RETOMA en vez de volver a subirla:
        # subirla de nuevo la cobra de nuevo. El 409 keyea por
        # `(comision_id, rubrica_id, alumno_nombre)` — el `rubrica_id` en el
        # match no es opcional: sin él se retomaba la entrega de OTRO TP del
        # mismo alumno y se adjuntaba la devolución de otra unidad.
        entrega_id = await _ubicar_entrega(cliente, comision_id, rubrica_id, alumno_nombre)
        if entrega_id is None:
            return {
                "error_code": "CONFLICTO_SIN_SALIDA",
                "error_detail": (
                    "Active-IA dice que la entrega ya existe pero no se pudo ubicar. "
                    "Revisala en el panel de Active-IA."
                ),
            }
    elif resp.status_code not in (200, 201):
        return {
            "error_code": f"HTTP_{resp.status_code}",
            "error_detail": f"Active-IA respondió {resp.status_code} al subir la entrega.",
        }
    else:
        entrega_id = str(resp.json().get("id") or "")

    if not entrega_id:
        return {"error_code": "SIN_ENTREGA_ID", "error_detail": "Active-IA no devolvió el id."}

    disp = await cliente.request("POST", f"/correcciones/entregas/{entrega_id}/corregir")
    if disp.status_code >= 500:
        return {
            "external_entrega_id": entrega_id,
            "error_code": "GEMINI_OVERLOADED",
            "error_detail": "El motor no pudo arrancar la corrección.",
        }
    if disp.status_code >= 400:
        # Un 4xx es un RECHAZO: la corrección no arrancó y no va a arrancar.
        # Antes sólo se cortaba con >=500, así que un rechazo se poleteaba
        # igual hasta quemar el presupuesto entero y recién ahí colgarse.
        return {
            "external_entrega_id": entrega_id,
            "error_code": f"HTTP_{disp.status_code}",
            "error_detail": (
                f"Active-IA rechazó el disparo de la corrección ({disp.status_code}). "
                "Reintentar sin cambiar nada va a devolver lo mismo."
            ),
        }

    return {"external_entrega_id": entrega_id, **(await _poletear(cliente, entrega_id))}


async def _poletear(cliente: Any, entrega_id: str) -> dict[str, Any]:
    """`GET /correcciones/entregas/{id}`: 200 = corregida, 404 = todavía no.

    NO se usa `GET /entregas/{id}`, que está roto del lado del server (500).

    **Tope propio**, además del presupuesto de afuera. Un `while True` que
    sólo corta por cancelación externa depende de que el envoltorio esté
    puesto: si alguien llama a este flujo sin él, gira para siempre. Y salir
    por cancelación es peor que salir por decisión propia — la primera no
    puede cerrar la fila, la segunda sí.
    """
    restante = _POLL_PRESUPUESTO_S
    while restante > 0:
        await asyncio.sleep(_POLL_INTERVAL_S)
        restante -= _POLL_INTERVAL_S
        r = await cliente.request("GET", f"/correcciones/entregas/{entrega_id}")
        if r.status_code == 404:
            continue
        if r.status_code != 200:
            # Cualquier otro status corta. Seguir leyendo el cuerpo de una
            # respuesta que no es 200 y sacarle una nota de ahí sería tomar
            # por buena una respuesta que el servicio no dio por buena.
            return {
                "error_code": f"HTTP_{r.status_code}",
                "error_detail": "Active-IA respondió mal al consultar la corrección.",
            }
        cuerpo = r.json()
        nota = cuerpo.get("nota") or cuerpo.get("nota_final") or cuerpo.get("calificacion")
        if nota is None:
            return {
                "error_code": cuerpo.get("error_code") or "SIN_NOTA",
                "error_detail": cuerpo.get("error_mensaje") or "La corrección terminó sin nota.",
            }
        return {
            "nota_100": nota,
            "desglose": cuerpo.get("desglose") or cuerpo.get("criterios") or [],
            "external_correccion_id": str(cuerpo.get("correccion_id") or cuerpo.get("id") or ""),
        }

    return {
        "error_code": "TIMEOUT",
        "error_detail": (
            "Active-IA no terminó la corrección a tiempo. La entrega quedó subida allá, "
            "así que reintentar retoma ese trabajo en vez de duplicarlo."
        ),
    }


async def _ubicar_entrega(
    cliente: Any, comision_id: str, rubrica_id: str, alumno_nombre: str
) -> str | None:
    """Busca la entrega que ya está arriba, para retomarla.

    Compara `rubrica_id` **y** nombre. Sin la rúbrica alcanzaba el nombre, y se
    retomaba la entrega de otro TP del mismo alumno: el tutor le adjuntaba la
    devolución de otra unidad. Se compara como texto porque la API no
    garantiza el tipo (12 vs "12").
    """
    r = await cliente.request(
        "GET", "/entregas/", params={"comision_id": comision_id, "per_page": 100}
    )
    if r.status_code != 200:
        return None
    objetivo = alumno_nombre.strip().lower()
    for item in r.json().get("items", []):
        if str(item.get("rubrica_id")) != str(rubrica_id):
            continue
        if str(item.get("alumno_nombre", "")).strip().lower() == objetivo:
            return str(item.get("id"))
    return None
