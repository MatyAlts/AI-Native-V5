"""Modelos de material y chunks del RAG.

Un `Material` es un archivo cargado por un docente (PDF, Markdown,
ZIP de código, video). Al procesarse se descompone en `Chunk`s con
embedding vectorial para retrieval semántico.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_service.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    fk_uuid,
    utc_now,
    uuid_pk,
)

# Dimensión del modelo de embeddings default (multilingual-e5-large = 1024)
EMBEDDING_DIM = 1024


class Material(Base, TenantMixin, TimestampMixin):
    """Archivo subido por un docente a una materia."""

    __tablename__ = "materiales"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Migration 20260606_0001 agregó materia_id (UUID nullable) y volvió comision_id
    # nullable. La materia es ahora la entidad académica de scope para los materiales;
    # comision_id queda deprecated (drop futuro).
    comision_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    materia_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    # No hay FK a comisiones/materias porque esas tablas viven en academic_main (ADR-003).
    # La consistencia se verifica en capa de servicio mediante HTTP a academic-service.

    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    # "pdf" | "markdown" | "code_archive" | "video" | "text"

    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # ej. "materials/{tenant_id}/{comision_id}/{material_id}/original.pdf"

    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    # uploaded | extracting | chunking | embedding | indexed | failed

    uploaded_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata rica: páginas totales, idioma detectado, etc.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Contador desnormalizado para dashboards
    chunks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Hash del contenido original para detectar re-uploads idénticos
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )


class Chunk(Base, TenantMixin):
    """Unidad semántica de un material, con su embedding para retrieval.

    Los chunks son append-only por material_id: si el material se
    re-ingesta, se borran los chunks viejos y se crean nuevos en una
    sola transacción.
    """

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = uuid_pk()
    material_id: Mapped[uuid.UUID] = fk_uuid("materiales.id")
    # Migration 20260606_0001: comision_id nullable + materia_id agregado.
    # Denormalizado desde Material para permitir filtrar sin join.
    comision_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    materia_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )

    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    contenido_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # Nullable porque la creación del chunk y su embedding son pasos
    # separados del pipeline (chunking síncrono, embedding asíncrono).

    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # "multilingual-e5-large" | "voyage-multilingual-2" | ...

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Orden secuencial del chunk dentro del material

    chunk_type: Mapped[str] = mapped_column(String(30), default="prose")
    # "prose" | "code_function" | "code_class" | "table" | "heading" | "video_segment"

    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Metadata específica del tipo: {source_page, source_file, start_line,
    # timestamp_seconds, heading_path, ...}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    material: Mapped[Material] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "material_id",
            "position",
            name="uq_chunks_tenant_material_position",
        ),
    )
