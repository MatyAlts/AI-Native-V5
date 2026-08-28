"""Endpoints de ejecucion (tareas 3.1 y 3.2).

Asincrono con consulta de estado (D2), no peticion-respuesta bloqueante.

Compilar y arrancar una JVM no es instantaneo, y a eso se le suma la latencia de
red y la cola del sandbox. Con una comision entera ejecutando en la misma
ventana de dos minutos —el caso real, no el peor teorico— una peticion sincrona
deja el editor congelado sin poder distinguir "esta compilando" de "se colgo".
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from execution_service.auth import User, require_role
from execution_service.config import settings
from execution_service.services import execution_store, metrics
from execution_service.services.academic_client import (
    AcademicClient,
    AcademicUnavailableError,
    Ejercicio,
)
from execution_service.services.ctr_emitter import build_payload, should_emit
from execution_service.services.execution_store import ExecutionState
from execution_service.services.executor import run_cases, to_client_payload
from execution_service.services.quotas import QuotaUnavailableError, check_and_consume
from execution_service.services.result_mapper import RunResult, infrastructure_failure
from execution_service.services.tutor_client import TutorClient

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])

logger = logging.getLogger(__name__)

_ROLES = ("estudiante", "docente", "docente_admin", "jtp", "auxiliar", "superadmin")

# La habilitacion progresiva (9.3) acota la exposicion de los ALUMNOS mientras se
# despliega. El personal docente queda afuera del filtro a proposito: los
# ejercicios del banco son reusables entre comisiones (ADR-047) y el panel de
# prueba corre fuera de todo episodio, asi que una corrida suya no tiene comision
# que mirar. Aplicarles el filtro los dejaria sin poder probar NADA justo durante
# el rollout, que es cuando mas falta hace.
_ROLES_STAFF = frozenset({"docente", "docente_admin", "jtp", "auxiliar", "superadmin"})


class ExecutionRequest(BaseModel):
    ejercicio_id: UUID
    source_code: str = Field(min_length=1, max_length=100_000)
    # Para la habilitacion progresiva (9.3). Opcional: sin lista configurada el
    # servicio esta habilitado para todas y este campo no se mira.
    comision_id: UUID | None = None
    # Episodio al que pertenece la corrida (tarea 5.1). Sin esto no hay a que
    # cadena adjuntar `tests_ejecutados`, y era la razon de fondo por la que el
    # emisor nunca se cableo: `ctr_emitter` armaba el payload y no habia destino.
    #
    # Opcional a proposito: el panel del docente prueba ejercicios FUERA de un
    # episodio, y esa corrida no es actividad de ningun alumno — no debe generar
    # evento. `None` => no se emite.
    episode_id: UUID | None = None


class ExecutionAccepted(BaseModel):
    execution_id: UUID
    state: str
    quota_remaining: int


async def _run_and_store(execution_id: UUID, *, req: ExecutionRequest, user: User) -> None:
    """Corre la ejecucion y persiste el resultado. Nunca propaga excepciones.

    Es una tarea de fondo: si explota, nadie la ve. Cualquier fallo se guarda
    como resultado de infraestructura para que el cliente lo lea en el GET.
    """
    import time as _time

    started = _time.perf_counter()
    metrics.record_started()
    outcome = "infrastructure_failure"
    # Solo quedan no-None si la corrida llego a ejecutarse de verdad. Es la
    # condicion para emitir: sin `ejercicio` no se sabe que casos eran ocultos,
    # y sin `run` no hay conteos.
    run: RunResult | None = None
    ejercicio: Ejercicio | None = None
    try:
        await execution_store.put(
            execution_id,
            state=ExecutionState.RUNNING,
            owner_id=user.id,
            tenant_id=user.tenant_id,
        )
        ejercicio = await AcademicClient().get_ejercicio(req.ejercicio_id, user.tenant_id)
        run = await run_cases(source_code=req.source_code, ejercicio=ejercicio)
        payload = to_client_payload(run, ejercicio)
        outcome = run.outcome.value
    except AcademicUnavailableError as exc:
        logger.warning("execution_academic_unavailable id=%s: %s", execution_id, exc)
        payload = {
            "outcome": "infrastructure_failure",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "cases": [],
            "compile_output": "",
        }
    except Exception as exc:
        logger.exception("execution_failed id=%s", execution_id)
        run = infrastructure_failure(f"{type(exc).__name__}")
        payload = {
            "outcome": run.outcome.value,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "cases": [],
            "compile_output": "",
        }

    ejecucion_ms = int((_time.perf_counter() - started) * 1000)
    metrics.record_finished(outcome=outcome, duration_seconds=_time.perf_counter() - started)

    # Tarea 5.1 — el evento de trazabilidad. Va DESPUES de medir y ANTES de
    # guardar el resultado: emitir es lo unico que el alumno no ve, asi que si
    # falla no puede retrasarle la respuesta ni tumbar la corrida.
    #
    # `should_emit` es el guard anti-inflacion: si no se ejecuto NINGUN caso no
    # se emite, porque el labeler lee `failed == 0` como "paso todo" y etiquetaria
    # N4 —el nivel mas alto del modelo— un episodio donde no corrio nada. Cubre
    # las dos formas de que no corra nada: el sandbox caido
    # (`INFRASTRUCTURE_FAILURE`) y la corrida vacia (ejercicio sin casos, o
    # lenguaje sin runtime con todo `skipped`). Ver `ctr_emitter`.
    #
    # El alumno IGUAL ve el resultado: `to_client_payload` ya se calculo y se
    # guarda mas abajo. Lo unico que no ocurre es el evento CTR.
    if (
        req.episode_id is not None
        and run is not None
        and ejercicio is not None
        and should_emit(run)
    ):
        await TutorClient().emit_tests_ejecutados(
            episode_id=req.episode_id,
            execution_id=execution_id,
            user_id=user.id,
            tenant_id=user.tenant_id,
            payload=build_payload(
                run,
                hidden_case_ids={c.id for c in ejercicio.hidden_cases},
                ejecucion_ms=ejecucion_ms,
                engine="docker-java",
            ),
        )

    try:
        await execution_store.put(
            execution_id,
            state=ExecutionState.DONE,
            owner_id=user.id,
            tenant_id=user.tenant_id,
            result=payload,
        )
    except execution_store.ExecutionStoreUnavailableError:
        logger.exception("execution_result_lost id=%s", execution_id)


@router.post("", response_model=ExecutionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def request_execution(
    req: ExecutionRequest,
    background: BackgroundTasks,
    user: User = Depends(require_role(*_ROLES)),
) -> ExecutionAccepted:
    """Encola una ejecucion y responde de inmediato con su identificador."""
    # Habilitacion progresiva / apagado (9.2 y 9.3). Va ANTES que la cuota: si
    # el lenguaje no esta habilitado para esta comision, no se consume nada.
    #
    # El staff no pasa por el filtro por comision (ver `_ROLES_STAFF`), pero SI
    # por el interruptor general: con `EXECUTION_ENABLED=false` no ejecuta nadie,
    # que es el procedimiento de apagado y no admite excepciones.
    es_staff = bool(user.roles & _ROLES_STAFF)
    if not settings.execution_enabled or (
        not es_staff
        and not settings.comision_habilitada(str(req.comision_id) if req.comision_id else None)
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "La ejecucion de codigo no esta habilitada para esta comision todavia. "
                "Podes seguir escribiendo codigo y consultando al tutor."
            ),
        )

    # Cuota PRIMERO: si no hay, no se toca el sandbox ni se lee el ejercicio.
    try:
        decision = await check_and_consume(tenant_id=user.tenant_id, user_id=user.id)
    except QuotaUnavailableError as exc:
        # Fallo CERRADO (D5). 503 y no 429: no es que el alumno se paso, es que
        # no podemos garantizar el techo de costo.
        logger.error("quota_unavailable user=%s: %s", user.id, exc)
        metrics.record_quota_rejection(reason="counter_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El servicio de ejecucion no esta disponible en este momento. "
                "Podes seguir escribiendo codigo y consultando al tutor."
            ),
        ) from exc

    if not decision.allowed:
        metrics.record_quota_rejection(reason="limit_reached")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=decision.reason)

    execution_id = uuid4()
    await execution_store.put(
        execution_id,
        state=ExecutionState.QUEUED,
        owner_id=user.id,
        tenant_id=user.tenant_id,
    )
    background.add_task(_run_and_store, execution_id, req=req, user=user)

    return ExecutionAccepted(
        execution_id=execution_id,
        state=ExecutionState.QUEUED.value,
        quota_remaining=decision.remaining,
    )


@router.get("/{execution_id}")
async def get_execution(
    execution_id: UUID,
    user: User = Depends(require_role(*_ROLES)),
) -> dict[str, Any]:
    """Estado y resultado de una ejecucion."""
    entry = await execution_store.get(execution_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ejecucion no encontrada")

    # Un id ajeno no alcanza para leer el resultado de otro alumno. Se responde
    # 404 y no 403 para no confirmar que el id existe.
    if entry.get("owner_id") != str(user.id) or entry.get("tenant_id") != str(user.tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ejecucion no encontrada")

    return {
        "execution_id": str(execution_id),
        "state": entry["state"],
        "result": entry.get("result"),
    }
