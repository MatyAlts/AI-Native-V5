"""Endpoints de Carreras."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import (
    CarreraCreate,
    CarreraOut,
    CarreraUpdate,
    ListMeta,
    ListResponse,
)
from academic_service.services import CarreraService

router = APIRouter(prefix="/api/v1/carreras", tags=["carreras"])


@router.post("", response_model=CarreraOut, status_code=status.HTTP_201_CREATED)
async def create_carrera(
    data: CarreraCreate,
    user: User = Depends(require_permission("carrera", "create")),
    db: AsyncSession = Depends(get_db),
) -> CarreraOut:
    svc = CarreraService(db)
    obj = await svc.create(data, user)
    return CarreraOut.model_validate(obj)


@router.get("", response_model=ListResponse[CarreraOut])
async def list_carreras(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    universidad_id: UUID | None = None,
    facultad_id: UUID | None = None,
    user: User = Depends(require_permission("carrera", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[CarreraOut]:
    svc = CarreraService(db)
    objs = await svc.list(
        limit=limit,
        cursor=cursor,
        universidad_id=universidad_id,
        facultad_id=facultad_id,
    )
    items = [CarreraOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/{carrera_id}", response_model=CarreraOut)
async def get_carrera(
    carrera_id: UUID,
    user: User = Depends(require_permission("carrera", "read")),
    db: AsyncSession = Depends(get_db),
) -> CarreraOut:
    svc = CarreraService(db)
    obj = await svc.get(carrera_id)
    return CarreraOut.model_validate(obj)


@router.patch("/{carrera_id}", response_model=CarreraOut)
async def update_carrera(
    carrera_id: UUID,
    data: CarreraUpdate,
    user: User = Depends(require_permission("carrera", "update")),
    db: AsyncSession = Depends(get_db),
) -> CarreraOut:
    svc = CarreraService(db)
    obj = await svc.update(carrera_id, data, user)
    return CarreraOut.model_validate(obj)


@router.delete("/{carrera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_carrera(
    carrera_id: UUID,
    user: User = Depends(require_permission("carrera", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = CarreraService(db)
    await svc.soft_delete(carrera_id, user)
