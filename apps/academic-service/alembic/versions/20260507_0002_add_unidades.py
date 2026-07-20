"""add_unidades

Revision ID: 20260507_0002
Revises: 20260507_0001
Create Date: 2026-05-07

ADR-041: Tabla `unidades` para agrupar TPs pedagogicamente por comision.
FK `tareas_practicas.unidad_id` con ON DELETE SET NULL (huerfanamiento
en lugar de cascade-delete — ADR-041, invariante 4).

Tablas:
1. `unidades` — entidad tematica scoped a comision.
2. ADD COLUMN `tareas_practicas.unidad_id` — FK opcional.

Constraints:
- UNIQUE `(tenant_id, comision_id, nombre)` — evita duplicados por comision.
- UNIQUE DEFERRABLE `(tenant_id, comision_id, orden)` — permite swap atomico
  de orden en una sola transaccion (deferrable=True, initially=DEFERRED).
- ON DELETE SET NULL en la FK — borrar Unidad huerfana las TPs, no las borra.

RLS:
- `unidades` tiene ENABLE + FORCE ROW LEVEL SECURITY (CI gate make check-rls).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260507_0002"
down_revision: str | None = "20260507_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. CREATE TABLE unidades
    op.create_table(
        "unidades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "comision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comisiones.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # UNIQUE constraint: sin duplicados de nombre dentro de (tenant, comision)
        sa.UniqueConstraint("tenant_id", "comision_id", "nombre", name="uq_unidad_nombre"),
    )

    # Index para tenant_id (requerido por make check-rls y para performance)
    op.create_index("ix_unidades_tenant_id", "unidades", ["tenant_id"])
    op.create_index("ix_unidades_comision_id", "unidades", ["comision_id"])
    op.create_index("ix_unidades_deleted_at", "unidades", ["deleted_at"])

    # UNIQUE DEFERRABLE para orden — permite swap atomico en una transaccion
    # (swap U1.orden=1 y U3.orden=3 sin violar la constraint intermedia).
    # Creado con DDL directo porque SQLAlchemy/Alembic no expone DEFERRABLE
    # en create_unique_constraint.
    op.execute(
        "ALTER TABLE unidades ADD CONSTRAINT uq_unidad_orden "
        "UNIQUE (tenant_id, comision_id, orden) "
        "DEFERRABLE INITIALLY DEFERRED"
    )

    # 2. RLS — mismo patron que el resto de tablas con tenant_id (ADR-001)
    op.execute("ALTER TABLE unidades ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE unidades FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY unidades_tenant_isolation ON unidades "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )

    # 3. ADD COLUMN tareas_practicas.unidad_id (nullable FK, ON DELETE SET NULL)
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "unidad_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("unidades.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tareas_practicas_unidad_id", "tareas_practicas", ["unidad_id"])


def downgrade() -> None:
    # Revertir en orden inverso
    op.drop_index("ix_tareas_practicas_unidad_id", table_name="tareas_practicas")
    op.drop_column("tareas_practicas", "unidad_id")

    op.execute("DROP POLICY IF EXISTS unidades_tenant_isolation ON unidades")
    op.execute("ALTER TABLE unidades DISABLE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE unidades DROP CONSTRAINT IF EXISTS uq_unidad_orden")
    op.drop_index("ix_unidades_deleted_at", table_name="unidades")
    op.drop_index("ix_unidades_comision_id", table_name="unidades")
    op.drop_index("ix_unidades_tenant_id", table_name="unidades")
    op.drop_table("unidades")
