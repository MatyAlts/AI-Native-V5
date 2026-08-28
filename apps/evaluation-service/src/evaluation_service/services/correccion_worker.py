"""El trabajo en background de una corrección (tareas 3.12, 3.13, 3.16).

**Sesión de DB corta.** El trabajo dura hasta 180s entre el sandbox y Gemini.
Sostener un `Depends(get_db)` todo ese tiempo agota el pool, que es de 8: con
corrección por ejercicio, cuatro docentes disparando a la vez lo vacían y el
servicio deja de responder para todos. Se abre, se escribe, se cierra.

**Semáforo.** Por la misma razón, y además porque cada corrección concurrente
es una llamada a Gemini que se paga.

**Presupuesto de tiempo TOTAL**, no por intento. N intentos de 60s son 60s o
son diez minutos según cuántos hagan falta, y un docente esperando no puede
depender de eso.

**Reconciliador.** Un deploy a mitad de una corrección deja filas en `running`
para siempre. Al arrancar, las viejas se cierran como error de infraestructura
— que es lo que fueron: el proceso se murió, no el alumno.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, text, update

from evaluation_service.db.session import tenant_session
from evaluation_service.models.correcciones_ia import CorreccionIA

log = structlog.get_logger()

# El pool es de 8. Tres correcciones concurrentes dejan margen para que el
# resto del servicio siga respondiendo.
_MAX_CONCURRENTES = 3
_semaforo = asyncio.Semaphore(_MAX_CONCURRENTES)

# Presupuesto TOTAL de una corrección, de punta a punta.
PRESUPUESTO_TOTAL_S = 180.0

# Una `running` más vieja que esto es de un proceso que ya no existe.
_UMBRAL_HUERFANA = timedelta(seconds=PRESUPUESTO_TOTAL_S * 2)


async def reconciliar_running(tenant_id: UUID) -> int:
    """Cierra las huérfanas de un deploy anterior: `running` **y `pending`**.

    Se cierran como error de INFRAESTRUCTURA y sin nota: el proceso se murió a
    mitad, que no dice nada sobre el código del alumno. Dejarlas colgadas sería
    peor — la UI las muestra girando para siempre y el docente espera un
    resultado que no va a llegar.

    **`pending` también cuenta.** `background.add_task` corre DESPUÉS de que
    salió el 202: si el proceso muere en esa ventana —un deploy, un OOM, o el
    semáforo con cola— la fila queda `pending`, con `started_at` en NULL. Para
    el docente es indistinguible de una `running` colgada (el panel poletea
    mientras el estado sea `pending` o `running`), y además consume una
    corrección de su cuota diaria que nunca se libera.

    Por eso el corte usa `COALESCE(started_at, created_at)`: una `pending`
    nunca arrancó, así que su reloj es el de cuándo se creó.
    """
    corte = datetime.now(UTC) - _UMBRAL_HUERFANA
    async with tenant_session(tenant_id) as db:
        stmt = (
            update(CorreccionIA)
            .where(
                and_(
                    CorreccionIA.tenant_id == tenant_id,
                    CorreccionIA.estado.in_(("running", "pending")),
                    func.coalesce(CorreccionIA.started_at, CorreccionIA.created_at) < corte,
                )
            )
            .values(
                estado="error",
                nota_100=None,
                error_code="PROCESO_INTERRUMPIDO",
                error_detail=(
                    "La corrección quedó a medias, probablemente por un reinicio del "
                    "servicio. No se llegó a ninguna nota. Podés volver a dispararla."
                ),
                finished_at=datetime.now(UTC),
            )
        )
        res = await db.execute(stmt)
        # `CursorResult` sí trae `rowcount`; el tipo declarado de `execute` es
        # el `Result` genérico, que no lo declara.
        n = getattr(res, "rowcount", 0) or 0
    if n:
        log.warning("activeia_correcciones_huerfanas_cerradas", tenant_id=str(tenant_id), n=n)
    return n


async def tenants_con_running() -> list[UUID]:
    """Los tenants que tienen correcciones en vuelo.

    Es la ÚNICA query del servicio que tiene que cruzar tenants: corre sin
    request, o sea sin `app.current_tenant`, para descubrir sobre qué tenants
    hay que reconciliar.

    **Hasta el 2026-08-27 devolvía cero filas, siempre, y sin tirar error.** El
    comentario decía que "corre como owner para poder ver todos los tenants", y
    era falso: las migraciones corren como `postgres` (así que `postgres` es el
    owner) y el runtime conecta como `academic_user`, que no es owner y se creó
    sin `SUPERUSER` ni `BYPASSRLS`. La policy pide `tenant_id =
    current_setting('app.current_tenant', true)::uuid`; sin el setting eso es
    `tenant_id = NULL`, que evalúa NULL, y la fila se filtra.

    Es exactamente el modo de falla que el docstring de la migración
    `20260818_0002` advierte: en Postgres una policy que no matchea filtra en el
    SELECT, no falla. El reconciliador entero era código muerto en producción —
    y el design D9 se apoya en él para justificar `BackgroundTasks` sin cola
    durable.

    Ahora se prende `app.reconciliador` con SET LOCAL, que habilita la policy
    `correcciones_ia_reconciliador_lectura` (migración `20260827_0001`). Es
    `FOR SELECT` y dura lo que la transacción: lo único que puede hacer alguien
    que se cuele por ahí es LEER, y esta función lee `tenant_id` y nada más.

    Incluye las `pending` por la misma razón que `reconciliar_running`: una
    corrección que murió antes de arrancar es tan huérfana como una que murió a
    mitad, y el docente no las distingue.
    """
    from evaluation_service.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        # SET LOCAL: vive lo que dura esta transacción. La policy que habilita
        # es de SELECT y esta query devuelve SÓLO ids, nunca contenido.
        await db.execute(text("SELECT set_config('app.reconciliador', 'on', true)"))
        rows = await db.execute(
            select(CorreccionIA.tenant_id)
            .where(CorreccionIA.estado.in_(("running", "pending")))
            .distinct()
        )
        return [r[0] for r in rows.all()]


async def cerrar_por_timeout(tenant_id: UUID, correccion_id: UUID) -> None:
    """Cierra una corrección que se quedó sin presupuesto.

    Vive acá y no en el ejecutor porque el ejecutor está siendo CANCELADO
    cuando esto hace falta: cualquier `await` suyo levantaría de nuevo. Este
    corre en el task de afuera, que sigue vivo.
    """
    from datetime import datetime as _dt

    async with tenant_session(tenant_id) as db:
        c = await db.get(CorreccionIA, correccion_id)
        if c is None or c.estado in ("done", "error"):
            return
        c.estado = "error"
        c.nota_100 = None
        c.error_code = "TIMEOUT"
        c.error_detail = (
            f"La corrección pasó los {int(PRESUPUESTO_TOTAL_S)} segundos de presupuesto y se "
            "cortó. No se llegó a ninguna nota. Puede que reintentar sirva."
        )
        c.finished_at = _dt.now(UTC)


async def con_semaforo_y_presupuesto(coro_factory, *, tenant_id: UUID, correccion_id: UUID):
    """Corre el trabajo con el semáforo tomado y el reloj total corriendo.

    `coro_factory` y no una corrutina ya creada: si la creáramos antes de
    tomar el semáforo, N disparos simultáneos crearían N corrutinas que
    esperan, y el timeout empezaría a contar antes de que el trabajo arranque.

    **El cierre por timeout se hace ACÁ, no en el ejecutor.** `wait_for`
    cancela la corrutina interna, y la cancelación llega como
    `CancelledError`, que hereda de `BaseException` y NO de `Exception`: un
    `except Exception` adentro no la ve. Sin este cierre, la corrección
    quedaba `running` para siempre —girando en la pantalla del docente— y el
    reconciliador tampoco la levantaba, porque corre una sola vez al arrancar
    el servicio y sólo sobre filas viejas.

    Nada de esto se propaga hacia afuera: corre en un `BackgroundTask`, la
    respuesta 202 ya salió y no hay quién atrape una excepción acá.
    """
    async with _semaforo:
        try:
            return await asyncio.wait_for(coro_factory(), timeout=PRESUPUESTO_TOTAL_S)
        except TimeoutError:
            log.warning(
                "activeia_correccion_sin_presupuesto",
                correccion_id=str(correccion_id),
                presupuesto_s=PRESUPUESTO_TOTAL_S,
            )
            await _cerrar_sin_escapar(tenant_id, correccion_id)
        except Exception:
            # El ejecutor ya cierra sus propios errores; esto es la red por si
            # alguno se le escapa. Tragarlo es correcto: no hay a quién
            # devolvérselo, y dejarlo escapar mataría el task sin cerrar nada.
            log.exception("activeia_correccion_escapo", correccion_id=str(correccion_id))
            await _cerrar_sin_escapar(tenant_id, correccion_id)
        return None


async def _cerrar_sin_escapar(tenant_id: UUID, correccion_id: UUID) -> None:
    """`cerrar_por_timeout` envuelto, para que el docstring de arriba sea
    verdad.

    Si la base no responde, no hay nada que se pueda escribir de todas formas,
    y dejar que la excepción escape del `BackgroundTask` la pierde sin dejar
    más rastro que un log de Starlette. La fila queda colgada igual, pero al
    menos queda un log nuestro que dice cuál.
    """
    try:
        await cerrar_por_timeout(tenant_id, correccion_id)
    except Exception:
        log.exception("activeia_no_se_pudo_cerrar_por_timeout", correccion_id=str(correccion_id))


async def run_reconciliador(*, intervalo_s: float) -> None:
    """Reconcilia huérfanas cada `intervalo_s`, además de la pasada del arranque.

    **Por qué no alcanzaba con la del arranque** (hallazgo de la auditoría del
    19/08): el reconciliador sólo toca filas más viejas que `_UMBRAL_HUERFANA`
    (2× el presupuesto, 6 minutos). Un deploy que reinicie en menos de eso deja
    huérfanas todas las correcciones que arrancaron en la ventana: al arrancar
    todavía son "recientes", y no había una segunda pasada nunca.

    El resultado era una corrección `running` para siempre, con el panel del
    docente girando sin tope. Y el design D9 se apoya en el reconciliador para
    justificar que el trabajo corra en `BackgroundTasks` sin cola durable — o
    sea que el agujero salía justo debajo de lo que sostiene la decisión.

    Mismo patrón que `abandonment_worker` del tutor-service: un fallo de una
    pasada NO corta el loop, y la cancelación del shutdown se re-lanza.
    """
    log.info("activeia_reconciliador_periodico_arranca", intervalo_s=intervalo_s)
    try:
        while True:
            await asyncio.sleep(intervalo_s)
            try:
                for tenant_id in await tenants_con_running():
                    cerradas = await reconciliar_running(tenant_id)
                    if cerradas:
                        log.info(
                            "activeia_reconciliador_periodico_cerro",
                            tenant_id=str(tenant_id),
                            cerradas=cerradas,
                        )
            except Exception:
                # Una pasada que falla no puede matar el loop: sin él, las
                # huérfanas vuelven a no tener quien las levante.
                log.exception("activeia_reconciliador_periodico_fallo")
    except asyncio.CancelledError:
        log.info("activeia_reconciliador_periodico_cancelado")
        raise
