"""Service de PlanEstudios."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, PlanEstudios
from academic_service.repositories import CarreraRepository, PlanEstudiosRepository
from academic_service.schemas.plan import PlanCreate, PlanUpdate


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PlanEstudiosRepository(session)
        self.carreras = CarreraRepository(session)

    async def create(self, data: PlanCreate, user: User) -> PlanEstudios:
        carrera = await self.carreras.get_or_404(data.carrera_id)

        new_id = uuid4()
        plan = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "carrera_id": carrera.id,
                "version": data.version,
                "año_inicio": data.año_inicio,
                "ordenanza": data.ordenanza,
                "vigente": data.vigente,
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="plan.create",
            resource_type="plan",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return plan

    async def update(self, id_: UUID, data: PlanUpdate, user: User) -> PlanEstudios:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="plan.update",
            resource_type="plan",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> PlanEstudios:
        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="plan.delete",
            resource_type="plan",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> PlanEstudios:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
        carrera_id: UUID | None = None,
    ) -> list[PlanEstudios]:
        filters: dict = {}
        if carrera_id:
            filters["carrera_id"] = carrera_id
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)
