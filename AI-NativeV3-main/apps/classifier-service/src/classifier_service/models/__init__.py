"""Modelos del classifier-service (ADR-010: append-only).

Clasificaciones son append-only con flag `is_current`. Reclasificar con
nuevo `classifier_config_hash` produce nueva fila; la anterior se marca
`is_current=false` pero no se borra.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: "JSONB"}


def utc_now_f() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


class TenantMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)


class Classification(Base, TenantMixin):
    """Clasificación N4 de un episodio.

    Campos:
      - appropriation: "delegacion_pasiva" | "apropiacion_superficial" | "apropiacion_reflexiva"
      - appropriation_reason: texto justificando la decisión del árbol
      - ct_summary: coherencia temporal (0-1, ventanas de trabajo consecutivas)
      - ccd_mean: coherencia código-discurso (0-1, alineación código/texto)
      - ccd_orphan_ratio: fracción de código/discurso "huérfano"
      - cii_stability: coherencia inter-iteración (estabilidad de enfoque)
      - cii_evolution: evolución de calidad entre iteraciones

    Regla append-only (ADR-010):
      - Reclasificar = UPDATE is_current=false en fila vieja + INSERT fila nueva.
      - Nunca se borra ni modifica el resto de la fila anterior.
    """

    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    episode_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    comision_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    classifier_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    appropriation: Mapped[str] = mapped_column(String(40), nullable=False)
    appropriation_reason: Mapped[str] = mapped_column(Text, nullable=False)

    ct_summary: Mapped[float | None] = mapped_column(Float, nullable=True)
    ccd_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ccd_orphan_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    cii_stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    cii_evolution: Mapped[float | None] = mapped_column(Float, nullable=True)

    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Features intermedios para debugging/explainability

    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "classifier_config_hash",
            name="uq_classifications_episode_config",
        ),
        Index("ix_classifications_episode_current", "episode_id", "is_current"),
    )
