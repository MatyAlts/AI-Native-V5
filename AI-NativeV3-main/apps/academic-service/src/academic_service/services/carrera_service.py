"""Service de Carrera."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Carrera
from academic_service.repositories import (
    CarreraRepository,
    FacultadRepository,
    UniversidadRepository,
)
from academic_service.schemas.carrera import CarreraCreate, CarreraUpdate


class CarreraService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CarreraRepository(session)
        self.universidades = UniversidadRepository(session)
        self.facultades = FacultadRepository(session)

    async def create(self, data: CarreraCreate, user: User) -> Carrera:
        # La facultad es el ancla: `universidad_id` se deriva de ella
        # (denormalizado — ver `institucional.Carrera`). El payload ya NO
        # acepta `universidad_id`.
        facultad = await self.facultades.get_or_404(data.facultad_id)
        if "superadmin" not in user.roles and facultad.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede crear carreras en otra universidad",
            )

        # Valida que la universidad referida por la facultad sigue existiendo
        # (defensivo — FK ya la garantiza, pero devuelve 404 claro si fue
        # soft-deleted).
        universidad = await self.universidades.get_or_404(facultad.universidad_id)

        new_id = uuid4()
        carrera = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "universidad_id": universidad.id,
                "facultad_id": facultad.id,
                "nombre": data.nombre,
                "codigo": data.codigo,
                "duracion_semestres": data.duracion_semestres,
                "modalidad": data.modalidad,
                "director_user_id": data.director_user_id,
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="carrera.create",
            resource_type="carrera",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return carrera

    async def update(self, id_: UUID, data: CarreraUpdate, user: User) -> Carrera:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="carrera.update",
            resource_type="carrera",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Carrera:
        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="carrera.delete",
            resource_type="carrera",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> Carrera:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
        universidad_id: UUID | None = None,
        facultad_id: UUID | None = None,
    ) -> list[Carrera]:
        filters: dict = {}
        if universidad_id:
            filters["universidad_id"] = universidad_id
        if facultad_id:
            filters["facultad_id"] = facultad_id
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)
