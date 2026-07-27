"""Proxy básico del api-gateway.

En F1 el gateway hace passthrough de JWT y rutea por path a los servicios
downstream. En F3 el gateway valida firma del JWT y extrae claims a
headers X-* para los servicios downstream.

Mapa de rutas:
    /api/v1/universidades/*  → academic-service
    /api/v1/carreras/*       → academic-service
    /api/v1/materias/*       → academic-service
    /api/v1/comisiones/*     → academic-service
    /api/v1/periodos/*       → academic-service
    /api/v1/bulk/*           → academic-service (incluye inscripciones, ADR-029)

Nota historica: `/api/v1/imports/*` (enrollment-service) fue removido por
ADR-030 — el bulk-import unificado de academic-service cubre todos los casos.
"""

from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api_gateway.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["proxy"])

# Routing por prefijo → servicio
ROUTE_MAP: dict[str, str] = {
    "/api/v1/universidades": settings.academic_service_url,
    "/api/v1/facultades": settings.academic_service_url,
    "/api/v1/carreras": settings.academic_service_url,
    "/api/v1/planes": settings.academic_service_url,
    "/api/v1/materias": settings.academic_service_url,
    "/api/v1/comisiones": settings.academic_service_url,
    # Auto-llenado del perfil del alumno desde Clerk (full_name + email).
    # POST /api/v1/users/me/profile invocado por web-student al loguearse;
    # GET /api/v1/comisiones/{id}/students/profiles consumido por web-teacher.
    "/api/v1/users": settings.academic_service_url,
    "/api/v1/periodos": settings.academic_service_url,
    "/api/v1/tareas-practicas": settings.academic_service_url,
    "/api/v1/ejercicios": settings.academic_service_url,
    "/api/v1/unidades": settings.academic_service_url,
    "/api/v1/bulk": settings.academic_service_url,
    # plan-mejora-instrumentos-research: cuestionario IA previa, pretest
    # autoeficacia Lishinski, test transferencia H2 — consumido por
    # web-student (api.ts:943-1090) y web-teacher (api.ts:1772-1812).
    "/api/v1/instrumentos": settings.academic_service_url,
    # /api/v1/imports REMOVED — ADR-030 deprecation. Usar /api/v1/bulk/inscripciones
    # de academic-service (ADR-029) para el alta masiva de inscripciones.
    "/api/v1/materiales": settings.content_service_url,
    # `/api/v1/retrieve` removido del ROUTE_MAP (2026-05-17): no era consumido
    # por ningún frontend. El tutor-service llama al content-service directo
    # (service-to-service via `content_service_url`), no via gateway.
    "/api/v1/episodes": settings.tutor_service_url,
    "/api/v1/classify_episode": settings.classifier_service_url,
    "/api/v1/classifications": settings.classifier_service_url,
    # Codificación inter-jueces (validación κ): el docente etiqueta episodios a
    # ciegas y se persiste en classifier_db (la agregación/κ vive en analytics).
    "/api/v1/interrater": settings.classifier_service_url,
    # `/api/v1/classifier` (singular) removido del ROUTE_MAP (2026-05-17): el
    # comentario histórico afirmaba que web-student consumía
    # /api/v1/classifier/config-hash, pero es falso — web-student usa
    # /comisiones/{id}/config-hashes (plural) del academic-service, y este
    # último llama a classifier-service directo (service-to-service). Ningún
    # frontend consume el prefix `/api/v1/classifier/`.
    "/api/v1/analytics": settings.analytics_service_url,
    # ADR-046 / paper-draft (extensiones operativas "inspirado en Caliper/xAPI"):
    # analytics-service expone GET /api/v1/export/caliper/{episode_id} y
    # GET /api/v1/export/xapi/{episode_id} (export_standards.py). Sin esta
    # entrada quedaban inalcanzables vía gateway.
    "/api/v1/export": settings.analytics_service_url,
    # ADR-031 (D.4): alias publicos del CTR (verify cadena criptografica +
    # read del episodio para auditoria docente). Bajo prefix /api/v1/audit
    # para evitar el conflicto con /api/v1/episodes (tutor-service).
    "/api/v1/audit": settings.ctr_service_url,
    # ADR-038/039 (Sec 7 epic ai-native-completion): BYOK keys CRUD via
    # ai-gateway. Solo superadmin/docente_admin pueden gestionar — el
    # ai-gateway enforced via X-User-Roles del header inyectado por este
    # proxy. ROUTE_MAP cubre /keys + /keys/{id}/{revoke,usage}.
    "/api/v1/byok": settings.ai_gateway_url,
    # tp-entregas-correccion: entregas + calificaciones via evaluation-service (puerto 8004)
    "/api/v1/entregas": settings.evaluation_service_url,
    "/api/v1/calificaciones": settings.evaluation_service_url,
    # `/api/v1/active_configs` (governance-service) NO se expone a propósito.
    # governance-service es interno by-design (prompts versionados; ver CLAUDE.md
    # "governance-service NO expuesto en ROUTE_MAP"). El manifest declarativo de
    # versiones lo lee el AuditFooter de forma hardcodeada por ahora — no necesita
    # el endpoint. Si un dashboard futuro requiere versiones dinámicas, exponer un
    # alias específico (patrón ctr `/api/v1/audit`), no el servicio entero.
    # Documentado para que el QA no lo re-marque como 404 inesperado (ADMIN-BUG-004).
}


