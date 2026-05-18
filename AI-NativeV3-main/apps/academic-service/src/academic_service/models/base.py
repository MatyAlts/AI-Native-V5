"""Base declarativa y mixins comunes.

Todos los modelos del dominio académico heredan de Base. Los que son
multi-tenant además mezclan TenantMixin (agrega tenant_id + policy RLS
al momento de crearse la tabla).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming convention determinista para que las migraciones Alembic no
# generen nombres aleatorios de constraints.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa del dominio."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        dict[str, Any]: "JSONB",
    }


def utc_now() -> datetime:
    """Helper para default de timestamps."""
    return datetime.now(UTC)


class TimestampMixin:
    """Agrega created_at y deleted_at para soft-delete."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class TenantMixin:
    """Agrega tenant_id indexado.

    Las tablas que tienen este mixin deben llamarse a sí mismas desde la
    migración correspondiente con `apply_tenant_rls(t.name)` — esto no se
    hace automáticamente porque Alembic no ejecuta código Python en la
    creación de tablas, pero SÍ lo hace el helper del servicio que se usa
    en tests y en migraciones manuales.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Primary key UUID v7 (ordenable temporalmente)."""
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),  # v7 cuando esté disponible en ext
    )


def fk_uuid(target: str, nullable: bool = False) -> Mapped[uuid.UUID]:
    """Foreign key tipada para UUIDs."""
    return mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(target, ondelete="RESTRICT"),
        nullable=nullable,
        index=True,
    )
