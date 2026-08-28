"""Endpoints HTTP del tutor-service.

POST /api/v1/episodes                    crear episodio (devuelve episode_id)
GET  /api/v1/episodes/{id}               estado del episodio (recovery del frontend)
POST /api/v1/episodes/{id}/message       SSE con la respuesta del tutor
POST /api/v1/episodes/{id}/close         cerrar episodio (emite evento cierre)
POST /api/v1/episodes/{id}/abandoned     ADR-025: emite EpisodioAbandonado (idempotente)
POST /api/v1/episodes/{id}/resume        ADR-055: reanuda episodio pausado (reconstruye sesión)
POST /api/v1/episodes/{id}/reflection    ADR-035: emite ReflexionCompletada (post-cierre, opcional)
POST /api/v1/episodes/{id}/run-tests     ADR-033/034: emite TestsEjecutados (conteos de Pyodide)
"""

from __future__ import annotations

import contextlib
import json
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, status
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
from tutor_service.services.guardrails import OveruseDetector
from tutor_service.services.session import SeqReservationPendingError, SessionManager
from tutor_service.services.tutor_core import TutorCore

router = APIRouter(prefix="/api/v1/episodes", tags=["tutor"])


_redis: redis.Redis | None = None
_tutor: TutorCore | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        # Resiliencia (FIX-20): evita usar conexiones colgadas y reintenta en timeout.
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=30,
            retry_on_timeout=True,
            socket_keepalive=True,
        )
    return _redis


def _get_tutor() -> TutorCore:
    global _tutor
    if _tutor is None:
        _tutor = TutorCore(
            governance=GovernanceClient(
                settings.governance_service_url,
                internal_service_token=settings.internal_service_token,
            ),
            content=ContentClient(settings.content_service_url),
            ai_gateway=AIGatewayClient(
                settings.ai_gateway_url,
                internal_service_token=settings.internal_service_token,
            ),
            ctr=CTRClient(settings.ctr_service_url),
            sessions=SessionManager(_get_redis()),
            academic=AcademicClient(settings.academic_service_url),
            default_prompt_version=settings.default_prompt_version,
            default_model=settings.default_model,
            # FIX (2026-06-10): el detector de sobreuso existía pero NUNCA se
            # inyectaba → self.overuse_detector quedaba None y el bloque de
            # deteccion (tutor_core.py) no corria. Cero eventos overuse en prod.
            overuse_detector=OveruseDetector(_get_redis()),
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


async def _idempotent_seq(
    episode_id: UUID,
    idempotency_key: str | None,
    emit: Callable[[], Awaitable[int]],
) -> int:
    """Envuelve la emisión de un evento CTR con dedup por Idempotency-Key (P-17).

    La cola offline del ctr-client (`packages/ctr-client`) reintenta un POST
    cuando pierde el ACK de una request que el servidor SÍ persistió, reenviando
    el MISMO `event_uuid` de cliente (que llega en el header `Idempotency-Key`).
    Sin dedup, cada reintento llama a `next_seq()` y avanza el contador de
    sesión, dejando un hueco en la secuencia que el partition_worker no puede
    cerrar → el episodio queda `integrity_compromised` de forma permanente.

    Delega en `SessionManager.reserve_or_get_seq` (FIX A), que hace el claim de
    idempotencia de forma ATÓMICA (HSETNX ANTES de reservar el seq). Esto cierra
    el race del check-then-act previo (`get_seen_seq`→`emit`→`mark_seen`), donde
    dos coroutines con el mismo `event_uuid` veían `seen=None` y ambas emitían.

    Sin header (`idempotency_key=None`) el comportamiento es idéntico al previo:
    los callers legacy que no mandan el header no cambian.
    """
    sessions = _get_tutor().sessions
    try:
        return await sessions.reserve_or_get_seq(episode_id, idempotency_key, emit)
    except SeqReservationPendingError as e:
        # Caso degenerado y raro (ganador del claim en otra réplica, lento o
        # caído). Fail-safe: NO duplicamos ni inventamos seq — pedimos reintento.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reserva de secuencia en curso, reintentá en un momento.",
        ) from e


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
    # multi-language-research-integrity (episode-language-provenance, D1):
    # deliberadamente SIN campo `language`. El lenguaje del episodio es dato
    # de procedencia para la tesis doctoral y se resuelve EXCLUSIVAMENTE
    # server-side en `TutorCore._resolve_episode_language` desde el
    # Ejercicio/TareaPractica — nunca del cliente. Si alguna vez agregás un
    # campo `language` acá para "que el frontend lo mande", estás
    # reintroduciendo el precedente peligroso que este mismo change señala
    # (`edicion_codigo` hoy manda `language:"python"` hardcodeado desde
    # `web-student/EpisodePage.tsx` — un dato que PARECE procedencia real y
    # no lo es). No lo repitas acá. Cualquier `language` que un cliente
    # meta en el body queda ignorado por Pydantic (`extra="ignore"`
    # default) — test en test_episode_language_provenance.py.


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
    estado: str  # open | paused | closed
    opened_at: datetime
    closed_at: datetime | None = None
    last_code_snapshot: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    # ADR-049/055: ejercicio del banco asociado al episodio (None = TP
    # monolítica). Sale del payload de episodio_abierto — el frontend lo usa
    # para decidir si un episodio pausado corresponde al contexto que el
    # alumno quiere retomar.
    ejercicio_id: UUID | None = None
    ejercicio_orden: int | None = None


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


