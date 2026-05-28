"""Schemas para student_profile (auto-llenado desde Clerk)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentProfileUpsert(BaseModel):
    """Payload que envia el web-student al loguearse con Clerk."""

    full_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None


class StudentProfileOut(BaseModel):
    """Vista del docente: pseudonym + nombre real (si lo cargo el alumno)."""

    model_config = ConfigDict(from_attributes=True)

    student_pseudonym: uuid.UUID
    full_name: str | None = None
    email: str | None = None
    updated_at: datetime | None = None
