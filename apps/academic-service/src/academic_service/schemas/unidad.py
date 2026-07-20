"""Schemas para Unidad temática (ADR-041)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UnidadCreate(BaseModel):
    """Request de creación de Unidad."""

    comision_id: UUID
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    orden: int = Field(default=0, ge=0)


class UnidadUpdate(BaseModel):
    """Request de actualización parcial de Unidad.

    Todos los campos son opcionales — PATCH semántico.
    """

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = None
    orden: int | None = Field(default=None, ge=0)


class UnidadOut(BaseModel):
    """Response de Unidad serializado desde el ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    nombre: str
    descripcion: str | None = None
    orden: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class UnidadReorderItem(BaseModel):
    """Item del request de bulk-reorder."""

    id: UUID
    orden: int = Field(ge=0)


class UnidadReorderRequest(BaseModel):
    """Request de reordenamiento bulk de Unidades.

    Contiene la lista de pares (id, nuevo_orden). La transacción aplica
    todos los cambios con la constraint uq_unidad_orden DEFERRABLE para
    permitir swaps sin violar la unicidad durante la operación.
    """

    items: list[UnidadReorderItem] = Field(min_length=1)
