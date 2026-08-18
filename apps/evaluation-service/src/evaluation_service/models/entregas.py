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
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
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
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # sha256 del conjunto de artefactos, calculado en el submit. Se guarda y
    # NO se recalcula al leer: recalcularlo haría que un cambio silencioso del
    # contenido pase desapercibido, y el hash dejaría de probar nada.
    artefacto_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Entregas anteriores a la persistencia del artefacto. Su código puede
    # reconstruirse best-effort desde el CTR, pero eso es una lectura, no lo
    # que el alumno entregó: no son elegibles para correccion automatica.
    legacy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.text("false")
    )

    calificacion: Mapped[Calificacion | None] = relationship(
        back_populates="entrega", uselist=False
    )
    artefactos: Mapped[list[EntregaArtefacto]] = relationship(
        back_populates="entrega",
        cascade="all, delete-orphan",
        order_by="EntregaArtefacto.orden",
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


class EntregaArtefacto(Base, TenantMixin):
    """El código que el alumno entregó, una fila por ejercicio.

    Se escribe en el submit con lo que manda el cliente. NO se reconstruye
    leyendo el CTR: esa ingesta es asíncrona y el editor emite
    fire-and-forget, así que lo que se leyera podría no ser lo último que el
    alumno escribió. La diferencia entre "lo que leí" y "lo que entregó"
    importa cuando el resultado termina en un legajo.

    Una fila por ejercicio y no un blob porque la corrección asistida es por
    ejercicio: cada uno se manda con su propia rúbrica y necesita su propio
    hash (design.md D1 y D3).
    """

    __tablename__ = "entrega_artefactos"

    id: Mapped[uuid.UUID] = uuid_pk()
    entrega_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("entregas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable: la TP monolítica (sin ejercicioContext) todavía no lo resuelve.
    episode_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    ejercicio_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(
        String(20), nullable=False, default="python", server_default="python"
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    entrega: Mapped[Entrega] = relationship(back_populates="artefactos")

    __table_args__ = (
        UniqueConstraint("tenant_id", "entrega_id", "orden", name="uq_entrega_artefacto_orden"),
        CheckConstraint("orden >= 1", name="ck_entrega_artefactos_orden"),
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
    # updated_at: timestamp de la ULTIMA re-calificacion (NB-4). NULL hasta que
    # el docente corrige una nota ya puesta. `graded_at` preserva el momento de
    # la primera calificacion; `updated_at` marca la correccion mas reciente.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entrega: Mapped[Entrega] = relationship(back_populates="calificacion")

    __table_args__ = (
        CheckConstraint(
            "nota_final >= 0 AND nota_final <= 10",
            name="ck_calificaciones_nota",
        ),
    )
