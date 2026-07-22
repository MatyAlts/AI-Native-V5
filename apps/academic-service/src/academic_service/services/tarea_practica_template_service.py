"""Service de Tarea Práctica Template (refactor 2026-05-12).

La plantilla es un BRIEF pedagógico (consigna + meta) que sirve como prompt
para que el docente o la IA generen el TP real en cada comisión. Sin fan-out
automático: crear un template NO crea instancias.

Invariantes:
- Publicados/archivados son **inmutables** — PATCH sobre no-draft → 409.
- Soft delete del template NO toca instancias que lo referencian (`template_id`
  en `tareas_practicas` solo marca trazabilidad de origen, no dependencia).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth.dependencies import User
from academic_service.models import AuditLog, TareaPractica, TareaPracticaTemplate
from academic_service.repositories import TareaPracticaTemplateRepository
from academic_service.schemas.tarea_practica_template import (
    TareaPracticaTemplateCreate,
    TareaPracticaTemplateUpdate,
)

logger = logging.getLogger(__name__)


class TareaPracticaTemplateService:
    """CRUD + versionado + export-prompt de `TareaPracticaTemplate`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TareaPracticaTemplateRepository()

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _get_template_or_404(
        self, template_id: UUID, tenant_id: UUID
    ) -> TareaPracticaTemplate:
        obj = await self.repo.get_by_id(self.session, tenant_id, template_id)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="TareaPracticaTemplate no encontrada",
            )
        return obj

    def _add_audit(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        action: str,
        resource_id: UUID,
        changes: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                resource_type="tarea_practica_template",
                resource_id=resource_id,
                changes=changes,
            )
        )

    # ------------------------------------------------------------------
    # CRUD público
    # ------------------------------------------------------------------

    async def create(self, data: TareaPracticaTemplateCreate, user: User) -> TareaPracticaTemplate:
        """Crea un template (brief pedagógico). NO instancia TPs en comisiones —
        los TPs se crean on-demand por el docente, opcionalmente referenciando
        este template via `template_id`.
        """
        template = await self.repo.create(
            self.session,
            user.tenant_id,
            {
                "id": uuid4(),
                "materia_id": data.materia_id,
                "periodo_id": data.periodo_id,
                "codigo": data.codigo,
                "titulo": data.titulo,
                "consigna": data.consigna,
                "peso": data.peso,
                "estado": "draft",
                "version": 1,
                "parent_template_id": None,
            },
            user.id,
        )

        self._add_audit(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="tarea_practica_template.create",
            resource_id=template.id,
            changes={
                "template_id": str(template.id),
                "materia_id": str(data.materia_id),
                "periodo_id": str(data.periodo_id),
            },
        )
        await self.session.flush()
        return template

    async def get(self, template_id: UUID, tenant_id: UUID) -> TareaPracticaTemplate:
        return await self._get_template_or_404(template_id, tenant_id)

    async def update(
        self,
        template_id: UUID,
        patch: TareaPracticaTemplateUpdate,
        user: User,
    ) -> TareaPracticaTemplate:
        """PATCH sobre draft. Templates publicados/archivados son inmutables.

        NO toca instancias — el docente decide cómo propagar via `new_version`.
        """
        obj = await self._get_template_or_404(template_id, user.tenant_id)
        if obj.estado != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"Template en estado '{obj.estado}' es inmutable; cree una nueva versión"),
            )

        changes = patch.model_dump(exclude_unset=True, exclude_none=True)
        for k, v in changes.items():
            setattr(obj, k, v)

        self._add_audit(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica_template.update",
            resource_id=template_id,
            changes={"after": changes},
        )
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def publish(self, template_id: UUID, user: User) -> TareaPracticaTemplate:
        """Marca template como published. NO publica instancias."""
        obj = await self._get_template_or_404(template_id, user.tenant_id)
        if obj.estado == "published":
            return obj
        if obj.estado != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"No se puede publicar un template en estado '{obj.estado}'; "
                    "cree una nueva versión"
                ),
            )

        obj.estado = "published"
        self._add_audit(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica_template.publish",
            resource_id=template_id,
            changes={"estado": {"before": "draft", "after": "published"}},
        )
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def archive(self, template_id: UUID, user: User) -> TareaPracticaTemplate:
        """Marca template como archived. No archiva instancias."""
        obj = await self._get_template_or_404(template_id, user.tenant_id)
        if obj.estado == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El template ya está archivado",
            )

        before = obj.estado
        obj.estado = "archived"
        self._add_audit(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica_template.archive",
            resource_id=template_id,
            changes={"estado": {"before": before, "after": "archived"}},
        )
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def new_version(
        self,
        template_id: UUID,
        patch: TareaPracticaTemplateUpdate,
        user: User,
    ) -> TareaPracticaTemplate:
        """Crea v+1 del template (siempre en draft). Hereda campos del padre
        salvo los que el patch sobreescriba.
        """
        parent = await self._get_template_or_404(template_id, user.tenant_id)
        overrides = patch.model_dump(exclude_unset=True, exclude_none=True)

        new_template = await self.repo.create(
            self.session,
            user.tenant_id,
            {
                "id": uuid4(),
                "materia_id": parent.materia_id,
                "periodo_id": parent.periodo_id,
                "codigo": parent.codigo,
                "titulo": overrides.get("titulo", parent.titulo),
                "consigna": overrides.get("consigna", parent.consigna),
                "peso": overrides.get("peso", parent.peso),
                "estado": "draft",
                "version": parent.version + 1,
                "parent_template_id": parent.id,
            },
            user.id,
        )

        self._add_audit(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="tarea_practica_template.new_version",
            resource_id=new_template.id,
            changes={
                "old_id": str(parent.id),
                "new_id": str(new_template.id),
            },
        )
        await self.session.flush()
        return new_template

    async def get_prompt(self, template_id: UUID, tenant_id: UUID) -> dict[str, Any]:
        """Devuelve la plantilla formateada como prompt para usar en una IA
        externa o pasar al wizard interno de generación de TPs.
        """
        t = await self._get_template_or_404(template_id, tenant_id)
        prompt = (
            f"# {t.titulo}\n\n"
            f"**Código:** {t.codigo}\n"
            f"**Peso en la materia:** {t.peso}\n\n"
            f"## Consigna pedagógica\n\n"
            f"{t.consigna}\n\n"
            f"---\n\n"
            f"Generá un Trabajo Práctico que cumpla la consigna anterior. "
            f"Devolvé un enunciado claro para el alumno, una lista de "
            f"ejercicios secuenciales (con título, descripción en markdown, "
            f"código inicial opcional y peso relativo), y una rúbrica de "
            f"evaluación con criterios y pesos."
        )
        return {
            "template_id": t.id,
            "codigo": t.codigo,
            "titulo": t.titulo,
            "prompt": prompt,
        }

    async def list_instances(self, template_id: UUID, tenant_id: UUID) -> list[TareaPractica]:
        """Lista las instancias vigentes del template."""
        # Valida que el template exista (y pertenezca al tenant) antes de
        # listar; evita devolver `[]` falso positivo para un id inexistente.
        await self._get_template_or_404(template_id, tenant_id)
        return await self.repo.list_instances(self.session, tenant_id, template_id)

    async def list_versions(self, template_id: UUID, tenant_id: UUID) -> list[dict[str, Any]]:
        """Devuelve la cadena de versiones con flag `is_current` en la última no archivada."""
        await self._get_template_or_404(template_id, tenant_id)
        chain = await self.repo.list_versions(self.session, tenant_id, template_id)

        # "current" = la mayor versión no archivada (si existe).
        non_archived = [t for t in chain if t.estado != "archived"]
        current_id: UUID | None = None
        if non_archived:
            current_id = max(non_archived, key=lambda t: t.version).id

        return [
            {
                "id": t.id,
                "version": t.version,
                "estado": t.estado,
                "created_at": t.created_at,
                "is_current": t.id == current_id,
            }
            for t in chain
        ]

    async def soft_delete(self, template_id: UUID, user: User) -> TareaPracticaTemplate:
        """Soft-delete del template. NO borra instancias (evidencia CTR)."""
        obj = await self._get_template_or_404(template_id, user.tenant_id)

        # Contar instancias vigentes ANTES de soft-delete — para audit log.
        instances = await self.repo.list_instances(self.session, user.tenant_id, template_id)
        instances_remaining = len(instances)

        await self.repo.soft_delete(self.session, obj)

        self._add_audit(
            tenant_id=obj.tenant_id,
            user_id=user.id,
            action="tarea_practica_template.delete",
            resource_id=template_id,
            changes={
                "template_id": str(template_id),
                "instances_remaining": instances_remaining,
            },
        )
        await self.session.flush()
        return obj

    # `list` se define al final para no shadowar el builtin `list[X]` en las
    # anotaciones de retorno de los métodos previos (mypy lo detecta).
    async def list(
        self,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        periodo_id: UUID | None = None,
        estado: str | None = None,
    ) -> list[TareaPracticaTemplate]:
        """Lista templates del tenant. Si `materia_id` es None, listar todo."""
        stmt = select(TareaPracticaTemplate).where(
            TareaPracticaTemplate.tenant_id == tenant_id,
            TareaPracticaTemplate.deleted_at.is_(None),
        )
        if materia_id is not None:
            stmt = stmt.where(TareaPracticaTemplate.materia_id == materia_id)
        if periodo_id is not None:
            stmt = stmt.where(TareaPracticaTemplate.periodo_id == periodo_id)
        if estado is not None:
            stmt = stmt.where(TareaPracticaTemplate.estado == estado)
        stmt = stmt.order_by(TareaPracticaTemplate.codigo, TareaPracticaTemplate.version)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
