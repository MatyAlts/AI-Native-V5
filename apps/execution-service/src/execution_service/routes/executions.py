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
from execution_service.services import execution_store
from execution_service.services.academic_client import (
    AcademicClient,
    AcademicUnavailableError,
)
from execution_service.services.execution_store import ExecutionState
from execution_service.services.executor import run_cases, to_client_payload
from execution_service.services.quotas import QuotaUnavailableError, check_and_consume
from execution_service.services.result_mapper import infrastructure_failure

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])

logger = logging.getLogger(__name__)

_ROLES = ("estudiante", "docente", "docente_admin", "jtp", "auxiliar", "superadmin")


class ExecutionRequest(BaseModel):
    ejercicio_id: UUID
    source_code: str = Field(min_length=1, max_length=100_000)


class ExecutionAccepted(BaseModel):
    execution_id: UUID
    state: str
    quota_remaining: int


async def _run_and_store(execution_id: UUID, *, req: ExecutionRequest, user: User) -> None:
    """Corre la ejecucion y persiste el resultado. Nunca propaga excepciones.

    Es una tarea de fondo: si explota, nadie la ve. Cualquier fallo se guarda
    como resultado de infraestructura para que el cliente lo lea en el GET.
    """
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
    # Cuota PRIMERO: si no hay, no se toca el sandbox ni se lee el ejercicio.
    try:
        decision = await check_and_consume(tenant_id=user.tenant_id, user_id=user.id)
    except QuotaUnavailableError as exc:
        # Fallo CERRADO (D5). 503 y no 429: no es que el alumno se paso, es que
        # no podemos garantizar el techo de costo.
        logger.error("quota_unavailable user=%s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El servicio de ejecucion no esta disponible en este momento. "
                "Podes seguir escribiendo codigo y consultando al tutor."
            ),
        ) from exc

    if not decision.allowed:
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
