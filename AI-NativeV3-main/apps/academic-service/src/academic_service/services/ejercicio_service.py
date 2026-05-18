"""Service del banco de ejercicios reusables (ADR-047).

CRUD de la entidad Ejercicio standalone. Los ejercicios viven en una
biblioteca por tenant — son reusables entre TPs via la tabla intermedia
`tp_ejercicios` (ver `tp_ejercicio_service.py` cuando se implemente).

Versionado: no implementado en este batch — si un docente edita un
ejercicio referenciado por TPs publicadas, la edición se propaga (deuda
diferida del ADR-047). Endpoint PATCH guarda audit log con el cambio
para trazabilidad.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Ejercicio
from academic_service.repositories import EjercicioRepository
from platform_contracts.academic.ejercicio import (
    EjercicioCreate,
    EjercicioUpdate,
)


class EjercicioService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EjercicioRepository(session)

    async def create(self, data: EjercicioCreate, user: User) -> Ejercicio:
        new_id = uuid4()
        payload = data.model_dump(mode="json")
        ejercicio = await self.repo.create(
            {
                "id": new_id,
                "tenant_id": user.tenant_id,
                "created_by": user.id,
                **payload,
            }
        )

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="ejercicio.create",
            resource_type="ejercicio",
            resource_id=new_id,
            changes={"after": payload},
        )
        self.session.add(audit)
        await self.session.flush()
        return ejercicio

    async def update(self, id_: UUID, data: EjercicioUpdate, user: User) -> Ejercicio:
        obj = await self.repo.get_or_404(id_)
        changes = data.model_dump(exclude_unset=True, mode="json")
        for k, v in changes.items():
            setattr(obj, k, v)

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="ejercicio.update",
            resource_type="ejercicio",
            resource_id=id_,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID, user: User) -> Ejercicio:
        # NOTA: el ADR-047 deja como deuda diferida el guard cross-service
        # que verifica que el ejercicio no esté referenciado por TPs
        # publicadas. Hoy el borrado procede sin guard; las filas de
        # tp_ejercicios quedan con FK a un ejercicio soft-deleted. El listado
        # del banco filtra por `deleted_at IS NULL` así que UI no lo ve más,
        # pero el tutor-service podría servir un ejercicio borrado si abre
        # un episodio que ya lo referencia. Mitigación: validar referencias
        # en el service de tp_ejercicios cuando se implemente.
        obj = await self.repo.soft_delete(id_)
        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="ejercicio.delete",
            resource_type="ejercicio",
            resource_id=id_,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()
        return obj

    async def get(self, id_: UUID) -> Ejercicio:
        return await self.repo.get_or_404(id_)

    async def list(
        self,
        unidad_tematica: str | None = None,
        dificultad: str | None = None,
        created_by: UUID | None = None,
        created_via_ai: bool | None = None,
        limit: int = 50,
        cursor: UUID | None = None,
    ) -> list[Ejercicio]:
        filters: dict[str, Any] = {}
        if unidad_tematica:
            filters["unidad_tematica"] = unidad_tematica
        if dificultad:
            filters["dificultad"] = dificultad
        if created_by:
            filters["created_by"] = created_by
        if created_via_ai is not None:
            filters["created_via_ai"] = created_via_ai
        return await self.repo.list(limit=limit, cursor=cursor, filters=filters)
