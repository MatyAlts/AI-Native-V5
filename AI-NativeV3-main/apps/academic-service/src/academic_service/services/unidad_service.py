"""Service de Unidad temática (ADR-041).

Gestión CRUD de Unidades por comisión. Cada Unidad agrupa TPs
pedagógicamente para habilitar trazabilidad longitudinal cuando
template_id=NULL.

Comportamiento crítico:
- Soft-delete: `deleted_at = NOW`. La FK `tareas_practicas.unidad_id`
  es ON DELETE SET NULL, así que borrar la Unidad en la DB huerfana las
  TPs automáticamente. El soft-delete solo marca la Unidad; las TPs
  siguen apuntando a la Unidad hasta que la migración de DROP TABLE se
  ejecute. En la práctica, las TPs con `unidad.deleted_at IS NOT NULL`
  deben tratarse como "Sin unidad" en las lecturas.
- Reorder: el constraint `uq_unidad_orden` es DEFERRABLE INITIALLY
  DEFERRED, lo que permite actualizar múltiples órdenes en una sola
  transacción sin violar la unicidad en estados intermedios.
- Validación de comisión: toda operación valida que la comisión existe
  en este tenant (RLS la filtra, pero validamos explícitamente para
  devolver 404 semántico en lugar de una constraint error).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, Unidad
from academic_service.models.base import utc_now
from academic_service.repositories import ComisionRepository
from academic_service.schemas.unidad import (
    UnidadCreate,
    UnidadReorderItem,
    UnidadUpdate,
)


class UnidadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.comisiones = ComisionRepository(session)

    async def create(self, data: UnidadCreate, user: User) -> Unidad:
        """Crea una nueva Unidad.

        Valida que la comisión existe en este tenant y que no existe
        una Unidad con el mismo nombre en esa comisión (409 en duplicados).
        """
        # Valida que la comisión existe (RLS filtra por tenant)
        await self.comisiones.get_or_404(data.comision_id)

        # Verifica unicidad de nombre dentro de (tenant, comision)
        existing = await self._find_by_nombre(
            user.tenant_id, data.comision_id, data.nombre
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una Unidad con nombre '{data.nombre}' en esta comisión",
            )

        new_id = uuid4()
        unidad = Unidad(
            id=new_id,
            tenant_id=user.tenant_id,
            comision_id=data.comision_id,
            nombre=data.nombre,
            descripcion=data.descripcion,
            orden=data.orden,
            created_by=user.id,
        )
        self.session.add(unidad)

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="unidad.create",
            resource_type="unidad",
            resource_id=new_id,
            changes={"after": data.model_dump(mode="json")},
        )
        self.session.add(audit)
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            msg = str(e.orig) if e.orig else str(e)
            if "uq_unidad_orden" in msg:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe una Unidad con orden={data.orden} en esta comisión",
                ) from e
            if "uq_unidad_nombre" in msg:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe una Unidad con nombre '{data.nombre}' en esta comisión",
                ) from e
            raise
        await self.session.refresh(unidad)
        return unidad

    async def list_by_comision(
        self, tenant_id: UUID, comision_id: UUID
    ) -> list[Unidad]:
        """Lista Unidades activas de una comisión ordenadas por `orden` ASC."""
        stmt = (
            select(Unidad)
            .where(
                Unidad.tenant_id == tenant_id,
                Unidad.comision_id == comision_id,
                Unidad.deleted_at.is_(None),
            )
            .order_by(Unidad.orden.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, unidad_id: UUID) -> Unidad:
        """Devuelve una Unidad por id o lanza 404."""
        stmt = select(Unidad).where(
            Unidad.id == unidad_id,
            Unidad.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unidad {unidad_id} no encontrada",
            )
        return obj

    async def update(self, unidad_id: UUID, data: UnidadUpdate, user: User) -> Unidad:
        """Actualiza parcialmente una Unidad (PATCH)."""
        obj = await self.get_by_id(unidad_id)

        changes = data.model_dump(exclude_unset=True)

        # Si se cambia el nombre, validar unicidad dentro de la misma comisión
        new_nombre = changes.get("nombre")
        if new_nombre is not None and new_nombre != obj.nombre:
            existing = await self._find_by_nombre(
                obj.tenant_id, obj.comision_id, new_nombre
            )
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe una Unidad con nombre '{new_nombre}' en esta comisión",
                )

        for k, v in changes.items():
            setattr(obj, k, v)
        obj.updated_at = utc_now()

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="unidad.update",
            resource_type="unidad",
            resource_id=unidad_id,
            changes={"after": changes},
        )
        self.session.add(audit)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, unidad_id: UUID, user: User) -> None:
        """Soft-delete de una Unidad (sets deleted_at=NOW).

        Las TPs asignadas quedan con unidad_id apuntando a la Unidad
        soft-deleted. El ON DELETE SET NULL del FK solo actúa cuando
        se hace un DROP o DELETE real de la fila (hard-delete). En
        lecturas, filtrar por `deleted_at IS NULL` excluye la Unidad.
        """
        obj = await self.get_by_id(unidad_id)
        obj.deleted_at = utc_now()
        obj.updated_at = utc_now()

        audit = AuditLog(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="unidad.delete",
            resource_type="unidad",
            resource_id=unidad_id,
            changes={"soft_delete": True},
        )
        self.session.add(audit)
        await self.session.flush()

    async def reorder(
        self,
        items: list[UnidadReorderItem],
        user: User,
    ) -> list[Unidad]:
        """Actualiza el campo `orden` de múltiples Unidades en una transacción.

        El constraint `uq_unidad_orden` es DEFERRABLE INITIALLY DEFERRED,
        lo que permite que un swap (ej. U1.orden 1→3, U3.orden 3→1) no
        viole la unicidad durante la actualización. La constraint se evalúa
        al COMMIT, no en cada SET.
        """
        unidad_ids = [item.id for item in items]

        # Cargar todas las Unidades del batch en una query
        stmt = select(Unidad).where(
            Unidad.id.in_(unidad_ids),
            Unidad.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        unidades = {u.id: u for u in result.scalars().all()}

        # Validar que todas existen
        missing = [str(uid) for uid in unidad_ids if uid not in unidades]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unidades no encontradas: {', '.join(missing)}",
            )

        # Aplicar nuevos ordenes
        for item in items:
            unidades[item.id].orden = item.orden
            unidades[item.id].updated_at = utc_now()

        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="unidad.reorder",
            resource_type="unidad",
            resource_id=unidad_ids[0] if unidad_ids else None,
            changes={
                "reorder": [
                    {"id": str(item.id), "orden": item.orden} for item in items
                ]
            },
        )
        self.session.add(audit)
        await self.session.flush()

        # Retornar las unidades actualizadas ordenadas por nuevo orden
        return sorted(unidades.values(), key=lambda u: u.orden)

    # ── helpers privados ──────────────────────────────────────────────

    async def _find_by_nombre(
        self,
        tenant_id: UUID,
        comision_id: UUID,
        nombre: str,
    ) -> Unidad | None:
        """Busca una Unidad activa por nombre en una comisión."""
        stmt = select(Unidad).where(
            Unidad.tenant_id == tenant_id,
            Unidad.comision_id == comision_id,
            Unidad.nombre == nombre,
            Unidad.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
