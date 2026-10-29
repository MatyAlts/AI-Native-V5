"""Modelo de `pedidos_ayuda`: un alumno le pide ayuda a los docentes de su comision.

Vive fuera de la traza cognitiva: no hay FK ni referencia al CTR. `episode_id`
es un UUID suelto (los episodios viven en `ctr_store`, otra base) y se guarda
tal cual, exista o no.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from evaluation_service.models.base import Base, TenantMixin, uuid_pk


class PedidoAyuda(Base, TenantMixin):
    __tablename__ = "pedidos_ayuda"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Derivada de la TP por el servidor, nunca del body.
    comision_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Sin FK: la TP es de academic-service (mismo criterio que `entregas`).
    tarea_practica_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    entrega_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("entregas.id", ondelete="SET NULL"), nullable=True
    )
    ejercicio_orden: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)
    mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    contexto: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente", server_default="pendiente"
    )
    resuelto_por: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    resuelto_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "categoria IN ('no_puedo_avanzar', 'error_plataforma', 'duda_consigna', 'otro')",
            name="categoria",
        ),
        CheckConstraint("estado IN ('pendiente', 'resuelto')", name="estado"),
        CheckConstraint("mensaje IS NULL OR char_length(mensaje) <= 1000", name="mensaje"),
        CheckConstraint(
            "(estado = 'resuelto') = (resuelto_at IS NOT NULL)",
            name="resuelto_coherente",
        ),
        sa.Index(
            "ix_pedidos_ayuda_comision_estado",
            "tenant_id",
            "comision_id",
            "estado",
            sa.text("created_at DESC"),
        ),
        sa.Index(
            "ix_pedidos_ayuda_alumno",
            "tenant_id",
            "student_pseudonym",
            sa.text("created_at DESC"),
        ),
    )
