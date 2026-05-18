"""Endpoints de Facultades."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import ListMeta, ListResponse
from academic_service.schemas.facultad import (
    FacultadCreate,
    FacultadOut,
    FacultadUpdate,
)
from academic_service.services.facultad_service import FacultadService

router = APIRouter(prefix="/api/v1/facultades", tags=["facultades"])


@router.post("", response_model=FacultadOut, status_code=status.HTTP_201_CREATED)
async def create_facultad(
    data: FacultadCreate,
    user: User = Depends(require_permission("facultad", "create")),
    db: AsyncSession = Depends(get_db),
) -> FacultadOut:
    svc = FacultadService(db)
    obj = await svc.create(data, user)
    return FacultadOut.model_validate(obj)


@router.get("", response_model=ListResponse[FacultadOut])
async def list_facultades(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    universidad_id: UUID | None = None,
    user: User = Depends(require_permission("facultad", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[FacultadOut]:
    svc = FacultadService(db)
    objs = await svc.list(limit=limit, cursor=cursor, universidad_id=universidad_id)
    items = [FacultadOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/{facultad_id}", response_model=FacultadOut)
async def get_facultad(
    facultad_id: UUID,
    user: User = Depends(require_permission("facultad", "read")),
    db: AsyncSession = Depends(get_db),
) -> FacultadOut:
    svc = FacultadService(db)
    obj = await svc.get(facultad_id)
    return FacultadOut.model_validate(obj)


@router.patch("/{facultad_id}", response_model=FacultadOut)
async def update_facultad(
    facultad_id: UUID,
    data: FacultadUpdate,
    user: User = Depends(require_permission("facultad", "update")),
    db: AsyncSession = Depends(get_db),
) -> FacultadOut:
    svc = FacultadService(db)
    obj = await svc.update(facultad_id, data, user)
    return FacultadOut.model_validate(obj)


@router.delete("/{facultad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_facultad(
    facultad_id: UUID,
    user: User = Depends(require_permission("facultad", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = FacultadService(db)
    await svc.soft_delete(facultad_id, user)