async def _emitir_con_heal(
    episode_id: UUID,
    idempotency_key: str | None,
    user: User,
    emit: Callable[[], Awaitable[int]],
) -> int:
    """Emite un evento CTR; si la sesión no existe, la reconstruye y reintenta.

    La sesión Redis puede faltar por dos motivos bien distintos: venció su TTL,
    o el `partition_worker` la invalidó al mandar un evento a la DLQ (el heal
    del contador de seq). En los dos casos el episodio puede seguir vivo y el
    alumno seguir trabajando.

    Sin este reintento el handler responde 409 y el `ctr-client` lo trata como
    definitivo — un 4xx que no sea 408/429 se descarta sin reintentar. El
    trabajo del alumno se perdería justo en el momento en que el sistema está
    intentando recuperarse de una desincronización, que es exactamente el
    incidente que el heal viene a resolver.

    `resume_episode` valida dueño, tenant y estado, así que un episodio
    realmente cerrado sigue devolviendo 409. Eso separa dos casos que hasta
    ahora compartían código de respuesta: «sesión ausente pero episodio vivo»
    (recuperable) y «episodio cerrado» (definitivo).

    Reintentar con el mismo `Idempotency-Key` es seguro: si el primer intento
    falló, `reserve_or_get_seq` liberó el claim con HDEL y el reintento lo
    vuelve a ganar.
    """
    try:
        return await _idempotent_seq(episode_id, idempotency_key, emit)
    except ValueError as sin_sesion:
        try:
            await _get_tutor().resume_episode(
                episode_id=episode_id,
                tenant_id=user.tenant_id,
                user_id=user.id,
            )
        except HTTPException:
            # El episodio esta cerrado, es de otro alumno o de otro tenant.
            # El codigo que devuelve `resume_episode` YA es la respuesta
            # correcta (409/403/404) y es mas preciso que el 409 generico.
            raise
        except Exception:
            # El heal no pudo correr (CTR caido, Redis caido, lo que sea).
            # Degradamos al comportamiento previo en vez de convertir un
            # 409 conocido en un 500 nuevo.
            raise sin_sesion from None
        return await _idempotent_seq(episode_id, idempotency_key, emit)


