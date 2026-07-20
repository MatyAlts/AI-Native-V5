"""Service de Facultad."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Facultad
from academic_service.repositories import FacultadRepository, UniversidadRepository
from academic_service.schemas.facultad import FacultadCreate, FacultadUpdate


class FacultadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = FacultadRepository(session)
        self.universidades = UniversidadRepository(session)

    async def create(self, data: FacultadCreate, user: User) -> Facultad:
        # Validar que la universidad existe y pertenece al tenant del user
        universidad = await self.universidades.get_or_404(data.universidad_id)
        if "superadmin" not in user.roles and universidad.id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede crear facultades en otra universidad",
            )

        new_id = uuid4()
        facultad = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "universidad_id": universidad.id,
                "nombre": data.nombre,
                "codigo": data.codigo,
                "decano_user_id": data.decano_user_id,
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="facultad.create",
            resource_type="facultad",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return facultad

    async def update(self, id_: UUID, data: FacultadUpdate, user: User) -> Facultad:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="facultad.update",
            resource_type="facultad",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Facultad:
        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="facultad.delete",
            resource_type="facultad",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> Facultad:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
        universidad_id: UUID | None = None,
    ) -> list[Facultad]:
        filters: dict = {}
        if universidad_id:
            filters["universidad_id"] = universidad_id
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)
