"""Endpoints de Comisiones y Periodos."""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.config import settings
from academic_service.schemas import (
    ComisionCreate,
    ComisionOut,
    ComisionUpdate,
    ConfigHashesOut,
    InscripcionCreateIndividual,
    InscripcionOut,
    ListMeta,
    ListResponse,
    PeriodoCreate,
    PeriodoOut,
    PeriodoUpdate,
    UsuarioComisionCreate,
    UsuarioComisionOut,
)
from academic_service.services import ComisionService, PeriodoService

logger = logging.getLogger(__name__)

# Fallback hardcoded del piloto cuando el classifier-service no responde.
# Mantiene compatibilidad con el comportamiento legacy del frontend
# (que mandaba "d"*64 antes de F9). Documentado como degradación
# best-effort en el response del endpoint.
_CLASSIFIER_HASH_FALLBACK = "d" * 64

periodos_router = APIRouter(prefix="/api/v1/periodos", tags=["periodos"])
comisiones_router = APIRouter(prefix="/api/v1/comisiones", tags=["comisiones"])


# ── Periodos ───────────────────────────────────────────


@periodos_router.post("", response_model=PeriodoOut, status_code=status.HTTP_201_CREATED)
async def create_periodo(
    data: PeriodoCreate,
    user: User = Depends(require_permission("periodo", "create")),
    db: AsyncSession = Depends(get_db),
) -> PeriodoOut:
    svc = PeriodoService(db)
    obj = await svc.create(data, user)
    return PeriodoOut.model_validate(obj)


