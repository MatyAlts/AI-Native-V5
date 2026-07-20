"""Repositorio base con operaciones CRUD comunes.

Los repos son la única capa que habla con SQLAlchemy directamente.
Los services consumen repos; los routers consumen services.
"""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT: Base]:
    """CRUD genérico sobre un modelo SQLAlchemy."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: UUID) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == id_,  # type: ignore[attr-defined]
            self.model.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, id_: UUID) -> ModelT:
        obj = await self.get(id_)
        if obj is None:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} {id_} no encontrado",
            )
        return obj

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[ModelT]:
        stmt = select(self.model).where(
            self.model.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        if cursor:
            stmt = stmt.where(self.model.id > cursor)  # type: ignore[attr-defined]
        if filters:
            for col, val in filters.items():
                if hasattr(self.model, col):
                    stmt = stmt.where(getattr(self.model, col) == val)
        stmt = stmt.order_by(self.model.id).limit(limit)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        if filters:
            for col, val in filters.items():
                if hasattr(self.model, col):
                    stmt = stmt.where(getattr(self.model, col) == val)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, data: dict[str, Any]) -> ModelT:
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id_: UUID, data: dict[str, Any]) -> ModelT:
        obj = await self.get_or_404(id_)
        for k, v in data.items():
            if v is not None:
                setattr(obj, k, v)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID) -> ModelT:
        from academic_service.models.base import utc_now

        obj = await self.get_or_404(id_)
        obj.deleted_at = utc_now()  # type: ignore[attr-defined]
        await self.session.flush()
        return obj
