"""Endpoints de plantillas de campus (HU-036).

  POST /api/v1/plantillas-campus                       — guardar el campus de una comision
  GET  /api/v1/plantillas-campus?comision_id=          — plantillas de la materia de la comision
  POST /api/v1/plantillas-campus/{plantilla_id}/aplicar — aplicar a una comision

Todas exigen membresia de la comision (`assert_comision_member`) ademas del
permiso Casbin `plantilla_campus`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import ListMeta, ListResponse
from academic_service.schemas.plantilla_campus import (
    AplicacionPlantillaOut,
    PlantillaCampusAplicar,
    PlantillaCampusCreate,
    PlantillaCampusOut,
)
from academic_service.services.plantilla_campus_service import PlantillaCampusService

router = APIRouter(prefix="/api/v1/plantillas-campus", tags=["plantillas-campus"])


@router.post("", response_model=PlantillaCampusOut, status_code=status.HTTP_201_CREATED)
async def guardar_plantilla(
    data: PlantillaCampusCreate,
    user: User = Depends(require_permission("plantilla_campus", "create")),
    db: AsyncSession = Depends(get_db),
) -> PlantillaCampusOut:
    """Guarda el campus de la comision como plantilla de su materia."""
    obj = await PlantillaCampusService(db).guardar(data.comision_id, data.nombre, user)
    return PlantillaCampusOut.model_validate(obj)


@router.get("", response_model=ListResponse[PlantillaCampusOut])
async def listar_plantillas(
    comision_id: UUID = Query(..., description="Comision cuya materia se consulta"),
    user: User = Depends(require_permission("plantilla_campus", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[PlantillaCampusOut]:
    """Plantillas de la materia de la comision (requiere ser staff de ella)."""
    objs = await PlantillaCampusService(db).listar(comision_id, user)
    return ListResponse(
        data=[PlantillaCampusOut.model_validate(o) for o in objs],
        meta=ListMeta(cursor_next=None),
    )


@router.post("/{plantilla_id}/aplicar", response_model=AplicacionPlantillaOut)
async def aplicar_plantilla(
    plantilla_id: UUID,
    data: PlantillaCampusAplicar,
    user: User = Depends(require_permission("plantilla_campus", "create")),
    db: AsyncSession = Depends(get_db),
) -> AplicacionPlantillaOut:
    """Aplica la plantilla: crea unidades, introducciones, bienvenida y TPs en borrador."""
    resultado = await PlantillaCampusService(db).aplicar(plantilla_id, data.comision_id, user)
    return AplicacionPlantillaOut(**resultado)
