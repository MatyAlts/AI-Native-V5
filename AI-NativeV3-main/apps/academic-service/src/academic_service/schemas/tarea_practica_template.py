"""Schemas para Tarea Práctica Template (refactor 2026-05-12).

La plantilla es un BRIEF pedagógico (no una copia del TP). Contiene la
consigna que sirve como prompt para que el docente o la IA generen el TP
real en cada comisión. Sin fan-out automático.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TareaPracticaTemplateBase(BaseModel):
    titulo: str = Field(min_length=2, max_length=200)
    consigna: str = Field(
        min_length=1,
        description="Directiva pedagógica: qué debe cubrir el TP. Sirve como prompt para el docente o la IA.",
    )
    peso: Decimal = Field(default=Decimal("1.0"), ge=0, le=1)


class TareaPracticaTemplateCreate(TareaPracticaTemplateBase):
    materia_id: UUID
    periodo_id: UUID
    codigo: str = Field(min_length=1, max_length=20)


class TareaPracticaTemplateUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=2, max_length=200)
    consigna: str | None = Field(default=None, min_length=1)
    peso: Decimal | None = Field(default=None, ge=0, le=1)


class TareaPracticaTemplateOut(TareaPracticaTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    periodo_id: UUID
    codigo: str
    estado: Literal["draft", "published", "archived"]
    version: int
    parent_template_id: UUID | None = None
    created_by: UUID
    created_at: datetime
    deleted_at: datetime | None = None


class TareaPracticaTemplateVersionRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    estado: str
    created_at: datetime
    is_current: bool


class TareaPracticaTemplatePrompt(BaseModel):
    """Respuesta de `GET /tareas-practicas-templates/{id}/prompt`.

    Texto formateado para copiar/pegar en una IA externa o usar como base
    en el wizard de generación de TPs.
    """

    template_id: UUID
    codigo: str
    titulo: str
    prompt: str