@periodos_router.get("", response_model=ListResponse[PeriodoOut])
async def list_periodos(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    user: User = Depends(require_permission("periodo", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[PeriodoOut]:
    svc = PeriodoService(db)
    objs = await svc.list(limit=limit, cursor=cursor)
    items = [PeriodoOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@periodos_router.patch("/{periodo_id}", response_model=PeriodoOut)
async def update_periodo(
    periodo_id: UUID,
    data: PeriodoUpdate,
    user: User = Depends(require_permission("periodo", "update")),
    db: AsyncSession = Depends(get_db),
) -> PeriodoOut:
    svc = PeriodoService(db)
    obj = await svc.update(periodo_id, data, user)
    return PeriodoOut.model_validate(obj)


@periodos_router.delete("/{periodo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_periodo(
    periodo_id: UUID,
    user: User = Depends(require_permission("periodo", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = PeriodoService(db)
    await svc.soft_delete(periodo_id, user)


# ── Comisiones ────────────────────────────────────────


@comisiones_router.post("", response_model=ComisionOut, status_code=status.HTTP_201_CREATED)
async def create_comision(
    data: ComisionCreate,
    user: User = Depends(require_permission("comision", "create")),
    db: AsyncSession = Depends(get_db),
) -> ComisionOut:
    svc = ComisionService(db)
    obj = await svc.create(data, user)
    return ComisionOut.model_validate(obj)


@comisiones_router.get("", response_model=ListResponse[ComisionOut])
async def list_comisiones(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    materia_id: UUID | None = None,
    periodo_id: UUID | None = None,
    user: User = Depends(require_permission("comision", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[ComisionOut]:
    svc = ComisionService(db)
    objs = await svc.list(limit=limit, cursor=cursor, materia_id=materia_id, periodo_id=periodo_id)
    items = [ComisionOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@comisiones_router.get("/mis", response_model=ListResponse[ComisionOut])
async def list_my_comisiones(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    user: User = Depends(require_permission("comision", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[ComisionOut]:
    """Devuelve las comisiones donde el user tiene un rol activo.

    El endpoint busca matches en `usuarios_comision` (docente, jtp,
    auxiliar, etc.). Para inscripciones de estudiantes ver
    `/api/v1/inscripciones?student_pseudonym=...` — la separación es
    deliberada: el estudiante se identifica por pseudónimo opaco y no
    debe enumerar comisiones por user_id.
    """
    svc = ComisionService(db)
    objs = await svc.list_for_user(user_id=user.id, limit=limit, cursor=cursor)
    items = [ComisionOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@comisiones_router.get("/{comision_id}", response_model=ComisionOut)
async def get_comision(
    comision_id: UUID,
    user: User = Depends(require_permission("comision", "read")),
    db: AsyncSession = Depends(get_db),
) -> ComisionOut:
    svc = ComisionService(db)
    obj = await svc.get(comision_id)
    return ComisionOut.model_validate(obj)


@comisiones_router.get("/{comision_id}/config-hashes", response_model=ConfigHashesOut)
async def get_config_hashes(
    comision_id: UUID,
    user: User = Depends(require_permission("comision", "read")),
    db: AsyncSession = Depends(get_db),
) -> ConfigHashesOut:
    """Bootstrap mínimo F9 — hashes vigentes para abrir un episodio.

    Reemplaza los hashes hardcoded del piloto (`"c"*64` / `"d"*64`) que
    el web-student venía enviando al `POST /api/v1/episodes`. Hoy ese
    contrato sigue exigiéndolos en el request body, así que este
    endpoint los provee desde una fuente derivada.

    - `curso_config_hash`: SHA-256 del JSON canónico de la config
      mínima de la comisión (`comision_id`, `materia_id`, `periodo_id`,
      `tenant_id`, `version`). Determinista por comisión hoy. Misma
      fórmula JSON canónica que CTR/classifier (`sort_keys=True`,
      `ensure_ascii=False`, `separators=(",", ":")`).
    - `classifier_config_hash`: lo que el classifier-service usa al
      clasificar (`compute_classifier_config_hash`). Si el classifier
      no responde, degrada al fallback `"d"*64` con warning — no
      bloquea la apertura del episodio.

    RLS filtra por tenant automáticamente vía `tenant_session`.
    """
    svc = ComisionService(db)
    comision = await svc.get(comision_id)

    # curso_config_hash — JSON canónico igual a la fórmula del CTR/classifier.
    payload = {
        "comision_id": str(comision.id),
        "materia_id": str(comision.materia_id),
        "periodo_id": str(comision.periodo_id),
        "tenant_id": str(comision.tenant_id),
        "version": "1.0.0",
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    curso_config_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # classifier_config_hash — pedir al servicio dueño de la fórmula.
    classifier_hash = _CLASSIFIER_HASH_FALLBACK
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.classifier_service_url}/api/v1/classifier/config-hash"
            )
            r.raise_for_status()
            data = r.json()
            value = data.get("classifier_config_hash")
            if isinstance(value, str) and len(value) == 64:
                classifier_hash = value
            else:
                logger.warning(
                    "classifier-service devolvio payload inesperado",
                    extra={"payload": data},
                )
    except Exception as exc:  # noqa: BLE001 — best-effort: fallback hardcoded.
        logger.warning(
            "classifier-service no respondio config-hash; usando fallback",
            extra={"error": str(exc), "comision_id": str(comision_id)},
        )

    return ConfigHashesOut(
        comision_id=comision.id,
        curso_config_hash=curso_config_hash,
        classifier_config_hash=classifier_hash,
    )


@comisiones_router.patch("/{comision_id}", response_model=ComisionOut)
async def update_comision(
    comision_id: UUID,
    data: ComisionUpdate,
    user: User = Depends(require_permission("comision", "update")),
    db: AsyncSession = Depends(get_db),
) -> ComisionOut:
    svc = ComisionService(db)
    obj = await svc.update(comision_id, data, user)
    return ComisionOut.model_validate(obj)


@comisiones_router.delete("/{comision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comision(
    comision_id: UUID,
    user: User = Depends(require_permission("comision", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ComisionService(db)
    await svc.soft_delete(comision_id, user)


# ── Docentes de comision ──────────────────────────────────────────────


@comisiones_router.get("/{comision_id}/docentes", response_model=ListResponse[UsuarioComisionOut])
async def list_docentes(
    comision_id: UUID,
    user: User = Depends(require_permission("usuario_comision", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[UsuarioComisionOut]:
    svc = ComisionService(db)
    objs = await svc.list_docentes(comision_id)
    items = [UsuarioComisionOut.model_validate(o) for o in objs]
    return ListResponse(data=items, meta=ListMeta(cursor_next=None))


@comisiones_router.post(
    "/{comision_id}/docentes",
    response_model=UsuarioComisionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_docente(
    comision_id: UUID,
    data: UsuarioComisionCreate,
    user: User = Depends(require_permission("usuario_comision", "create")),
    db: AsyncSession = Depends(get_db),
) -> UsuarioComisionOut:
    svc = ComisionService(db)
    obj = await svc.add_docente(comision_id, data, user)
    return UsuarioComisionOut.model_validate(obj)


@comisiones_router.delete(
    "/{comision_id}/docentes/{uc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_docente(
    comision_id: UUID,
    uc_id: UUID,
    user: User = Depends(require_permission("usuario_comision", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ComisionService(db)
    await svc.remove_docente(comision_id, uc_id, user)


# ── Inscripciones de comision ─────────────────────────────────────────


@comisiones_router.get(
    "/{comision_id}/inscripciones", response_model=ListResponse[InscripcionOut]
)
async def list_inscripciones(
    comision_id: UUID,
    user: User = Depends(require_permission("inscripcion", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[InscripcionOut]:
    """Lista inscripciones de una comisión con filtrado por rol (fix QA A11).

    - Roles privilegiados (docente, docente_admin, superadmin, jtp,
      auxiliar) → ven todos los pseudonyms inscriptos.
    - Estudiantes → solo ven su propia inscripción (WHERE
      student_pseudonym = user.id); si no están inscriptos, devuelve
      lista vacía. Cierra el leak de pseudonyms entre alumnos.
    """
    svc = ComisionService(db)
    objs = await svc.list_inscripciones(comision_id, user=user)
    items = [InscripcionOut.model_validate(o) for o in objs]
    return ListResponse(data=items, meta=ListMeta(cursor_next=None))


@comisiones_router.post(
    "/{comision_id}/inscripciones",
    response_model=InscripcionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_inscripcion(
    comision_id: UUID,
    data: InscripcionCreateIndividual,
    user: User = Depends(require_permission("inscripcion", "create")),
    db: AsyncSession = Depends(get_db),
) -> InscripcionOut:
    svc = ComisionService(db)
    obj = await svc.add_inscripcion(comision_id, data, user)
    return InscripcionOut.model_validate(obj)


@comisiones_router.delete(
    "/{comision_id}/inscripciones/{insc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_inscripcion(
    comision_id: UUID,
    insc_id: UUID,
    user: User = Depends(require_permission("inscripcion", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ComisionService(db)
    await svc.remove_inscripcion(comision_id, insc_id, user)
