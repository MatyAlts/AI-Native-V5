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
      - appropriation: "delegacion_pasiva" | "apropiacion_superficial" | "apropiacion_reflexiva" | "autonomo"
        (los 3 primeros son el continuo superficial↔reflexiva; "autonomo" es un 4º eje ORTOGONAL al continuo — brazo sin-tutor, prompts == 0)
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


class InterraterRating(Base, TenantMixin):
    """Etiqueta HUMANA de un episodio para validación inter-jueces (κ de Cohen).

    Un docente clasifica un episodio A CIEGAS (sin ver la etiqueta de la máquina
    ni la de otros codificadores) en uno de los perfiles. Una fila por
    (episodio, codificador): dos docentes etiquetando el mismo episodio = dos
    filas, que se cruzan para computar el acuerdo (κ).

    Upsert por (tenant, episode, rater): si el docente re-etiqueta el mismo
    episodio, se ACTUALIZA su fila (no se acumulan duplicados). La etiqueta de
    la máquina NO se guarda acá — al agregar se compara contra `classifications`
    (rater "máquina" vs rater docente).
    """

    __tablename__ = "interrater_ratings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    episode_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    comision_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    # Materia del episodio. Permite agregar el acuerdo a nivel MATERIA (cruzando
    # comisiones). Nullable: las filas viejas (comisión-scoped) quedan en NULL.
    materia_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # Docente que puso la etiqueta (del header X-User-Id).
    rater_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    # Perfil asignado por el humano. String libre (validado en la capa de ruta
    # contra el protocolo): ejes canónicos / 10 subgrupos / N1-N4.
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    # Qué vocabulario usa la etiqueta: "ejes" | "subgrupos" | "niveles".
    protocol: Mapped[str] = mapped_column(String(20), nullable=False, default="ejes")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )

    __table_args__ = (
        # Un codificador tiene UNA etiqueta por episodio (upsert al re-etiquetar).
        UniqueConstraint(
            "tenant_id",
            "episode_id",
            "rater_id",
            name="uq_interrater_episode_rater",
        ),
        Index("ix_interrater_comision", "comision_id"),
        Index("ix_interrater_materia", "materia_id"),
    )
