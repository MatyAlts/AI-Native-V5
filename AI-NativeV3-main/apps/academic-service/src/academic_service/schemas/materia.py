"""Schemas para Materia."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MateriaBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    codigo: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    horas_totales: int = Field(ge=16, le=500, default=96)
    cuatrimestre_sugerido: int = Field(ge=1, le=20, default=1)
    objetivos: str | None = Field(default=None, max_length=5000)
    correlativas_cursar: list[UUID] = Field(default_factory=list)
    correlativas_rendir: list[UUID] = Field(default_factory=list)


class MateriaCreate(MateriaBase):
    plan_id: UUID


class MateriaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    horas_totales: int | None = Field(default=None, ge=16, le=500)
    cuatrimestre_sugerido: int | None = Field(default=None, ge=1, le=20)
    objetivos: str | None = Field(default=None, max_length=5000)
    correlativas_cursar: list[UUID] | None = None
    correlativas_rendir: list[UUID] | None = None


class MateriaOut(MateriaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    plan_id: UUID
    created_at: datetime
    deleted_at: datetime | None = None
