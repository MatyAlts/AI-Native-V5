"""Services de Materia y PlanEstudios."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Materia
from academic_service.repositories import (
    ComisionRepository,
    MateriaRepository,
    PlanEstudiosRepository,
)
from academic_service.schemas.materia import MateriaCreate, MateriaUpdate


class MateriaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MateriaRepository(session)
        self.planes = PlanEstudiosRepository(session)
        self.comisiones = ComisionRepository(session)

    async def _validate_correlativas(self, correlativas: list[UUID], tenant_id: UUID) -> None:
        """Valida que las correlativas existan y estén en el mismo tenant."""
        for corr_id in correlativas:
            corr = await self.repo.get(corr_id)
            if corr is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Correlativa {corr_id} no existe",
                )

    async def create(self, data: MateriaCreate, user: User) -> Materia:
        plan = await self.planes.get_or_404(data.plan_id)

        await self._validate_correlativas(data.correlativas_cursar, user.tenant_id)
        await self._validate_correlativas(data.correlativas_rendir, user.tenant_id)

        new_id = uuid4()
        materia = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "plan_id": plan.id,
                "nombre": data.nombre,
                "codigo": data.codigo,
                "horas_totales": data.horas_totales,
                "cuatrimestre_sugerido": data.cuatrimestre_sugerido,
                "objetivos": data.objetivos,
                "correlativas_cursar": [str(c) for c in data.correlativas_cursar],
                "correlativas_rendir": [str(c) for c in data.correlativas_rendir],
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="materia.create",
            resource_type="materia",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        await self.session.flush()
        return materia

    async def update(self, id_: UUID, data: MateriaUpdate, user: User) -> Materia:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)

        # UUID a str para JSONB
        if "correlativas_cursar" in changes:
            await self._validate_correlativas(changes["correlativas_cursar"], user.tenant_id)
            changes["correlativas_cursar"] = [str(c) for c in changes["correlativas_cursar"]]
        if "correlativas_rendir" in changes:
            await self._validate_correlativas(changes["correlativas_rendir"], user.tenant_id)
            changes["correlativas_rendir"] = [str(c) for c in changes["correlativas_rendir"]]

        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="materia.update",
            resource_type="materia",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Materia:
        comisiones_activas = await self.comisiones.count(filters={"materia_id": id_})
        if comisiones_activas > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Materia tiene {comisiones_activas} comisiones activas",
            )

        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="materia.delete",
            resource_type="materia",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> Materia:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        limit: int = 50,
        cursor: UUID | None = None,
        plan_id: UUID | None = None,
    ) -> list[Materia]:
        filters: dict = {}
        if plan_id:
            filters["plan_id"] = plan_id
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)