def resolve_target(path: str) -> str | None:
    """Encuentra el servicio destino para un path."""
    for prefix, target in ROUTE_MAP.items():
        if path.startswith(prefix):
            return target
    return None


# Rutas que superan el timeout del client compartido (120s) por diseño, no por
# falla. El wizard IA de ejercicios (ADR-047/048) genera un borrador completo
# —enunciado, banco socrático N1-N4, misconceptions, anti-patrones, tests,
# rúbrica— con UNA sola llamada al LLM y sin streaming, así que la request queda
# abierta minutos. El default NO se sube global: cada request colgada retendría
# una conexión del pool ese tiempo, que es justamente lo que el timeout evita.
#
# La cascada va de MÁS a MENOS hacia adentro; si una capa externa corta antes
# que una interna, el cliente recibe un timeout opaco en vez del error real:
#
#   cliente 300s  >  gateway 270s (acá)  >  academic-service → ai-gateway 240s
#
# Al mover cualquiera de los tres, mover los tres.
LONG_RUNNING_ROUTES: dict[str, float] = {
    "/api/v1/ejercicios/generate": settings.proxy_long_running_timeout_seconds,
}


def resolve_timeout(path: str) -> float:
    """Timeout (segundos) a aplicar en el request al servicio destino."""
    for prefix, timeout in LONG_RUNNING_ROUTES.items():
        if path.startswith(prefix):
            return timeout
    return settings.proxy_client_timeout_seconds


# Content-types que se reenvían chunk-a-chunk (SSE / streaming) en vez de
# bufferearse punta a punta. El tutor socrático (POST
# /api/v1/episodes/{id}/message) responde `text/event-stream`; sin forwarding
# incremental el alumno mira la nada hasta que el stream cierra (bug P-1).
_STREAMING_CONTENT_TYPES: frozenset[str] = frozenset({"text/event-stream"})

# Headers hop-by-hop que NO se propagan al cliente — los fija el server HTTP del
# gateway según el transfer real (chunked vs content-length).
_EXCLUDED_RESPONSE_HEADERS: frozenset[str] = frozenset(
    {"content-length", "transfer-encoding", "connection"}
)


def _is_streaming_response(content_type: str | None) -> bool:
    """True si el upstream declara un content-type de streaming (SSE)."""
    if not content_type:
        return False
    # `text/event-stream; charset=utf-8` → comparar sólo el media type.
    return content_type.split(";", 1)[0].strip().lower() in _STREAMING_CONTENT_TYPES


