"""Schemas para Unidad temática (ADR-041)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# HU-033: tope del HTML del campus (bienvenida e introduccion de unidad).
# Alcanza para un resumen interactivo con su JS inline; mas largo es 422.
HTML_CAMPUS_MAX_CHARS = 512_000


class UnidadCreate(BaseModel):
    """Request de creación de Unidad."""

    comision_id: UUID
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    orden: int = Field(default=0, ge=0)
    introduccion_html: str | None = Field(default=None, max_length=HTML_CAMPUS_MAX_CHARS)
    fecha_apertura: date | None = None


class UnidadUpdate(BaseModel):
    """Request de actualización parcial de Unidad.

    Todos los campos son opcionales — PATCH semántico.
    """

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = None
    orden: int | None = Field(default=None, ge=0)
    introduccion_html: str | None = Field(default=None, max_length=HTML_CAMPUS_MAX_CHARS)
    # `null` explicito = sin fecha (la unidad queda abierta).
    fecha_apertura: date | None = None


class UnidadOut(BaseModel):
    """Response de Unidad serializado desde el ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    nombre: str
    descripcion: str | None = None
    orden: int
    introduccion_html: str | None = None
    fecha_apertura: date | None = None
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
