"""Schemas para student_profile (auto-llenado desde Clerk)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StudentProfileUpsert(BaseModel):
    """Payload que envia el web-student al loguearse con Clerk.

    Nota: email viene como str (no EmailStr) para no depender del extra
    `pydantic[email]` que no esta instalado en el container slim. Clerk
    ya valida el email del lado del frontend antes de mandarlo.
    """

    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)


class StudentProfileOut(BaseModel):
    """Vista del docente: pseudonym + nombre real (si lo cargo el alumno)."""

    model_config = ConfigDict(from_attributes=True)

    student_pseudonym: uuid.UUID
    full_name: str | None = None
    email: str | None = None
    updated_at: datetime | None = None
