"""Schemas para Universidad (tenant raíz)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UniversidadBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    codigo: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    dominio_email: str | None = Field(default=None, max_length=200)
    keycloak_realm: str = Field(min_length=2, max_length=100)


class UniversidadCreate(UniversidadBase):
    config: dict[str, Any] = Field(default_factory=dict)


class UniversidadUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    dominio_email: str | None = None
    config: dict[str, Any] | None = None


class UniversidadOut(UniversidadBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    config: dict[str, Any]
    created_at: datetime
    deleted_at: datetime | None = None