def _passthrough_response_headers(upstream_headers: httpx.Headers) -> dict[str, str]:
    """Headers del upstream a reenviar, sin los hop-by-hop."""
    return {
        k: v for k, v in upstream_headers.items() if k.lower() not in _EXCLUDED_RESPONSE_HEADERS
    }


@router.api_route(
    "/api/{full_path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
)
async def proxy(full_path: str, request: Request) -> StreamingResponse:
    path = f"/api/{full_path}"

    target = resolve_target(path)
    if not target:
        # Mensaje genérico al cliente; el path va al log interno (F-11: no
        # revelar qué rutas existen/no existen ni la topología de servicios).
        logger.info("unregistered_route", path=path)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    url = f"{target.rstrip('/')}{path}"

    # Preservar headers relevantes: auth + los X-* que el JWTMiddleware inyectó
    # autoritativamente en request.scope["headers"] (X-User-Id/X-Tenant-Id/
    # X-User-Roles + firma X-Gateway-Signature), content-type, etc.
    headers = dict(request.headers)
    headers.pop("host", None)  # httpx setea el correcto

    body = await request.body()

    # Client httpx COMPARTIDO de larga vida (P-3): creado una vez en el lifespan
    # (`main.py`) y reusado en cada request para no abrir una connection pool
    # nueva por request. NO se cierra acá — es del ciclo de vida de la app; el
    # shutdown del lifespan lo cierra. Solo se cierra el `upstream` (la response).
    client: httpx.AsyncClient = request.app.state.http_client

    upstream_request = client.build_request(
        request.method,
        url,
        # `.multi_items()` preserva los parámetros REPETIDOS (ej.
        # `?comision_id=a&comision_id=b` del corpus inter-jueces). Pasar el
        # QueryParams directo a httpx los colapsa a uno solo (se queda con el
        # último) — bug silencioso para cualquier endpoint con params repetidos.
        # `tuple(...)` en vez de list: `list[tuple[str, str]]` no es subtipo de
        # `list[tuple[str, str | int | ...]]` (list es invariante), pero la
        # tupla homogénea `tuple[X, ...]` sí es covariante — mismo contenido,
        # sólo se ajusta el contenedor para que el type checker vea la garantía.
        params=tuple(request.query_params.multi_items()),
        headers=headers,
        content=body,
        # El timeout va por request (httpx lo lleva en `request.extensions`),
        # NO en el client compartido: así el default de 120s sigue intacto para
        # todo el resto y sólo las rutas de LONG_RUNNING_ROUTES esperan de más.
        # `send()` no acepta `timeout` en httpx — tiene que ir acá.
        timeout=resolve_timeout(path),
    )
    # `stream=True` devuelve los headers apenas llegan, sin leer el body:
    # así se decide bufferear vs reenviar chunk-a-chunk mirando el
    # content-type real, y las respuestas SSE fluyen incrementalmente. Si `send`
    # falla no hay `upstream` que cerrar (el client compartido NO se toca).
    upstream = await client.send(upstream_request, stream=True)

    response_headers = _passthrough_response_headers(upstream.headers)

    if _is_streaming_response(upstream.headers.get("content-type")):
        # Camino streaming (SSE): reenviar los chunks a medida que llegan, sin
        # bufferear. Solo el `upstream` se cierra cuando el generador termina
        # (fin del stream o desconexión del cliente) — el client es compartido.
        async def forward_stream():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(
            forward_stream(),
            status_code=upstream.status_code,
            headers=response_headers,
        )

    # Camino no-streaming: bufferear la respuesta completa (comportamiento
    # histórico intacto para todo endpoint no-SSE). Solo se cierra el `upstream`.
    try:
        await upstream.aread()
    finally:
        await upstream.aclose()

    async def iter_content():
        yield upstream.content

    return StreamingResponse(
        iter_content(),
        status_code=upstream.status_code,
        headers=response_headers,
    )