def _build_episode_state(episode_id: UUID, ep: dict[str, Any]) -> EpisodeStateResponse:
    """Reduce el `EpisodeWithEvents` del CTR al subset que la UI necesita.

    Reglas de extracción:
      - last_code_snapshot: payload.code más reciente entre los eventos
        `edicion_codigo` y `codigo_ejecutado` (orden por seq).
      - messages: pares (prompt_enviado, tutor_respondio) en orden de seq.
        prompt_enviado.payload.content → role="user".
        tutor_respondio.payload.content → role="assistant".
      - notes: eventos `anotacion_creada` con payload.content.

    Eventos sin los campos esperados se ignoran silenciosamente — la UI
    debe ser tolerante a versiones viejas del schema.
    """
    events: list[dict[str, Any]] = ep.get("events") or []
    # Asegurar orden por seq aún si el ctr-service no garantiza el orden.
    events = sorted(events, key=lambda e: e.get("seq", 0))

    # ADR-049/055: contexto de ejercicio desde el episodio_abierto (seq=0).
    ejercicio_id: UUID | None = None
    ejercicio_orden: int | None = None
    if events and events[0].get("event_type") == "episodio_abierto":
        abierto = events[0].get("payload") or {}
        ej_raw = abierto.get("ejercicio_id")
        if ej_raw:
            try:
                ejercicio_id = UUID(str(ej_raw))
            except ValueError:
                ejercicio_id = None
        orden_raw = abierto.get("ejercicio_orden")
        ejercicio_orden = orden_raw if isinstance(orden_raw, int) else None

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
        elif et in ("anotacion_creada", "nota_personal", "nota_estudiante"):
            # El evento real es `anotacion_creada` con `payload.content` — asi
            # lo emite `record_anotacion_creada` y asi lo define el contrato
            # (`AnotacionCreadaPayload`). Este filtro buscaba `nota_personal`
            # y `nota_estudiante`, dos literales que no existen en ninguna
            # parte del codigo: las notas del alumno nunca se reconstruian.
            # Escribia su reflexion, refrescaba, y el panel aparecia vacio —
            # el dato seguia intacto en la cadena, pero el no volvia a verlo.
            #
            # Los dos nombres viejos se conservan por el criterio del
            # docstring (tolerar versiones anteriores del schema); no cuestan
            # nada y cubren cualquier evento historico que los usara.
            contenido = payload.get("content") or payload.get("contenido")
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
        ejercicio_id=ejercicio_id,
        ejercicio_orden=ejercicio_orden,
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


async def _enforce_message_rate_limit(user_id: UUID) -> None:
    """Rate limit por usuario del POST /message. Ventana de 60s en Redis.

    Protege el budget de IA de la comision contra rafagas (un alumno con un
    script mandando cientos de requests). Fail-open: si Redis no responde NO
    bloqueamos — es proteccion de budget, no de seguridad critica, y no queremos
    tumbar el tutor si Redis hipa.
    """
    key = f"tutor:msg_rate:{user_id}"
    try:
        redis_client = _get_redis()
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
    except Exception:
        return
    if count > settings.message_rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Estas mandando mensajes muy rapido. Espera unos segundos.",
        )


@router.post("/{episode_id}/message")
async def send_message(
    episode_id: UUID,
    req: MessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
):
    """SSE streaming de la respuesta del tutor.

    FIX B: el frontend manda un `Idempotency-Key` estable por turno (messageUuid)
    que reusa en el "Reintentar" de UI-8. Se propaga a `interact()` para
    deduplicar el `prompt_enviado`: si el LLM falla a mitad y el alumno
    reintenta, el prompt NO se re-emite (mismo seq, sin re-publicar), evitando
    prompts huérfanos que inflarían CCD_orphan_ratio y el conteo de la tesis.
    """
    await _enforce_message_rate_limit(user.id)
    tutor = _get_tutor()

    # Curar la sesion ANTES de abrir el stream. `interact()` es un generador:
    # si falla en el primer paso, el error ya viaja como evento SSE y no queda
    # forma limpia de reintentar sin arriesgar duplicar lo emitido.
    #
    # La sesion puede faltar por TTL o porque el `partition_worker` intervino
    # tras un evento que no entro en la cadena. En los dos casos el episodio
    # puede seguir vivo, y sin esto la conversacion con el tutor se pierde —
    # que para la trazabilidad pesa igual que el codigo: es lo que distingue
    # haber pensado de haber copiado.
    #
    # Fail-safe: si el heal no puede correr, seguimos igual y `interact()`
    # falla como antes. No convertimos un error conocido en uno nuevo.
    if await tutor.sessions.get(episode_id) is None:
        with contextlib.suppress(Exception):
            await tutor.resume_episode(
                episode_id=episode_id,
                tenant_id=user.tenant_id,
                user_id=user.id,
            )

    async def event_stream():
        try:
            async for event in tutor.interact(
                episode_id, req.content, prompt_idempotency_key=idempotency_key
            ):
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


