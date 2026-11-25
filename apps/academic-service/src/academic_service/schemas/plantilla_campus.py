"""Schemas de plantillas de campus (HU-036)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlantillaCampusCreate(BaseModel):
    """Guardar el campus de `comision_id` como plantilla de su materia."""

    comision_id: UUID
    nombre: str = Field(min_length=1, max_length=200)

    @field_validator("nombre")
    @classmethod
    def _nombre_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de la plantilla no puede estar vacio")
        return v


class PlantillaCampusAplicar(BaseModel):
    comision_id: UUID


class PlantillaCampusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    materia_id: UUID
    created_at: datetime


class AplicacionPlantillaOut(BaseModel):
    unidades_creadas: int
    unidades_omitidas: list[str]
    tps_creados: int
    bienvenida_aplicada: bool
    tps_omitidos: list[str] = []
