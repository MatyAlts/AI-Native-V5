"""Modelo de `correcciones_ia` (Epic 3 de `correccion-activeia`)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from evaluation_service.models.base import Base, TenantMixin, uuid_pk


class CorreccionIA(Base, TenantMixin):
    """Una corrección asistida de UN ejercicio de UNA entrega.

    `nota_100` es nullable, y eso es la propiedad central de esta tabla: un
    fallo de infraestructura NUNCA puede convertirse en una nota. Si fuera
    NOT NULL, la única forma de registrar un fallo sería inventarle un cero —
    y un cero que en realidad significa "el servicio no respondió" termina en
    el legajo de una persona. El CHECK de la migration lo hace cumplir a nivel
    base: sólo `estado='done'` puede llevar nota.
    """

    __tablename__ = "correcciones_ia"

    id: Mapped[uuid.UUID] = uuid_pk()
    entrega_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("entregas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: la TP monolítica no tiene filas en `tp_ejercicios`.
    tp_ejercicio_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    # Quién apretó el botón: corre con SU cuenta y contra SU cuota.
    disparado_por: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    rubrica_id: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    nota_100: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    desglose: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    # Resultado de correr los test cases en el sandbox AL CORREGIR. Se
    # re-ejecutan y no se leen de la corrida vieja: aquel detalle murió en
    # Redis a los 600s, y re-ejecutar hace la corrección reproducible.
    tests_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    artefacto_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sin esto, un reintento tras un timeout no puede retomar la entrega que ya
    # está arriba y la sube de nuevo — y la cobra de nuevo.
    external_entrega_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_correccion_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Donde quedo el PDF de devolucion. La KEY, no el contenido: un PDF en una
    # columna infla la tabla que el docente consulta en cada apertura del form.
    pdf_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "estado IN ('pending', 'running', 'done', 'error')",
            name="ck_correcciones_ia_estado",
        ),
        CheckConstraint(
            "(estado = 'done' AND nota_100 IS NOT NULL) OR (estado <> 'done' AND nota_100 IS NULL)",
            name="ck_correcciones_ia_nota_solo_si_done",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "entrega_id",
            "orden",
            "rubrica_id",
            "artefacto_sha256",
            name="uq_correccion_ia_idempotencia",
        ),
    )