class ResumeEpisodeResponse(BaseModel):
    """Contexto del episodio reanudado (ADR-055, fix 2026-06-10 #2).

    `problema_id` puede venir None en el caso idempotente (la sesión ya
    estaba viva y no guarda la TP) — el frontend que reanuda desde el
    selector de TPs ya conoce la tarea; el que reanuda por hydration usa
    GET /episodes/{id} para el detalle.
    """

    episode_id: UUID
    problema_id: UUID | None = None
    comision_id: UUID
    ejercicio_id: UUID | None = None
    ejercicio_orden: int | None = None


@router.post("/{episode_id}/resume", response_model=ResumeEpisodeResponse)
async def resume_episode(
    episode_id: UUID,
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> ResumeEpisodeResponse:
    """Reanuda un episodio pausado por abandono (ADR-055, fix 2026-06-10 #2).

    Reconstruye la sesión Redis desde la cadena CTR persistida (seq =
    events_count, historia conversacional, último código). NO emite evento:
    la reanudación es derivable de la cadena (episodio_abandonado seguido de
    más eventos) y el partition_worker repone `estado=open` con el primer
    evento posterior.

    Solo el estudiante dueño puede retomar su episodio, y la TP tiene que
    seguir vigente (mismas validaciones que la apertura).

    Estados:
      - 200: sesión reconstruida (o ya viva — idempotente).
      - 404: episodio o TP inexistente.
      - 403: episodio de otro estudiante / otro tenant.
      - 409: episodio cerrado o TP fuera de plazo.
    """
    tutor = _get_tutor()
    ctx = await tutor.resume_episode(
        episode_id=episode_id,
        tenant_id=user.tenant_id,
        user_id=user.id,
    )
    return ResumeEpisodeResponse(**ctx)


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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento codigo_ejecutado al CTR con seq correcto del episodio.

    Este endpoint es el puente entre la ejecución Pyodide del navegador
    y la cadena criptográfica del CTR. El cliente envía el resultado de
    la ejecución; el tutor-service asigna el seq (atómicamente desde el
    session manager) y publica al ctr-stream, que luego el worker
    persiste en la cadena.

    Idempotencia (P-17): si el ctr-client reintenta este POST mandando el
    mismo `event_uuid` de cliente en el header `Idempotency-Key`, devolvemos
    el mismo seq sin avanzar el contador ni re-publicar al CTR.
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.emit_codigo_ejecutado(
                episode_id=episode_id,
                user_id=user.id,
                payload={
                    "code": req.code,
                    "stdout": req.stdout,
                    "stderr": req.stderr,
                    "duration_ms": req.duration_ms,
                    "runtime": "pyodide-0.26",
                },
            ),
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
    ("student_typed"), copia desde el chat del tutor ("copied_from_tutor"),
    paste externo ("pasted_external") o expansión de un snippet de ceremonia
    del editor ("snippet_expanded"). Es evidencia directa de
    delegación/apropiación que no depende solo de inferencia temporal.

    ⚠️ Este Literal ESPEJA `EdicionCodigoPayload.origin` de
    `packages/contracts` — es el schema de entrada del endpoint, así que un
    valor que falte acá se rechaza con 422 ANTES de llegar al contrato, aunque
    el contrato ya lo acepte. Agregar un valor obliga a tocar los dos, más la
    firma de `tutor_core.record_edicion_codigo`.
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
    origin: (
        Literal["student_typed", "copied_from_tutor", "pasted_external", "snippet_expanded"] | None
    ) = Field(
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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

    Idempotencia (P-17): si el ctr-client reintenta este POST mandando el
    mismo `event_uuid` de cliente en el header `Idempotency-Key`, devolvemos
    el mismo seq sin avanzar el contador ni re-publicar al CTR. El frontend
    igual debe debounce-ar los eventos para no saturar el CTR.
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_edicion_codigo(
                episode_id=episode_id,
                snapshot=req.snapshot,
                diff_chars=req.diff_chars,
                language=req.language,
                user_id=user.id,
                origin=req.origin,
            ),
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento lectura_enunciado (LecturaEnunciado) al CTR.

    Estados:
      - 202: evento aceptado, devuelve `seq` asignado.
      - 409: episodio cerrado, expirado o inexistente.
      - 422: validación de payload falló (duration_seconds negativo o >86400).

    El `user_id` autoritativo es el del estudiante (header X-User-Id) —
    la lectura es del estudiante, su acción directa.

    Idempotencia (P-17): si el ctr-client reintenta este POST mandando el
    mismo `event_uuid` de cliente en el header `Idempotency-Key`, devolvemos
    el mismo seq sin avanzar el contador ni re-publicar al CTR (evita doble
    contabilización del delta).
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_lectura_enunciado(
                episode_id=episode_id,
                duration_seconds=req.duration_seconds,
                user_id=user.id,
            ),
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento anotacion_creada (AnotacionCreada) al CTR.

    Estados:
      - 202: evento aceptado, devuelve `seq` asignado.
      - 409: episodio cerrado, expirado o inexistente (no se aceptan más eventos).
      - 422: validación de payload falló (vacío o >5000 chars).

    El `user_id` autoritativo es el del estudiante (header `X-User-Id`
    inyectado por el api-gateway) — la nota es del estudiante, su autoría.

    Idempotencia (P-17): si el ctr-client reintenta este POST mandando el
    mismo `event_uuid` de cliente en el header `Idempotency-Key`, devolvemos
    el mismo seq sin avanzar el contador ni re-publicar al CTR.
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
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_anotacion_creada(
                episode_id=episode_id,
                contenido=req.contenido,
                user_id=user.id,
            ),
        )
    except ValueError as e:
        # Sesión inexistente o eliminada (cierre/expiración) → episodio
        # ya no acepta eventos.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {"status": "accepted", "seq": str(seq)}


# ── Integridad: foco y clipboard ────────────────────────────────────────


class PestanaPerdidaRequest(BaseModel):
    """Disparada por el frontend cuando el alumno cambia de pestaña/blur."""

    trigger: Literal["visibilitychange", "blur"] = Field(
        description="Evento DOM que disparo la deteccion"
    )


@router.post(
    "/{episode_id}/events/pestana_perdida",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_pestana_perdida(
    episode_id: UUID,
    req: PestanaPerdidaRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento pestana_perdida al CTR.

    El frontend lo dispara con `document.visibilitychange` o `window.blur`.
    NO se puede bloquear desde browser — esto es solo registro side-channel.
    El worker de abandono cierra el episodio si supera el umbral configurado.

    Idempotencia (P-17): si el ctr-client reintenta este POST mandando el
    mismo `event_uuid` de cliente en el header `Idempotency-Key`, devolvemos
    el mismo seq sin avanzar el contador ni re-publicar al CTR. Estos eventos
    disparan en cada cambio de pestaña — el reintento del ACK-perdido es el
    caso que envenenaba el episodio antes del fix.
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_pestana_perdida(
                episode_id=episode_id,
                user_id=user.id,
                trigger=req.trigger,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"status": "accepted", "seq": str(seq)}


class PestanaRecuperadaRequest(BaseModel):
    tiempo_fuera_segundos: float = Field(ge=0, le=86400)


@router.post(
    "/{episode_id}/events/pestana_recuperada",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_pestana_recuperada(
    episode_id: UUID,
    req: PestanaRecuperadaRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento pestana_recuperada al CTR.

    Idempotencia (P-17): dedup por header `Idempotency-Key` (event_uuid de
    cliente) — el reintento devuelve el mismo seq sin avanzar el contador.
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_pestana_recuperada(
                episode_id=episode_id,
                user_id=user.id,
                tiempo_fuera_segundos=req.tiempo_fuera_segundos,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"status": "accepted", "seq": str(seq)}


class CopiaIntentadaRequest(BaseModel):
    seleccion_chars: int = Field(ge=0)
    metodo: Literal["shortcut", "menu_contextual"] = "shortcut"


@router.post(
    "/{episode_id}/events/copia_intentada",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_copia_intentada(
    episode_id: UUID,
    req: CopiaIntentadaRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento copia_intentada al CTR (la UI bloquea la accion).

    Idempotencia (P-17): dedup por header `Idempotency-Key` (event_uuid de
    cliente) — el reintento devuelve el mismo seq sin avanzar el contador.
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_copia_intentada(
                episode_id=episode_id,
                user_id=user.id,
                seleccion_chars=req.seleccion_chars,
                metodo=req.metodo,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"status": "accepted", "seq": str(seq)}


class PegaIntentadaRequest(BaseModel):
    contenido_longitud: int = Field(ge=0)
    contenido_preview: str = Field(max_length=200)
    metodo: Literal["shortcut", "menu_contextual", "drag_drop"] = "shortcut"


@router.post(
    "/{episode_id}/events/pega_intentada",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_pega_intentada(
    episode_id: UUID,
    req: PegaIntentadaRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite evento pega_intentada al CTR (la UI bloquea la accion).

    Idempotencia (P-17): dedup por header `Idempotency-Key` (event_uuid de
    cliente) — el reintento devuelve el mismo seq sin avanzar el contador.
    """
    tutor = _get_tutor()
    try:
        seq = await _emitir_con_heal(
            episode_id,
            idempotency_key,
            user,
            lambda: tutor.record_pega_intentada(
                episode_id=episode_id,
                user_id=user.id,
                contenido_longitud=req.contenido_longitud,
                contenido_preview=req.contenido_preview,
                metodo=req.metodo,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"status": "accepted", "seq": str(seq)}


class RunTestsRequest(BaseModel):
    """Conteos de la corrida de tests (ADR-033/034 Sec 9; ADR-060 server-side).

    El cliente NO manda la lista detallada de tests ni el codigo del alumno —
    solo conteos agregados. Defensa de privacidad + cardinalidad del CTR.

    `tests_hidden` YA NO se capea a 0. El `le=0` original describia el mundo en
    que la unica ejecucion era client-side: los tests `is_public=false` quedan
    opacos al navegador, asi que un cliente Pyodide no podia haber corrido
    ninguno. Con el `execution-service` (ADR-060) los ocultos SI se ejecutan —
    server-side, que es justamente donde el alumno no los ve — y el conteo real
    es por primera vez distinto de cero.

    Ese `le=0` era un bloqueo silencioso del cableo: `ctr_emitter.build_payload`
    del execution-service ya producia el conteo real, y este endpoint lo habria
    rechazado con 422 en cuanto un ejercicio tuviera un caso oculto. Es la misma
    forma que el techo de `max_tokens` del ai-gateway — el schema de entrada
    corta antes de que el contrato importe.
    """

    test_count_total: int = Field(ge=0)
    test_count_passed: int = Field(ge=0)
    test_count_failed: int = Field(ge=0)
    tests_publicos: int = Field(ge=0)
    tests_hidden: int = Field(
        ge=0,
        description=(
            "Casos ocultos ejecutados. 0 desde el cliente Pyodide (no los ve); "
            "real desde el execution-service, que corre server-side."
        ),
    )
    ejecucion_ms: int = Field(ge=0, le=10 * 60 * 1000)  # cap a 10min
    chunks_used_hash: str | None = Field(default=None, min_length=64, max_length=64)
    execution_engine: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Motor que corrio los casos ('pyodide', 'docker-java'). Informativo: "
            "el classifier NO lo consulta, asi que es inerte para la clasificacion "
            "y no obliga a bumpear LABELER_VERSION."
        ),
    )


def _es_emisor_interno(token: str | None) -> bool:
    """True si la llamada viene de un servicio interno, probado por secreto.

    NO alcanza con que el header ESTE presente: el api-gateway no filtra
    `X-Internal-Service-Token` (no lo menciona en ningun lado), asi que un
    navegador puede mandarlo forjado y llega igual. Lo que prueba procedencia es
    conocer el valor, que nunca sale del servidor.

    Falla CERRADO: sin secreto configurado no hay forma de verificar a nadie, asi
    que nadie es interno. En dev eso significa que el execution-service no puede
    reportar ocultos hasta que se comparta el token — preferible a que un browser
    pueda hacerlo por default.

    `compare_digest` y no `==`: comparar secretos con `==` corta en el primer
    byte distinto y filtra el token por temporizacion.
    """
    esperado = settings.internal_service_token
    if not esperado or not token:
        return False
    return secrets.compare_digest(token, esperado)


@router.post(
    "/{episode_id}/run-tests",
    status_code=status.HTTP_202_ACCEPTED,
)
async def emit_tests_ejecutados(
    episode_id: UUID,
    req: RunTestsRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_internal_service_token: str | None = Header(default=None),
    user: User = Depends(require_role("estudiante", "docente", "docente_admin", "superadmin")),
) -> dict[str, str]:
    """Emite tests_ejecutados al CTR con conteos del cliente Pyodide.

    Estados:
      - 202: evento aceptado, devuelve seq.
      - 409: episodio cerrado, expirado o inexistente.
      - 422: payload invalido (conteos inconsistentes, tests_hidden!=0).

    El user_id autoritativo es el del estudiante (header X-User-Id) — la
    ejecucion es del estudiante, su accion directa.

    Idempotencia (P-17): dedup por header `Idempotency-Key`, igual que las otras
    ocho rutas de evento. Era la UNICA que no lo tenia, y desde que este evento
    viaja por la cola durable del `ctr-client` eso dejo de ser cosmetico: la cola
    reintenta hasta `DEFAULT_MAX_ATTEMPTS` veces cuando pierde el ACK de una
    request que el servidor SI proceso, y sin dedup cada reintento appendeaba
    otro `tests_ejecutados`. El evento del que el labeler deriva N3 vs N4 pasaba
    de perderse (visible) a duplicarse (silencioso) — que es peor.

    Se envuelve en `_idempotent_seq` y NO en `_emitir_con_heal`: esta ruta
    levanta `ValueError` tambien por payload invalido (conteos inconsistentes,
    `tests_hidden != 0`), y el heal dispararia un `resume_episode` completo
    —tres round-trips inter-servicio— ante un request malformado. El dedup es
    lo que arregla el bug; el heal traeria un amplificador de carga.
    """
    tutor = _get_tutor()
    try:
        seq = await _idempotent_seq(
            episode_id,
            idempotency_key,
            lambda: tutor.emit_tests_ejecutados(
                episode_id=episode_id,
                user_id=user.id,
                test_count_total=req.test_count_total,
                test_count_passed=req.test_count_passed,
                test_count_failed=req.test_count_failed,
                tests_publicos=req.tests_publicos,
                tests_hidden=req.tests_hidden,
                ejecucion_ms=req.ejecucion_ms,
                chunks_used_hash=req.chunks_used_hash,
                emisor_interno=_es_emisor_interno(x_internal_service_token),
            ),
        )
    except ValueError as e:
        msg = str(e)
        # 422 si conteos inconsistentes; 409 si sesion no existe.
        if "Conteos inconsistentes" in msg or "tests_hidden" in msg:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
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
