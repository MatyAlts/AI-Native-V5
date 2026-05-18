"""Modelos de Entrega y Calificacion (tp-entregas-correccion).

Tablas en academic_main — mismo DB que academic-service.
Ver design.md D2: entregas + calificaciones viven aquí para evitar
cross-DB joins con tareas_practicas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evaluation_service.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    fk_uuid,
    uuid_pk,
)

if TYPE_CHECKING:
    pass


class Entrega(Base, TenantMixin, TimestampMixin):
    """Entrega formal de un alumno para una TareaPractica.

    Agrupa el trabajo del alumno sobre todos los ejercicios de la TP.
    Estado: draft → submitted → graded → returned.

    Una sola entrega por (tenant_id, tarea_practica_id, student_pseudonym).
    Si el docente devuelve (returned), el alumno puede re-enviar actualizando
    la misma entrega (no se crea una nueva).
    """

    __tablename__ = "entregas"

    id: Mapped[uuid.UUID] = uuid_pk()
    tarea_practica_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    comision_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # ejercicio_estados: lista de {orden, episode_id, completado, completed_at}
    ejercicio_estados: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    calificacion: Mapped[Calificacion | None] = relationship(
        back_populates="entrega", uselist=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "tarea_practica_id",
            "student_pseudonym",
            name="uq_entrega_student_tp",
        ),
        CheckConstraint(
            "estado IN ('draft', 'submitted', 'graded', 'returned')",
            name="ck_entregas_estado",
        ),
    )


class Calificacion(Base, TenantMixin, TimestampMixin):
    """Calificacion docente de una Entrega.

    FK UNIQUE a entregas: una calificacion por entrega (v1 no permite
    re-correccion — el docente edita la misma calificacion si hay error).
    """

    __tablename__ = "calificaciones"

    id: Mapped[uuid.UUID] = uuid_pk()
    entrega_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("entregas.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    graded_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    nota_final: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    feedback_general: Mapped[str | None] = mapped_column(Text, nullable=True)
    # detalle_criterios: [{criterio, puntaje, max_puntaje, comentario}]
    detalle_criterios: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    graded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    entrega: Mapped[Entrega] = relationship(back_populates="calificacion")

    __table_args__ = (
        CheckConstraint(
            "nota_final >= 0 AND nota_final <= 10",
            name="ck_calificaciones_nota",
        ),
    )
