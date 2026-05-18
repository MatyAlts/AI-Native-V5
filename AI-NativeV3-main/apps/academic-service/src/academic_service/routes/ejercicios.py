"""Endpoints REST del banco de ejercicios reusables (ADR-047).

Biblioteca por tenant. Los ejercicios son entidades de primera clase
con UUID propio, schema pedagógico rico (ADR-048) y reusables entre TPs
via la tabla intermedia `tp_ejercicios`.

Incluye el wizard IA standalone (`POST /generate`) que invoca al
ai-gateway con el prompt `ejercicio_generator/v1.0.0` y devuelve un
borrador editable de `EjercicioCreate` con TODOS los campos pedagógicos.
NO persiste — el docente revisa y dispara `POST /ejercicios` para
guardar.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import ListMeta, ListResponse
from academic_service.services.ejercicio_service import EjercicioService
from platform_contracts.academic.ejercicio import (
    EjercicioCreate,
    EjercicioRead,
    EjercicioUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ejercicios", tags=["ejercicios"])


@router.post("", response_model=EjercicioRead, status_code=status.HTTP_201_CREATED)
async def create_ejercicio(
    data: EjercicioCreate,
    user: User = Depends(require_permission("ejercicio", "create")),
    db: AsyncSession = Depends(get_db),
) -> EjercicioRead:
    svc = EjercicioService(db)
    obj = await svc.create(data, user)
    return EjercicioRead.model_validate(obj)


@router.get("", response_model=ListResponse[EjercicioRead])
async def list_ejercicios(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    unidad_tematica: Literal[
        "secuenciales", "condicionales", "repetitivas", "mixtos"
    ]
    | None = None,
    dificultad: Literal["basica", "intermedia", "avanzada"] | None = None,
    created_by: UUID | None = None,
    created_via_ai: bool | None = None,
    user: User = Depends(require_permission("ejercicio", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[EjercicioRead]:
    """Lista ejercicios del banco con filtros opcionales.

    - `unidad_tematica`: filtra por taxonomía pedagógica del ejercicio.
    - `dificultad`: filtra por dificultad declarada.
    - `created_by`: docente creador.
    - `created_via_ai`: filtra ejercicios generados con el wizard IA.
    """
    svc = EjercicioService(db)
    objs = await svc.list(
        unidad_tematica=unidad_tematica,
        dificultad=dificultad,
        created_by=created_by,
        created_via_ai=created_via_ai,
        limit=limit,
        cursor=cursor,
    )
    items = [EjercicioRead.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/{ejercicio_id}", response_model=EjercicioRead)
async def get_ejercicio(
    ejercicio_id: UUID,
    user: User = Depends(require_permission("ejercicio", "read")),
    db: AsyncSession = Depends(get_db),
) -> EjercicioRead:
    svc = EjercicioService(db)
    obj = await svc.get(ejercicio_id)
    return EjercicioRead.model_validate(obj)


@router.patch("/{ejercicio_id}", response_model=EjercicioRead)
async def update_ejercicio(
    ejercicio_id: UUID,
    data: EjercicioUpdate,
    user: User = Depends(require_permission("ejercicio", "update")),
    db: AsyncSession = Depends(get_db),
) -> EjercicioRead:
    svc = EjercicioService(db)
    obj = await svc.update(ejercicio_id, data, user)
    return EjercicioRead.model_validate(obj)


@router.delete("/{ejercicio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ejercicio(
    ejercicio_id: UUID,
    user: User = Depends(require_permission("ejercicio", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = EjercicioService(db)
    await svc.soft_delete(ejercicio_id, user)


# ── Wizard IA standalone (ADR-047 + ADR-048) ──────────────────────────────


class EjercicioGenerateRequest(BaseModel):
    """Request del wizard IA standalone para generar un Ejercicio.

    El docente describe en NL qué quiere; el endpoint llama al ai-gateway
    via governance-service (prompt `ejercicio_generator/v1.0.0`) y devuelve
    un borrador completo con todos los campos pedagógicos PID-UTN. NO
    persiste — el docente revisa y dispara `POST /ejercicios` para guardar.

    `materia_id` es opcional: si no viene, el endpoint resuelve la primera
    materia del tenant (modo demo / piloto sin selector encadenado). En el
    futuro habrá un selector en el frontend; por ahora aceptamos None para
    que el wizard sea usable sin saber UUIDs de memoria.
    """

    materia_id: UUID | None = None
    descripcion_nl: str = Field(min_length=10, max_length=2000)
    unidad_tematica: Literal[
        "secuenciales", "condicionales", "repetitivas", "mixtos"
    ]
    dificultad: Literal["basica", "intermedia", "avanzada"] | None = None
    contexto: str | None = Field(default=None, max_length=2000)
    comision_id: UUID | None = None


class EjercicioGenerateResponse(BaseModel):
    """Borrador editable del Ejercicio + metadata de la generación."""

    borrador: dict[str, Any]
    prompt_version: str
    model_used: str
    provider_used: str
    tokens_input: int
    tokens_output: int
    rag_chunks_used: int
    rag_chunks_hash: str | None


@router.post("/generate", response_model=EjercicioGenerateResponse)
async def generate_ejercicio(
    req: EjercicioGenerateRequest,
    user: User = Depends(require_permission("ejercicio", "create")),
    db: AsyncSession = Depends(get_db),
) -> EjercicioGenerateResponse:
    """Genera un borrador de Ejercicio via IA (ADR-047 + ADR-048).

    Flow:
      1. Valida materia_id existe en este tenant.
      2. governance-service resuelve el prompt `ejercicio_generator/{version}`.
      3. RAG opcional sobre material de cátedra (scope materia_id).
      4. ai-gateway con `feature="ejercicio_generator"` + `materia_id` para BYOK.
      5. Parse del JSON estructurado del LLM con todos los campos pedagógicos.
      6. Audit log structlog `ejercicio_generated_by_ai`.

    Errores:
      - 400 si materia_id no existe o no pertenece al tenant.
      - 502 si el ai-gateway falla o el LLM devuelve JSON invalido.
      - 403 (Casbin) si el caller es estudiante.
    """
    from sqlalchemy import select

    from academic_service.config import settings
    from academic_service.models.institucional import Materia
    from academic_service.routes.tareas_practicas import _retrieve_rag_context
    from academic_service.services.ai_clients import AIGatewayClient, GovernanceClient

    # 1. Resolver materia. Si el frontend no envia materia_id (no hay selector
    # encadenado todavia en el wizard), resolvemos la primera materia del
    # tenant via RLS. Si tampoco hay materias, error claro.
    if req.materia_id is not None:
        stmt = select(Materia).where(Materia.id == req.materia_id)
        materia = (await db.execute(stmt)).scalar_one_or_none()
        if materia is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Materia {req.materia_id} no encontrada en este tenant",
            )
        materia_id_resolved = req.materia_id
    else:
        stmt = select(Materia).limit(1)
        materia = (await db.execute(stmt)).scalar_one_or_none()
        if materia is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No hay materias en este tenant. Crea al menos una materia "
                    "antes de usar el wizard IA, o paseme un materia_id explicito."
                ),
            )
        materia_id_resolved = materia.id

    # 2. Resolver prompt activo
    governance = GovernanceClient(settings.governance_service_url)
    prompt_version_full = (
        f"ejercicio_generator/{settings.ejercicio_generator_prompt_version}"
    )
    try:
        prompt_cfg = await governance.get_prompt(
            "ejercicio_generator", settings.ejercicio_generator_prompt_version
        )
    except Exception as exc:
        logger.error("ejercicio_generator_prompt_fetch_failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo resolver el prompt activo del ejercicio_generator",
        ) from exc

    # 3. RAG opcional sobre material de cátedra
    rag_context, rag_chunks_used, rag_chunks_hash = await _retrieve_rag_context(
        req.descripcion_nl,
        materia_id_resolved,
        user.tenant_id,
        req.comision_id,
    )

    # 4. Construir user message
    user_message_parts: list[str] = [
        f"Descripción: {req.descripcion_nl}",
        f"Unidad temática: {req.unidad_tematica}",
    ]
    if req.dificultad:
        user_message_parts.append(f"Dificultad: {req.dificultad}")
    if req.contexto:
        user_message_parts.append(f"Contexto adicional: {req.contexto}")
    if rag_context:
        user_message_parts.append(rag_context)
    user_message = "\n\n".join(user_message_parts)

    messages = [
        {"role": "system", "content": prompt_cfg.content},
        {"role": "user", "content": user_message},
    ]

    # 5. Pegar al ai-gateway con retry
    ai = AIGatewayClient(settings.ai_gateway_url)
    max_attempts = 2
    parsed: dict[str, Any] = {}
    result = None
    t0 = time.perf_counter()

    for attempt in range(max_attempts):
        try:
            result = await ai.complete(
                messages=messages,
                model=settings.ejercicio_generator_default_model,
                feature="ejercicio_generator",
                tenant_id=user.tenant_id,
                materia_id=materia_id_resolved,
                temperature=0.7,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
        except httpx.HTTPError as exc:
            logger.error("ai_gateway_call_failed: %s", exc)
            if attempt < max_attempts - 1:
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="ai-gateway no respondió correctamente",
            ) from exc

        # Parsear JSON
        raw_content = result.content.strip()
        if not raw_content.startswith("{"):
            brace_start = raw_content.find("{")
            brace_end = raw_content.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                raw_content = raw_content[brace_start : brace_end + 1]
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            logger.error(
                "ejercicio_generator_invalid_json provider=%s model=%s error=%s "
                "raw_start=%r",
                result.provider,
                result.model,
                str(exc),
                raw_content[:300],
            )
            if attempt < max_attempts - 1:
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM devolvió JSON inválido (revisar prompt o modelo)",
            ) from exc

        if "error" in parsed and attempt < max_attempts - 1:
            logger.warning(
                "ejercicio_generator_llm_returned_error attempt=%d: %s",
                attempt,
                parsed["error"],
            )
            continue

        break

    assert result is not None
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if "error" in parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"LLM no pudo generar borrador: {parsed['error']}",
        )

    # 6. Sobreescribir unidad_tematica con la del request (no confiar al LLM)
    parsed["unidad_tematica"] = req.unidad_tematica
    if req.dificultad:
        parsed["dificultad"] = req.dificultad

    # 7. Marcar created_via_ai para trazabilidad académica
    parsed["created_via_ai"] = True

    # 8. Audit log structlog
    try:
        import structlog

        structlog.get_logger().info(
            "ejercicio_generated_by_ai",
            tenant_id=str(user.tenant_id),
            user_id=str(user.id),
            materia_id=str(materia_id_resolved),
            unidad_tematica=req.unidad_tematica,
            dificultad=req.dificultad,
            prompt_version=prompt_version_full,
            tokens_input=result.input_tokens,
            tokens_output=result.output_tokens,
            latency_ms=latency_ms,
            provider_used=result.provider,
            model_used=result.model,
            cache_hit=result.cache_hit,
            rag_chunks_used=rag_chunks_used,
            rag_chunks_hash=rag_chunks_hash,
        )
    except ImportError:
        logger.info(
            "ejercicio_generated_by_ai tenant=%s user=%s materia=%s "
            "prompt=%s tokens_in=%d tokens_out=%d latency_ms=%d "
            "provider=%s model=%s",
            user.tenant_id,
            user.id,
            materia_id_resolved,
            prompt_version_full,
            result.input_tokens,
            result.output_tokens,
            latency_ms,
            result.provider,
            result.model,
        )

    return EjercicioGenerateResponse(
        borrador=parsed,
        prompt_version=prompt_version_full,
        model_used=result.model,
        provider_used=result.provider,
        tokens_input=result.input_tokens,
        tokens_output=result.output_tokens,
        rag_chunks_used=rag_chunks_used,
        rag_chunks_hash=rag_chunks_hash,
    )
