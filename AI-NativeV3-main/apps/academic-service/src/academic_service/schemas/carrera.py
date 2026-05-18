"""Schemas para Carrera."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CarreraBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    codigo: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    duracion_semestres: int = Field(ge=1, le=20, default=8)
    modalidad: Literal["presencial", "virtual", "hibrida"] = "presencial"


class CarreraCreate(CarreraBase):
    facultad_id: UUID
    director_user_id: UUID | None = None


class CarreraUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    duracion_semestres: int | None = Field(default=None, ge=1, le=20)
    modalidad: Literal["presencial", "virtual", "hibrida"] | None = None
    director_user_id: UUID | None = None


class CarreraOut(CarreraBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    universidad_id: UUID
    facultad_id: UUID
    director_user_id: UUID | None
    created_at: datetime
    deleted_at: datetime | None = None
