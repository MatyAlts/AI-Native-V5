"""Schemas para UsuarioComision (docente/auxiliar asignado a una comision)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsuarioComisionCreate(BaseModel):
    # El admin asigna por EMAIL (no conoce el user_id: el docente todavia no
    # se logueo). La identidad real se resuelve en el primer login con Clerk.
    # `str` y no `EmailStr` a proposito: EmailStr exige el extra pydantic[email]
    # que no esta instalado en el container slim del academic-service.
    email: str
    rol: Literal["titular", "adjunto", "jtp", "ayudante", "corrector"] = "titular"
    fecha_desde: date | None = None
    fecha_hasta: date | None = None


class UsuarioComisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    user_id: UUID | None = None
    email: str | None = None
    rol: str
    permisos_extra: list[str] = Field(default_factory=list)
    fecha_desde: date
    fecha_hasta: date | None = None
    created_at: datetime
    deleted_at: datetime | None = None
