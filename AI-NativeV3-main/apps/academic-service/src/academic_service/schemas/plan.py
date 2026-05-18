"""Schemas para PlanEstudios."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanBase(BaseModel):
    version: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9._-]+$")
    año_inicio: int = Field(ge=1950, le=2100)
    ordenanza: str | None = Field(default=None, max_length=100)
    vigente: bool = True


class PlanCreate(PlanBase):
    carrera_id: UUID


class PlanUpdate(BaseModel):
    version: str | None = Field(
        default=None, min_length=1, max_length=20, pattern=r"^[A-Za-z0-9._-]+$"
    )
    año_inicio: int | None = Field(default=None, ge=1950, le=2100)
    ordenanza: str | None = Field(default=None, max_length=100)
    vigente: bool | None = None


class PlanOut(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    carrera_id: UUID
    created_at: datetime
    deleted_at: datetime | None = None
