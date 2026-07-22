"""Schemas para Inscripcion (estudiante en una comisión).

ADR-029 (B.1, 2026-04-29): inscripciones se sumaron al bulk-import de
academic-service para destrabar el alta masiva via CSV. El endpoint de
enrollment-service `POST /api/v1/imports` queda deprecated por ADR-030.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InscripcionBase(BaseModel):
    rol: Literal["regular", "oyente", "reinscripcion"] = "regular"
    estado: Literal["activa", "cursando", "aprobado", "desaprobado", "abandono"] = "activa"
    fecha_inscripcion: date


class InscripcionCreate(InscripcionBase):
    """Payload para crear una inscripcion (CSV bulk o REST).

    El `student_pseudonym` se acepta como UUID — debe ser pre-derivado por
    enrollment / federacion LDAP antes de llegar al CSV. La identidad real
    vive en Keycloak (no en este monorepo).
    """

    comision_id: UUID
    student_pseudonym: UUID
    nota_final: Decimal | None = Field(default=None, ge=0, le=10)
    fecha_cierre: date | None = None


class InscripcionCreateIndividual(InscripcionBase):
    """Payload para crear una inscripcion individual via REST.

    A diferencia de `InscripcionCreate` (usada por bulk-import via CSV), no
    requiere `comision_id` porque ese viene del path param del endpoint
    `POST /api/v1/comisiones/{comision_id}/inscripciones`. Pensado para los
    flujos manuales del docente desde el web-teacher.
    """

    student_pseudonym: UUID
    nota_final: Decimal | None = Field(default=None, ge=0, le=10)
    fecha_cierre: date | None = None


class InscripcionOut(InscripcionBase):
    """Response model de Inscripcion.

    `nota_final` (calificación final de cursada del estudiante en la comisión)
    se serializa como `float` (no `Decimal`) para evitar el wire-format `"8.50"`
    (string) que los frontends tipan como `number`. La columna SQLAlchemy sigue
    siendo `Numeric(5,2)` — la conversión es solo en serialización. Para nota
    académica 0-10 con un decimal de precisión, `float` es adecuado y no
    introduce error. Mismo patrón que `CalificacionOut.nota_final` (entregas,
    sprint 2026-05-17) — replicado acá para la nota de cursada.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    nota_final: float | None = None
    fecha_cierre: date | None = None
    created_at: datetime

    @field_validator("nota_final", mode="before")
    @classmethod
    def _decimal_to_float(cls, v: object) -> object:
        """Castea Decimal -> float al construir desde el ORM.

        Pydantic acepta Decimal en `float` field, pero el cast explícito
        garantiza wire-format `8.5` (no `"8.50"`) sin depender del
        comportamiento implícito del serializer. Preserva nullability.
        """
        if v is None:
            return None
        if isinstance(v, Decimal):
            return float(v)
        return v


class MateriaInscripta(BaseModel):
    """Vista flatten de una materia en la que el estudiante está inscripto.

    Combina datos de Inscripcion + Comision + Materia + Periodo en una sola
    fila por inscripcion activa. Es el shape que necesita la home del
    web-student: el alumno elige materia (no comision), y la comision queda
    como metadata implícita.

    El `horario_resumen` se deriva del JSONB `comisiones.horario` cuando
    contiene un string descriptivo; si no, queda en None y la UI no lo muestra.
    """

    model_config = ConfigDict(from_attributes=True)

    materia_id: UUID
    codigo: str  # codigo de la materia (ej. "PROG2")
    nombre: str  # nombre de la materia (ej. "Programacion 2")
    comision_id: UUID
    comision_codigo: str  # codigo de la comision (ej. "A")
    comision_nombre: str | None  # nombre legible de la comision (ej. "A-Manana")
    horario_resumen: str | None  # resumen humano del horario, derivado de horario JSONB
    periodo_id: UUID
    periodo_codigo: str  # codigo del periodo (ej. "2026-S1")
    inscripcion_id: UUID
    fecha_inscripcion: date
