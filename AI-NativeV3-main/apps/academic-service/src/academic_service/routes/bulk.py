"""Endpoint de importación bulk vía CSV."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_current_user, get_db
from academic_service.auth.casbin_setup import check_permission
from academic_service.services.bulk_import import (
    SUPPORTED_ENTITIES,
    BulkImportCommitResult,
    BulkImportReport,
    BulkImportService,
)

router = APIRouter(prefix="/api/v1/bulk", tags=["bulk-import"])

# Mapeo entity (plural URL) → resource (singular Casbin)
_RESOURCE_BY_ENTITY: dict[str, str] = {
    "facultades": "facultad",
    "carreras": "carrera",
    "planes": "plan",
    "materias": "materia",
    "periodos": "periodo",
    "comisiones": "comision",
    "tareas_practicas": "tarea_practica",
    "inscripciones": "inscripcion",
}


@router.post(
    "/{entity}",
    response_model=BulkImportReport | BulkImportCommitResult,
    status_code=status.HTTP_200_OK,
)
async def bulk_import(
    entity: str,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkImportReport | BulkImportCommitResult:
    if entity not in SUPPORTED_ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Entidad '{entity}' no soportada. Soportadas: {', '.join(SUPPORTED_ENTITIES)}"
            ),
        )

    resource = _RESOURCE_BY_ENTITY[entity]
    if not check_permission(user, resource, "create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Permiso denegado: se requiere create sobre {resource} "
                f"(roles actuales: {', '.join(user.roles) or 'ninguno'})"
            ),
        )

    content = await file.read()
    svc = BulkImportService(db)
    try:
        rows = svc.parse_csv(content, entity)
    except HTTPException as exc:
        # parse_csv ya devuelve códigos correctos (400 malformado, 413 too large);
        # se re-raise tal cual para preservar status_code y detail.
        if exc.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="CSV too large (max 5 MB)",
            ) from exc
        raise

    if dry_run:
        return await svc.dry_run(entity, rows, user)
    return await svc.commit(entity, rows, user)
