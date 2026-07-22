"""Endpoints de Tarea Práctica Template (refactor 2026-05-12).

La plantilla es un BRIEF pedagógico (consigna + meta) que sirve como prompt
para que el docente o el wizard de IA generen el TP real en cada comisión.
Sin fan-out automático.

Todos los endpoints exigen `X-Tenant-Id` + `X-User-Id` inyectados por
api-gateway (o por los vite proxies en dev_trust_headers). El permiso
Casbin `tarea_practica_template:<action>` se verifica en `require_permission`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas.tarea_practica import TareaPracticaOut
from academic_service.schemas.tarea_practica_template import (
    TareaPracticaTemplateCreate,
    TareaPracticaTemplateOut,
    TareaPracticaTemplatePrompt,
    TareaPracticaTemplateUpdate,
    TareaPracticaTemplateVersionRef,
)
from academic_service.services.tarea_practica_template_service import (
    TareaPracticaTemplateService,
)

router = APIRouter(
    prefix="/api/v1/tareas-practicas-templates",
    tags=["tareas-practicas-templates"],
)


class NewVersionRequest(BaseModel):
    """Body del endpoint `new-version`: solo el patch a aplicar."""

    patch: TareaPracticaTemplateUpdate


@router.post(
    "",
    response_model=TareaPracticaTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    data: TareaPracticaTemplateCreate,
    user: User = Depends(require_permission("tarea_practica_template", "create")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplateOut:
    svc = TareaPracticaTemplateService(db)
    obj = await svc.create(data, user)
    return TareaPracticaTemplateOut.model_validate(obj)


@router.get("", response_model=list[TareaPracticaTemplateOut])
async def list_templates(
    materia_id: UUID | None = Query(default=None),
    periodo_id: UUID | None = Query(default=None),
    estado: Literal["draft", "published", "archived"] | None = Query(default=None),
    user: User = Depends(require_permission("tarea_practica_template", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[TareaPracticaTemplateOut]:
    svc = TareaPracticaTemplateService(db)
    objs = await svc.list(
        tenant_id=user.tenant_id,
        materia_id=materia_id,
        periodo_id=periodo_id,
        estado=estado,
    )
    return [TareaPracticaTemplateOut.model_validate(o) for o in objs]


@router.get("/{template_id}", response_model=TareaPracticaTemplateOut)
async def get_template(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "read")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplateOut:
    svc = TareaPracticaTemplateService(db)
    obj = await svc.get(template_id, user.tenant_id)
    return TareaPracticaTemplateOut.model_validate(obj)


@router.patch("/{template_id}", response_model=TareaPracticaTemplateOut)
async def update_template(
    template_id: UUID,
    data: TareaPracticaTemplateUpdate,
    user: User = Depends(require_permission("tarea_practica_template", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplateOut:
    svc = TareaPracticaTemplateService(db)
    obj = await svc.update(template_id, data, user)
    return TareaPracticaTemplateOut.model_validate(obj)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = TareaPracticaTemplateService(db)
    await svc.soft_delete(template_id, user)


@router.post("/{template_id}/publish", response_model=TareaPracticaTemplateOut)
async def publish_template(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplateOut:
    svc = TareaPracticaTemplateService(db)
    obj = await svc.publish(template_id, user)
    return TareaPracticaTemplateOut.model_validate(obj)


@router.post("/{template_id}/archive", response_model=TareaPracticaTemplateOut)
async def archive_template(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplateOut:
    svc = TareaPracticaTemplateService(db)
    obj = await svc.archive(template_id, user)
    return TareaPracticaTemplateOut.model_validate(obj)


@router.post(
    "/{template_id}/new-version",
    response_model=TareaPracticaTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def new_version_template(
    template_id: UUID,
    body: NewVersionRequest,
    user: User = Depends(require_permission("tarea_practica_template", "update")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplateOut:
    svc = TareaPracticaTemplateService(db)
    obj = await svc.new_version(template_id, body.patch, user)
    return TareaPracticaTemplateOut.model_validate(obj)


@router.get(
    "/{template_id}/instances",
    response_model=list[TareaPracticaOut],
)
async def list_template_instances(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[TareaPracticaOut]:
    """Lista TPs (instancias) creados manualmente que referencian este template
    via `template_id`. Útil para trazabilidad — qué TPs nacieron de qué brief.
    """
    svc = TareaPracticaTemplateService(db)
    instances = await svc.list_instances(template_id, user.tenant_id)
    return [TareaPracticaOut.model_validate(i) for i in instances]


@router.get(
    "/{template_id}/prompt",
    response_model=TareaPracticaTemplatePrompt,
)
async def export_template_prompt(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "read")),
    db: AsyncSession = Depends(get_db),
) -> TareaPracticaTemplatePrompt:
    """Devuelve la plantilla formateada como prompt listo para copiar/pegar
    en una IA externa (ChatGPT, Claude) o pasar al wizard interno.
    """
    svc = TareaPracticaTemplateService(db)
    data = await svc.get_prompt(template_id, user.tenant_id)
    return TareaPracticaTemplatePrompt.model_validate(data)


@router.get(
    "/{template_id}/versions",
    response_model=list[TareaPracticaTemplateVersionRef],
)
async def list_template_versions(
    template_id: UUID,
    user: User = Depends(require_permission("tarea_practica_template", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[TareaPracticaTemplateVersionRef]:
    svc = TareaPracticaTemplateService(db)
    versions = await svc.list_versions(template_id, user.tenant_id)
    return [TareaPracticaTemplateVersionRef.model_validate(v) for v in versions]
