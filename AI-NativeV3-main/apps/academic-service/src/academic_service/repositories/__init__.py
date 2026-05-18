"""Repositorios específicos por entidad del dominio."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.models import (
    Carrera,
    Comision,
    Ejercicio,
    Facultad,
    Inscripcion,
    Materia,
    Periodo,
    PlanEstudios,
    TareaPractica,
    TareaPracticaTemplate,
    TpEjercicio,
    Unidad,
    Universidad,
    UsuarioComision,
)
from academic_service.models.base import utc_now
from academic_service.repositories.base import BaseRepository


class UniversidadRepository(BaseRepository[Universidad]):
    model = Universidad


class FacultadRepository(BaseRepository[Facultad]):
    model = Facultad


class CarreraRepository(BaseRepository[Carrera]):
    model = Carrera


class PlanEstudiosRepository(BaseRepository[PlanEstudios]):
    model = PlanEstudios


class MateriaRepository(BaseRepository[Materia]):
    model = Materia


class PeriodoRepository(BaseRepository[Periodo]):
    model = Periodo


class ComisionRepository(BaseRepository[Comision]):
    model = Comision


class InscripcionRepository(BaseRepository[Inscripcion]):
    model = Inscripcion


class UsuarioComisionRepository(BaseRepository[UsuarioComision]):
    model = UsuarioComision


class TareaPracticaRepository(BaseRepository[TareaPractica]):
    model = TareaPractica


class UnidadRepository(BaseRepository[Unidad]):
    model = Unidad


class EjercicioRepository(BaseRepository[Ejercicio]):
    """CRUD del banco de ejercicios reusables (ADR-047)."""

    model = Ejercicio


class TpEjercicioRepository:
    """Asociaciones N:M entre TareaPractica y Ejercicio (ADR-047).

    No hereda de BaseRepository porque la tabla NO tiene `deleted_at`
    (soft-delete no aplica — la asociación se borra hard cuando el
    docente saca el ejercicio de una TP, y CASCADE-deletea con la TP).
    """

    model = TpEjercicio

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_tp(self, tarea_practica_id: UUID) -> list[TpEjercicio]:
        stmt = (
            select(TpEjercicio)
            .where(TpEjercicio.tarea_practica_id == tarea_practica_id)
            .order_by(TpEjercicio.orden)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pair(
        self, tarea_practica_id: UUID, ejercicio_id: UUID
    ) -> TpEjercicio | None:
        stmt = select(TpEjercicio).where(
            TpEjercicio.tarea_practica_id == tarea_practica_id,
            TpEjercicio.ejercicio_id == ejercicio_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        tenant_id: UUID,
        tarea_practica_id: UUID,
        ejercicio_id: UUID,
        orden: int,
        peso_en_tp: Any,
    ) -> TpEjercicio:
        obj = TpEjercicio(
            id=uuid4(),
            tenant_id=tenant_id,
            tarea_practica_id=tarea_practica_id,
            ejercicio_id=ejercicio_id,
            orden=orden,
            peso_en_tp=peso_en_tp,
        )
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: TpEjercicio) -> None:
        await self.session.delete(obj)
        await self.session.flush()


class TareaPracticaTemplateRepository:
    """Repositorio de plantillas canónicas de TP (ADR-016).

    No hereda de `BaseRepository` porque sus métodos necesitan `session`
    + `tenant_id` explícitos (patrón defensivo por ADR-016 — los queries
    filtran tenant además del RLS). Mantiene paridad conceptual con los
    demás repos pero con una firma propia alineada a los service endpoints
    del template (create/new-version/publish/archive requieren user_id).
    """

    model = TareaPracticaTemplate

    async def create(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        data: dict[str, Any],
        user_id: UUID,
    ) -> TareaPracticaTemplate:
        payload: dict[str, Any] = {
            "id": data.get("id", uuid4()),
            "tenant_id": tenant_id,
            "materia_id": data["materia_id"],
            "periodo_id": data["periodo_id"],
            "codigo": data["codigo"],
            "titulo": data["titulo"],
            "consigna": data["consigna"],
            "peso": data["peso"],
            "estado": data.get("estado", "draft"),
            "version": data.get("version", 1),
            "parent_template_id": data.get("parent_template_id"),
            "created_by": user_id,
        }
        obj = TareaPracticaTemplate(**payload)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def get_by_id(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        template_id: UUID,
    ) -> TareaPracticaTemplate | None:
        stmt = select(TareaPracticaTemplate).where(
            TareaPracticaTemplate.id == template_id,
            TareaPracticaTemplate.tenant_id == tenant_id,
            TareaPracticaTemplate.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_materia_periodo(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        materia_id: UUID,
        periodo_id: UUID,
        *,
        estado: str | None = None,
    ) -> list[TareaPracticaTemplate]:
        stmt = select(TareaPracticaTemplate).where(
            TareaPracticaTemplate.tenant_id == tenant_id,
            TareaPracticaTemplate.materia_id == materia_id,
            TareaPracticaTemplate.periodo_id == periodo_id,
            TareaPracticaTemplate.deleted_at.is_(None),
        )
        if estado is not None:
            stmt = stmt.where(TareaPracticaTemplate.estado == estado)
        stmt = stmt.order_by(TareaPracticaTemplate.codigo, TareaPracticaTemplate.version)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        template: TareaPracticaTemplate,
        patch: dict[str, Any],
    ) -> TareaPracticaTemplate:
        for key, value in patch.items():
            if value is not None:
                setattr(template, key, value)
        await session.flush()
        await session.refresh(template)
        return template

    async def soft_delete(self, session: AsyncSession, template: TareaPracticaTemplate) -> None:
        template.deleted_at = utc_now()
        await session.flush()

    async def list_versions(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        template_id: UUID,
    ) -> list[TareaPracticaTemplate]:
        """Devuelve toda la cadena de versiones (ancestros + descendientes).

        Parte del template dado, sube hasta la raíz siguiendo
        `parent_template_id`, y luego baja por hijos. Mismo patrón que
        `TareaPracticaService.list_versions`, pero acotado por tenant.
        """
        anchor = await self.get_by_id(session, tenant_id, template_id)
        if anchor is None:
            return []

        root = anchor
        while root.parent_template_id is not None:
            stmt = select(TareaPracticaTemplate).where(
                TareaPracticaTemplate.id == root.parent_template_id,
                TareaPracticaTemplate.tenant_id == tenant_id,
                TareaPracticaTemplate.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            root = parent

        chain: list[TareaPracticaTemplate] = [root]
        seen: set[UUID] = {root.id}
        frontier: list[UUID] = [root.id]
        while frontier:
            stmt = select(TareaPracticaTemplate).where(
                TareaPracticaTemplate.parent_template_id.in_(frontier),
                TareaPracticaTemplate.tenant_id == tenant_id,
                TareaPracticaTemplate.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            children = list(result.scalars().all())
            new_frontier: list[UUID] = []
            for child in children:
                if child.id in seen:
                    continue
                seen.add(child.id)
                chain.append(child)
                new_frontier.append(child.id)
            frontier = new_frontier

        chain.sort(key=lambda t: t.version)
        return chain

    async def list_instances(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        template_id: UUID,
    ) -> list[TareaPractica]:
        """Lista las instancias vigentes (no soft-deleted) de un template."""
        stmt = (
            select(TareaPractica)
            .where(
                TareaPractica.template_id == template_id,
                TareaPractica.tenant_id == tenant_id,
                TareaPractica.deleted_at.is_(None),
            )
            .order_by(TareaPractica.comision_id, TareaPractica.version)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
