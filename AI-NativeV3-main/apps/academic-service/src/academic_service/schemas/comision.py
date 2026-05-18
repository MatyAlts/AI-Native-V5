"""Schemas para Periodo y Comisión."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PeriodoBase(BaseModel):
    codigo: str = Field(min_length=4, max_length=20)  # ej. "2026-S1"
    nombre: str = Field(min_length=2, max_length=100)
    fecha_inicio: date
    fecha_fin: date
    estado: Literal["abierto", "cerrado"] = "abierto"

    @model_validator(mode="after")
    def check_dates(self) -> PeriodoBase:
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("fecha_fin debe ser posterior a fecha_inicio")
        return self


class PeriodoCreate(PeriodoBase):
    pass


class PeriodoUpdate(BaseModel):
    """Update parcial de periodo.

    `codigo` es immutable (downstream: comisiones lo referencian). La
    transición de `estado` es one-way (abierto → cerrado); el service
    valida la regla (cerrado no se puede reabrir ni modificar).
    """

    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estado: Literal["abierto", "cerrado"] | None = None

    @model_validator(mode="after")
    def check_dates(self) -> PeriodoUpdate:
        if (
            self.fecha_inicio is not None
            and self.fecha_fin is not None
            and self.fecha_fin <= self.fecha_inicio
        ):
            raise ValueError("fecha_fin debe ser posterior a fecha_inicio")
        return self


class PeriodoOut(PeriodoBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_at: datetime


class ComisionBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=50)
    nombre: str = Field(min_length=1, max_length=100)
    cupo_maximo: int = Field(ge=1, le=500, default=50)
    horario: dict[str, Any] = Field(default_factory=dict)
    ai_budget_monthly_usd: Decimal = Field(default=Decimal("100.00"), ge=0, le=10000)


class ComisionCreate(ComisionBase):
    materia_id: UUID
    periodo_id: UUID


class ComisionUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    cupo_maximo: int | None = Field(default=None, ge=1, le=500)
    horario: dict[str, Any] | None = None
    ai_budget_monthly_usd: Decimal | None = Field(default=None, ge=0, le=10000)


class ComisionOut(ComisionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    periodo_id: UUID
    curso_config_hash: str | None = None
    created_at: datetime
    deleted_at: datetime | None = None


class ConfigHashesOut(BaseModel):
    """Bootstrap mínimo F9: hashes vigentes para abrir un episodio.

    El frontend del estudiante consulta este endpoint antes de pegarle a
    `POST /api/v1/episodes`. Reemplaza los hashes hardcoded de piloto
    ("c"*64 / "d"*64) por valores derivados deterministicamente de la
    config de la comisión y del classifier-service.

    - `curso_config_hash`: SHA-256 canónico de un dict mínimo
      (comision_id, materia_id, periodo_id, tenant_id, version). Es
      determinista por comisión hoy; en piloto-2 podría incluir rúbrica
      del curso u otros campos.
    - `classifier_config_hash`: el hash que el classifier-service usa al
      clasificar (`compute_classifier_config_hash`). Si el classifier no
      responde, el handler degrada al fallback "d"*64 (con warning).
    """

    comision_id: UUID
    curso_config_hash: str
    classifier_config_hash: str
