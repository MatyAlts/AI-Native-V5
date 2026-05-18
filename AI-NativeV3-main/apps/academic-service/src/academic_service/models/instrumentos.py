"""Modelos para los 3 instrumentos del diseño cuasi-experimental.

Cierran P2-1, P2-2, P2-3 del PlanMejora.md como ESQUELETO TECNICO. El
contenido academico (items, escalas, problemas) queda como placeholder
hasta revision coautoral con Ana Garis + comite etico UNSL.

Referencia conceptual:
- Cuestionario IA: paper Cortez & Garis §6.2 Tabla 4 (control "experiencia previa con IA")
- Pretest: docs/research/protocolo-autoeficacia-programacion.md (Lishinski et al. 2016)
- Transferencia: paper §6.1 H2 (medida dependiente "desempeño en tareas de transferencia")

Invariante: respuesta unica por (tenant, comision, student, version) — UNIQUE
constraint en cada tabla. Para transferencia se suma test_id porque un mismo
estudiante hace varios problemas.

ADR de respaldo: ADR-053 (marcos interpretativos + 7 principios) + ADR-001 (RLS).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from academic_service.models.base import Base, TenantMixin, utc_now


class RespuestaCuestionarioIA(Base, TenantMixin):
    """P2-2: Respuesta del estudiante al cuestionario sobre experiencia previa con IA.

    Una sola respuesta por (tenant, comision, student, instrument_version).
    Si el contenido del cuestionario evoluciona, se bumpea `instrument_version`
    y se acepta una nueva respuesta del mismo estudiante; analisis historico
    estratifica por version.
    """

    __tablename__ = "respuestas_cuestionario_ia"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            "instrument_version",
            name="uq_resp_cuestionario_ia_estudiante",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    comision_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("comisiones.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    instrument_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default="cuestionario-ia-v0.1.0-draft",
    )
    responses: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RespuestaPretestAutoeficacia(Base, TenantMixin):
    """P2-1: Respuesta del estudiante al pretest estandarizado de autoeficacia.

    Variable de control covariable para H1 y H2 del paper. El instrumento
    de referencia es Lishinski et al. 2016 (CS Self-Efficacy Scale 28 items)
    en su adaptacion al castellano v0.1.0-draft. Ver
    docs/research/protocolo-autoeficacia-programacion.md.
    """

    __tablename__ = "respuestas_pretest_autoeficacia"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            "instrument_version",
            name="uq_resp_pretest_autoeficacia_estudiante",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    comision_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("comisiones.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    instrument_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default="lishinski-2016-es-utn-v0.1.0-draft",
    )
    responses: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscale_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RespuestaTestTransferencia(Base, TenantMixin):
    """P2-3: Respuesta del estudiante a un problema del test de transferencia.

    Aplica al grupo experimental (con CTR activo) y al grupo de comparacion
    (sin CTR). El campo `group_assignment` discrimina entre ambos para los
    analisis de H2 del paper Cortez & Garis §6.1.

    UNIQUE incluye `test_id` porque un mismo estudiante responde varios problemas
    (el draft `docs/research/diseno-test-transfer.md` propone 5 problemas).
    """

    __tablename__ = "respuestas_test_transferencia"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            "test_id",
            "instrument_version",
            name="uq_resp_transfer_estudiante_test",
        ),
        CheckConstraint(
            "group_assignment IN ('experimental', 'comparison')",
            name="ck_resp_transfer_group_assignment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    comision_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("comisiones.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    instrument_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default="transfer-test-v0.1.0-draft",
    )
    group_assignment: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    test_id: Mapped[str] = mapped_column(String(50), nullable=False)
    correct_answer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    time_taken_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    response_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
