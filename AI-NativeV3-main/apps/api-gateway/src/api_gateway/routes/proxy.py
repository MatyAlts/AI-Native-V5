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
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from api_gateway.config import settings

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
}


def resolve_target(path: str) -> str | None:
    """Encuentra el servicio destino para un path."""
    for prefix, target in ROUTE_MAP.items():
        if path.startswith(prefix):
            return target
    return None


@router.api_route(
    "/api/{full_path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
)
async def proxy(full_path: str, request: Request) -> StreamingResponse:
    path = f"/api/{full_path}"

    target = resolve_target(path)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay servicio registrado para {path}",
        )

    url = f"{target.rstrip('/')}{path}"

    # Preservar headers relevantes (auth, content-type, etc.)
    headers = dict(request.headers)
    headers.pop("host", None)  # httpx setea el correcto

    body = await request.body()

    async with httpx.AsyncClient(timeout=120.0) as client:
        upstream = await client.request(
            request.method,
            url,
            params=request.query_params,
            headers=headers,
            content=body,
        )

    # Stream response al cliente
    async def iter_content():
        yield upstream.content

    return StreamingResponse(
        iter_content(),
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in {"content-length", "transfer-encoding", "connection"}
        },
    )
