"""Endpoints de Universidades."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import (
    ListMeta,
    ListResponse,
    UniversidadCreate,
    UniversidadOut,
    UniversidadUpdate,
)
from academic_service.services import UniversidadService

router = APIRouter(prefix="/api/v1/universidades", tags=["universidades"])


@router.post(
    "",
    response_model=UniversidadOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_universidad(
    data: UniversidadCreate,
    user: User = Depends(require_permission("universidad", "create")),
    db: AsyncSession = Depends(get_db),
) -> UniversidadOut:
    svc = UniversidadService(db)
    obj = await svc.create(data, user)
    return UniversidadOut.model_validate(obj)


@router.get("", response_model=ListResponse[UniversidadOut])
async def list_universidades(
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    user: User = Depends(require_permission("universidad", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[UniversidadOut]:
    svc = UniversidadService(db)
    objs = await svc.list(limit=limit, cursor=cursor, user=user)
    items = [UniversidadOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/mine", response_model=ListResponse[UniversidadOut])
async def list_mine_universidades(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("universidad", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[UniversidadOut]:
    """Lista universidades donde el caller tiene rol activo.

    Reemplaza la policy laxa `authenticated_can_list` (cualquier user
    autenticado podia listar TODAS las unis). Ahora:
    - superadmin → TODAS (idem `GET /universidades`).
    - docente → solo donde tiene `usuarios_comision` activa.
    - estudiante → solo donde tiene `inscripciones` con `estado='activa'`.
    """
    svc = UniversidadService(db)
    objs = await svc.list_mine(user=user, limit=limit)
    items = [UniversidadOut.model_validate(o) for o in objs]
    return ListResponse(data=items, meta=ListMeta(cursor_next=None))


@router.get("/{universidad_id}", response_model=UniversidadOut)
async def get_universidad(
    universidad_id: UUID,
    user: User = Depends(require_permission("universidad", "read")),
    db: AsyncSession = Depends(get_db),
) -> UniversidadOut:
    svc = UniversidadService(db)
    obj = await svc.get(universidad_id)
    return UniversidadOut.model_validate(obj)


@router.patch("/{universidad_id}", response_model=UniversidadOut)
async def update_universidad(
    universidad_id: UUID,
    data: UniversidadUpdate,
    user: User = Depends(require_permission("universidad", "update")),
    db: AsyncSession = Depends(get_db),
) -> UniversidadOut:
    svc = UniversidadService(db)
    obj = await svc.update(universidad_id, data, user)
    return UniversidadOut.model_validate(obj)


@router.delete("/{universidad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_universidad(
    universidad_id: UUID,
    user: User = Depends(require_permission("universidad", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = UniversidadService(db)
    await svc.soft_delete(universidad_id, user)
