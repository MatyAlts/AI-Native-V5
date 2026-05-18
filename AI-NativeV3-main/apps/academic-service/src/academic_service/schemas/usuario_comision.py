"""Schemas para UsuarioComision (docente/auxiliar asignado a una comision)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsuarioComisionCreate(BaseModel):
    user_id: UUID
    rol: Literal["titular", "adjunto", "jtp", "ayudante", "corrector"]
    fecha_desde: date
    fecha_hasta: date | None = None


class UsuarioComisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    user_id: UUID
    rol: str
    permisos_extra: list[str] = Field(default_factory=list)
    fecha_desde: date
    fecha_hasta: date | None = None
    created_at: datetime
    deleted_at: datetime | None = None
