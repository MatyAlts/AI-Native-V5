"""Endpoints de Planes de Estudio."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import (
    ListMeta,
    ListResponse,
    PlanCreate,
    PlanOut,
    PlanUpdate,
)
from academic_service.services import PlanService

router = APIRouter(prefix="/api/v1/planes", tags=["planes"])


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: PlanCreate,
    user: User = Depends(require_permission("plan", "create")),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    svc = PlanService(db)
    obj = await svc.create(data, user)
    return PlanOut.model_validate(obj)


@router.get("", response_model=ListResponse[PlanOut])
async def list_planes(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    carrera_id: UUID | None = None,
    user: User = Depends(require_permission("plan", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[PlanOut]:
    svc = PlanService(db)
    objs = await svc.list(limit=limit, cursor=cursor, carrera_id=carrera_id)
    items = [PlanOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: UUID,
    user: User = Depends(require_permission("plan", "read")),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    svc = PlanService(db)
    obj = await svc.get(plan_id)
    return PlanOut.model_validate(obj)


@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: UUID,
    data: PlanUpdate,
    user: User = Depends(require_permission("plan", "update")),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    svc = PlanService(db)
    obj = await svc.update(plan_id, data, user)
    return PlanOut.model_validate(obj)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID,
    user: User = Depends(require_permission("plan", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = PlanService(db)
    await svc.soft_delete(plan_id, user)
