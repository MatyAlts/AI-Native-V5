"""Endpoints de Unidades temáticas (ADR-041).

Agrupa 6 endpoints para gestión de Unidades por comisión:
  POST   /api/v1/unidades              — crear
  GET    /api/v1/unidades?comision_id  — listar (comision_id REQUIRED)
  GET    /api/v1/unidades/{id}         — obtener por id
  PATCH  /api/v1/unidades/{id}         — actualizar
  DELETE /api/v1/unidades/{id}         — soft-delete
  POST   /api/v1/unidades/reorder      — bulk reorder

El endpoint de reorder DEBE registrarse ANTES del de `/{id}` para que
FastAPI no confunda `/reorder` con un UUID como path param.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import ListMeta, ListResponse
from academic_service.schemas.unidad import (
    UnidadCreate,
    UnidadOut,
    UnidadReorderRequest,
    UnidadUpdate,
)
from academic_service.services.unidad_service import UnidadService

router = APIRouter(prefix="/api/v1/unidades", tags=["unidades"])


@router.post("", response_model=UnidadOut, status_code=status.HTTP_201_CREATED)
async def create_unidad(
    data: UnidadCreate,
    user: User = Depends(require_permission("unidad", "create")),
    db: AsyncSession = Depends(get_db),
) -> UnidadOut:
    """Crea una nueva Unidad temática.

    Requiere rol con `unidad:create` (docente/docente_admin/superadmin).
    Devuelve 409 si ya existe una Unidad con el mismo nombre en la comisión.
    """
    svc = UnidadService(db)
    obj = await svc.create(data, user)
    return UnidadOut.model_validate(obj)


@router.post("/reorder", response_model=list[UnidadOut])
async def reorder_unidades(
    data: UnidadReorderRequest,
    user: User = Depends(require_permission("unidad", "update")),
    db: AsyncSession = Depends(get_db),
) -> list[UnidadOut]:
    """Actualiza el `orden` de múltiples Unidades en una transacción.

    IMPORTANTE: este endpoint DEBE estar registrado antes de `/{id}`
    para evitar que FastAPI interprete la literal "reorder" como UUID.

    El constraint `uq_unidad_orden` es DEFERRABLE INITIALLY DEFERRED,
    lo que permite swaps atómicos sin errores de unicidad intermedios.
    """
    svc = UnidadService(db)
    objs = await svc.reorder(data.items, user)
    return [UnidadOut.model_validate(o) for o in objs]


@router.get("", response_model=ListResponse[UnidadOut])
async def list_unidades(
    comision_id: UUID = Query(..., description="ID de la comisión (requerido)"),
    user: User = Depends(require_permission("unidad", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[UnidadOut]:
    """Lista las Unidades activas de una comisión ordenadas por `orden` ASC.

    `comision_id` es REQUERIDO — sin él se devuelve 422.
    Solo devuelve Unidades con `deleted_at=NULL`.
    RLS garantiza aislamiento multi-tenant automáticamente.
    """
    svc = UnidadService(db)
    objs = await svc.list_by_comision(user.tenant_id, comision_id)
    items = [UnidadOut.model_validate(o) for o in objs]
    return ListResponse(data=items, meta=ListMeta(cursor_next=None))


@router.get("/{unidad_id}", response_model=UnidadOut)
async def get_unidad(
    unidad_id: UUID,
    user: User = Depends(require_permission("unidad", "read")),
    db: AsyncSession = Depends(get_db),
) -> UnidadOut:
    svc = UnidadService(db)
    obj = await svc.get_by_id(unidad_id)
    return UnidadOut.model_validate(obj)


@router.patch("/{unidad_id}", response_model=UnidadOut)
async def update_unidad(
    unidad_id: UUID,
    data: UnidadUpdate,
    user: User = Depends(require_permission("unidad", "update")),
    db: AsyncSession = Depends(get_db),
) -> UnidadOut:
    """Actualización parcial de nombre/descripcion/orden.

    Devuelve 409 si el nuevo nombre ya existe en la misma comisión.
    """
    svc = UnidadService(db)
    obj = await svc.update(unidad_id, data, user)
    return UnidadOut.model_validate(obj)


@router.delete("/{unidad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unidad(
    unidad_id: UUID,
    user: User = Depends(require_permission("unidad", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete de una Unidad (sets deleted_at=NOW).

    Las TPs asignadas NO se borran — quedan con `unidad_id` apuntando
    a la Unidad soft-deleted. En lecturas posteriores de la Unidad,
    el filtro `deleted_at IS NULL` la excluye. Las TPs se tratan como
    "Sin unidad" en las vistas de trazabilidad.
    """
    svc = UnidadService(db)
    await svc.soft_delete(unidad_id, user)
