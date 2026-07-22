"""Eventos del plano académico que se publican al bus."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AcademicBaseEvent(BaseModel):
    """Base de eventos del plano académico."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_uuid: UUID
    tenant_id: UUID
    ts: datetime
    event_type: str


class UniversidadCreadaPayload(BaseModel):
    universidad_id: UUID
    nombre: str
    codigo: str
    config_keycloak_realm: str


class UniversidadCreada(AcademicBaseEvent):
    event_type: Literal["UniversidadCreada"] = "UniversidadCreada"
    payload: UniversidadCreadaPayload


class CarreraCreadaPayload(BaseModel):
    carrera_id: UUID
    universidad_id: UUID
    facultad_id: UUID | None = None
    nombre: str
    codigo: str


class CarreraCreada(AcademicBaseEvent):
    event_type: Literal["CarreraCreada"] = "CarreraCreada"
    payload: CarreraCreadaPayload


class ComisionCreadaPayload(BaseModel):
    comision_id: UUID
    materia_id: UUID
    periodo_id: UUID
    codigo: str
    cupo_maximo: int = Field(ge=0)


class ComisionCreada(AcademicBaseEvent):
    event_type: Literal["ComisionCreada"] = "ComisionCreada"
    payload: ComisionCreadaPayload


class EstudianteInscriptoPayload(BaseModel):
    inscripcion_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    rol: Literal["regular", "oyente", "reinscripcion"] = "regular"


class EstudianteInscripto(AcademicBaseEvent):
    event_type: Literal["EstudianteInscripto"] = "EstudianteInscripto"
    payload: EstudianteInscriptoPayload


class MaterialIngeridoPayload(BaseModel):
    material_id: UUID
    comision_id: UUID
    tipo: Literal["pdf", "markdown", "code_archive", "video"]
    chunks_count: int = Field(ge=0)
    embedding_model: str


class MaterialIngerido(AcademicBaseEvent):
    event_type: Literal["MaterialIngerido"] = "MaterialIngerido"
    payload: MaterialIngeridoPayload
