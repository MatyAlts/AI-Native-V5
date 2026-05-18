"""Jerarquía institucional: Universidad → Facultad → Carrera → Plan → Materia."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from academic_service.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    fk_uuid,
    uuid_pk,
)

if TYPE_CHECKING:
    from academic_service.models.operacional import Comision


class Universidad(Base, TenantMixin, TimestampMixin):
    """Raíz del árbol institucional. 1 universidad = 1 tenant.

    Por convencion enforzada en `UniversidadService.create()`,
    `tenant_id == id`. La migration `20260514_0004` agrega el `tenant_id`
    + RLS forced para que `GET /universidades` solo devuelva la propia
    universidad del caller (aislamiento academico).
    """

    __tablename__ = "universidades"

    id: Mapped[uuid.UUID] = uuid_pk()
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    dominio_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    keycloak_realm: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    facultades: Mapped[list[Facultad]] = relationship(back_populates="universidad")
    carreras: Mapped[list[Carrera]] = relationship(back_populates="universidad")


class Facultad(Base, TenantMixin, TimestampMixin):
    """Facultad (opcional, algunas universidades no la tienen)."""

    __tablename__ = "facultades"

    id: Mapped[uuid.UUID] = uuid_pk()
    universidad_id: Mapped[uuid.UUID] = fk_uuid("universidades.id")
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    decano_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    universidad: Mapped[Universidad] = relationship(back_populates="facultades")
    carreras: Mapped[list[Carrera]] = relationship(back_populates="facultad")

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_facultad_tenant_codigo"),)


class Carrera(Base, TenantMixin, TimestampMixin):
    """Carrera (programa académico)."""

    __tablename__ = "carreras"

    id: Mapped[uuid.UUID] = uuid_pk()
    universidad_id: Mapped[uuid.UUID] = fk_uuid("universidades.id")
    facultad_id: Mapped[uuid.UUID] = fk_uuid("facultades.id")
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    duracion_semestres: Mapped[int] = mapped_column(Integer, default=8)
    modalidad: Mapped[str] = mapped_column(String(30), default="presencial")
    director_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    universidad: Mapped[Universidad] = relationship(back_populates="carreras")
    facultad: Mapped[Facultad] = relationship(back_populates="carreras")
    planes: Mapped[list[PlanEstudios]] = relationship(back_populates="carrera")

    __table_args__ = (UniqueConstraint("tenant_id", "codigo", name="uq_carrera_tenant_codigo"),)


class PlanEstudios(Base, TenantMixin, TimestampMixin):
    """Plan de estudios versionado por año de ingreso."""

    __tablename__ = "planes_estudio"

    id: Mapped[uuid.UUID] = uuid_pk()
    carrera_id: Mapped[uuid.UUID] = fk_uuid("carreras.id")
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    año_inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    ordenanza: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vigente: Mapped[bool] = mapped_column(default=True)

    carrera: Mapped[Carrera] = relationship(back_populates="planes")
    materias: Mapped[list[Materia]] = relationship(back_populates="plan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "carrera_id", "version", name="uq_plan_version"),
    )


class Materia(Base, TenantMixin, TimestampMixin):
    """Materia como plantilla atemporal. Las instancias concretas son Comisiones."""

    __tablename__ = "materias"

    id: Mapped[uuid.UUID] = uuid_pk()
    plan_id: Mapped[uuid.UUID] = fk_uuid("planes_estudio.id")
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    horas_totales: Mapped[int] = mapped_column(Integer, default=96)
    cuatrimestre_sugerido: Mapped[int] = mapped_column(Integer, default=1)
    objetivos: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Correlatividades: lista de UUIDs de Materias requeridas
    correlativas_cursar: Mapped[list[str]] = mapped_column(JSONB, default=list)
    correlativas_rendir: Mapped[list[str]] = mapped_column(JSONB, default=list)

    plan: Mapped[PlanEstudios] = relationship(back_populates="materias")
    comisiones: Mapped[list[Comision]] = relationship(back_populates="materia")

    __table_args__ = (UniqueConstraint("tenant_id", "plan_id", "codigo", name="uq_materia_codigo"),)
