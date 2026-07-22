"""tp_entregas_correccion: ejercicios JSONB en TareaPractica + entregas + calificaciones

Revision ID: 20260506_0001
Revises: 20260504_0002
Create Date: 2026-05-06

Epic tp-entregas-correccion:
- Agrega columna `ejercicios JSONB` a `tareas_practicas` (nullable false, default '[]').
- Crea tabla `entregas` (entrega del alumno para una TP, con estado draft/submitted/graded/returned).
- Crea tabla `calificaciones` (nota docente por entrega, FK UNIQUE a entregas).
- RLS en ambas tablas nuevas con tenant_id (mismo patron que el resto de academic_main).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260506_0001"
down_revision: str | None = "20260504_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Agregar ejercicios a tareas_practicas
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "ejercicios",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 2. Tabla entregas
    op.create_table(
        "entregas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "tarea_practica_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tareas_practicas.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "student_pseudonym",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "comision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comisiones.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("estado", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "ejercicio_estados",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.UniqueConstraint(
            "tenant_id",
            "tarea_practica_id",
            "student_pseudonym",
            name="uq_entrega_student_tp",
        ),
        sa.CheckConstraint(
            "estado IN ('draft', 'submitted', 'graded', 'returned')",
            name="ck_entregas_estado",
        ),
    )

    op.execute("ALTER TABLE entregas ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY entregas_tenant_isolation ON entregas "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )

    # 3. Tabla calificaciones
    op.create_table(
        "calificaciones",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "entrega_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entregas.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("graded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nota_final", sa.Numeric(5, 2), nullable=False),
        sa.Column("feedback_general", sa.Text(), nullable=True),
        sa.Column(
            "detalle_criterios",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "graded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.CheckConstraint(
            "nota_final >= 0 AND nota_final <= 10",
            name="ck_calificaciones_nota",
        ),
    )

    op.execute("ALTER TABLE calificaciones ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY calificaciones_tenant_isolation ON calificaciones "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS calificaciones_tenant_isolation ON calificaciones")
    op.drop_table("calificaciones")

    op.execute("DROP POLICY IF EXISTS entregas_tenant_isolation ON entregas")
    op.drop_table("entregas")

    op.drop_column("tareas_practicas", "ejercicios")
