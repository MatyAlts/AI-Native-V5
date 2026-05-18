"""Schemas para Facultad."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FacultadBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    codigo: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")


class FacultadCreate(FacultadBase):
    universidad_id: UUID
    decano_user_id: UUID | None = None


class FacultadUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    decano_user_id: UUID | None = None


class FacultadOut(FacultadBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    universidad_id: UUID
    decano_user_id: UUID | None
    created_at: datetime
    deleted_at: datetime | None = None
