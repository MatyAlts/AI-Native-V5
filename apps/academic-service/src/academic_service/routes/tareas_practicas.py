"""Endpoints de Tareas Prácticas (TP)."""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from platform_contracts.academic.ejercicio import (
    DEFAULT_LANGUAGE,
    EjercicioRead,
    Language,
    TpEjercicioCreate,
    TpEjercicioRead,
    TpEjercicioUpdate,
)

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import ListMeta, ListResponse
from academic_service.schemas.tarea_practica import (
    TareaPracticaCreate,
    TareaPracticaOut,
    TareaPracticaUpdate,
    TareaPracticaVersionRef,
)
from academic_service.services.comision_service import (
    OVERSIGHT_ROLES,
    assert_comision_access,
)
from academic_service.services.content_visibility import (
    sanitize_ejercicio_for_student,
    sanitize_tarea_practica_for_student,
)
from academic_service.services.prompt_variants import resolve_prompt_name
from academic_service.services.tarea_practica_service import TareaPracticaService
from academic_service.services.tp_ejercicio_service import TpEjercicioService

router = APIRouter(prefix="/api/v1/tareas-practicas", tags=["tareas-practicas"])


@router.post("", response_model=TareaPracticaOut, status_code=status.HTTP_201_CREATED)
async def create_tarea_practica(
    data: TareaPracticaCreate,
    user: User = Depends(require_permission("tarea_practica", "create")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaOut:
    svc = TareaPracticaService(db)
    obj = await svc.create(data, user)
    return TareaPracticaOut.model_validate(obj)


@router.get("", response_model=ListResponse[TareaPracticaOut])
async def list_tareas_practicas(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    comision_id: UUID | None = None,
    estado: Literal["draft", "published", "archived"] | None = None,
    unidad_id: UUID | None = None,
    user: User = Depends(require_permission("tarea_practica", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[TareaPracticaOut]:
    """Lista TPs con filtros opcionales (fix QA A13: unidad_id).

    - `unidad_id` filtra a las TPs asignadas a esa Unidad temática
      (ADR-041). Sin el query param, devuelve TPs sin filtrar por
      unidad (comportamiento actual).
    - Aislamiento por comisión: el acceso es válido para docentes asignados
      (`usuarios_comision`) o alumnos inscriptos (`inscripciones`). Pedir una
      comisión ajena → 403; sin `comision_id` → lista vacía (no se permite
      listar todo el tenant, que en prod es compartido). Oversight ve todo.
    - Visibilidad por estado: los alumnos (no staff) solo ven TPs
      `published` — se fuerza server-side, sin importar el `estado` pedido,
      para no filtrar borradores/archivadas.
    """
    is_staff = True  # oversight (comision_id=None) ve todo; se recalcula abajo
    if comision_id is not None:
        is_staff = await assert_comision_access(db, user, comision_id)
        if not is_staff:
            estado = "published"
    elif not (user.roles & OVERSIGHT_ROLES):
        return ListResponse(data=[], meta=ListMeta(cursor_next=None))
    svc = TareaPracticaService(db)
    objs = await svc.list(
        comision_id=comision_id,
        estado=estado,
        unidad_id=unidad_id,
        limit=limit,
        cursor=cursor,
    )
    items = [TareaPracticaOut.model_validate(o) for o in objs]
    if not is_staff:
        # A0.3: el alumno no debe ver test cases ocultos (con respuesta esperada).
        items = [sanitize_tarea_practica_for_student(it) for it in items]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/{tarea_id}", response_model=TareaPracticaOut)
async def get_tarea_practica(
    tarea_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "read")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaOut:
    """Detalle de una TP por id.

    IDOR fix: además del permiso Casbin, valida acceso a la comisión de la TP
    (docente asignado o alumno inscripto). Un alumno solo ve TPs `published`
    de su comisión; pedir una ajena o un borrador → 404 (no se revela).
    """
    svc = TareaPracticaService(db)
    obj = await svc.get(tarea_id)
    is_staff = await assert_comision_access(db, user, obj.comision_id)
    if not is_staff and obj.estado != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrada")
    out = TareaPracticaOut.model_validate(obj)
    if not is_staff:
        # A0.3: filtrar test cases ocultos (respuesta esperada) para el alumno.
        out = sanitize_tarea_practica_for_student(out)
    return out


@router.patch("/{tarea_id}", response_model=TareaPracticaOut)
async def update_tarea_practica(
    tarea_id: UUID,
    data: TareaPracticaUpdate,
    user: User = Depends(require_permission("tarea_practica", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaOut:
    svc = TareaPracticaService(db)
    obj = await svc.update(tarea_id, data, user)
    return TareaPracticaOut.model_validate(obj)


@router.delete("/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tarea_practica(
    tarea_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = TareaPracticaService(db)
    await svc.soft_delete(tarea_id, user)


@router.post("/{tarea_id}/publish", response_model=TareaPracticaOut)
async def publish_tarea_practica(
    tarea_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaOut:
    svc = TareaPracticaService(db)
    obj = await svc.publish(tarea_id, user)
    return TareaPracticaOut.model_validate(obj)


@router.post("/{tarea_id}/archive", response_model=TareaPracticaOut)
async def archive_tarea_practica(
    tarea_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaOut:
    svc = TareaPracticaService(db)
    obj = await svc.archive(tarea_id, user)
    return TareaPracticaOut.model_validate(obj)


@router.post(
    "/{tarea_id}/new-version",
    response_model=TareaPracticaOut,
    status_code=status.HTTP_201_CREATED,
)
async def new_version_tarea_practica(
    tarea_id: UUID,
    data: TareaPracticaUpdate,
    user: User = Depends(require_permission("tarea_practica", "create")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaOut:
    svc = TareaPracticaService(db)
    obj = await svc.new_version(tarea_id, data, user)
    return TareaPracticaOut.model_validate(obj)


# ── TP-gen IA (Sec 11 epic ai-native-completion / ADR-036) ─────────────


async def _retrieve_rag_context(
    descripcion_nl: str,
    materia_id: UUID,
    tenant_id: UUID,
    comision_id: UUID | None = None,
) -> tuple[str, int, str | None]:
    """Consulta RAG al content-service. Devuelve (context_text, n_chunks, hash).

    Usa materia_id como scope principal (el material pertenece a la materia).
    """
    try:
        from academic_service.config import settings
        from academic_service.services.ai_clients import ContentClient

        content = ContentClient(settings.content_service_url)
        retrieval = await content.retrieve(
            query=descripcion_nl,
            tenant_id=tenant_id,
            materia_id=materia_id,
            comision_id=comision_id,
            top_k=5,
        )
        if not retrieval.chunks:
            return "", 0, None
        chunks_text = "\n---\n".join(
            f"[{c.material_nombre}]\n{c.contenido}" for c in retrieval.chunks
        )
        context = (
            "\n\nMaterial de referencia de la catedra (usa este contenido "
            "como base para el ejercicio):\n\n" + chunks_text
        )
        return context, len(retrieval.chunks), retrieval.chunks_used_hash
    except Exception as exc:
        logger.warning("rag_retrieval_failed_for_tp_gen: %s (continuing without RAG)", exc)
        return "", 0, None


class TPGenerateRequest(BaseModel):
    """Request del wizard TP-gen del web-teacher.

    El docente describe en NL que TP quiere; el endpoint pega al ai-gateway
    via governance-service (resuelve prompt activo) y devuelve un borrador
    editable. NO persiste — el docente edita y dispara `POST /tareas-practicas`
    tradicional con `created_via_ai=true`.
    """

    materia_id: UUID
    descripcion_nl: str = Field(min_length=10, max_length=2000)
    num_ejercicios: int = Field(default=1, ge=1, le=10)
    dificultad: Literal["basica", "intermedia", "avanzada"] | None = None
    contexto: str | None = Field(default=None, max_length=2000)
    comision_id: UUID | None = None
    # Lenguaje de la TP. Decide QUE variante de prompt se usa y aplica a TODOS
    # los ejercicios generados: una TP admite un solo lenguaje. Omitirlo conserva
    # el comportamiento previo a `java-authoring-experience`.
    language: Language = DEFAULT_LANGUAGE
    # Si el wizard se abrió desde una plantilla, la pasamos para prefijar la
    # consigna pedagógica al mensaje del LLM. Trazabilidad solamente; el TP
    # resultante puede asociarse al template via `template_id` en el POST final.
    template_id: UUID | None = None


class EjercicioGenerado(BaseModel):
    titulo: str
    enunciado: str
    inicial_codigo: str
    rubrica: dict[str, Any]
    test_cases: list[dict[str, Any]]


class TPGenerateResponse(BaseModel):
    ejercicios: list[EjercicioGenerado]
    prompt_version: str
    model_used: str
    provider_used: str
    tokens_input: int
    tokens_output: int
    rag_chunks_used: int
    rag_chunks_hash: str | None


@router.post("/generate", response_model=TPGenerateResponse)
async def generate_tarea_practica(  # noqa: PLR0912, PLR0915
    req: TPGenerateRequest,
    user: User = Depends(require_permission("tarea_practica", "create")),
) -> TPGenerateResponse:
    """Genera un borrador de TP via IA (ADR-036, Sec 11 epic ai-native-completion).

    Flow:
      1. Valida materia_id existe en este tenant (+ consigna de plantilla opcional).
      2. governance-service resuelve el prompt `tp_generator/{version}` activo.
      3. ai-gateway con `feature="tp_generator"` + `materia_id` para BYOK.
      4. Parse del JSON estructurado del LLM (formato declarado en el prompt).
      5. Audit log structlog `tp_generated_by_ai` con todos los campos.

    Errores:
      - 400 si materia_id no existe o no pertenece al tenant.
      - 502 si el ai-gateway falla o el LLM devuelve JSON invalido.
      - 403 (Casbin) si el caller es estudiante.

    Manejo del pool (P-9 / A2.4): NO tomamos la sesión DB por `Depends(get_db)`
    (que la retendría durante los hasta 3×90s del LLM, agotando el pool bajo
    concurrencia). Leemos lo mínimo (materia + consigna de plantilla) en una
    sesión CORTA y la soltamos ANTES de pegar al LLM. Este endpoint no persiste.
    """
    import asyncio
    import json
    import time

    from sqlalchemy import select

    from academic_service.config import settings
    from academic_service.db import tenant_session
    from academic_service.models.institucional import Materia
    from academic_service.services.ai_clients import (
        AIGatewayClient,
        GovernanceClient,
        get_generation_semaphore,
    )

    # 1. Lecturas DB en una sesión CORTA (materia + consigna de plantilla). Se
    # cierra al salir del `async with`, devolviendo la conexión al pool ANTES de
    # governance/RAG/LLM. Adelantamos la lectura de la plantilla acá (antes se
    # hacía tras el RAG) para consolidar todo el uso de DB en una sola ventana.
    consigna_plantilla: str | None = None
    async with tenant_session(user.tenant_id) as db:
        stmt = select(Materia).where(Materia.id == req.materia_id)
        materia = (await db.execute(stmt)).scalar_one_or_none()
        if materia is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Materia {req.materia_id} no encontrada en este tenant",
            )

        if req.template_id is not None:
            from academic_service.models.operacional import TareaPracticaTemplate

            stmt_t = select(TareaPracticaTemplate).where(
                TareaPracticaTemplate.id == req.template_id,
                TareaPracticaTemplate.tenant_id == user.tenant_id,
                TareaPracticaTemplate.deleted_at.is_(None),
            )
            template_obj = (await db.execute(stmt_t)).scalar_one_or_none()
            if template_obj is not None:
                consigna_plantilla = template_obj.consigna

    # 2. Resolver prompt (governance-service) — la familia depende del lenguaje
    #    pedido; para el lenguaje por omision el nombre no cambia.
    governance = GovernanceClient(settings.governance_service_url)
    prompt_name = resolve_prompt_name("tp_generator", req.language)
    prompt_version_full = f"{prompt_name}/{settings.tp_generator_prompt_version}"
    try:
        prompt_cfg = await governance.get_prompt(prompt_name, settings.tp_generator_prompt_version)
    except Exception as exc:
        logger.error(
            "tp_generator_prompt_fetch_failed prompt=%s language=%s: %s",
            prompt_name,
            req.language,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"No se pudo resolver el prompt activo del generador de TPs "
                f"para el lenguaje '{req.language}'"
            ),
        ) from exc

    # 2b. RAG: buscar materiales relevantes con materia_id como scope principal
    rag_context, rag_chunks_used, rag_chunks_hash = await _retrieve_rag_context(
        req.descripcion_nl,
        req.materia_id,
        user.tenant_id,
        req.comision_id,
    )

    # 3. Construir mensajes para LLM. La consigna de plantilla (leída en el paso 1
    # dentro de la sesión corta) suma contexto pedagógico: define el QUÉ, mientras
    # la descripcion del docente define el detalle.
    user_message_parts: list[str] = []
    if consigna_plantilla:
        user_message_parts.append(
            f"Consigna pedagógica de la cátedra (plantilla):\n{consigna_plantilla}"
        )
    user_message_parts.append(f"Descripcion: {req.descripcion_nl}")
    user_message_parts.append(f"num_ejercicios: {req.num_ejercicios}")
    if req.dificultad:
        user_message_parts.append(f"Dificultad: {req.dificultad}")
    if req.contexto:
        user_message_parts.append(f"Contexto: {req.contexto}")
    if rag_context:
        user_message_parts.append(rag_context)
    user_message = "\n\n".join(user_message_parts)

    messages = [
        {"role": "system", "content": prompt_cfg.content},
        {"role": "user", "content": user_message},
    ]

    # 4. Pegar al ai-gateway con retry + backoff exponencial.
    # QA 2026-05-18: mismo patron que ejercicios.py — 502 transitorios en el
    # primer attempt mientras el ai-gateway sí procesa el LLM. Subimos 2→3
    # y agregamos backoff para no machacar al gateway.
    ai = AIGatewayClient(settings.ai_gateway_url, timeout=90.0)
    max_attempts = 3
    parsed: dict = {}
    result = None
    t0 = time.perf_counter()

    max_output_tokens = settings.tp_generator_max_tokens

    # Sin sesión DB abierta acá (P-9): la conexión ya volvió al pool. El semáforo
    # limita cuántas generaciones IA corren a la vez (no cuántas conexiones DB).
    async with get_generation_semaphore():
        for attempt in range(max_attempts):
            try:
                result = await ai.complete(
                    messages=messages,
                    model=settings.tp_generator_default_model,
                    feature="tp_generator",
                    tenant_id=user.tenant_id,
                    materia_id=req.materia_id,
                    temperature=0.7,
                    max_tokens=max_output_tokens,
                    response_format={"type": "json_object"},
                )
            except httpx.HTTPError as exc:
                logger.error(
                    "ai_gateway_call_failed attempt=%d exc_type=%s detail=%s",
                    attempt,
                    type(exc).__name__,
                    str(exc)[:200],
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="ai-gateway no respondio correctamente tras 3 intentos",
                ) from exc

            # 5. Parsear JSON
            raw_content = result.content.strip()
            if not raw_content.startswith("{"):
                brace_start = raw_content.find("{")
                brace_end = raw_content.rfind("}")
                if brace_start != -1 and brace_end > brace_start:
                    raw_content = raw_content[brace_start : brace_end + 1]
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError as exc:
                # Distinguir JSON *malformado* de JSON *truncado*, igual que el
                # generador de ejercicios. Si el modelo agotó el techo de salida,
                # la respuesta viene cortada a mitad de string y nunca va a
                # parsear: reintentar es determinista, falla las 3 veces y quema
                # llamadas al LLM para terminar en el mismo 502. Se corta en el
                # primer intento con un mensaje que apunta al techo y no al prompt.
                truncated = result.output_tokens >= max_output_tokens
                logger.error(
                    "tp_generator_invalid_json provider=%s model=%s "
                    "truncated=%s output_tokens=%d/%d error=%s raw_start=%r",
                    result.provider,
                    result.model,
                    truncated,
                    result.output_tokens,
                    max_output_tokens,
                    str(exc),
                    raw_content[:300],
                )
                if truncated:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=(
                            f"La respuesta del modelo se corto por limite de tokens "
                            f"({result.output_tokens}/{max_output_tokens}). Subi "
                            f"TP_GENERATOR_MAX_TOKENS o pedi una TP mas acotada."
                        ),
                    ) from exc
                if attempt < max_attempts - 1:
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="LLM devolvio JSON invalido (revisar prompt o modelo)",
                ) from exc

            if "error" in parsed and attempt < max_attempts - 1:
                logger.warning(
                    "tp_generator_llm_returned_error attempt=%d: %s",
                    attempt,
                    parsed["error"],
                )
                continue

            break

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM no respondio tras agotar reintentos",
        )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if "error" in parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"LLM no pudo generar borrador: {parsed['error']}",
        )

    raw_ejercicios = parsed.get("ejercicios") or []
    if not isinstance(raw_ejercicios, list) or not raw_ejercicios:
        if "enunciado" in parsed:
            raw_ejercicios = [parsed]
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM no devolvio ejercicios validos",
            )

    ejercicios = []
    for i, ej in enumerate(raw_ejercicios):
        rubrica = ej.get("rubrica") or {}
        test_cases = ej.get("test_cases") or []
        if not isinstance(rubrica, dict):
            rubrica = {}
        if not isinstance(test_cases, list):
            test_cases = []
        ejercicios.append(
            EjercicioGenerado(
                titulo=str(ej.get("titulo", f"Ejercicio {i + 1}")),
                enunciado=str(ej.get("enunciado", "")),
                inicial_codigo=str(ej.get("inicial_codigo", "")),
                rubrica=rubrica,
                test_cases=test_cases,
            )
        )

    # 6. Audit log structlog (queryable via Loki)
    try:
        import structlog

        structlog.get_logger().info(
            "tp_generated_by_ai",
            tenant_id=str(user.tenant_id),
            user_id=str(user.id),
            materia_id=str(req.materia_id),
            prompt_version=prompt_version_full,
            tokens_input=result.input_tokens,
            tokens_output=result.output_tokens,
            latency_ms=latency_ms,
            provider_used=result.provider,
            model_used=result.model,
            cache_hit=result.cache_hit,
            rag_chunks_used=rag_chunks_used,
            rag_chunks_hash=rag_chunks_hash,
            num_ejercicios=len(ejercicios),
        )
    except ImportError:
        logger.info(
            "tp_generated_by_ai tenant=%s user=%s materia=%s prompt=%s "
            "tokens_in=%d tokens_out=%d latency_ms=%d provider=%s model=%s ejercicios=%d",
            user.tenant_id,
            user.id,
            req.materia_id,
            prompt_version_full,
            result.input_tokens,
            result.output_tokens,
            latency_ms,
            result.provider,
            result.model,
            len(ejercicios),
        )

    return TPGenerateResponse(
        ejercicios=ejercicios,
        prompt_version=prompt_version_full,
        model_used=result.model,
        provider_used=result.provider,
        tokens_input=result.input_tokens,
        tokens_output=result.output_tokens,
        rag_chunks_used=rag_chunks_used,
        rag_chunks_hash=rag_chunks_hash,
    )


# ── Test cases (Sec 9 epic ai-native-completion / ADR-034) ─────────────


@router.get("/{tarea_id}/test-cases")
async def get_tarea_practica_test_cases(
    tarea_id: UUID,
    include_hidden: bool = False,
    user: User = Depends(require_permission("tarea_practica", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Devuelve los test cases de una TP filtrados por rol del caller.

    Filtrado por rol (ADR-034):
      - Estudiante con `include_hidden=true`        => 403.
      - Estudiante (default `include_hidden=false`) => solo `is_public=true`.
      - Docente / docente_admin / superadmin        => respeta `include_hidden`.

    El endpoint NO ejecuta tests (eso lo hace Pyodide client-side en
    web-student). Solo devuelve la metadata.

    Tests `is_public=false` quedan opacos al cliente — defensa critica para
    que el alumno no pueda ver los tests hidden via dev tools del browser.
    """
    is_priv_role = bool({"docente", "docente_admin", "superadmin", "jtp", "auxiliar"} & user.roles)
    if include_hidden and not is_priv_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="include_hidden requiere rol docente, docente_admin o superior",
        )

    svc = TareaPracticaService(db)
    obj = await svc.get(tarea_id)

    raw: list[dict[str, Any]] = list(obj.test_cases or [])
    if include_hidden:
        # Caller privilegiado pidiendo todo — devolvemos sin filtrar
        visible = raw
    else:
        # Default: omitir tests privados (sin importar el rol)
        visible = [tc for tc in raw if tc.get("is_public") is True]

    return {
        "tarea_id": str(tarea_id),
        "test_cases": visible,
        "total_count": len(raw),
        "visible_count": len(visible),
        "include_hidden": include_hidden,
    }


@router.get("/{tarea_id}/ejercicios", response_model=list[TpEjercicioRead])
async def get_tarea_practica_ejercicios(
    tarea_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[TpEjercicioRead]:
    """Lista los ejercicios asociados a una TP, ordenados por `orden`.

    ADR-047: lee de la tabla intermedia `tp_ejercicios` JOIN `ejercicios`
    (cada item incluye el Ejercicio embebido). Lista vacía = TP monolítica.

    A0.3 (seguridad): antes este endpoint devolvía el Ejercicio COMPLETO
    (test cases ocultos con respuesta esperada, `respuesta_pista`, banco
    socrático, misconceptions) a cualquiera con `tarea_practica:read` —
    incluidos los alumnos, que podían leer la solución. Ahora:
      - valida acceso a la comisión de la TP (cierra el IDOR de paso);
      - el alumno recibe la vista saneada (`sanitize_ejercicio_for_student`);
      - docentes / oversight / tutor-service reciben el objeto completo.
    """
    tp_svc = TareaPracticaService(db)
    tp = await tp_svc.get(tarea_id)  # 404 si no existe
    is_staff = await assert_comision_access(db, user, tp.comision_id)
    if not is_staff and tp.estado != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrada")

    svc = TpEjercicioService(db)
    pairs = await svc.list_by_tp(tarea_id)
    result: list[TpEjercicioRead] = []
    for pair, ej in pairs:
        ejercicio = EjercicioRead.model_validate(ej)
        if not is_staff:
            ejercicio = sanitize_ejercicio_for_student(ejercicio)
        result.append(
            TpEjercicioRead(
                id=pair.id,
                tarea_practica_id=pair.tarea_practica_id,
                ejercicio_id=pair.ejercicio_id,
                orden=pair.orden,
                peso_en_tp=pair.peso_en_tp,
                ejercicio=ejercicio,
            )
        )
    return result


@router.post(
    "/{tarea_id}/ejercicios",
    response_model=TpEjercicioRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_ejercicio_to_tarea_practica(
    tarea_id: UUID,
    data: TpEjercicioCreate,
    user: User = Depends(require_permission("tarea_practica", "update")),
    db: AsyncSession = Depends(get_db),
) -> TpEjercicioRead:
    """Asocia un Ejercicio existente del banco a esta TP (ADR-047).

    Solo permitido en TPs con `estado='draft'`. Requiere `orden` único
    dentro de la TP y `peso_en_tp` en `(0, 1]`. Para reordenar o cambiar
    pesos sin quitar el ejercicio, usar PATCH.
    """
    svc = TpEjercicioService(db)
    pair = await svc.add_ejercicio(
        tarea_practica_id=tarea_id,
        ejercicio_id=data.ejercicio_id,
        orden=data.orden,
        peso_en_tp=data.peso_en_tp,
        user=user,
    )
    ej = await svc.ejercicio_repo.get_or_404(pair.ejercicio_id)
    return TpEjercicioRead(
        id=pair.id,
        tarea_practica_id=pair.tarea_practica_id,
        ejercicio_id=pair.ejercicio_id,
        orden=pair.orden,
        peso_en_tp=pair.peso_en_tp,
        ejercicio=EjercicioRead.model_validate(ej),
    )


@router.patch(
    "/{tarea_id}/ejercicios/{ejercicio_id}",
    response_model=TpEjercicioRead,
)
async def update_tp_ejercicio_pair(
    tarea_id: UUID,
    ejercicio_id: UUID,
    data: TpEjercicioUpdate,
    user: User = Depends(require_permission("tarea_practica", "update")),
    db: AsyncSession = Depends(get_db),
) -> TpEjercicioRead:
    """Cambia `orden` y/o `peso_en_tp` de un ejercicio dentro de la TP.

    Solo permitido en TPs con `estado='draft'`. No cambia el `ejercicio_id`
    (para eso, quitar el viejo y agregar el nuevo).
    """
    svc = TpEjercicioService(db)
    pair = await svc.update_pair(
        tarea_practica_id=tarea_id,
        ejercicio_id=ejercicio_id,
        orden=data.orden,
        peso_en_tp=data.peso_en_tp,
        user=user,
    )
    ej = await svc.ejercicio_repo.get_or_404(pair.ejercicio_id)
    return TpEjercicioRead(
        id=pair.id,
        tarea_practica_id=pair.tarea_practica_id,
        ejercicio_id=pair.ejercicio_id,
        orden=pair.orden,
        peso_en_tp=pair.peso_en_tp,
        ejercicio=EjercicioRead.model_validate(ej),
    )


@router.delete(
    "/{tarea_id}/ejercicios/{ejercicio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_ejercicio_from_tarea_practica(
    tarea_id: UUID,
    ejercicio_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "update")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Quita un Ejercicio de la TP. El Ejercicio sobrevive en el banco.

    Solo permitido en TPs con `estado='draft'`.
    """
    svc = TpEjercicioService(db)
    await svc.remove_ejercicio(
        tarea_practica_id=tarea_id,
        ejercicio_id=ejercicio_id,
        user=user,
    )


@router.get("/{tarea_id}/versions", response_model=list[TareaPracticaVersionRef])
async def list_tarea_practica_versions(
    tarea_id: UUID,
    user: User = Depends(require_permission("tarea_practica", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[TareaPracticaVersionRef]:
    svc = TareaPracticaService(db)
    chain = await svc.list_versions(tarea_id)

    latest_published_version: int | None = None
    for t in chain:
        if t.estado == "published":
            if latest_published_version is None or t.version > latest_published_version:
                latest_published_version = t.version

    if latest_published_version is not None:
        current_version = latest_published_version
    else:
        current_version = max(t.version for t in chain)

    return [
        TareaPracticaVersionRef(
            id=t.id,
            version=t.version,
            estado=t.estado,
            titulo=t.titulo,
            created_at=t.created_at,
            is_current=(t.version == current_version),
        )
        for t in chain
    ]
