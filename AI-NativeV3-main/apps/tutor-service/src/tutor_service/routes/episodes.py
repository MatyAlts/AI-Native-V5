"""Endpoints HTTP del tutor-service.

POST /api/v1/episodes                    crear episodio (devuelve episode_id)
GET  /api/v1/episodes/{id}               estado del episodio (recovery del frontend)
POST /api/v1/episodes/{id}/message       SSE con la respuesta del tutor
POST /api/v1/episodes/{id}/close         cerrar episodio (emite evento cierre)
POST /api/v1/episodes/{id}/abandoned     ADR-025: emite EpisodioAbandonado (idempotente)
POST /api/v1/episodes/{id}/reflection    ADR-035: emite ReflexionCompletada (post-cierre, opcional)
POST /api/v1/episodes/{id}/run-tests     ADR-033/034: emite TestsEjecutados (conteos de Pyodide)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tutor_service.auth.dependencies import User, require_role
from tutor_service.config import settings
from tutor_service.services.academic_client import AcademicClient
from tutor_service.services.clients import (
    AIGatewayClient,
    ContentClient,
    CTRClient,
    GovernanceClient,
)
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

router = APIRouter(prefix="/api/v1/episodes", tags=["tutor"])


_redis: redis.Redis | None = None
_tutor: TutorCore | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _get_tutor() -> TutorCore:
    global _tutor
    if _tutor is None:
        _tutor = TutorCore(
            governance=GovernanceClient(settings.governance_service_url),
            content=ContentClient(settings.content_service_url),
            ai_gateway=AIGatewayClient(settings.ai_gateway_url),
            ctr=CTRClient(settings.ctr_service_url),
            sessions=SessionManager(_get_redis()),
            academic=AcademicClient(settings.academic_service_url),
            default_prompt_version=settings.default_prompt_version,
            default_model=settings.default_model,
        )
    return _tutor


_ctr_client: CTRClient | None = None


def _get_ctr_client() -> CTRClient:
    """CTRClient compartido para reads (GET /episodes/{id}).

    El TutorCore ya tiene su propio CTRClient para writes; éste es el
    mismo tipo, separado para hacer override fácil en tests del endpoint.
    """
    global _ctr_client
    if _ctr_client is None:
        _ctr_client = CTRClient(settings.ctr_service_url)
    return _ctr_client


# UUID fijo del service-account del tutor (mismo que `tutor_core.py`).
# Se usa como caller_id al pegarle al ctr-service en lecturas.
TUTOR_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000010")


# ── Schemas ─────────────────────────────────────────────────────────


class OpenEpisodeRequest(BaseModel):
    comision_id: UUID
    problema_id: UUID
    curso_config_hash: str = Field(min_length=64, max_length=64)
    classifier_config_hash: str = Field(min_length=64, max_length=64)
    # ADR-047: UUID del Ejercicio del banco standalone que el estudiante
    # va a resolver. None = TP monolítica (sin ejercicio específico). El
    # `ejercicio_orden` denormalizado se resuelve internamente en el
    # tutor_core via la tabla intermedia tp_ejercicios.
    ejercicio_id: UUID | None = None


class OpenEpisodeResponse(BaseModel):
    episode_id: UUID


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class CloseEpisodeRequest(BaseModel):
    reason: str = "student_closed"


class EpisodeStateResponse(BaseModel):
    """Estado reconstruído del episodio para que el web-student
    recupere el contexto al recargar el browser.

    NO devuelve la cadena completa de eventos del CTR — sólo lo que la UI
    necesita para volver a renderizar la sesión:
      - metadata del episodio (estado, tarea, comisión, fechas)
      - última snapshot del editor de código
      - mensajes user/assistant de la conversación
      - notas personales del estudiante

    Si el episodio está `closed` igual se devuelve, en modo lectura.
    """

    episode_id: UUID
    tarea_practica_id: UUID
    comision_id: UUID
    estado: str  # open | closed
    opened_at: datetime
    closed_at: datetime | None = None
    last_code_snapshot: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("", response_model=OpenEpisodeResponse, status_code=status.HTTP_201_CREATED)
async def open_episode(
    req: OpenEpisodeRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> OpenEpisodeResponse:
    """Abre un episodio respetando feature flags del tenant.

    F6: consulta los flags del tenant para:
      - Modelo LLM (`enable_claude_opus` → opus; sino → sonnet)
      - Enforcement de `max_episodes_per_day` (deferred a F7 cuando tengamos
        contador en Redis; por ahora solo log)
    """
    from platform_ops import FeatureNotDeclaredError

    from tutor_service.services.features import get_flags

    tutor = _get_tutor()

    # Feature flag: modelo LLM por tenant
    flags = get_flags()
    try:
        use_opus = flags.is_enabled(user.tenant_id, "enable_claude_opus")
    except FeatureNotDeclaredError:
        use_opus = False
    model = settings.opus_model if use_opus else settings.default_model

    episode_id = await tutor.open_episode(
        tenant_id=user.tenant_id,
        comision_id=req.comision_id,
        student_pseudonym=user.id,
        problema_id=req.problema_id,
        curso_config_hash=req.curso_config_hash,
        classifier_config_hash=req.classifier_config_hash,
        model=model,
        ejercicio_id=req.ejercicio_id,
    )
    return OpenEpisodeResponse(episode_id=episode_id)


def _build_episode_state(episode_id: UUID, ep: dict[str, Any]) -> EpisodeStateResponse:
    """Reduce el `EpisodeWithEvents` del CTR al subset que la UI necesita.

    Reglas de extracción:
      - last_code_snapshot: payload.code más reciente entre los eventos
        `edicion_codigo` y `codigo_ejecutado` (orden por seq).
      - messages: pares (prompt_enviado, tutor_respondio) en orden de seq.
        prompt_enviado.payload.content → role="user".
        tutor_respondio.payload.content → role="assistant".
      - notes: eventos `nota_personal` con payload.contenido.

    Eventos sin los campos esperados se ignoran silenciosamente — la UI
    debe ser tolerante a versiones viejas del schema.
    """
    events: list[dict[str, Any]] = ep.get("events") or []
    # Asegurar orden por seq aún si el ctr-service no garantiza el orden.
    events = sorted(events, key=lambda e: e.get("seq", 0))

    last_code: str | None = None
    messages: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []

    for ev in events:
        et = ev.get("event_type")
        payload = ev.get("payload") or {}
        ts = ev.get("ts")
        if et in ("edicion_codigo", "codigo_ejecutado"):
            code = payload.get("snapshot") or payload.get("code")
            if isinstance(code, str):
                last_code = code
        elif et == "prompt_enviado":
            content = payload.get("content")
            if isinstance(content, str):
                messages.append({"role": "user", "content": content, "ts": ts})
        elif et == "tutor_respondio":
            content = payload.get("content")
            if isinstance(content, str):
                messages.append({"role": "assistant", "content": content, "ts": ts})
        elif et in ("nota_personal", "nota_estudiante"):
            contenido = payload.get("contenido") or payload.get("content")
            if isinstance(contenido, str):
                notes.append({"contenido": contenido, "ts": ts})

    return EpisodeStateResponse(
        episode_id=episode_id,
        tarea_practica_id=UUID(str(ep["problema_id"])),
        comision_id=UUID(str(ep["comision_id"])),
        estado=ep["estado"],
        opened_at=_parse_dt(ep["opened_at"]),
        closed_at=_parse_dt(closed) if (closed := ep.get("closed_at")) else None,
        last_code_snapshot=last_code,
        messages=messages,
        notes=notes,
    )


def _parse_dt(value: str | datetime) -> datetime:
    """Parsea ISO-8601 con sufijo Z o offset. Acepta datetime ya parseado."""
    if isinstance(value, datetime):
        return value
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


@router.get("/{episode_id}", response_model=EpisodeStateResponse)
async def get_episode_state(
    episode_id: UUID,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> EpisodeStateResponse:
    """Devuelve el estado reconstruído del episodio para recovery del UI.

    Usado por el web-student al montar la vista — si el browser se
    refresca y pierde el `episodeId` en memoria, lo persiste en
    `localStorage` y luego pega acá para reconstruir mensajes, código y
    notas. Funciona también para episodios ya cerrados (modo lectura).

    Errores:
      - 404 si el episodio no existe.
      - 403 si el episodio pertenece a otro tenant.
    """
    ctr = _get_ctr_client()
    ep = await ctr.get_episode(
        episode_id=episode_id,
        tenant_id=user.tenant_id,
        caller_id=TUTOR_SERVICE_USER_ID,
    )
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_id} no encontrado",
        )

    # Defensa en profundidad: si el ctr-service por alguna razón
    # devuelve un episodio de otro tenant (shouldn't happen — RLS
    # debería filtrarlo), no lo expongamos.
    if str(ep.get("tenant_id")) != str(user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Episode pertenece a otro tenant",
        )

    return _build_episode_state(episode_id, ep)


@router.post("/{episode_id}/message")
async def send_message(
    episode_id: UUID,
    req: MessageRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
):
    """SSE streaming de la respuesta del tutor."""
    tutor = _get_tutor()

    async def event_stream():
        try:
            async for event in tutor.interact(episode_id, req.content):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Internal error: {e}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{episode_id}/close", status_code=status.HTTP_204_NO_CONTENT)
async def close_episode(
    episode_id: UUID,
    req: CloseEpisodeRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> None:
    tutor = _get_tutor()
    try:
        await tutor.close_episode(episode_id, reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


class AbandonedEpisodeRequest(BaseModel):
    """ADR-025 (G10-A): payload del POST /episodes/{id}/abandoned.

    Disparado por el frontend en `beforeunload` (cierre de pestana o
    navegacion). El worker server-side emite con reason="timeout" sin pasar
    por este endpoint. Validamos solo los reason que el cliente puede pedir.
    """

    reason: Literal["beforeunload", "explicit"] = Field(
        description=(
            "'beforeunload' = navegador disparo el evento del mismo nombre. "
            "'explicit' = el frontend decidio abandonar (ej. logout, error fatal)."
        )
    )
    last_activity_seconds_ago: float = Field(
        default=0.0,
        ge=0.0,
        le=86400.0,  # cap a 24h, episodios reales son <2h
        description=(
            "Segundos desde la ultima actividad observable del estudiante. "
            "Si el frontend no puede medirlo confiablemente, mandar 0."
        ),
    )


@router.post("/{episode_id}/abandoned", status_code=status.HTTP_204_NO_CONTENT)
async def emit_episodio_abandonado(
    episode_id: UUID,
    req: AbandonedEpisodeRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> None:
    """Emite EpisodioAbandonado al CTR (ADR-025, G10-A).

    Idempotente por diseno: si el episodio ya no tiene sesion activa (ya
    fue cerrado, abandonado por timeout o expirado), responde 204 sin
    emitir. Esto cubre la carrera entre `beforeunload` (frontend) y el
    worker de timeout (server-side) — ambos pueden disparar para el mismo
    episodio en una ventana de segundos.

    El `user_id` autoritativo viene del header X-User-Id (api-gateway) y
    se usa como caller del evento — la accion es del estudiante.

    Estados:
      - 204: evento emitido o sesion ya inactiva (idempotente).
      - 422: payload invalido (reason fuera del enum, last_activity_seconds_ago negativo).

    Triggers tipicos:
      - reason="beforeunload": el browser cerro la pestana o el usuario
        navego afuera. El frontend usa navigator.sendBeacon() preferentemente
        para garantizar el envio.
      - reason="explicit": logout, error fatal en el cliente, switch de
        modo (ej. dejar de practicar).
    """
    tutor = _get_tutor()
    await tutor.record_episodio_abandonado(
        episode_id=episode_id,
        reason=req.reason,
        last_activity_seconds_ago=req.last_activity_seconds_ago,
        user_id=user.id,
    )


class CodigoEjecutadoRequest(BaseModel):
    """Evento emitido por el frontend cuando Pyodide corre código."""

    code: str = Field(..., description="Código Python ejecutado")
    stdout: str = Field(default="", description="Stdout capturado")
    stderr: str = Field(default="", description="Stderr capturado")
    duration_ms: float = Field(..., ge=0, description="Duración de la ejecución")


@router.post(
    "/{episode_id}/events/codigo_ejecutado",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_codigo_ejecutado(
    episode_id: UUID,
    req: CodigoEjecutadoRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento codigo_ejecutado al CTR con seq correcto del episodio.

    Este endpoint es el puente entre la ejecución Pyodide del navegador
    y la cadena criptográfica del CTR. El cliente envía el resultado de
    la ejecución; el tutor-service asigna el seq (atómicamente desde el
    session manager) y publica al ctr-stream, que luego el worker
    persiste en la cadena.

    Idempotencia: el cliente NO debe reintentar este POST en error de
    red — generará una segunda fila con seq distinto. En caso de duda,
    consultar el episodio para ver si el evento quedó registrado.
    """
    tutor = _get_tutor()
    try:
        seq = await tutor.emit_codigo_ejecutado(
            episode_id=episode_id,
            user_id=user.id,
            payload={
                "code": req.code,
                "stdout": req.stdout,
                "stderr": req.stderr,
                "duration_ms": req.duration_ms,
                "runtime": "pyodide-0.26",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {"status": "accepted", "seq": str(seq)}


class EdicionCodigoRequest(BaseModel):
    """Evento emitido por el editor del frontend en cada cambio de código.

    Crítico para CCD: distingue "tipeando/pensando" de "idle". Sin este
    evento, los gaps temporales entre prompts y ejecuciones no son
    interpretables por el clasificador.

    F6: el campo opcional `origin` permite distinguir tipeo directo
    ("student_typed"), copia desde el chat del tutor ("copied_from_tutor")
    o paste externo ("pasted_external"). Es evidencia directa de
    delegación/apropiación que no depende solo de inferencia temporal.
    """

    snapshot: str = Field(
        ...,
        max_length=50000,
        description="Código completo en el momento del evento (≤50KB)",
    )
    diff_chars: int = Field(
        ..., ge=0, description="Cantidad de caracteres cambiados desde evento anterior"
    )
    language: str = Field(default="python", min_length=1, max_length=32)
    origin: Literal["student_typed", "copied_from_tutor", "pasted_external"] | None = Field(
        default=None,
        description=(
            "Procedencia del cambio. None = legacy/desconocido. "
            "F6 — alimenta clasificador para distinguir delegación/apropiación."
        ),
    )


@router.post(
    "/{episode_id}/events/edicion_codigo",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_edicion_codigo(
    episode_id: UUID,
    req: EdicionCodigoRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento edicion_codigo al CTR con el seq correcto del episodio.

    El cliente envía un snapshot del código y la cantidad de caracteres
    cambiados desde el snapshot anterior; el tutor-service asigna el seq
    (atómicamente desde el session manager) y publica al ctr-stream, que
    luego el worker persiste en la cadena.

    Estados:
      - 202: evento aceptado, devuelve `seq` asignado.
      - 409: episodio cerrado, expirado o inexistente (no se aceptan más eventos).
      - 422: validación de payload falló (snapshot >50KB, diff_chars negativo).

    Idempotencia: el cliente NO debe reintentar este POST en error de
    red — generará una segunda fila con seq distinto. El frontend debe
    debounce-ar los eventos para no saturar el CTR.
    """
    tutor = _get_tutor()
    try:
        seq = await tutor.record_edicion_codigo(
            episode_id=episode_id,
            snapshot=req.snapshot,
            diff_chars=req.diff_chars,
            language=req.language,
            user_id=user.id,
            origin=req.origin,
        )
    except ValueError as e:
        # Sesión inexistente o eliminada (cierre/expiración) → episodio
        # ya no acepta eventos.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {"status": "accepted", "seq": str(seq)}


class LecturaEnunciadoRequest(BaseModel):
    """Evento emitido por el frontend al acumular tiempo de lectura del panel.

    El frontend mide visibilidad del panel del enunciado con
    IntersectionObserver + visibilitychange y emite cada ~30s acumulados
    O al cerrar el episodio. Es la señal observable canónica de N1
    (Comprensión).
    """

    duration_seconds: float = Field(
        ...,
        ge=0,
        le=86400,  # un día — sanity cap, episodios reales <2h
        description="Segundos acumulados de lectura visible desde la última emisión",
    )


@router.post(
    "/{episode_id}/events/lectura_enunciado",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_lectura_enunciado(
    episode_id: UUID,
    req: LecturaEnunciadoRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento lectura_enunciado (LecturaEnunciado) al CTR.

    Estados:
      - 202: evento aceptado, devuelve `seq` asignado.
      - 409: episodio cerrado, expirado o inexistente.
      - 422: validación de payload falló (duration_seconds negativo o >86400).

    El `user_id` autoritativo es el del estudiante (header X-User-Id) —
    la lectura es del estudiante, su acción directa.

    Idempotencia: el cliente NO debe reintentar este POST en error de red
    — generaría doble contabilización. Si el cliente pierde respuesta,
    asume que el delta NO se acumuló y vuelve a contar desde 0.
    """
    tutor = _get_tutor()
    try:
        seq = await tutor.record_lectura_enunciado(
            episode_id=episode_id,
            duration_seconds=req.duration_seconds,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {"status": "accepted", "seq": str(seq)}


class AnotacionCreadaRequest(BaseModel):
    """Evento emitido por el frontend cuando el estudiante guarda una nota.

    Es la señal explícita de reflexión que alimenta CCD orphan ratio.
    Sin este evento, los episodios reflexivos quedan marcados como
    huérfanos de evidencia y se distorsiona la métrica.
    """

    contenido: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Texto de la nota personal del estudiante (1–5000 chars)",
    )


@router.post(
    "/{episode_id}/events/anotacion_creada",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_anotacion_creada(
    episode_id: UUID,
    req: AnotacionCreadaRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento anotacion_creada (AnotacionCreada) al CTR.

    Estados:
      - 202: evento aceptado, devuelve `seq` asignado.
      - 409: episodio cerrado, expirado o inexistente (no se aceptan más eventos).
      - 422: validación de payload falló (vacío o >5000 chars).

    El `user_id` autoritativo es el del estudiante (header `X-User-Id`
    inyectado por el api-gateway) — la nota es del estudiante, su autoría.

    Idempotencia: el cliente NO debe reintentar este POST en error de red
    — cada POST exitoso registra una nueva nota con seq distinto.
    """
    tutor = _get_tutor()
    # Defensa adicional: contenido sólo whitespace no aporta señal y
    # rompería la semántica de "reflexión explícita".
    if not req.contenido.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="contenido no puede ser vacío o sólo whitespace",
        )
    try:
        seq = await tutor.record_anotacion_creada(
            episode_id=episode_id,
            contenido=req.contenido,
            user_id=user.id,
        )
    except ValueError as e:
        # Sesión inexistente o eliminada (cierre/expiración) → episodio
        # ya no acepta eventos.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {"status": "accepted", "seq": str(seq)}


class RunTestsRequest(BaseModel):
    """Conteos de la corrida de tests Pyodide (ADR-033/034, Sec 9 epic).

    El cliente NO manda la lista detallada de tests ni el codigo del alumno —
    solo conteos agregados. Defensa de privacidad + cardinalidad del CTR.
    Tests `is_public=false` quedan opacos al cliente (filtrados en el
    endpoint de `tareas-practicas/{id}/test-cases?include_hidden=false`),
    asi que `tests_hidden` debe llegar 0 en piloto-1.
    """

    test_count_total: int = Field(ge=0)
    test_count_passed: int = Field(ge=0)
    test_count_failed: int = Field(ge=0)
    tests_publicos: int = Field(ge=0)
    tests_hidden: int = Field(
        ge=0,
        le=0,
        description="Siempre 0 en piloto-1 — los tests hidden no se ejecutan client-side.",
    )
    ejecucion_ms: int = Field(ge=0, le=10 * 60 * 1000)  # cap a 10min
    chunks_used_hash: str | None = Field(default=None, min_length=64, max_length=64)


@router.post(
    "/{episode_id}/run-tests",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_tests_ejecutados(
    episode_id: UUID,
    req: RunTestsRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite tests_ejecutados al CTR con conteos del cliente Pyodide.

    Estados:
      - 202: evento aceptado, devuelve seq.
      - 409: episodio cerrado, expirado o inexistente.
      - 422: payload invalido (conteos inconsistentes, tests_hidden!=0).

    El user_id autoritativo es el del estudiante (header X-User-Id) — la
    ejecucion es del estudiante, su accion directa.
    """
    tutor = _get_tutor()
    try:
        seq = await tutor.emit_tests_ejecutados(
            episode_id=episode_id,
            user_id=user.id,
            test_count_total=req.test_count_total,
            test_count_passed=req.test_count_passed,
            test_count_failed=req.test_count_failed,
            tests_publicos=req.tests_publicos,
            tests_hidden=req.tests_hidden,
            ejecucion_ms=req.ejecucion_ms,
            chunks_used_hash=req.chunks_used_hash,
        )
    except ValueError as e:
        msg = str(e)
        # 422 si conteos inconsistentes; 409 si sesion no existe.
        if "Conteos inconsistentes" in msg or "tests_hidden" in msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return {"status": "accepted", "seq": str(seq)}


class ReflectionRequest(BaseModel):
    """Cuerpo del POST /api/v1/episodes/{id}/reflection (ADR-035).

    Cuestionario opcional metacognitivo que el estudiante responde post-cierre
    del episodio. Cada campo libre <=500 chars; el frontend ya recorta pero
    el backend valida defensivo. `prompt_version` identifica el cuestionario
    activo (ej. "reflection/v1.0.0") para distinguir reflexiones tomadas con
    versiones distintas en analisis longitudinal.
    """

    que_aprendiste: str = Field(min_length=0, max_length=500)
    dificultad_encontrada: str = Field(min_length=0, max_length=500)
    que_haria_distinto: str = Field(min_length=0, max_length=500)
    prompt_version: str = Field(
        default="reflection/v1.0.0",
        max_length=64,
        description="Identificador del cuestionario, ej. 'reflection/v1.0.0'.",
    )
    tiempo_completado_ms: int = Field(
        ge=0,
        le=24 * 3600 * 1000,
        description=(
            "Milisegundos transcurridos entre apertura del modal y submit. "
            "Cap a 24h por sanity (modales reales son <5min)."
        ),
    )


@router.post("/{episode_id}/reflection", status_code=status.HTTP_202_ACCEPTED)
async def emit_reflexion_completada(
    episode_id: UUID,
    req: ReflectionRequest,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite reflexion_completada al CTR DESPUES del cierre del episodio (ADR-035).

    Modal opcional metacognitivo. El cierre del episodio NO espera la
    respuesta — son flujos independientes. El CTR es append-only: un episodio
    con `estado=closed` sigue aceptando eventos posteriores y la cadena
    criptografica continua (chain_hash sigue ligando seq+1 al anterior).

    Privacy: el contenido textual viaja como string libre. El export academico
    (`packages/platform-ops/academic_export.py`) redacta los 3 campos por
    default; investigador con consentimiento usa `--include-reflections`.

    Estados:
      - 202: evento aceptado, devuelve seq asignado.
      - 404: episodio no encontrado o de otro tenant.
      - 409: episodio no esta cerrado (la reflexion solo se acepta post-cierre).
      - 422: payload invalido (campos > 500 chars o tiempo_completado_ms negativo).

    El user_id autoritativo es el del estudiante (header X-User-Id) — la
    reflexion es del estudiante, su autoria.
    """
    tutor = _get_tutor()
    try:
        seq = await tutor.record_reflexion_completada(
            episode_id=episode_id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            que_aprendiste=req.que_aprendiste,
            dificultad_encontrada=req.dificultad_encontrada,
            que_haria_distinto=req.que_haria_distinto,
            prompt_version=req.prompt_version,
            tiempo_completado_ms=req.tiempo_completado_ms,
        )
    except ValueError as e:
        msg = str(e)
        # 404 si el episodio no existe o es de otro tenant; 409 si no esta cerrado.
        if "no encontrado" in msg or "otro tenant" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)

    return {"status": "accepted", "seq": str(seq)}
