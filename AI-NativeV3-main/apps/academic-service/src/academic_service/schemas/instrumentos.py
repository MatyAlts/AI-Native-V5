"""Schemas Pydantic para los 3 instrumentos del diseño cuasi-experimental.

Cierran P2-1, P2-2, P2-3 del PlanMejora.md. Cada instrumento tiene Create
(POST request) y Out (GET response). El JSONB `responses` es genérico para
no acoplar el contrato al contenido específico de cada versión del instrumento.

Validacion de contenido: se hace server-side via `services/instrumentos_service.py`
contra el schema declarativo de la version del instrumento (que vive en
`services/instrumentos_content.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# P2-2 — CUESTIONARIO IA PREVIA
# ============================================================================


class CuestionarioIACreate(BaseModel):
    """Request POST /api/v1/instrumentos/cuestionario-ia.

    El campo `responses` es un dict con las respuestas del estudiante.
    El schema concreto de las respuestas depende de `instrument_version` y
    se valida server-side contra el catalogo de items vigente.
    """

    comision_id: UUID
    student_pseudonym: UUID
    instrument_version: str = Field(
        default="cuestionario-ia-v0.1.0-draft",
        max_length=40,
        description="Version del instrumento. Default = v0.1.0-draft (pendiente validacion coautoral).",
    )
    responses: dict[str, Any] = Field(
        ...,
        description="Respuestas del estudiante por item. Schema validado server-side.",
    )


class CuestionarioIAOut(BaseModel):
    """Response del cuestionario IA persistido."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    instrument_version: str
    responses: dict[str, Any]
    submitted_at: datetime
    created_at: datetime


# ============================================================================
# P2-1 — PRETEST AUTOEFICACIA
# ============================================================================


class PretestAutoeficaciaCreate(BaseModel):
    """Request POST /api/v1/instrumentos/pretest-autoeficacia.

    El score total y por sub-escala se calculan server-side a partir de las
    respuestas crudas; el cliente NO los envia.
    """

    comision_id: UUID
    student_pseudonym: UUID
    instrument_version: str = Field(
        default="lishinski-2016-es-utn-v0.1.0-draft",
        max_length=40,
    )
    responses: dict[str, Any] = Field(
        ...,
        description="Respuestas Likert por item. Schema validado server-side.",
    )


class PretestAutoeficaciaOut(BaseModel):
    """Response del pretest persistido con scores calculados."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    instrument_version: str
    responses: dict[str, Any]
    total_score: int | None = None
    subscale_scores: dict[str, Any] | None = None
    submitted_at: datetime
    created_at: datetime


# ============================================================================
# P2-3 — TEST DE TRANSFERENCIA
# ============================================================================


GroupAssignment = Literal["experimental", "comparison"]


class TestTransferenciaCreate(BaseModel):
    """Request POST /api/v1/instrumentos/transferencia.

    Aplica al grupo experimental (con CTR activo) y al grupo de comparacion
    (sin CTR). El campo `group_assignment` discrimina entre ambos.

    El `correct_answer` se calcula server-side comparando `response_detail`
    contra la solucion canonica del test_id. El cliente NO lo envia.
    """

    comision_id: UUID
    student_pseudonym: UUID
    instrument_version: str = Field(
        default="transfer-test-v0.1.0-draft",
        max_length=40,
    )
    group_assignment: GroupAssignment
    test_id: str = Field(min_length=1, max_length=50)
    time_taken_seconds: int = Field(ge=0)
    response_detail: dict[str, Any] = Field(
        ...,
        description="Respuesta cruda del estudiante (codigo, opcion, texto). Server-side se compara contra solucion canonica.",
    )


class TestTransferenciaOut(BaseModel):
    """Response del intento de transferencia persistido con correct_answer evaluado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    instrument_version: str
    group_assignment: GroupAssignment
    test_id: str
    correct_answer: bool
    time_taken_seconds: int
    response_detail: dict[str, Any]
    submitted_at: datetime
    created_at: datetime
