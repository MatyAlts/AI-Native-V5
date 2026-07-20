"""add_tareas_practicas

Revision ID: 20260421_0002
Revises: 20260420_0001
Create Date: 2026-04-21

Crea la tabla tareas_practicas (TP) con versioning inmutable
(parent_tarea_id auto-FK), constraints de estado/peso/version y
política RLS por tenant_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260421_0002"
down_revision: str | None = "20260420_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tareas_practicas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("enunciado", sa.Text, nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peso", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("rubrica", postgresql.JSONB, nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("parent_tarea_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tareas_practicas"),
        sa.ForeignKeyConstraint(
            ["comision_id"],
            ["comisiones.id"],
            name="fk_tareas_practicas_comision_id_comisiones",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_tarea_id"],
            ["tareas_practicas.id"],
            name="fk_tareas_practicas_parent_tarea_id_tareas_practicas",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "comision_id",
            "codigo",
            "version",
            name="uq_tarea_codigo_version",
        ),
        sa.CheckConstraint(
            "estado IN ('draft', 'published', 'archived')",
            name="ck_tareas_practicas_estado",
        ),
        sa.CheckConstraint(
            "peso >= 0 AND peso <= 1",
            name="ck_tareas_practicas_peso",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_tareas_practicas_version",
        ),
    )
    op.create_index("ix_tareas_practicas_tenant_id", "tareas_practicas", ["tenant_id"])
    op.create_index("ix_tareas_practicas_comision_id", "tareas_practicas", ["comision_id"])
    op.create_index("ix_tareas_practicas_parent_tarea_id", "tareas_practicas", ["parent_tarea_id"])
    op.create_index("ix_tareas_practicas_deleted_at", "tareas_practicas", ["deleted_at"])

    # Aplicar RLS por tenant_id
    op.execute("SELECT apply_tenant_rls('tareas_practicas')")


def downgrade() -> None:
    op.drop_table("tareas_practicas")
